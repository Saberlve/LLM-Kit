from deduplication.qa_deduplication import QADeduplication
from utils.hparams import DedupParams
from motor.motor_asyncio import AsyncIOMotorClient
from app.components.models.mongodb import DedupRecord, KeptQAPair
import json
from typing import List
from datetime import datetime


class QADedupService:
    def __init__(self, db: AsyncIOMotorClient):
        self.db = db
        self.dedup_records = db.llm_kit.dedup_records
        self.kept_pairs = db.llm_kit.kept_pairs
        self.error_logs = db.llm_kit.error_logs

    async def _log_error(self, error_message: str, source: str, stack_trace: str = None):
        error_log = {
            "timestamp": datetime.utcnow(),
            "error_message": error_message,
            "source": source,
            "stack_trace": stack_trace
        }
        await self.error_logs.insert_one(error_log)

    async def deduplicate_qa(
            self,
            input_file: List[str],
            output_file: str,
            dedup_by_answer: bool,
            dedup_threshold: float,
            min_answer_length: int = 10,
            deleted_pairs_file: str = "deleted.json",
    ):
        try:
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
                dedup_by_answer=dedup_by_answer,
                threshold=dedup_threshold,
                min_answer_length=min_answer_length,
                deleted_pairs_file=deleted_pairs_file,
                status="processing",
                source_text="\n".join(source_texts),
                original_count=len(original_pairs),
                kept_count=0
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

            qa_deduplication = QADeduplication(hparams)
            kept_pairs = qa_deduplication.process_qa_file(hparams)

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

            # 更新去重记录
            await self.dedup_records.update_one(
                {"_id": record_id},
                {
                    "$set": {
                        "status": "completed",
                        "original_count": len(original_pairs),
                        "kept_count": len(kept_pairs)
                    }
                }
            )

            return {
                "dedup_id": str(record_id),
                "kept_pairs": kept_pairs,
                "original_count": len(original_pairs),
                "kept_count": len(kept_pairs),
                "deleted_count": len(original_pairs) - len(kept_pairs)
            }

        except Exception as e:
            import traceback
            await self._log_error(str(e), "deduplicate_qa", traceback.format_exc())
            raise Exception(f"Deduplication failed: {str(e)}")

    async def get_dedup_records(self):
        """获取去重历史记录"""
        try:
            cursor = self.dedup_records.find().sort("created_at", -1)
            records = []
            async for record in cursor:
                qa_cursor = self.kept_pairs.find({"dedup_id": record["_id"]})
                kept_pairs = []
                async for qa in qa_cursor:
                    kept_pairs.append({
                        "question": qa["question"],
                        "answer": qa["answer"]
                    })

                records.append({
                    "dedup_id": str(record["_id"]),
                    "input_file": record["input_file"],
                    "status": record["status"],
                    "source_text": record["source_text"],
                    "original_count": record["original_count"],
                    "kept_count": record["kept_count"],
                    "kept_pairs": kept_pairs
                })
            return records
        except Exception as e:
            raise Exception(f"Failed to get records: {str(e)}")