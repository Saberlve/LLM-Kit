from deduplication.qa_deduplication import QADeduplication
from utils.hparams import DedupParams
from motor.motor_asyncio import AsyncIOMotorClient
from app.components.models.mongodb import DedupRecord, KeptQAPair, DeletedQAPair
import json
from typing import List
from datetime import datetime
import os
import time
import asyncio
from bson import ObjectId


class QADedupService:
    def __init__(self, db: AsyncIOMotorClient):
        self.db = db
        self.dedup_records = db.llm_kit.dedup_records
        self.kept_pairs = db.llm_kit.kept_pairs
        self.error_logs = db.llm_kit.error_logs
        self.deleted_pairs = db.llm_kit.deleted_pairs
        self.base_output_dir = "results/dedup"  # 添加基础输出目录
        os.makedirs(self.base_output_dir, exist_ok=True)
        self.last_progress_update = {}  # 用于存储每个任务的最后更新时间

    async def _log_error(self, error_message: str, source: str, stack_trace: str = None):
        error_log = {
            "timestamp": datetime.utcnow(),
            "error_message": error_message,
            "source": source,
            "stack_trace": stack_trace
        }
        await self.error_logs.insert_one(error_log)

    def _generate_output_paths(self, timestamp: datetime):
        """生成输出文件路径"""
        date_str = timestamp.strftime("%Y%m%d_%H%M%S")
        output_file = os.path.join(self.base_output_dir, f"dedup_result_{date_str}.json")
        deleted_file = os.path.join(self.base_output_dir, f"deleted_pairs_{date_str}.json")
        return output_file, deleted_file

    async def update_progress(self, record_id: str, progress: int):
        """更新进度（带节流控制）"""
        current_time = time.time()
        last_update = self.last_progress_update.get(record_id, 0)
        
        # 每0.5秒最多更新一次进度
        if current_time - last_update >= 0.5:
            await self.dedup_records.update_one(
                {"_id": ObjectId(record_id)},
                {"$set": {"progress": progress}}
            )
            self.last_progress_update[record_id] = current_time

    async def deduplicate_qa(
            self,
            input_file: List[str],
            dedup_by_answer: bool,
            dedup_threshold: float,
            min_answer_length: int = 10,
    ):
        try:
            # 生成输出文件路径
            timestamp = datetime.now()
            output_file, deleted_pairs_file = self._generate_output_paths(timestamp)

            # 读取所有源文件的内容
            original_pairs = []
            source_texts = []
            for file_path in input_file:
                with open(file_path, 'r', encoding='utf-8') as f:
                    source_text = f.read()
                    source_texts.append(source_text)
                    pairs = json.loads(source_text)
                    original_pairs.extend(pairs)

            # 创建去重记录
            dedup_record = DedupRecord(
                input_file=input_file,
                output_file=output_file,
                deleted_pairs_file=deleted_pairs_file,
                dedup_by_answer=dedup_by_answer,
                threshold=dedup_threshold,
                min_answer_length=min_answer_length,
                status="processing",
                source_text="\n".join(source_texts),
                original_count=len(original_pairs),
                kept_count=0,
                progress=0
            )
            result = await self.dedup_records.insert_one(dedup_record.dict(by_alias=True))
            record_id = result.inserted_id

            # 执行去重
            hparams = DedupParams(
                input_file=input_file,
                output_file=output_file,
                dedup_by_answer=dedup_by_answer,
                dedup_threshold=dedup_threshold,
                min_answer_length=min_answer_length,
                deleted_pairs_file=deleted_pairs_file,
            )

            qa_deduplication = QADeduplication(
                hparams,
                progress_callback=lambda p: asyncio.create_task(
                    self.update_progress(str(record_id), p)
                )
            )
            kept_pairs, deleted_groups = qa_deduplication.process_qa_file(hparams)

            # 保存保留的问答对到数据库
            if kept_pairs:
                kept_records = []
                for qa in kept_pairs:
                    record = KeptQAPair(
                        dedup_id=record_id,
                        qa_id=qa['id'],
                        question=qa['question'],
                        answer=qa['answer']
                    ).dict(by_alias=True)
                    kept_records.append(record)

                if kept_records:
                    await self.kept_pairs.insert_many(kept_records)

            # 保存被删除的问答对到数据库
            if deleted_groups:
                deleted_records = []
                for group in deleted_groups:
                    main_pair = group[0]  # 主要的问答对
                    similar_pairs = group[1:]  # 相似的问答对
                    record = DeletedQAPair(
                        dedup_id=record_id,
                        qa_id=main_pair['id'],
                        question=main_pair['question'],
                        answer=main_pair['answer'],
                        similar_pairs=[{
                            'qa_id': pair['id'],
                            'question': pair['question'],
                            'answer': pair['answer']
                        } for pair in similar_pairs]
                    ).dict(by_alias=True)
                    deleted_records.append(record)

                if deleted_records:
                    await self.deleted_pairs.insert_many(deleted_records)

            # 更新去重记录
            await self.dedup_records.update_one(
                {"_id": record_id},
                {
                    "$set": {
                        "status": "completed",
                        "original_count": len(original_pairs),
                        "kept_count": len(kept_pairs),
                        "progress": 100
                    }
                }
            )

            return {
                "dedup_id": str(record_id),
                "output_file": output_file,
                "deleted_pairs_file": deleted_pairs_file,
                "kept_pairs": kept_pairs,
                "original_count": len(original_pairs),
                "kept_count": len(kept_pairs),
                "deleted_count": len(original_pairs) - len(kept_pairs)
            }

        except Exception as e:
            import traceback
            await self._log_error(str(e), "deduplicate_qa", traceback.format_exc())
            if record_id:
                await self.dedup_records.update_one(
                    {"_id": record_id},
                    {"$set": {"status": "failed"}}
                )
            raise Exception(f"Deduplication failed: {str(e)}")

    async def get_dedup_records(self):
        """获取最近一次的去重历史记录"""
        try:
            # 只获取最新的一条记录
            record = await self.dedup_records.find_one(
                sort=[("created_at", -1)]
            )
            
            if not record:
                return []
            
            # 获取保留的问答对
            qa_cursor = self.kept_pairs.find({"dedup_id": record["_id"]})
            kept_pairs = []
            async for qa in qa_cursor:
                kept_pairs.append({
                    "question": qa["question"],
                    "answer": qa["answer"]
                })

            # 获取被删除的问答对
            deleted_cursor = self.deleted_pairs.find({"dedup_id": record["_id"]})
            deleted_pairs = []
            async for deleted in deleted_cursor:
                deleted_pairs.append({
                    "main_pair": {
                        "question": deleted["question"],
                        "answer": deleted["answer"]
                    },
                    "similar_pairs": deleted["similar_pairs"]
                })

            return [{
                "dedup_id": str(record["_id"]),
                "input_file": record["input_file"],
                "output_file": record["output_file"],
                "deleted_pairs_file": record["deleted_pairs_file"],
                "status": record["status"],
                "source_text": record["source_text"],
                "original_count": record["original_count"],
                "kept_count": record["kept_count"],
                "kept_pairs": kept_pairs,
                "deleted_pairs": deleted_pairs,
                "created_at": record["created_at"]
            }]
        except Exception as e:
            raise Exception(f"Failed to get records: {str(e)}")