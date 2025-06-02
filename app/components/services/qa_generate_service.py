from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from generate_qas.qa_generator import QAGenerator
from utils.hparams import HyperParams
from app.components.models.mongodb import QAGeneration, QAPairDB, PyObjectId
from utils.helper import generate, extract_qa
import json
import os
from bson import ObjectId
from concurrent.futures import ThreadPoolExecutor, as_completed
import asyncio
import logging

logger = logging.getLogger(__name__)

class QAGenerateService:
    def __init__(self, db: AsyncIOMotorClient):
        self.db = db
        self.qa_generations = db.llm_kit.qa_generations
        self.qa_pairs = db.llm_kit.qa_pairs
        self.error_logs = db.llm_kit.error_logs
        self.tex_records = db.llm_kit.tex_records

    async def _log_error(self, error_message: str, source: str, stack_trace: str = None):
        error_log = {
            "timestamp": datetime.utcnow(),
            "error_message": error_message,
            "source": source,
            "stack_trace": stack_trace
        }
        await self.error_logs.insert_one(error_log)

    def process_chunk_with_api(self, text: str, ak: str, sk: str, model_name: str, domain: str):
        """Synchronously process a single text chunk"""
        qa_pairs = []
        max_retries = 5
        
        # 估计子块数量，基于文本长度
        # 假设每1000个字符需要一个子块处理
        # 这个估计可能不准确，但为了进度条显示目的足够了
        sub_chunks_count = max(1, len(text) // 1000)
        logger.info(f"估计该块包含 {sub_chunks_count} 个子块 (基于文本长度 {len(text)})")

        for attempt in range(max_retries):
            try:
                response = generate(text, model_name, 'ToQA', ak, sk)
                qas = extract_qa(response)
                for qa_pair in qas:
                    qa_pair["text"] = text
                    qa_pairs.append(qa_pair)
                break
            except Exception as e:
                if attempt == max_retries - 1:
                    print(f"Failed to process text chunk: {str(e)}")
        
        return qa_pairs, sub_chunks_count

    async def process_chunks_parallel(self, chunks: list, ak_list: list, sk_list: list,
                                    parallel_num: int, model_name: str, domain: str, generation_id: ObjectId):
        """Process multiple text chunks in parallel"""
        qa_pairs = []
        total_chunks = len(chunks)
        processed_chunks = 0
        start_time = datetime.now(timezone.utc)

        # Use context manager to create thread pool
        with ThreadPoolExecutor(max_workers=min(10, parallel_num)) as executor:
            try:
                # Initialization phase - 10%
                await self.qa_generations.update_one(
                    {"_id": generation_id},
                    {"$set": {"progress": 10, "start_time": start_time}}
                )

                # Task preparation - 20%
                loop = asyncio.get_event_loop()
                futures = []

                for i, chunk in enumerate(chunks):
                    ak = ak_list[i % len(ak_list)]
                    sk = sk_list[i % len(sk_list)]
                    future = loop.run_in_executor(
                        executor,
                        self.process_chunk_with_api,
                        chunk, ak, sk, model_name, domain
                    )
                    futures.append(future)

                await self.qa_generations.update_one(
                    {"_id": generation_id},
                    {"$set": {"progress": 20}}
                )

                # Processing phase - 20% to 80%
                for i, future in enumerate(asyncio.as_completed(futures)):
                    try:
                        chunk_result, sub_chunks_count = await future
                        if chunk_result:
                            qa_pairs.extend(chunk_result)

                        # Update progress - special handling for small text
                        processed_chunks += 1
                        if total_chunks == 1:
                            # Progress points for single chunk
                            progress_steps = [30, 40, 50, 60, 70]
                            progress = progress_steps[min(len(progress_steps)-1, i)]
                        else:
                            # Normal progress calculation for multiple chunks
                            progress = int(20 + (processed_chunks / total_chunks * 60))
                        
                        # 计算预估完成时间
                        elapsed_time = (datetime.now(timezone.utc) - start_time).total_seconds()
                        if processed_chunks > 0 and progress > 20:
                            # 基于已处理的块和已用时间估计总时间
                            total_estimated_seconds = (elapsed_time / (processed_chunks / total_chunks))
                            remaining_seconds = total_estimated_seconds - elapsed_time
                            estimated_completion = datetime.now(timezone.utc) + timedelta(seconds=remaining_seconds)
                            
                            await self.qa_generations.update_one(
                                {"_id": generation_id},
                                {"$set": {
                                    "progress": progress,
                                    "estimated_completion_time": estimated_completion
                                }}
                            )
                        else:
                            await self.qa_generations.update_one(
                                {"_id": generation_id},
                                {"$set": {"progress": progress}}
                            )
                    except Exception as e:
                        logger.error(f"Failed to process chunk: {str(e)}")
                        continue

                # Save preparation - 90%
                await self.qa_generations.update_one(
                    {"_id": generation_id},
                    {"$set": {"progress": 90}}
                )

                if not qa_pairs:
                    raise Exception("No QA pairs were generated")

                return qa_pairs

            except Exception as e:
                logger.error(f"Parallel processing failed: {str(e)}")
                raise e

    async def get_all_tex_files(self):
        """获取所有已转换的tex文件记录，只返回具有相同名称的文件的最新记录，完全从数据库获取"""
        try:
            # 获取所有已完成的记录
            records = await self.tex_records.find(
                {"status": "completed"},
                {"_id": 1, "input_file": 1, "content": 1, "created_at": 1}
            ).to_list(None)

            # 按文件名分组，保留最新的记录
            filename_dict = {}  # {filename: {"file_id": id, "filename": filename, "created_at": created_at}}

            for record in records:
                # 检查是否有内容
                if not record.get("content"):
                    continue

                # 获取文件名
                filename = record.get("input_file")
                if not filename:
                    continue
                    
                created_at = record["created_at"]

                # 如果文件名已存在，比较创建时间
                if filename in filename_dict:
                    if created_at > filename_dict[filename]["created_at"]:
                        filename_dict[filename] = {
                            "file_id": str(record["_id"]),
                            "filename": filename,
                            "created_at": created_at
                        }
                else:
                    filename_dict[filename] = {
                        "file_id": str(record["_id"]),
                        "filename": filename,
                        "created_at": created_at
                    }

            # 转换为列表并按创建时间降序排序
            files = list(filename_dict.values())
            files.sort(key=lambda x: x["created_at"], reverse=True)

            return files

        except Exception as e:
            await self._log_error(str(e), "get_all_tex_files")
            raise Exception(f"Failed to get tex file list: {str(e)}")

    async def get_tex_content(self, file_id: str):
        """Get tex converted content by file ID"""
        try:
            # Find record with specified ID
            record = await self.tex_records.find_one(
                {
                    "_id": ObjectId(file_id),
                    "status": "completed"
                }
            )

            if not record:
                raise Exception("File does not exist or conversion not completed")

            if not record.get("content"):
                raise Exception("File content is empty")

            # Ensure content is in JSON array format
            content = record["content"]
            if not isinstance(content, str):
                content = json.dumps(content)

            return {
                "content": content,
                "created_at": record["created_at"]
            }
        except Exception as e:
            await self._log_error(str(e), "get_tex_content")
            raise Exception(f"Failed to get tex content: {str(e)}")

    async def generate_qa_pairs(
            self,
            content: str,
            filename: str,
            SK: list,
            AK: list,
            parallel_num: int,
            model_name: str,
            domain: str
    ):
        generation_id = None
        try:
            # Get filename without extension
            base_filename = filename.rsplit('.', 1)[0]

            # 检查是否已存在记录，如果存在且包含有效内容，则重置进度
            # 只有当记录状态为completed且内容不为空时才认为是有效记录
            existing_record = await self.qa_generations.find_one({
                "input_file": filename,
                "status": "completed"
            })
            
            if existing_record and existing_record.get("content"):
                # 验证内容是否有效
                try:
                    content_data = existing_record.get("content")
                    if isinstance(content_data, str):
                        json_content = json.loads(content_data)
                        if json_content and len(json_content) > 0:
                            # 内容有效，重置记录
                            await self.qa_generations.update_one(
                                {"_id": existing_record["_id"]},
                                {"$set": {
                                    "status": "processing",
                                    "progress": 0,
                                    "model_name": model_name,
                                    "domain": domain,
                                    "start_time": datetime.now(timezone.utc),
                                    "chunk_info": {
                                        "total_chunks": 0,
                                        "processed_chunks": 0
                                    }
                                }}
                            )
                            generation_id = existing_record["_id"]
                            logger.info(f"找到有效的现有记录，ID: {generation_id}，重置状态")
                except (json.JSONDecodeError, TypeError):
                    # 内容无效，创建新记录
                    logger.warning(f"找到的记录内容无效，将创建新记录")
                    existing_record = None
            
            if not generation_id:
                # 没有找到有效记录或内容无效，创建新记录
                generation = QAGeneration(
                    input_file=filename,
                    model_name=model_name,
                    domain=domain,
                    status="processing",
                    source_text=content,
                    progress=0,  # Initialize progress to 0
                    start_time=datetime.now(timezone.utc),
                    chunk_info={
                        "total_chunks": 0,
                        "processed_chunks": 0
                    }
                )
                result = await self.qa_generations.insert_one(generation.dict(by_alias=True))
                generation_id = result.inserted_id
                logger.info(f"创建了新的QA生成记录，ID: {generation_id}")

            # 更新原始文件状态为处理中
            await self.db.llm_kit.uploaded_files.update_one(
                {"filename": filename},
                {"$set": {"status": "processing"}}
            )
            # Also update status in binary file collection (if exists)
            await self.db.llm_kit.uploaded_binary_files.update_one(
                {"filename": filename},
                {"$set": {"status": "processing"}}
            )

            try:
                chunks = json.loads(content)
                
                # 计算总块数和已处理块数，用于精确跟踪进度
                total_chunks = len(chunks)
                processed_chunks = 0
                
                # 初始估算子块总数，先估计每个块有5个子块
                estimated_total_sub_chunks = total_chunks * 5
                processed_sub_chunks = 0
                
                qa_pairs = []
                start_time = datetime.now(timezone.utc)
                
                # 初始化进度为10%（准备阶段），并保存总块数
                await self.qa_generations.update_one(
                    {"_id": generation_id},
                    {"$set": {
                        "progress": 10, 
                        "start_time": start_time,
                        "chunk_info": {
                            "total_chunks": estimated_total_sub_chunks,
                            "processed_chunks": 0
                        }
                    }}
                )
                
                # 获取事件循环
                loop = asyncio.get_event_loop()
                
                # 创建线程池
                with ThreadPoolExecutor(max_workers=min(10, parallel_num)) as executor:
                    futures = []
                    # 提交所有块到线程池，使用loop.run_in_executor创建asyncio.Future
                    for i, chunk in enumerate(chunks):
                        ak = AK[i % len(AK)]
                        sk = SK[i % len(SK)] if SK and len(SK) > 0 else ""
                        
                        # 使用loop.run_in_executor创建asyncio.Future
                        future = loop.run_in_executor(
                            executor,
                            self.process_chunk_with_api,
                            chunk.get("chunk", ""),
                            ak, 
                            sk,
                            model_name,
                            domain
                        )
                        futures.append(future)
                    
                    # 更新进度到20%（所有任务已提交）
                    await self.qa_generations.update_one(
                        {"_id": generation_id},
                        {"$set": {"progress": 20}}
                    )
                    
                    # 逐个处理完成的任务
                    real_total_sub_chunks = 0
                    for i, future in enumerate(asyncio.as_completed(futures)):
                        try:
                            # 正确获取并解构元组结果
                            chunk_result, sub_chunks_count = await future
                            real_total_sub_chunks += sub_chunks_count
                            
                            if chunk_result:
                                qa_pairs.extend(chunk_result)
                            
                            # 更新进度 - 即使只有一个块完成也更新
                            processed_chunks += 1
                            processed_sub_chunks += sub_chunks_count
                            
                            # 更新真实的子块总数
                            if i == 0 and total_chunks > 1:
                                # 基于第一个块更新估计的总子块数
                                estimated_total_sub_chunks = total_chunks * sub_chunks_count
                            
                            # 计算进度百分比（从20%到90%）
                            if total_chunks == 1:
                                # 只有一个块时使用固定步骤
                                progress_steps = [30, 40, 50, 60, 70, 80]
                                progress = progress_steps[min(len(progress_steps)-1, i)]
                            else:
                                # 基于子块进度计算
                                progress = int(20 + (processed_sub_chunks / estimated_total_sub_chunks * 70))
                            
                            # 计算预估完成时间
                            elapsed_time = (datetime.now(timezone.utc) - start_time).total_seconds()
                            if processed_sub_chunks > 0:
                                # 基于已处理的子块和已用时间估计剩余时间
                                avg_time_per_sub_chunk = elapsed_time / processed_sub_chunks
                                remaining_sub_chunks = estimated_total_sub_chunks - processed_sub_chunks
                                remaining_seconds = avg_time_per_sub_chunk * remaining_sub_chunks
                                estimated_completion = datetime.now(timezone.utc) + timedelta(seconds=remaining_seconds)
                                
                                # 更新进度、预估完成时间和块处理信息
                                await self.qa_generations.update_one(
                                    {"_id": generation_id},
                                    {"$set": {
                                        "progress": progress,
                                        "estimated_completion_time": estimated_completion,
                                        "chunk_info": {
                                            "total_chunks": estimated_total_sub_chunks,
                                            "processed_chunks": processed_sub_chunks
                                        }
                                    }}
                                )
                                
                                # 记录日志
                                logger.info(f"文件 {filename} - 进度: {progress}%, 已处理: {processed_sub_chunks}/{estimated_total_sub_chunks} 子块, 预计完成时间: {estimated_completion.isoformat()}")
                            else:
                                await self.qa_generations.update_one(
                                    {"_id": generation_id},
                                    {"$set": {
                                        "progress": progress,
                                        "chunk_info": {
                                            "total_chunks": estimated_total_sub_chunks,
                                            "processed_chunks": processed_sub_chunks
                                        }
                                    }}
                                )
                        except Exception as e:
                            logger.error(f"处理块失败: {str(e)}")
                            # 继续处理其他块
                            continue
                
                # 检查是否有成功生成的QA对
                if not qa_pairs:
                    raise Exception("未生成任何QA对")
                
                logger.info(f"处理了 {processed_sub_chunks} 个子块，总共估计有 {estimated_total_sub_chunks} 个子块")
                
                # 更新进度到90%（保存阶段）
                await self.qa_generations.update_one(
                    {"_id": generation_id},
                    {"$set": {
                        "progress": 90,
                        "chunk_info": {
                            "total_chunks": processed_sub_chunks,  # 使用实际处理的子块数
                            "processed_chunks": processed_sub_chunks
                        }
                    }}
                )
                
                # 将QA对序列化为JSON字符串
                qa_pairs_json = json.dumps(qa_pairs, ensure_ascii=False)
                logger.info(f"成功生成QA对，数量: {len(qa_pairs)}")

                # 更新原始记录状态为已完成
                await self.qa_generations.update_one(
                    {"_id": generation_id},
                    {"$set": {
                        "status": "completed",
                        "content": qa_pairs_json,  # 直接在数据库中存储QA对
                        "progress": 100,  # Processing complete, set progress to 100%
                        "chunk_info": {
                            "total_chunks": processed_sub_chunks,
                            "processed_chunks": processed_sub_chunks
                        }
                    }}
                )
                logger.info(f"已更新记录状态为已完成，并存储QA对到数据库中")

                # 更新原始文件状态为已完成
                await self.db.llm_kit.uploaded_files.update_one(
                    {"filename": filename},
                    {"$set": {"status": "completed"}}
                )
                # 同时更新二进制文件集合中的状态（如果存在）
                await self.db.llm_kit.uploaded_binary_files.update_one(
                    {"filename": filename},
                    {"$set": {"status": "completed"}}
                )

                # 添加一条新记录，使用标准化的命名方式
                saved_file_record = {
                    "input_file": f"{base_filename}_qa.json",  # 为兼容性保留这种命名方式
                    "original_file": filename,
                    "status": "completed",
                    "content": qa_pairs_json,  # 直接存储QA对
                    "created_at": datetime.now(timezone.utc),
                    "model_name": model_name,
                    "domain": domain
                }
                new_record = await self.qa_generations.insert_one(saved_file_record)
                logger.info(f"创建了新的QA记录: {new_record.inserted_id}")

                # 将QA对存储到数据库中
                # 首先删除具有相同文件名的以前的QA对记录
                await self.qa_pairs.delete_many({
                    "generation_id": {
                        "$in": [
                            doc["_id"] for doc in await self.qa_generations.find(
                                {"input_file": filename, "_id": {"$ne": generation_id}}
                            ).to_list(None)
                        ]
                    }
                })

                qa_records = []
                for qa in qa_pairs:
                    qa_record = QAPairDB(
                        generation_id=PyObjectId(generation_id),
                        question=qa["question"],
                        answer=qa["answer"]
                    )
                    qa_records.append(qa_record.dict(by_alias=True))

                if qa_records:
                    await self.qa_pairs.insert_many(qa_records)
                    logger.info(f"已将 {len(qa_records)} 个QA对存储到qa_pairs集合")

                # 更新生成记录状态
                await self.qa_generations.update_many(
                    {"input_file": filename, "_id": {"$ne": generation_id}},
                    {"$set": {"status": "overwritten"}}
                )

                await self.qa_generations.update_one(
                    {"_id": generation_id},
                    {"$set": {"status": "completed"}}
                )

                # 准备返回数据
                return {
                    "generation_id": str(generation_id),
                    "qa_pairs": qa_pairs,
                    "qa_data": qa_pairs,  # 添加qa_data字段，供路由函数使用
                    "source_text": content
                }

            except Exception as e:
                # When an error occurs, only update status, maintain current progress
                await self.qa_generations.update_one(
                    {"_id": generation_id},
                    {"$set": {
                        "status": "failed",
                        "error_message": str(e)
                    }}
                )

                # Maintain original error handling logic
                await self.db.llm_kit.uploaded_files.update_one(
                    {"filename": filename},
                    {"$set": {"status": "failed"}}
                )
                await self.db.llm_kit.uploaded_binary_files.update_one(
                    {"filename": filename},
                    {"$set": {"status": "failed"}}
                )
                raise e

        except Exception as e:
            import traceback
            await self._log_error(str(e), "generate_qa_pairs", traceback.format_exc())
            if generation_id:
                try:
                    await self.qa_generations.update_one(
                        {"_id": generation_id},
                        {"$set": {
                            "status": "failed",
                            "error_message": str(e)
                        }}
                    )
                except Exception as db_error:
                    print(f"Failed to update generation status: {str(db_error)}")
            raise Exception(f"QA generation failed: {str(e)}")

    async def get_qa_records(self):
        """获取最近的QA对生成历史记录，完全从数据库获取"""
        try:
            # 只获取最新的记录
            record = await self.qa_generations.find_one(
                {"status": "completed"},  # 只获取已完成的记录
                sort=[("created_at", -1)]
            )

            if not record:
                return []

            # 获取与此记录对应的所有QA对
            qa_pairs = []
            if record.get("content"):
                # 如果记录有content字段，直接使用
                try:
                    if isinstance(record["content"], str):
                        qa_pairs = json.loads(record["content"])
                    else:
                        qa_pairs = record["content"]
                except json.JSONDecodeError:
                    logger.warning(f"无法解析QA记录内容: {record['_id']}")
            else:
                # 否则从qa_pairs集合获取
                qa_cursor = self.qa_pairs.find({"generation_id": record["_id"]})
                async for qa in qa_cursor:
                    qa_pairs.append({
                        "question": qa["question"],
                        "answer": qa["answer"]
                    })

            return [{
                "generation_id": str(record["_id"]),
                "input_file": record["input_file"],
                "model_name": record.get("model_name", ""),
                "domain": record.get("domain", ""),
                "status": record["status"],
                "qa_pairs": qa_pairs,
                "created_at": record["created_at"]
            }]
        except Exception as e:
            await self._log_error(str(e), "get_qa_records")
            raise Exception(f"Failed to get records: {str(e)}")