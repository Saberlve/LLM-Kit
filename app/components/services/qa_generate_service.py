from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from generate_qas.qa_generator import QAGenerator
from utils.hparams import HyperParams
from app.components.models.mongodb import QAGeneration, QAPairDB, PyObjectId
from utils.helper import generate, extract_qa
import json
import os
from bson import ObjectId
import asyncio
import time
from typing import List


class QAGenerateService:
    def __init__(self, db: AsyncIOMotorClient):
        self.db = db
        self.qa_records = db.llm_kit.qa_generations
        self.qa_pairs = db.llm_kit.qa_pairs
        self.error_logs = db.llm_kit.error_logs
        self.tex_records = db.llm_kit.tex_records  # 修改为正确的集合名称
        self.last_progress_update = {}  # 用于存储每个任务的最后更新时间

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

    async def get_all_tex_files(self):
        """获取所有已转换的tex文件记录，同名文件只返回最新的记录"""
        try:
            # 使用聚合管道，按文件名分组并获取每组最新的记录
            pipeline = [
                # 只查找已完成的记录
                {"$match": {"status": "completed"}},
                
                # 按文件名分组，保留最新的记录
                {"$group": {
                    "_id": "$input_file",
                    "created_at": {"$max": "$created_at"},
                    "latest_doc": {"$first": "$$ROOT"}
                }},
                
                # 按创建时间降序排序
                {"$sort": {"created_at": -1}},
                
                # 重新格式化输出
                {"$project": {
                    "_id": 0,
                    "filename": "$_id",
                    "created_at": 1
                }}
            ]
            
            cursor = self.tex_records.aggregate(pipeline)
            files = []
            async for record in cursor:
                files.append({
                    "filename": record["filename"],
                    "created_at": record["created_at"]
                })
            
            return files
        except Exception as e:
            await self._log_error(str(e), "get_all_tex_files")
            raise Exception(f"获取tex文件列表失败: {str(e)}")

    async def get_tex_content(self, filename: str):
        """根据文件名获取tex转换后的内容"""
        try:
            # 查找指定文件名的最新已完成记录
            record = await self.tex_records.find_one(
                {
                    "input_file": filename,
                    "status": "completed"
                },
                sort=[("created_at", -1)]
            )
            
            if not record:
                raise Exception("文件不存在或未完成转换")
                
            if not record.get("content"):
                raise Exception("文件内容为空")
                
            return {
                "content": record["content"],
                "created_at": record["created_at"]
            }
        except Exception as e:
            await self._log_error(str(e), "get_tex_content")
            raise Exception(f"获取tex内容失败: {str(e)}")

    async def update_progress(self, record_id: str, progress: int):
        """更新进度（带节流控制）"""
        current_time = time.time()
        last_update = self.last_progress_update.get(record_id, 0)
        
        # 每0.5秒最多更新一次进度
        if current_time - last_update >= 0.5:
            await self.qa_records.update_one(
                {"_id": ObjectId(record_id)},
                {"$set": {"progress": progress}}
            )
            self.last_progress_update[record_id] = current_time

    async def generate_qa(self, content: str, filename: str, save_path: str,
                         SK: List[str], AK: List[str], model_name: str,
                         domain: str, parallel_num: int = 4):
        """生成问答对"""
        record_id = None
        try:
            # 创建生成记录
            qa_record = QAGeneration(
                input_file=filename,
                save_path=save_path,
                model_name=model_name,
                domain=domain,
                status="processing",
                source_text=content,
                progress=0
            )
            result = await self.qa_records.insert_one(
                qa_record.dict(by_alias=True)
            )
            record_id = result.inserted_id

            # 创建生成器实例
            hparams = HyperParams(
                SK=SK,
                AK=AK,
                parallel_num=parallel_num,
                model_name=model_name,
                domain=domain,
                save_path=save_path
            )

            generator = QAGenerator(
                content,
                hparams,
                progress_callback=lambda p: asyncio.create_task(
                    self.update_progress(str(record_id), p)
                )
            )

            # 执行生成
            qa_file_path = generator.convert_tex_to_qas()

            # 更新记录
            await self.qa_records.update_one(
                {"_id": record_id},
                {"$set": {
                    "status": "completed",
                    "save_path": qa_file_path,
                    "progress": 100
                }}
            )

            return {
                "record_id": str(record_id),
                "save_path": qa_file_path
            }

        except Exception as e:
            if record_id:
                await self.qa_records.update_one(
                    {"_id": record_id},
                    {"$set": {"status": "failed"}}
                )
            raise e

    async def get_qa_records(self):
        """获取最近一次的问答对生成历史记录"""
        try:
            # 只获取最新的一条记录
            record = await self.qa_records.find_one(
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