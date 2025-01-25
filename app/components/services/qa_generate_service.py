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
        self.error_logs = db.llm_kit.error_logs  # 添加错误日志集合

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
                                    parallel_num: int, model_name: str, domain: str):
        """并行处理多个文本块"""
        import asyncio
        
        qa_pairs = []
        tasks = set()
        
        async def process_single_chunk(chunk, ak, sk):
            return await self.process_chunk_with_api(chunk, ak, sk, model_name, domain)

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

    async def generate_qa_pairs(
            self,
            chunks_path: str,
            save_path: str,
            SK: list,
            AK: list,
            parallel_num: int,
            model_name: str,
            domain: str
    ):
        generation_id = None
        try:
            # 读取源文本
            try:
                with open(chunks_path, 'r', encoding='utf-8') as f:
                    source_text = f.read()
            except Exception as e:
                raise Exception(f"Failed to read source file: {str(e)}")

            # 创建生成记录
            generation = QAGeneration(
                input_file=chunks_path,
                save_path=save_path,
                model_name=model_name,
                domain=domain,
                status="processing",
                source_text=source_text
            )
            result = await self.qa_generations.insert_one(generation.dict(by_alias=True))
            generation_id = result.inserted_id

            # 读取并处理文本块
            with open(chunks_path, 'r', encoding='utf-8') as f:
                chunks = json.load(f)
            
            # 并行处理所有文本块
            qa_pairs = await self.process_chunks_parallel(
                [chunk.get("chunk", "") for chunk in chunks],
                AK,
                SK,
                parallel_num,
                model_name,
                domain
            )

            if not qa_pairs:
                raise Exception("No QA pairs generated")

            # 构建保存路径
            save_dir_path = os.path.join('result', 'qas', f"qa_for_{os.path.basename(chunks_path).split('.')[0]}")
            os.makedirs(save_dir_path, exist_ok=True)
            
            # 使用原始文件名作为保存文件名
            final_save_path = os.path.join(
                save_dir_path,
                os.path.basename(chunks_path)
            )

            # 保存问答对到文件
            try:
                with open(final_save_path, 'w', encoding='utf-8') as f:
                    json.dump(qa_pairs, f, ensure_ascii=False, indent=4)
            except Exception as e:
                raise Exception(f"Failed to save QA pairs to file: {str(e)}")

            # 更新保存路径
            await self.qa_generations.update_one(
                {"_id": generation_id},
                {"$set": {"save_path": final_save_path}}
            )

            # 保存问答对到数据库
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
            await self.qa_generations.update_one(
                {"_id": generation_id},
                {"$set": {"status": "completed"}}
            )

            return {
                "generation_id": str(generation_id),
                "qa_pairs": qa_pairs,
                "source_text": source_text
            }

        except Exception as e:
            import traceback
            await self._log_error(str(e), "generate_qa_pairs", traceback.format_exc())
            # 如果生成过程中出现错误，更新状态为failed
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
                    # 记录数据库更新失败，但仍然抛出原始异常
                    print(f"Failed to update generation status: {str(db_error)}")
            raise  # 直接重新抛出原始异常，保留完整的堆栈信息

    async def get_qa_records(self):
        """获取最近一次的问答对生成历史记录"""
        try:
            # 只获取最新的一条记录
            record = await self.qa_generations.find_one(
                sort=[("created_at", -1)]
            )
            
            if not record:
                return []
            
            # 获取该记录对应的所有问答对
            qa_cursor = self.qa_pairs.find({"generation_id": record["_id"]})
            qa_pairs = []
            async for qa in qa_cursor:
                qa_pairs.append({
                    "question": qa["question"],
                    "answer": qa["answer"]
                })

            return [{
                "generation_id": str(record["_id"]),
                "input_file": record["input_file"],
                "save_path": record.get("save_path", ""),
                "model_name": record["model_name"],
                "domain": record["domain"],
                "status": record["status"],
                "source_text": record["source_text"],
                "qa_pairs": qa_pairs,
                "created_at": record["created_at"]
            }]
        except Exception as e:
            raise Exception(f"Failed to get records: {str(e)}")