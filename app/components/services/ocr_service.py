from datetime import datetime
import logging
import os
import tempfile
from typing import List, Optional
import io

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from pdf2image import convert_from_bytes
from PIL import Image
import torch
import asyncio

# 设置日志
logger = logging.getLogger(__name__)

class OCRService:
    def __init__(self, db: AsyncIOMotorClient):
        self.db = db
        self.error_logs = db.llm_kit.error_logs
        self.tokenizer = None
        self.model = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.last_progress_update = {}
        
    async def _log_error(self, error_message: str, source: str, stack_trace: str = None):
        """记录错误到数据库"""
        error_log = {
            "timestamp": datetime.utcnow(),
            "error_message": error_message,
            "source": source,
            "stack_trace": stack_trace
        }
        await self.error_logs.insert_one(error_log)
    
    async def _load_model(self):
        """异步加载OCR模型"""
        if self.tokenizer is None or self.model is None:
            try:
                # 使用单独的线程加载模型，避免阻塞异步事件循环
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self._load_model_sync)
                logger.info(f"OCR模型加载成功，使用设备: {self.device}")
                return True
            except Exception as e:
                error_msg = f"OCR模型加载失败: {str(e)}"
                logger.error(error_msg)
                await self._log_error(error_msg, "ocr_load_model")
                return False
        return True
        
    def _load_model_sync(self):
        """同步加载OCR模型（在单独线程中执行）"""
        from transformers import AutoTokenizer, AutoModel
        
        # 默认使用GoT-OCR模型，可以根据需要更改
        MODEL_NAME = 'ucaslcl/GOT-OCR2_0'
        
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
        self.model = AutoModel.from_pretrained(
            MODEL_NAME, 
            trust_remote_code=True, 
            low_cpu_mem_usage=True, 
            device_map=self.device, 
            use_safetensors=True,
            pad_token_id=self.tokenizer.eos_token_id
        )
        self.model = self.model.eval()
    
    async def process_pdf(self, content: bytes, filename: str, record_id: str = None) -> str:
        """process PDF file, extract text content"""
        try:
            # update progress
            if record_id:
                await self._update_progress(record_id, 5)
                
            # 1. first try to extract text directly from PDF
            loop = asyncio.get_event_loop()
            
            # create temporary PDF file
            pdf_temp_path = None
            try:
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_pdf:
                    temp_pdf.write(content)
                    pdf_temp_path = temp_pdf.name
                
                logger.info(f"try to extract text directly from PDF '{filename}'")
                
                # use PyMuPDF (fitz) to extract text
                import fitz
                
                # execute in a separate thread to avoid blocking
                def extract_text_directly():
                    try:
                        doc = fitz.open(pdf_temp_path)
                        text = ""
                        for page in doc:
                            text += page.get_text()
                        doc.close()
                        return text
                    except Exception as e:
                        logger.warning(f"failed to extract text directly from PDF: {str(e)}")
                        return ""
                
                direct_text = await loop.run_in_executor(None, extract_text_directly)
                
                # 更新进度
                if record_id:
                    await self._update_progress(record_id, 10)
                

                TEXT_THRESHOLD = 50  # if less than 50 characters, it may be a scanned document
                
                if len(direct_text.strip()) > TEXT_THRESHOLD:
                    logger.info(f"successfully extracted text directly from PDF, text length: {len(direct_text)}")
                    
                    # create OCR processing record, although OCR is not needed, it still needs to record processing information
                    if record_id:
                        # set progress to 100%
                        await self._update_progress(record_id, 100)
                        
                        # 更新解析记录
                        await self.db.llm_kit.parse_records.update_one(
                            {"_id": ObjectId(record_id)},
                            {"$set": {
                                "status": "completed",
                                "progress": 100,
                                "task_type": "pdf_text",  # 
                                "content": direct_text,
                                "ocr_info": {
                                    "total_pages": 1,
                                    "processed_pages": 1,
                                    "status": "completed"
                                }
                            }}
                        )
                        
                        # 创建进度跟踪记录，即使是直接提取文本的情况
                        await self.db.llm_kit.ocr_processing_progress.insert_one({
                            "task_id": record_id,
                            "total_pages": 1,
                            "processed_pages": 1,
                            "status": "completed",
                            "start_time": datetime.utcnow(),
                            "last_update": datetime.utcnow()
                        })
                    
                    return direct_text
                
                logger.info(f"text content extracted from PDF is too short ({len(direct_text.strip())} characters), switch to OCR mode")
                
            except Exception as e:
                logger.warning(f"error occurred when trying to extract text directly from PDF: {str(e)}")
            finally:
                if pdf_temp_path and os.path.exists(pdf_temp_path):
                    os.unlink(pdf_temp_path)
            
            # 2. if direct extraction fails or text is too short, use OCR
            # ensure model is loaded
            model_loaded = await self._load_model()
            if not model_loaded:
                raise Exception("OCR model loading failed")
            
         
            if record_id:
                await self._update_progress(record_id, 15)
            
            images = await loop.run_in_executor(None, lambda: convert_from_bytes(content))
            
            if record_id:
                await self._update_progress(record_id, 20)
                
                # create OCR processing record, record total pages information
                total_pages = len(images)
                await self.db.llm_kit.parse_records.update_one(
                    {"_id": ObjectId(record_id)},
                    {"$set": {
                        "ocr_info": {
                            "total_pages": total_pages,
                            "processed_pages": 0,
                            "status": "processing"
                        },
                        "task_type": "ocr"  # confirm task type is OCR
                    }}
                )
                
                await self.db.llm_kit.ocr_processing_progress.insert_one({
                    "task_id": record_id,
                    "total_pages": total_pages,
                    "processed_pages": 0,
                    "status": "processing",
                    "start_time": datetime.utcnow(),
                    "last_update": datetime.utcnow()
                })
            
          
            all_text = ""
            total_pages = len(images)
            
            for i, image in enumerate(images):
             
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_file:
                    image.save(tmp_file.name, format="PNG")
                    temp_path = tmp_file.name
                
                try:
                    # OCR识别
                    res = await loop.run_in_executor(
                        None, 
                        lambda: self.model.chat(self.tokenizer, temp_path, ocr_type='ocr')
                    )
                    
                    all_text += f"--- 第 {i+1} 页 ---\n"
                    all_text += res + "\n\n"
                    
                    # 更新进度
                    if record_id:
                        progress = 20 + int(70 * (i + 1) / total_pages)
                        await self._update_progress(record_id, progress)
                        
                        await self.db.llm_kit.ocr_processing_progress.update_one(
                            {"task_id": record_id},
                            {"$set": {
                                "processed_pages": i + 1,
                                "last_update": datetime.utcnow()
                            }}
                        )
                        
                        await self.db.llm_kit.parse_records.update_one(
                            {"_id": ObjectId(record_id)},
                            {"$set": {
                                "ocr_info.processed_pages": i + 1
                            }}
                        )
                    
                finally:
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
            
            if record_id:
                await self._update_progress(record_id, 100)
                
                await self.db.llm_kit.parse_records.update_one(
                    {"_id": ObjectId(record_id)},
                    {"$set": {
                        "ocr_info.status": "completed",
                        "ocr_info.processed_pages": total_pages
                    }}
                )
                
                # 更新OCR进度跟踪记录
                await self.db.llm_kit.ocr_processing_progress.update_one(
                    {"task_id": record_id},
                    {"$set": {
                        "status": "completed",
                        "processed_pages": total_pages,
                        "last_update": datetime.utcnow()
                    }}
                )
                
            return all_text
            
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            error_msg = f"PDF OCR处理失败: {str(e)}"
            logger.error(f"{error_msg}\n{error_trace}")
            await self._log_error(error_msg, "process_pdf", error_trace)
            
            # 设置失败状态
            if record_id:
                await self.db.llm_kit.parse_records.update_one(
                    {"_id": ObjectId(record_id)},
                    {"$set": {
                        "status": "failed", 
                        "error_message": str(e),
                        "ocr_info.status": "failed"
                    }}
                )
                
                # 更新OCR进度跟踪记录
                await self.db.llm_kit.ocr_processing_progress.update_one(
                    {"task_id": record_id},
                    {"$set": {
                        "status": "failed",
                        "error_message": str(e),
                        "last_update": datetime.utcnow()
                    }}
                )
                
            raise Exception(f"PDF OCR处理失败: {str(e)}")
    
    async def process_image(self, content: bytes, filename: str, record_id: str = None) -> str:
        """处理图像文件，提取文本内容"""
        try:
            # 确保模型已加载
            model_loaded = await self._load_model()
            if not model_loaded:
                raise Exception("OCR模型加载失败")
            
            # 更新进度
            if record_id:
                await self._update_progress(record_id, 20)
                
                # 创建OCR处理记录
                await self.db.llm_kit.parse_records.update_one(
                    {"_id": ObjectId(record_id)},
                    {"$set": {
                        "ocr_info": {
                            "total_pages": 1,
                            "processed_pages": 0,
                            "status": "processing"
                        }
                    }}
                )
                
                # 创建进度跟踪记录
                await self.db.llm_kit.ocr_processing_progress.insert_one({
                    "task_id": record_id,
                    "total_pages": 1,
                    "processed_pages": 0,
                    "status": "processing",
                    "start_time": datetime.utcnow(),
                    "last_update": datetime.utcnow()
                })
            
            # 创建临时图像文件
            with tempfile.NamedTemporaryFile(suffix=os.path.splitext(filename)[1], delete=False) as tmp_file:
                tmp_file.write(content)
                temp_path = tmp_file.name
            
            try:
                # OCR识别
                loop = asyncio.get_event_loop()
                res = await loop.run_in_executor(
                    None, 
                    lambda: self.model.chat(self.tokenizer, temp_path, ocr_type='ocr')
                )
                
                # 更新进度
                if record_id:
                    await self._update_progress(record_id, 90)
                    
                    # 更新OCR进度跟踪记录
                    await self.db.llm_kit.ocr_processing_progress.update_one(
                        {"task_id": record_id},
                        {"$set": {
                            "processed_pages": 1,
                            "last_update": datetime.utcnow()
                        }}
                    )
                    
                    # 更新主记录中的OCR信息
                    await self.db.llm_kit.parse_records.update_one(
                        {"_id": ObjectId(record_id)},
                        {"$set": {
                            "ocr_info.processed_pages": 1
                        }}
                    )
                
                # 设置最终进度
                if record_id:
                    await self._update_progress(record_id, 100)
                    
                    # 更新OCR处理状态为已完成
                    await self.db.llm_kit.parse_records.update_one(
                        {"_id": ObjectId(record_id)},
                        {"$set": {
                            "ocr_info.status": "completed",
                            "ocr_info.processed_pages": 1
                        }}
                    )
                    
                    # 更新OCR进度跟踪记录
                    await self.db.llm_kit.ocr_processing_progress.update_one(
                        {"task_id": record_id},
                        {"$set": {
                            "status": "completed",
                            "processed_pages": 1,
                            "last_update": datetime.utcnow()
                        }}
                    )
                
                return res
                
            finally:
                # 删除临时文件
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            error_msg = f"图像OCR处理失败: {str(e)}"
            logger.error(f"{error_msg}\n{error_trace}")
            await self._log_error(error_msg, "process_image", error_trace)
            
            # 设置失败状态
            if record_id:
                await self.db.llm_kit.parse_records.update_one(
                    {"_id": ObjectId(record_id)},
                    {"$set": {
                        "status": "failed", 
                        "error_message": str(e),
                        "ocr_info.status": "failed"
                    }}
                )
                
                # 更新OCR进度跟踪记录
                await self.db.llm_kit.ocr_processing_progress.update_one(
                    {"task_id": record_id},
                    {"$set": {
                        "status": "failed",
                        "error_message": str(e),
                        "last_update": datetime.utcnow()
                    }}
                )
                
            raise Exception(f"图像OCR处理失败: {str(e)}")
    
    async def get_ocr_progress(self, record_id: str):
        """获取OCR处理进度详情"""
        try:
            # 从主记录获取基本信息
            main_record = await self.db.llm_kit.parse_records.find_one(
                {"_id": ObjectId(record_id)}
            )
            
            if not main_record:
                return {
                    "status": "not_found",
                    "progress": 0,
                    "total_pages": 0,
                    "processed_pages": 0,
                    "error_message": "记录不存在"
                }
            
            # 获取OCR信息
            ocr_info = main_record.get("ocr_info", {})
            status = ocr_info.get("status", main_record.get("status", "processing"))
            total_pages = ocr_info.get("total_pages", 0)
            processed_pages = ocr_info.get("processed_pages", 0)
            
            # 计算进度百分比
            progress = main_record.get("progress", 0)
            if total_pages > 0:
                calculated_progress = int((processed_pages / total_pages) * 100)
                # 如果计算的进度与记录的进度差异大，使用计算的进度
                if abs(calculated_progress - progress) > 10:
                    progress = calculated_progress
            
            # 获取详细的进度跟踪信息
            progress_record = await self.db.llm_kit.ocr_processing_progress.find_one(
                {"task_id": record_id}
            )
            
            # 计算已用时间
            elapsed_seconds = 0
            if progress_record and "start_time" in progress_record:
                start_time = progress_record["start_time"]
                current_time = datetime.utcnow()
                elapsed_seconds = int((current_time - start_time).total_seconds())
            
            # 估算剩余时间
            estimated_remaining_seconds = 0
            if status == "processing" and processed_pages > 0 and total_pages > processed_pages:
                # 基于已处理页数和已用时间估算
                time_per_page = elapsed_seconds / processed_pages
                estimated_remaining_seconds = int(time_per_page * (total_pages - processed_pages))
            
            return {
                "status": status,
                "progress": progress,
                "total_pages": total_pages,
                "processed_pages": processed_pages,
                "elapsed_seconds": elapsed_seconds,
                "estimated_remaining_seconds": estimated_remaining_seconds,
                "error_message": main_record.get("error_message", "")
            }
            
        except Exception as e:
            logger.error(f"获取OCR进度失败: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "progress": 0,
                "total_pages": 0,
                "processed_pages": 0,
                "error_message": str(e)
            }
    
    async def _update_progress(self, record_id: str, progress: int):
        """更新处理进度"""
        try:
            current_time = datetime.utcnow().timestamp()
            last_update = self.last_progress_update.get(record_id, 0)
            
            # 限制更新频率，避免频繁数据库操作
            if current_time - last_update >= 0.5:
                await self.db.llm_kit.parse_records.update_one(
                    {"_id": ObjectId(record_id)},
                    {"$set": {"progress": progress}}
                )
                self.last_progress_update[record_id] = current_time
        except Exception as e:
            logger.error(f"更新进度失败: {str(e)}") 