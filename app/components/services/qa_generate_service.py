from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from generate_qas.qa_generator import QAGenerator
from utils.hparams import HyperParams
from app.components.models.mongodb import QAGeneration, QAPairDB, PyObjectId
import json
from bson import ObjectId


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
            qa_pairs_path = generator.convert_tex_to_qas()  # 这里返回的是文件路径

            if not qa_pairs_path:
                raise Exception("QA pairs path is empty or None")
                
            try:
                with open(qa_pairs_path, 'r', encoding='utf-8') as f:
                    qa_pairs = json.load(f)
            except Exception as e:
                raise Exception(f"Failed to load generated QA pairs from {qa_pairs_path}: {str(e)}")

            if not qa_pairs:
                raise Exception("No QA pairs generated")

            # 保存问答对到数据库
            qa_records = []
            for qa in qa_pairs:
                if not isinstance(qa, dict) or "question" not in qa or "answer" not in qa:
                    raise Exception(f"Invalid QA pair format: {qa}")
                
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