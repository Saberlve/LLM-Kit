from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from app.components.models.mongodb import TexConversionRecord
import os
from typing import List
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils.helper import generate, split_chunk_by_tokens, split_text_into_chunks
import json
import logging
from bson import ObjectId
import asyncio
import queue
import time
from app.components.core.config import settings

logger = logging.getLogger(__name__)

class ToTexService:
    def __init__(self, db: AsyncIOMotorClient):
        self.db = db
        self.tex_records = db.llm_kit.tex_records
        self.parse_records = db.llm_kit.parse_records
        self.error_logs = db.llm_kit.error_logs

    async def _log_error(self, error_message: str, source: str, stack_trace: str = None):
        """Log error to database"""
        error_log = {
            "timestamp": datetime.utcnow(),
            "error_message": error_message,
            "source": source,
            "stack_trace": stack_trace
        }
        await self.error_logs.insert_one(error_log)

    def _process_chunk_with_api(self, chunk: str, ak: str, sk: str, model_name: str, max_tokens: int = 650, task_id: str = None, loop: asyncio.AbstractEventLoop = None) -> tuple:
        """Synchronously process a single text chunk"""
        try:
            logger.info(f"开始处理文本块，长度: {len(chunk)}, 模型: {model_name}")
            sub_chunks = split_chunk_by_tokens(chunk, max_tokens)
            total_sub_chunks = len(sub_chunks)
            logger.info(f"文本块已拆分为 {total_sub_chunks} 个子块")
            results = []
            processed_sub_chunks = 0  # 初始化计数器为0

            for idx, sub_chunk in enumerate(sub_chunks):
                success = False
                error_messages = []
                
                for attempt in range(3):
                    try:
                        logger.info(f"子块 {idx+1}/{total_sub_chunks}, 尝试 {attempt+1}/3, 长度: {len(sub_chunk)}")
                        # Directly call the synchronous generate function
                        tex_text = generate(sub_chunk, model_name, 'ToTex', ak, sk)
                        if tex_text:
                            logger.info(f"子块 {idx+1} 处理成功，结果长度: {len(tex_text)}")
                            clean_result = self._clean_result(tex_text)
                            results.append(clean_result)
                            success = True
                            break
                        else:
                            error_msg = f"子块 {idx+1} 返回空结果"
                            logger.warning(error_msg)
                            error_messages.append(error_msg)
                    except Exception as e:
                        error_msg = f"处理子块 {idx+1} 时出错 (尝试 {attempt+1}): {str(e)}"
                        logger.error(error_msg, exc_info=True)
                        error_messages.append(error_msg)
                        if attempt == 2:
                            logger.error(f"子块 {idx+1} 处理失败，已重试3次: {str(e)}")
                
                if not success:
                    logger.error(f"子块 {idx+1} 的所有尝试均失败: {'; '.join(error_messages)}")
                else:
                    processed_sub_chunks += 1  # 如果处理成功，递增计数器
                    
                    # 如果提供了task_id，则更新处理进度记录 - 每处理完一个子块就更新
                    if task_id and loop:
                        try:
                            # 异步更新处理进度记录
                            asyncio.run_coroutine_threadsafe(
                                self._update_processing_progress(task_id, processed_sub_chunks, total_sub_chunks),
                                loop
                            )
                            logger.info(f"CNMD更新处理进度: {processed_sub_chunks}/{total_sub_chunks}")
                        except Exception as e:
                            logger.error(f"更新处理进度失败: {str(e)}")
            
            logger.info(f"块处理完成，共生成 {len(results)} 个结果，成功处理了 {processed_sub_chunks}/{total_sub_chunks} 个子块")
            return results, processed_sub_chunks  # 返回结果和处理成功的子块数
        except Exception as e:
            logger.error(f"处理文本块时发生异常: {str(e)}", exc_info=True)
            raise Exception(f"Failed to process text chunk: {str(e)}")

    def _clean_result(self, text: str) -> str:
        """Clean up API response result"""
        if not text:
            return ""
            
        try:
            start_index = max(text.find('```') + 3 if '```' in text else -1, 0)
            end_index = text.rfind('```')
            
            if start_index > 0 and end_index > start_index:
                return text[start_index:end_index].strip()
            else:
                # 如果没有找到Markdown代码块，返回整个文本
                logger.warning(f"未找到Markdown代码块，返回完整文本 (长度: {len(text)})")
                return text.strip()
        except Exception as e:
            logger.error(f"清理结果时出错: {str(e)}", exc_info=True)
            return text.strip()  # 出错时返回原始文本

    async def get_parsed_files(self):
        """Get a list of all parsed files (only returns the latest for files with the same name)"""
        try:
            # Use aggregation pipeline to group by filename and get the latest record for each group
            pipeline = [
                # Only look for completed records
                {"$match": {"status": "completed"}},

                # Group by filename, keep the latest record
                {"$group": {
                    "_id": "$input_file",
                    "created_at": {"$max": "$created_at"},
                    "file_type": {"$first": "$file_type"},
                    "latest_doc": {"$first": "$$ROOT"}
                }},

                # Sort by creation time in descending order
                {"$sort": {"created_at": -1}},

                # Reformat output
                {"$project": {
                    "_id": 0,
                    "file_id": "$latest_doc._id",
                    "filename": "$_id",
                    "created_at": 1,
                    "file_type": 1
                }}
            ]

            cursor = self.parse_records.aggregate(pipeline)
            files = []
            async for record in cursor:
                files.append({
                    "file_id": str(record["file_id"]),
                    "filename": record["filename"],
                    "created_at": record["created_at"],
                    "file_type": record.get("file_type", "")
                })

            return files
        except Exception as e:
            logger.error(f"Failed to retrieve parsed file list: {str(e)}")
            raise Exception(f"Failed to retrieve parsed file list: {str(e)}")

    async def get_parsed_content(self, file_id: str):
        """Get parsed content based on file ID"""
        try:
            # Find completed record with the specified ID
            record = await self.parse_records.find_one(
                {
                    "_id": ObjectId(file_id),
                    "status": "completed"
                }
            )

            if not record:
                raise Exception(f"Parse record with ID {file_id} not found")

            if not record.get("content"):
                raise Exception(f"Parse content for ID {file_id} is empty")

            return {
                "content": record["content"],
                "filename": record["input_file"],
                "created_at": record["created_at"],
                "file_type": record["file_type"]
            }
        except Exception as e:
            logger.error(f"Failed to retrieve parsed content: {str(e)}")
            raise Exception(f"Failed to retrieve parsed content: {str(e)}")

    async def convert_to_latex(
            self,
            content: str,
            filename: str,
            save_path: str,
            SK: List[str],
            AK: List[str],
            parallel_num: int,
            model_name: str
    ):
        # Use context manager to create thread pool
        with ThreadPoolExecutor(max_workers=min(10, parallel_num)) as executor:
            try:
                # 确保文件名不包含非法字符
                safe_filename = os.path.basename(filename)
                
                # 打印调试信息
                logger.info(f"开始转换文件: {safe_filename}")
                logger.info(f"传入的内容长度: {len(content) if content else 0}")
                
                # Initialize progress to 0
                await self.tex_records.update_one(
                    {"input_file": safe_filename},
                    {"$set": {
                        "status": "processing",
                        "progress": 0
                    }},
                    upsert=True
                )

                # Validate input
                if not content:
                    raise ValueError("输入内容为空")
                
                if len(AK) < 1:
                    raise ValueError("至少需要提供一个API密钥")
                
                if parallel_num < 1:
                    parallel_num = 1
                
                if parallel_num > len(AK):
                    logger.warning(f"并行数 {parallel_num} 大于API密钥数 {len(AK)}，将使用可用的API密钥")
                    parallel_num = len(AK)

                # Get filename without extension
                base_filename = safe_filename.rsplit('.', 1)[0] if '.' in safe_filename else safe_filename

                # Check if record already exists, if so, reset progress
                existing_record = await self.tex_records.find_one({"input_file": safe_filename})
                if existing_record:
                    logger.info(f"找到现有记录，重置状态: {existing_record['_id']}")
                    await self.tex_records.update_one(
                        {"_id": existing_record["_id"]},
                        {"$set": {
                            "status": "processing", 
                            "progress": 0,
                            "start_time": datetime.now(timezone.utc),
                            "chunk_info": {
                                "total_chunks": 0,
                                "processed_chunks": 0
                            }
                        }}
                    )
                    record_id = existing_record["_id"]
                else:
                    # Create new record
                    record = TexConversionRecord(
                        input_file=safe_filename,
                        status="processing",
                        model_name=model_name,
                        progress=0,  # Initialize progress to 0
                        start_time=datetime.now(timezone.utc),
                        chunk_info={
                            "total_chunks": 0,
                            "processed_chunks": 0
                        }
                    )
                    result = await self.tex_records.insert_one(record.dict(by_alias=True))
                    record_id = result.inserted_id
                    logger.info(f"创建新记录: {record_id}")

                try:
                    # Text preprocessing stage - 10%
                    await self.tex_records.update_one(
                        {"_id": record_id},
                        {"$set": {"progress": 10}}
                    )

                    # Split text
                    text_chunks = split_text_into_chunks(parallel_num, content)
                    total_chunks = len(text_chunks)
                    processed_chunks = 0
                    logger.info(f"文本已拆分为 {total_chunks} 块")

                    # 使用split_chunk_by_tokens计算准确的子块总数，而不是估算
                    total_sub_chunks = 0
                    for chunk in text_chunks:
                        sub_chunks = split_chunk_by_tokens(chunk, max_tokens=650)
                        total_sub_chunks += len(sub_chunks)
                    
                    processed_sub_chunks = 0
                    
                    # Create task list - 20% and update chunk info
                    await self.tex_records.update_one(
                        {"_id": record_id},
                        {"$set": {
                            "progress": 20,
                            "chunk_info": {
                                "total_chunks": total_sub_chunks,
                                "processed_chunks": 0
                            }
                        }}
                    )
                    
                    # Use thread pool to execute tasks asynchronously
                    results = []
                    loop = asyncio.get_event_loop()

                    # Create task list
                    futures = []
                    for i, chunk in enumerate(text_chunks):
                        # 确保索引不会越界
                        ak_index = i % len(AK)
                        sk_index = i % len(SK) if SK and len(SK) > 0 else 0
                        
                        # 创建处理任务，传递进度队列参数和事件循环
                        future = loop.run_in_executor(
                            executor,
                            lambda ch=chunk, a=AK[ak_index], s=SK[sk_index] if SK and len(SK) > 0 else "", m=model_name, l=loop: 
                                self._process_chunk_with_api_wrapper(ch, a, s, m, 650, str(record_id), l)
                        )
                        futures.append(future)
                    
                    logger.info(f"已创建 {len(futures)} 个处理任务")

                    # Text processing stage - 20% to 80%
                    total_processed_sub_chunks = 0
                    for i, future in enumerate(asyncio.as_completed(futures)):
                        try:
                            chunk_result, sub_chunks_count = await future
                            
                            if chunk_result:
                                results.extend(chunk_result)
                                logger.info(f"成功处理第 {i+1} 块，获得 {len(chunk_result)} 个结果")
                            else:
                                logger.warning(f"第 {i+1} 块返回空结果")

                            # 更新已处理子块数
                            processed_chunks += 1
                            total_processed_sub_chunks += sub_chunks_count
                            
                            # 计算当前进度百分比
                            if total_chunks == 1:
                                # If there's only one chunk, show progress in multiple steps
                                progress_steps = [30, 40, 50, 60, 70]
                                progress = progress_steps[min(len(progress_steps)-1, i)]
                            else:
                                # Normal progress calculation for multiple chunks based on sub-chunks
                                progress = int(20 + (total_processed_sub_chunks / total_sub_chunks * 60))
                            
                            # 每个子块处理完成就更新主记录的进度，不再等待2个子块
                                await self.tex_records.update_one(
                                    {"_id": record_id},
                                    {"$set": {
                                        "progress": progress,
                                        "chunk_info": {
                                            "total_chunks": total_sub_chunks,
                                            "processed_chunks": total_processed_sub_chunks
                                        }
                                    }}
                                )
                                logger.info(f"更新主记录进度: {progress}%")
                        except Exception as e:
                            logger.error(f"处理第 {i+1} 块失败: {str(e)}", exc_info=True)
                            # Continue processing other chunks
                            continue

                    # 检查是否所有块都处理失败
                    if not results:
                        raise Exception("所有文本块处理失败，无法生成LaTeX内容")
                    
                    logger.info(f"所有块处理完成，总共获得 {len(results)} 个结果")
                    logger.info(f"处理了 {total_processed_sub_chunks} 个子块，总共有 {total_sub_chunks} 个子块")

                    # Prepare to save - 90%
                    await self.tex_records.update_one(
                        {"_id": record_id},
                        {"$set": {
                            "progress": 90,
                            "chunk_info": {
                                "total_chunks": total_sub_chunks,
                                "processed_chunks": total_processed_sub_chunks
                            }
                        }}
                    )

                    # 删除临时进度记录
                    delete_result = await self.db.llm_kit.tex_processing_progress.delete_one(
                        {"task_id": str(record_id)}
                    )
                    logger.info(f"删除临时进度记录: deleted_count={delete_result.deleted_count}")

                    # Prepare data format for saving
                    data_to_save = [
                        {"id": i + 1, "chunk": result}
                        for i, result in enumerate(results)
                    ]

                    # Complete - 100%
                    await self.tex_records.update_one(
                        {"_id": record_id},
                        {
                            "$set": {
                                "status": "completed",
                                "content": data_to_save,
                                "progress": 100,
                                "chunk_info": {
                                    "total_chunks": total_sub_chunks,
                                    "processed_chunks": total_processed_sub_chunks
                                }
                            }
                        }
                    )
                    logger.info(f"数据库记录已更新为已完成状态")

                    # Update uploaded file status to completed
                    try:
                        update_result = await self.db.llm_kit.uploaded_files.update_one(
                            {"filename": safe_filename},
                            {"$set": {"status": "completed"}}
                        )
                        logger.info(f"更新uploaded_files状态结果: 匹配={update_result.matched_count}, 修改={update_result.modified_count}")
                    except Exception as e:
                        logger.error(f"更新uploaded_files状态失败: {str(e)}", exc_info=True)

                    # Also update the status in the binary file collection (if it exists)
                    try:
                        binary_update_result = await self.db.llm_kit.uploaded_binary_files.update_one(
                            {"filename": safe_filename},
                            {"$set": {"status": "completed"}}
                        )
                        logger.info(f"更新uploaded_binary_files状态结果: 匹配={binary_update_result.matched_count}, 修改={binary_update_result.modified_count}")
                    except Exception as e:
                        logger.error(f"更新uploaded_binary_files状态失败: {str(e)}", exc_info=True)

                    # 创建新记录以提高兼容性，但不使用本地文件系统
                    try:
                        saved_file_record = {
                            "input_file": f"{base_filename}.json",  # 兼容性目的保留格式
                            "original_file": safe_filename,
                            "status": "completed",
                            "content": data_to_save,  # 直接存储数据
                            "created_at": datetime.now(timezone.utc),
                            "model_name": model_name
                        }
                        new_record_result = await self.tex_records.insert_one(saved_file_record)
                        logger.info(f"创建了新的记录: {new_record_result.inserted_id}")
                    except Exception as e:
                        logger.error(f"创建新记录失败: {str(e)}", exc_info=True)

                    # 返回结果
                    final_result = {
                        "filename": f"{base_filename}.json",  # 保持格式一致性
                        "content": data_to_save
                    }
                    logger.info("LaTeX转换成功完成")
                    return final_result

                except Exception as e:
                    # When an error occurs, maintain the current progress, only update the status
                    logger.error(f"LaTeX转换过程中出错: {str(e)}", exc_info=True)
                    
                    try:
                        await self.tex_records.update_one(
                            {"_id": record_id},
                            {"$set": {"status": "failed", "error_message": str(e)}}
                        )
                        logger.info(f"已将记录状态更新为失败")
                    except Exception as update_error:
                        logger.error(f"更新记录状态失败: {str(update_error)}", exc_info=True)

                    # Update uploaded file status to failed
                    try:
                        await self.db.llm_kit.uploaded_files.update_one(
                            {"filename": safe_filename},
                            {"$set": {"status": "failed"}}
                        )
                    except Exception as update_error:
                        logger.error(f"更新上传文件状态失败: {str(update_error)}", exc_info=True)

                    # Also update the binary file status (if it exists)
                    try:
                        await self.db.llm_kit.uploaded_binary_files.update_one(
                            {"filename": safe_filename},
                            {"$set": {"status": "failed"}}
                        )
                    except Exception as update_error:
                        logger.error(f"更新二进制文件状态失败: {str(update_error)}", exc_info=True)

                    raise e

            except Exception as e:
                import traceback
                error_trace = traceback.format_exc()
                logger.error(f"LaTeX转换总体失败: {str(e)}\n{error_trace}")
                await self._log_error(str(e), "convert_to_latex", error_trace)
                raise Exception(f"LaTeX转换失败: {str(e)}")

    async def get_tex_records(self):
        """
        获取最近的LaTeX转换历史记录，完全从数据库中获取，不依赖文件系统
        """
        try:
            # Only get the latest record
            record = await self.tex_records.find_one(
                sort=[("created_at", -1)]
            )

            if not record:
                return []

            return [{
                "record_id": str(record["_id"]),
                "input_file": record["input_file"],
                "status": record["status"],
                "content": record.get("content", ""),
                "created_at": record["created_at"]
            }]
        except Exception as e:
            raise Exception(f"Failed to get records: {str(e)}")

    async def get_tex_processing_progress(self, filename: str):
        """获取LaTeX处理的实时进度，包括子块处理信息和预估完成时间"""
        try:
            # 首先查找主记录获取基础信息
            main_record = await self.tex_records.find_one(
                {
                    "input_file": filename,
                    "status": {"$in": ["processing", "completed", "failed", "timeout"]}
                },
                sort=[("created_at", -1)]  # 获取最新的记录
            )
            
            if not main_record:
                logger.warning(f"未找到文件 {filename} 的LaTeX转换记录")
                return {
                    "progress": 0,
                    "status": "not_found",
                    "elapsed_time": 0,
                    "estimated_remaining_time": 0,
                    "estimated_completion_time": None,
                    "processed_chunks": 0,
                    "total_chunks": 0,
                    "step": "latex_conversion"
                }
            
            # 获取状态和进度
            status = main_record.get("status", "processing")
            progress = main_record.get("progress", 0)
            
            # 获取块处理信息
            chunk_info = main_record.get("chunk_info", {"total_chunks": 0, "processed_chunks": 0})
            total_chunks = chunk_info.get("total_chunks", 0)
            processed_chunks = chunk_info.get("processed_chunks", 0)
            
            # 如果主记录正在处理中，尝试从临时进度表获取更实时的进度
            if status == "processing" and str(main_record["_id"]):
                task_id = str(main_record["_id"])
                
                # 查询临时进度记录
                progress_record = await self.db.llm_kit.tex_processing_progress.find_one(
                    {"task_id": task_id}
                )
                
                if progress_record:
                    # 使用更实时的处理块信息
                    temp_processed = progress_record.get("processed_chunks", 0)
                    temp_total = progress_record.get("total_chunks", 0)
                    
                    # 只有当临时记录中的信息更新时才使用它
                    if temp_total > 0 and temp_processed <= temp_total:
                        processed_chunks = temp_processed
                        total_chunks = temp_total
                        
                        # 如果记录中total_chunks不为0，则更新进度百分比
                        if total_chunks > 0:
                            # 基于子块处理情况重新计算进度 (20-80% 区间)
                            new_progress = 20 + int((processed_chunks / total_chunks) * 60)
                            # 避免进度回退
                            if new_progress > progress:
                                progress = new_progress
            
            # 计算已经花费的时间（秒）
            current_time = datetime.now(timezone.utc)
            
            # 获取并标准化开始时间
            start_time = main_record.get("start_time")
            if start_time and not isinstance(start_time, datetime):
                try:
                    start_time = datetime.fromisoformat(str(start_time))
                except:
                    start_time = None
                    
            # 如果start_time为空或转换失败，使用created_at
            if not start_time:
                start_time = main_record.get("created_at")
                
            # 确保start_time有时区信息
            if start_time and start_time.tzinfo is None:
                start_time = start_time.replace(tzinfo=timezone.utc)
                
            if not start_time:
                start_time = current_time
            
            # 计算已用时间
            elapsed_seconds = int((current_time - start_time).total_seconds())
            
            # 计算预估剩余时间
            estimated_remaining_seconds = 0
            estimated_completion_time = None
            
            if status == "processing" and progress > 0:
                # 如果记录中已有预估完成时间，直接使用
                if "estimated_completion_time" in main_record and main_record["estimated_completion_time"]:
                    estimated_completion_time = main_record["estimated_completion_time"]
                    # 确保estimated_completion_time有时区信息
                    if estimated_completion_time and estimated_completion_time.tzinfo is None:
                        estimated_completion_time = estimated_completion_time.replace(tzinfo=timezone.utc)
                    if estimated_completion_time:
                        estimated_remaining_seconds = max(0, int((estimated_completion_time - current_time).total_seconds()))
                # 否则基于当前进度估算
                elif progress < 100 and progress > 10 and elapsed_seconds > 0:
                    # 基于已完成的百分比和已用时间来估计
                    total_estimated_seconds = (elapsed_seconds / progress) * 100
                    estimated_remaining_seconds = max(0, int(total_estimated_seconds - elapsed_seconds))
                    estimated_completion_time = current_time + timedelta(seconds=estimated_remaining_seconds)
            
            # 如果状态是已完成，设置进度为100%
            if status == "completed":
                progress = 100
                estimated_remaining_seconds = 0
                processed_chunks = total_chunks
            
            # 格式化时间显示
            formatted_elapsed_time = self._format_time_duration(elapsed_seconds)
            formatted_remaining_time = self._format_time_duration(estimated_remaining_seconds)
            formatted_completion_time = estimated_completion_time.strftime("%H:%M:%S") if estimated_completion_time else None
            
            return {
                "progress": progress,
                "status": status,
                "error_message": main_record.get("error_message", ""),
                "last_update": main_record.get("created_at", datetime.now(timezone.utc)).isoformat(),
                "elapsed_time": elapsed_seconds,
                "formatted_elapsed_time": formatted_elapsed_time,
                "estimated_remaining_time": estimated_remaining_seconds,
                "formatted_remaining_time": formatted_remaining_time,
                "estimated_completion_time": estimated_completion_time.isoformat() if estimated_completion_time else None,
                "formatted_completion_time": formatted_completion_time,
                "processed_chunks": processed_chunks,
                "total_chunks": total_chunks,
                "step": "latex_conversion"
            }
            
        except Exception as e:
            logger.error(f"获取LaTeX处理进度失败: {str(e)}", exc_info=True)
            await self._log_error(str(e), "get_tex_processing_progress")
            return {
                "progress": 0,
                "status": "error",
                "error_message": str(e),
                "elapsed_time": 0,
                "estimated_remaining_time": 0,
                "estimated_completion_time": None,
                "processed_chunks": 0,
                "total_chunks": 0,
                "step": "latex_conversion"
            }
    
    def _format_time_duration(self, seconds: int) -> str:
        """将秒数格式化为人类可读的时间格式（小时:分钟:秒）"""
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"

    def _process_chunk_with_api_wrapper(self, chunk: str, ak: str, sk: str, model_name: str, max_tokens: int = 650, task_id: str = None, loop: asyncio.AbstractEventLoop = None) -> tuple:
        """包装_process_chunk_with_api函数，方便在线程池中使用"""
        return self._process_chunk_with_api(chunk, ak, sk, model_name, max_tokens, task_id, loop)

    async def _update_processing_progress(self, task_id: str, processed_chunks: int, total_chunks: int):
        """更新子块处理进度到数据库中"""
        try:
            # 更新临时进度记录
            await self.db.llm_kit.tex_processing_progress.update_one(
                {"task_id": task_id},
                {
                    "$set": {
                        "processed_chunks": processed_chunks,
                        "total_chunks": total_chunks,
                        "last_update": datetime.now(timezone.utc)
                    }
                },
                upsert=True  # 如果记录不存在则创建
            )
            logger.info(f"已更新任务 {task_id} 的处理进度: {processed_chunks}/{total_chunks}")
        except Exception as e:
            logger.error(f"更新处理进度记录失败: {str(e)}", exc_info=True)