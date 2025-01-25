from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from text_parse.to_tex import LatexConverter
from utils.hparams import HyperParams
from app.components.models.mongodb import TexConversionRecord
import os
from typing import List
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from utils.helper import generate, split_chunk_by_tokens, split_text_into_chunks
import json
import logging
import time
import tempfile
import asyncio
from bson.objectid import ObjectId

logger = logging.getLogger(__name__)

class ToTexService:
    def __init__(self, db: AsyncIOMotorClient):
        self.db = db
        self.tex_records = db.llm_kit.tex_records
        self.parse_records = db.llm_kit.parse_records
        self.error_logs = db.llm_kit.error_logs
        self.last_progress_update = {}  # 用于存储每个任务的最后更新时间

    async def _log_error(self, error_message: str, source: str, stack_trace: str = None):
        error_log = {
            "timestamp": datetime.utcnow(),
            "error_message": error_message,
            "source": source,
            "stack_trace": stack_trace
        }
        await self.error_logs.insert_one(error_log)

    def _process_chunk_with_api(self, chunk: str, ak: str, sk: str, model_name: str, max_tokens: int = 650) -> list:
        """处理单个文本块"""
        sub_chunks = split_chunk_by_tokens(chunk, max_tokens)
        results = []

        for sub_chunk in sub_chunks:
            for attempt in range(3):  # 尝试3次
                try:
                    tex_text = generate(sub_chunk, model_name, 'ToTex', ak, sk)
                    results.append(self._clean_result(tex_text))
                    break
                except Exception as e:
                    if attempt == 2:  # 最后一次尝试失败
                        raise Exception(f"处理文本块失败: {str(e)}")
        return results

    def _clean_result(self, text: str) -> str:
        """清理API返回的结果"""
        start_index = max(text.find('```') + 3 if '```' in text else -1, 0)
        end_index = text.rfind('```')
        return text[start_index:end_index].strip()

    async def get_parsed_files(self):
        """获取所有已解析的文件列表（同名文件只返回最新的）"""
        try:
            # 使用聚合管道，按文件名分组并获取每组最新的记录
            pipeline = [
                # 只查找已完成的记录
                {"$match": {"status": "completed"}},
                
                # 按文件名分组，保留最新的记录
                {"$group": {
                    "_id": "$input_file",
                    "created_at": {"$max": "$created_at"},
                    "file_type": {"$first": "$file_type"},
                    "latest_doc": {"$first": "$$ROOT"}
                }},
                
                # 按创建时间降序排序
                {"$sort": {"created_at": -1}},
                
                # 重新格式化输出
                {"$project": {
                    "_id": 0,
                    "filename": "$_id",
                    "created_at": 1,
                    "file_type": 1
                }}
            ]
            
            cursor = self.parse_records.aggregate(pipeline)
            files = []
            async for record in cursor:
                files.append({
                    "filename": record["filename"],
                    "created_at": record["created_at"],
                    "file_type": record.get("file_type", "")
                })
            
            return files
        except Exception as e:
            logger.error(f"获取解析文件列表失败: {str(e)}")
            raise Exception(f"获取解析文件列表失败: {str(e)}")

    async def get_parsed_content(self, filename: str):
        """根据文件名获取解析后的内容"""
        try:
            # 查找指定文件名的已完成记录
            record = await self.parse_records.find_one(
                {
                    "input_file": filename,
                    "status": "completed"
                }
            )
            
            if not record:
                raise Exception(f"未找到文件 {filename} 的解析记录")
            
            if not record.get("content"):
                raise Exception(f"文件 {filename} 的解析内容为空")
            
            return {
                "content": record["content"],
                "filename": record["input_file"],
                "created_at": record["created_at"],
                "file_type": record["file_type"]
            }
        except Exception as e:
            logger.error(f"获取解析内容失败: {str(e)}")
            raise Exception(f"获取解析内容失败: {str(e)}")

    async def update_progress(self, record_id: str, progress: int):
        """更新进度（带节流控制）"""
        current_time = time.time()
        last_update = self.last_progress_update.get(record_id, 0)
        
        # 每0.5秒最多更新一次进度
        if current_time - last_update >= 0.5:
            await self.tex_records.update_one(
                {"_id": ObjectId(record_id)},
                {"$set": {"progress": progress}}
            )
            self.last_progress_update[record_id] = current_time

    async def convert_to_latex(self, content: str, filename: str, save_path: str, 
                             SK: List[str], AK: List[str], model_name: str, 
                             parallel_num: int = 4):
        """转换文本为LaTeX格式"""
        record_id = None
        try:
            # 创建转换记录
            tex_record = TexConversionRecord(
                input_file=filename,
                status="processing",
                model_name=model_name,
                progress=0
            )
            result = await self.tex_records.insert_one(
                tex_record.dict(by_alias=True)
            )
            record_id = result.inserted_id

            # 创建临时文件
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', 
                                           delete=False, encoding='utf-8') as temp_file:
                temp_file.write(content)
                temp_file_path = temp_file.name

            try:
                # 创建转换器实例
                hparams = HyperParams(
                    SK=SK,
                    AK=AK,
                    parallel_num=parallel_num,
                    model_name=model_name,
                    save_path=save_path
                )

                converter = LatexConverter(
                    temp_file_path, 
                    hparams,
                    progress_callback=lambda p: asyncio.create_task(
                        self.update_progress(str(record_id), p)
                    )
                )

                # 执行转换
                tex_file_path = converter.convert_to_latex()

                # 读取转换结果
                with open(tex_file_path, 'r', encoding='utf-8') as f:
                    tex_content = f.read()

                # 更新记录
                await self.tex_records.update_one(
                    {"_id": record_id},
                    {"$set": {
                        "status": "completed",
                        "content": tex_content,
                        "save_path": tex_file_path,
                        "progress": 100
                    }}
                )

                return {
                    "record_id": str(record_id),
                    "save_path": tex_file_path,
                    "content": tex_content
                }

            finally:
                # 清理临时文件
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
                # 清理进度更新记录
                if record_id and str(record_id) in self.last_progress_update:
                    del self.last_progress_update[str(record_id)]

        except Exception as e:
            if record_id:
                await self.tex_records.update_one(
                    {"_id": record_id},
                    {"$set": {"status": "failed"}}
                )
            raise e

    async def get_tex_records(self):
        """获取最近一次的LaTeX转换历史记录"""
        try:
            # 只获取最新的一条记录
            record = await self.tex_records.find_one(
                sort=[("created_at", -1)]
            )
            
            if not record:
                return []
            
            return [{
                "record_id": str(record["_id"]),
                "input_file": record["input_file"],
                "status": record["status"],
                "save_path": record.get("save_path"),
                "content": record.get("content", ""),
                "created_at": record["created_at"]
            }]
        except Exception as e:
            raise Exception(f"Failed to get records: {str(e)}")