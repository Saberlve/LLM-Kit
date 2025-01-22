from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from generate_qas.qa_generator import QAGenerator
from utils.hparams import HyperParams
from app.components.models.mongodb import QAGeneration, QAPairDB


class QAGenerateService:
    def __init__(self, db: AsyncIOMotorClient):
        self.db = db
        self.qa_generations = db.llm_kit.qa_generations
        self.qa_pairs = db.llm_kit.qa_pairs

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
        try:
            # 读取源文本
            with open(chunks_path, 'r', encoding='utf-8') as f:
                source_text = f.read()

            # 创建生成记录
            generation = QAGeneration(
                input_file=chunks_path,
                save_path=save_path,
                model_name=model_name,
                domain=domain,
                status="processing",
                source_text=source_text  # 保存源文本
            )
            result = await self.qa_generations.insert_one(generation.dict(by_alias=True))
            generation_id = result.inserted_id

            # 生成问答对
            hparams = HyperParams(
                file_path=chunks_path,
                save_path=save_path,
                SK=SK,
                AK=AK,
                parallel_num=parallel_num,
                model_name=model_name,
                domain=domain
            )

            generator = QAGenerator(chunks_path, hparams)
            qa_pairs = generator.convert_tex_to_qas()

            # 保存问答对到数据库
            qa_records = []
            for qa in qa_pairs:
                qa_record = QAPairDB(
                    generation_id=generation_id,
                    question=qa["question"],
                    answer=qa["answer"]
                    # 不再存储source_text
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
            raise Exception(f"Generation failed: {str(e)}")

    async def get_qa_records(self):
        """获取问答对生成历史记录"""
        try:
            cursor = self.qa_generations.find().sort("created_at", -1)
            records = []
            async for record in cursor:
                # 获取该记录对应的所有问答对
                qa_cursor = self.qa_pairs.find({"generation_id": record["_id"]})
                qa_pairs = []
                async for qa in qa_cursor:
                    qa_pairs.append({
                        "question": qa["question"],
                        "answer": qa["answer"]
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