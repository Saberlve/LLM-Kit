from datetime import datetime, timezone
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

    def _process_chunk_with_api(self, chunk: str, ak: str, sk: str, model_name: str, max_tokens: int = 650) -> list:
        """Synchronously process a single text chunk"""
        try:
            logger.info(f"开始处理文本块，长度: {len(chunk)}, 模型: {model_name}")
            sub_chunks = split_chunk_by_tokens(chunk, max_tokens)
            logger.info(f"文本块已拆分为 {len(sub_chunks)} 个子块")
            results = []

            for idx, sub_chunk in enumerate(sub_chunks):
                success = False
                error_messages = []
                
                for attempt in range(3):
                    try:
                        logger.info(f"子块 {idx+1}/{len(sub_chunks)}, 尝试 {attempt+1}/3, 长度: {len(sub_chunk)}")
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
            
            logger.info(f"块处理完成，共生成 {len(results)} 个结果")
            return results
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
                # 确保文件名和路径不包含非法字符
                safe_filename = os.path.basename(filename)
                
                # 打印调试信息
                logger.info(f"开始转换文件: {safe_filename}, 并保存到路径: {save_path}")
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

                # Create save directory - 使用os.path.join确保路径正确拼接
                if not os.path.isabs(save_path):
                    save_path = os.path.abspath(save_path)
                
                os.makedirs(save_path, exist_ok=True)
                logger.info(f"保存目录已创建: {save_path}")

                # Get filename without extension
                base_filename = safe_filename.rsplit('.', 1)[0] if '.' in safe_filename else safe_filename

                # Check if record already exists, if so, reset progress
                existing_record = await self.tex_records.find_one({"input_file": safe_filename})
                if existing_record:
                    logger.info(f"找到现有记录，重置状态: {existing_record['_id']}")
                    await self.tex_records.update_one(
                        {"_id": existing_record["_id"]},
                        {"$set": {"status": "processing", "progress": 0}}
                    )
                    record_id = existing_record["_id"]
                else:
                    # Create new record
                    record = TexConversionRecord(
                        input_file=safe_filename,
                        status="processing",
                        model_name=model_name,
                        save_path=save_path,
                        progress=0  # Initialize progress to 0
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

                    # Create task list - 20%
                    await self.tex_records.update_one(
                        {"_id": record_id},
                        {"$set": {"progress": 20}}
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
                        
                        future = loop.run_in_executor(
                            executor,
                            self._process_chunk_with_api,
                            chunk,
                            AK[ak_index],
                            SK[sk_index] if SK and len(SK) > 0 else "",
                            model_name
                        )
                        futures.append(future)
                    
                    logger.info(f"已创建 {len(futures)} 个处理任务")

                    # Text processing stage - 20% to 80%
                    for i, future in enumerate(asyncio.as_completed(futures)):
                        try:
                            chunk_result = await future
                            if chunk_result:
                                results.extend(chunk_result)
                                logger.info(f"成功处理第 {i+1} 块，获得 {len(chunk_result)} 个结果")
                            else:
                                logger.warning(f"第 {i+1} 块返回空结果")

                            # Update progress - even with just one chunk there will be progressive progress
                            processed_chunks += 1
                            if total_chunks == 1:
                                # If there's only one chunk, show progress in multiple steps
                                progress_steps = [30, 40, 50, 60, 70]
                                progress = progress_steps[min(len(progress_steps)-1, i)]
                            else:
                                # Normal progress calculation for multiple chunks
                                progress = int(20 + (processed_chunks / total_chunks * 60))

                            await self.tex_records.update_one(
                                {"_id": record_id},
                                {"$set": {"progress": progress}}
                            )
                        except Exception as e:
                            logger.error(f"处理第 {i+1} 块失败: {str(e)}", exc_info=True)
                            # Continue processing other chunks
                            continue

                    # 检查是否所有块都处理失败
                    if not results:
                        raise Exception("所有文本块处理失败，无法生成LaTeX内容")
                    
                    logger.info(f"所有块处理完成，总共获得 {len(results)} 个结果")

                    # Prepare to save - 90%
                    await self.tex_records.update_one(
                        {"_id": record_id},
                        {"$set": {"progress": 90}}
                    )

                    # Combine all LaTeX content
                    combined_tex = '\n'.join(results)
                    logger.info(f"合并后的LaTeX内容长度: {len(combined_tex)}")

                    # Prepare data format for saving
                    data_to_save = [
                        {"id": i + 1, "chunk": result}
                        for i, result in enumerate(results)
                    ]

                    # Generate simplified save path - 使用os.path.join确保路径正确拼接
                    tex_dir_path = os.path.join(save_path, 'tex_files')
                    os.makedirs(tex_dir_path, exist_ok=True)
                    tex_file_path = os.path.join(tex_dir_path, f'{base_filename}.json')
                    logger.info(f"将保存结果到: {tex_file_path}")

                    # Save as JSON format
                    try:
                        with open(tex_file_path, 'w', encoding='utf-8') as json_file:
                            json.dump(data_to_save, json_file, ensure_ascii=False, indent=4)
                        logger.info(f"文件保存成功: {tex_file_path}")
                    except Exception as e:
                        logger.error(f"保存文件失败: {str(e)}", exc_info=True)
                        raise Exception(f"保存LaTeX结果文件失败: {str(e)}")

                    # Complete - 100%
                    await self.tex_records.update_one(
                        {"_id": record_id},
                        {
                            "$set": {
                                "status": "completed",
                                "content": data_to_save,
                                "save_path": tex_file_path,
                                "progress": 100
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

                    # Add a new record using the simplified filename
                    try:
                        saved_file_record = {
                            "input_file": os.path.basename(tex_file_path),
                            "original_file": safe_filename,
                            "status": "completed",
                            "content": data_to_save,  # Use JSON format data
                            "created_at": datetime.now(timezone.utc),
                            "save_path": tex_file_path,
                            "model_name": model_name
                        }
                        new_record_result = await self.tex_records.insert_one(saved_file_record)
                        logger.info(f"创建了新的记录: {new_record_result.inserted_id}")
                    except Exception as e:
                        logger.error(f"创建新记录失败: {str(e)}", exc_info=True)

                    # 返回结果
                    final_result = {
                        "filename": os.path.basename(tex_file_path),
                        "save_path": tex_file_path,
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
        """Get the most recent LaTeX conversion history record"""
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
                "save_path": record.get("save_path"),
                "content": record.get("content", ""),
                "created_at": record["created_at"]
            }]
        except Exception as e:
            raise Exception(f"Failed to get records: {str(e)}")