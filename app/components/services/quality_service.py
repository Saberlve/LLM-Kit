from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from quality_control.quality_control import QAQualityGenerator
from utils.hparams import HyperParams
from app.components.models.mongodb import QAQualityRecord, QualityControlGeneration, PyObjectId
import json
import os
import time
import asyncio
from bson.objectid import ObjectId


class QualityService:
    def __init__(self, db: AsyncIOMotorClient):
        self.db = db
        self.quality_generations = db.llm_kit.quality_generations
        self.quality_records = db.llm_kit.quality_records
        self.error_logs = db.llm_kit.error_logs  # 添加错误日志集合
        self.last_progress_update = {}  # 用于存储每个任务的最后更新时间

    async def _log_error(self, error_message: str, source: str, stack_trace: str = None):
        error_log = {
            "timestamp": datetime.utcnow(),
            "error_message": error_message,
            "source": source,
            "stack_trace": stack_trace
        }
        await self.error_logs.insert_one(error_log)

    async def evaluate_and_optimize_qa(
            self,
            qa_path: str,
            save_path: str,
            SK: list,
            AK: list,
            parallel_num: int,
            model_name: str,
            similarity_rate: float,
            coverage_rate: float,
            max_attempts: int,
            domain: str
    ):
        generation_id = None
        try:
            # 读取源文本
            with open(qa_path, 'r', encoding='utf-8') as f:
                source_text = f.read()
                qa_pairs = json.loads(source_text)

            # 创建生成记录
            generation = QualityControlGeneration(
                input_file=qa_path,
                save_path=save_path,
                model_name=model_name,
                status="processing",
                source_text=source_text
            )
            result = await self.quality_generations.insert_one(generation.dict(by_alias=True))
            generation_id = result.inserted_id

            # 创建保存目录
            os.makedirs(save_path, exist_ok=True)
            
            # 将问答对分成parallel_num份进行并行处理
            chunk_size = len(qa_pairs) // parallel_num
            if chunk_size == 0:
                chunk_size = 1
            qa_chunks = [qa_pairs[i:i + chunk_size] for i in range(0, len(qa_pairs), chunk_size)]

            # 为每个chunk创建参数
            tasks = []
            chunk_paths = []
            for i, chunk in enumerate(qa_chunks):
                # 创建临时文件路径
                chunk_path = os.path.join(save_path, f"temp_chunk_{i}.json")
                chunk_paths.append(chunk_path)
                
                # 保存chunk到临时文件
                with open(chunk_path, 'w', encoding='utf-8') as f:
                    json.dump(chunk, f, ensure_ascii=False, indent=4)
                
                hparams = HyperParams(
                    file_path=chunk_path,
                    save_path=save_path,
                    SK=[SK[i % len(SK)]],  # 为每个chunk分配一个SK
                    AK=[AK[i % len(AK)]],  # 为每个chunk分配一个AK
                    parallel_num=1,  # 每个子任务使用单线程
                    model_name=model_name,
                    similarity_rate=similarity_rate,
                    coverage_rate=coverage_rate,
                    max_attempts=max_attempts,
                    domain=domain
                )
                
                generator = QAQualityGenerator(chunk_path, hparams)
                tasks.append(generator.iterate_optim_qa())

            # 等待所有任务完成并合并结果
            all_qa_pairs = []
            for qa_pairs_path in tasks:
                try:
                    with open(qa_pairs_path, 'r', encoding='utf-8') as f:
                        chunk_qa_pairs = json.load(f)
                        all_qa_pairs.extend(chunk_qa_pairs)
                except Exception as e:
                    raise Exception(f"Failed to load optimized QA pairs from {qa_pairs_path}: {str(e)}")

            # 清理临时文件
            for temp_path in chunk_paths:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                # 同时删除QAQualityGenerator生成的结果文件
                result_path = os.path.join(
                    'result', 
                    'qas_iterated', 
                    f"qa_iteratedfor_{os.path.basename(temp_path).split('.')[0]}", 
                    os.path.basename(temp_path)
                )
                if os.path.exists(result_path):
                    os.remove(result_path)

            # 保存最终结果
            final_filename = f"quality_control_{os.path.basename(qa_path)}"
            final_path = os.path.join(save_path, final_filename)
            with open(final_path, 'w', encoding='utf-8') as f:
                json.dump(all_qa_pairs, f, ensure_ascii=False, indent=4)

            # 保存问答对到数据库
            qa_records = []
            for qa in all_qa_pairs:
                if not isinstance(qa, dict) or "question" not in qa or "answer" not in qa:
                    raise Exception(f"Invalid QA pair format: {qa}")

                qa_record = QAQualityRecord(
                    generation_id=PyObjectId(generation_id),
                    question=qa["question"],
                    answer=qa["answer"],
                    similarity_score=qa.get("similarity_score", 0.0),
                    is_explicit=qa.get("is_explicit", False),
                    is_domain_relative=qa.get("is_domain_relative", False),
                    coverage_rate=qa.get("coverage_rate", 0.0),
                    status="passed"
                )
                qa_records.append(qa_record.dict(by_alias=True))

            if qa_records:
                await self.quality_records.insert_many(qa_records)

            # 更新状态
            await self.quality_generations.update_one(
                {"_id": generation_id},
                {"$set": {
                    "status": "completed",
                    "output_file": final_path  # 添加输出文件路径
                }}
            )

            return {
                "generation_id": str(generation_id),
                "qa_pairs": all_qa_pairs,
                "source_text": source_text,
                "output_file": final_path  # 在返回结果中也包含输出文件路径
            }

        except Exception as e:
            import traceback
            await self._log_error(str(e), "evaluate_and_optimize_qa", traceback.format_exc())
            # 如果发生错误，更新状态为失败
            if generation_id:
                await self.quality_generations.update_one(
                    {"_id": generation_id},
                    {"$set": {"status": "failed"}}
                )
            raise Exception(f"Quality control failed: {str(e)}")

    async def get_quality_records(self):
        """获取最近一次的质量控制历史记录"""
        try:
            # 只获取最新的一条记录
            record = await self.quality_generations.find_one(
                sort=[("created_at", -1)]
            )
            
            if not record:
                return []
            
            # 获取该记录对应的所有问答对
            qa_cursor = self.quality_records.find({"generation_id": record["_id"]})
            qa_pairs = []
            async for qa in qa_cursor:
                qa_pairs.append({
                    "question": qa["question"],
                    "answer": qa["answer"],
                    "similarity_score": qa["similarity_score"],
                    "coverage_rate": qa["coverage_rate"],
                    "status": qa["status"]
                })

            return [{
                "generation_id": str(record["_id"]),
                "input_file": record["input_file"],
                "output_file": record.get("output_file", ""),  # 添加输出文件路径
                "model_name": record["model_name"],
                "status": record["status"],
                "source_text": record["source_text"],
                "qa_pairs": qa_pairs,
                "created_at": record["created_at"]
            }]
        except Exception as e:
            raise Exception(f"Failed to get records: {str(e)}")

    async def update_progress(self, record_id: str, progress: int):
        """更新进度（带节流控制）"""
        current_time = time.time()
        last_update = self.last_progress_update.get(record_id, 0)
        
        # 每0.5秒最多更新一次进度
        if current_time - last_update >= 0.5:
            await self.quality_records.update_one(
                {"_id": ObjectId(record_id)},
                {"$set": {"progress": progress}}
            )
            self.last_progress_update[record_id] = current_time

    async def quality_control(self, qa_path: str, save_path: str, 
                            model_name: str, domain: str):
        """执行质量控制"""
        record_id = None
        try:
            # 创建质控记录
            quality_record = QualityControlGeneration(
                input_file=qa_path,
                save_path=save_path,
                model_name=model_name,
                status="processing",
                progress=0
            )
            result = await self.quality_records.insert_one(
                quality_record.dict(by_alias=True)
            )
            record_id = result.inserted_id

            # 创建质控器实例
            generator = QAQualityGenerator(
                qa_path,
                hparams,
                progress_callback=lambda p: asyncio.create_task(
                    self.update_progress(str(record_id), p)
                )
            )

            # 执行质控
            result_path = generator.iterate_optim_qa()

            # 更新记录
            await self.quality_records.update_one(
                {"_id": record_id},
                {"$set": {
                    "status": "completed",
                    "save_path": result_path,
                    "progress": 100
                }}
            )

            return {
                "record_id": str(record_id),
                "save_path": result_path
            }

        except Exception as e:
            if record_id:
                await self.quality_records.update_one(
                    {"_id": record_id},
                    {"$set": {"status": "failed"}}
                )
            raise e