from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from quality_control.quality_control import QAQualityGenerator
from utils.hparams import HyperParams
from app.components.models.mongodb import QAQualityRecord, QualityControlGeneration
from typing import List


class QualityService:
    def __init__(self, db: AsyncIOMotorClient):
        self.db = db
        self.quality_generations = db.llm_kit.quality_generations
        self.quality_records = db.llm_kit.quality_records

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
            max_attempts: int
    ):
        try:
            # 读取源文本
            with open(qa_path, 'r', encoding='utf-8') as f:
                source_text = f.read()

            # 创建生成记录
            generation = QualityControlGeneration(
                input_file=qa_path,
                save_path=save_path,
                model_name=model_name,
                status="processing",
                source_text=source_text  # 保存源文本
            )
            result = await self.quality_generations.insert_one(generation.dict(by_alias=True))
            generation_id = result.inserted_id

            # 生成高质量问答对
            hparams = HyperParams(
                file_path=qa_path,
                save_path=save_path,
                SK=SK,
                AK=AK,
                parallel_num=parallel_num,
                model_name=model_name,
                similarity_rate=similarity_rate,
                coverage_rate=coverage_rate,
                max_attempts=max_attempts
            )

            generator = QAQualityGenerator(qa_path, hparams)
            qa_pairs = generator.iterate_optim_qa()

            # 保存到数据库
            quality_records = []
            for qa in qa_pairs:
                record = QAQualityRecord(
                    generation_id=generation_id,
                    question=qa['question'],
                    answer=qa['answer'],
                    similarity_score=qa.get('ratio', 0.0),
                    is_explicit=True,
                    is_domain_relative=True,
                    coverage_rate=coverage_rate,
                    status='passed'
                )
                quality_records.append(record.dict(by_alias=True))

            if quality_records:
                await self.quality_records.insert_many(quality_records)

            # 更新状态
            await self.quality_generations.update_one(
                {"_id": generation_id},
                {"$set": {"status": "completed"}}
            )

            return {
                "generation_id": str(generation_id),
                "qa_pairs": qa_pairs,
                "source_text": source_text
            }

        except Exception as e:
            raise Exception(f"Quality control failed: {str(e)}")

    async def get_quality_records(self):
        """获取质量控制历史记录"""
        try:
            cursor = self.quality_generations.find().sort("created_at", -1)
            records = []
            async for record in cursor:
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

                records.append({
                    "generation_id": str(record["_id"]),
                    "input_file": record["input_file"],
                    "status": record["status"],
                    "source_text": record["source_text"],  # 添加源文本
                    "qa_pairs": qa_pairs
                })
            return records
        except Exception as e:
            raise Exception(f"Failed to get records: {str(e)}")