from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from generate_qas.qa_generator import QAGenerator
from utils.hparams import HyperParams
from app.components.models.mongodb import QAGeneration, QAPairDB, PyObjectId
from utils.helper import generate, extract_qa
import json
import os
from bson import ObjectId


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

    async def process_chunk_with_api(self, text: str, ak: str, sk: str, model_name: str, domain: str):
        """处理单个文本块并生成问答对"""
        qa_pairs = []
        max_retries = 5
        
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
                    # 改为同步记录错误
                    print(f"处理文本块失败: {str(e)}")
        return qa_pairs

    async def process_chunks_parallel(self, chunks: list, ak_list: list, sk_list: list, 
                                    parallel_num: int, model_name: str, domain: str, generation_id: ObjectId):
        """并行处理多个文本块"""
        import asyncio
        
        qa_pairs = []
        tasks = set()
        total_chunks = len(chunks)
        processed_chunks = 0
        
        async def process_single_chunk(chunk, ak, sk):
            nonlocal processed_chunks
            result = await self.process_chunk_with_api(chunk, ak, sk, model_name, domain)
            
            # 更新进度
            processed_chunks += 1
            progress = int((processed_chunks / total_chunks) * 100)
            await self.qa_generations.update_one(
                {"_id": generation_id},
                {"$set": {"progress": progress}}
            )
            
            return result

        for i, chunk in enumerate(chunks):
            ak = ak_list[i % len(ak_list)]
            sk = sk_list[i % len(sk_list)]
            
            if len(tasks) >= parallel_num:
                # 等待一个任务完成后再添加新任务
                done, pending = await asyncio.wait(
                    tasks, 
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                for task in done:
                    result = await task
                    if result:
                        qa_pairs.extend(result)
                tasks = pending
            
            task = asyncio.create_task(process_single_chunk(chunk, ak, sk))
            tasks.add(task)
        
        # 等待所有剩余任务完成
        if tasks:
            done, _ = await asyncio.wait(tasks)
            for task in done:
                result = await task
                if result:
                    qa_pairs.extend(result)
                    
        return qa_pairs

    async def get_all_tex_files(self):
        """获取所有已转换的tex文件记录，同名文件只返回最新的记录"""
        try:
            # 获取所有已完成的记录
            records = await self.tex_records.find(
                {"status": "completed"},
                {"_id": 1, "save_path": 1, "created_at": 1}
            ).to_list(None)
            
            # 按文件名分组，保留最新的记录
            filename_dict = {}  # {filename: {"file_id": id, "filename": filename, "created_at": created_at}}
            
            for record in records:
                if not record.get("save_path"):
                    continue
                    
                # 从save_path中提取文件名
                filename = os.path.basename(record["save_path"])
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
            raise Exception(f"获取tex文件列表失败: {str(e)}")

    async def get_tex_content(self, file_id: str):
        """根据文件ID获取tex转换后的内容"""
        try:
            # 查找指定ID的记录
            record = await self.tex_records.find_one(
                {
                    "_id": ObjectId(file_id),
                    "status": "completed"
                }
            )
            
            if not record:
                raise Exception("文件不存在或未完成转换")
                
            if not record.get("content"):
                raise Exception("文件内容为空")
                
            # 确保content是JSON数组格式
            content = record["content"]
            if not isinstance(content, str):
                content = json.dumps(content)
                
            return {
                "content": content,
                "created_at": record["created_at"]
            }
        except Exception as e:
            await self._log_error(str(e), "get_tex_content")
            raise Exception(f"获取tex内容失败: {str(e)}")

    async def generate_qa_pairs(
            self,
            content: str,
            filename: str,
            save_path: str,
            SK: list,
            AK: list,
            parallel_num: int,
            model_name: str,
            domain: str
    ):
        generation_id = None
        try:
            # 获取不带扩展名的文件名
            base_filename = filename.rsplit('.', 1)[0]

            # 检查是否已有记录，如果有，重置进度
            existing_record = await self.qa_generations.find_one({"input_file": filename})
            if existing_record:
                await self.qa_generations.update_one(
                    {"_id": existing_record["_id"]},
                    {"$set": {"status": "processing", "progress": 0}}
                )
            else:
                # 创建新记录
                generation = QAGeneration(
                    input_file=filename,
                    save_path=save_path,
                    model_name=model_name,
                    domain=domain,
                    status="processing",
                    source_text=content,
                    progress=0  # 初始化进度为 0
                )
                result = await self.qa_generations.insert_one(generation.dict(by_alias=True))
                generation_id = result.inserted_id

            # 更新原始文件状态为processing
            await self.db.llm_kit.uploaded_files.update_one(
                {"filename": filename},
                {"$set": {"status": "processing"}}
            )
            # 同时更新二进制文件集合中的状态（如果存在）
            await self.db.llm_kit.uploaded_binary_files.update_one(
                {"filename": filename},
                {"$set": {"status": "processing"}}
            )

            try:
                chunks = json.loads(content)
                # 并行处理所有文本块，传入generation_id用于更新进度
                qa_pairs = await self.process_chunks_parallel(
                    [chunk.get("chunk", "") for chunk in chunks],
                    AK,
                    SK,
                    parallel_num,
                    model_name,
                    domain,
                    generation_id
                )

                if not qa_pairs:
                    raise Exception("No QA pairs generated")

                # 构建简化的保存路径和文件名
                save_dir_path = os.path.join('result', 'qas')
                os.makedirs(save_dir_path, exist_ok=True)

                # 使用简化的文件名格式：原文件名_qa.json
                final_save_path = os.path.join(
                    save_dir_path,
                    f"{base_filename}_qa.json"
                )

                # 保存问答对到文件
                try:
                    with open(final_save_path, 'w', encoding='utf-8') as f:
                        json.dump(qa_pairs, f, ensure_ascii=False, indent=4)
                except Exception as e:
                    raise Exception(f"Failed to save QA pairs to file: {str(e)}")

                # 更新原始记录状态
                await self.qa_generations.update_one(
                    {"_id": generation_id},
                    {"$set": {
                        "status": "completed",
                        "save_path": final_save_path,
                        "progress": 100  # 处理完成，进度设为 100%
                    }}
                )

                # 更新原始文件状态为completed
                await self.db.llm_kit.uploaded_files.update_one(
                    {"filename": filename},
                    {"$set": {"status": "completed"}}
                )
                # 同时更新二进制文件集合中的状态（如果存在）
                await self.db.llm_kit.uploaded_binary_files.update_one(
                    {"filename": filename},
                    {"$set": {"status": "completed"}}
                )

                # 添加一条新记录，使用简化的文件名
                saved_file_record = {
                    "input_file": os.path.basename(final_save_path),
                    "original_file": filename,
                    "status": "completed",
                    "content": json.dumps(qa_pairs),
                    "created_at": datetime.now(timezone.utc),
                    "save_path": final_save_path,
                    "model_name": model_name,
                    "domain": domain
                }
                await self.qa_generations.insert_one(saved_file_record)

                # 保存问答对到数据库
                # 先删除之前同文件名的问答对记录
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

                # 更新生成记录状态
                await self.qa_generations.update_many(
                    {"input_file": filename, "_id": {"$ne": generation_id}},
                    {"$set": {"status": "overwritten"}}
                )

                await self.qa_generations.update_one(
                    {"_id": generation_id},
                    {"$set": {"status": "completed"}}
                )

                return {
                    "generation_id": str(generation_id),
                    "filename": os.path.basename(final_save_path),
                    "qa_pairs": qa_pairs,
                    "source_text": content
                }

            except Exception as e:
                # 更新原始文件状态为failed
                await self.db.llm_kit.uploaded_files.update_one(
                    {"filename": filename},
                    {"$set": {"status": "failed"}}
                )
                # 同时更新二进制文件的状态（如果存在）
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
        """获取最近一次的问答对生成历史记录"""
        try:
            # 只获取最新的一条记录
            record = await self.qa_generations.find_one(
                {"status": "completed"},  # 只获取已完成的记录
                sort=[("created_at", -1)]
            )
            
            if not record:
                return []
            
            # 获取该记录对应的所有问答对
            qa_pairs = []
            if record.get("content"):
                # 如果记录中有content字段，直接使用
                qa_pairs = json.loads(record["content"])
            else:
                # 否则从qa_pairs集合中获取
                qa_cursor = self.qa_pairs.find({"generation_id": record["_id"]})
                async for qa in qa_cursor:
                    qa_pairs.append({
                        "question": qa["question"],
                        "answer": qa["answer"]
                    })

            return [{
                "generation_id": str(record["_id"]),
                "input_file": record["input_file"],
                "save_path": record.get("save_path", ""),
                "model_name": record.get("model_name", ""),
                "domain": record.get("domain", ""),
                "status": record["status"],
                "qa_pairs": qa_pairs,
                "created_at": record["created_at"]
            }]
        except Exception as e:
            await self._log_error(str(e), "get_qa_records")
            raise Exception(f"Failed to get records: {str(e)}")