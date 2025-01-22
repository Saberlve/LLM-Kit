from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from text_parse.to_tex import LatexConverter
from utils.hparams import HyperParams
from app.components.models.mongodb import TexConversionRecord


class ToTexService:
    def __init__(self, db: AsyncIOMotorClient):
        self.db = db
        self.tex_records = db.llm_kit.tex_records

    async def convert_to_latex(
            self,
            parsed_file_path: str,
            save_path: str,
            SK: list,
            AK: list,
            parallel_num: int,
            model_name: str
    ):
        try:
            # 创建记录
            record = TexConversionRecord(
                input_file=parsed_file_path,
                file_type="tex",
                status="processing"
            )

            result = await self.tex_records.insert_one(record.dict(by_alias=True))
            record_id = result.inserted_id

            # 转换为LaTeX
            hparams = HyperParams(
                file_path=parsed_file_path,
                save_path=save_path,
                SK=SK,
                AK=AK,
                parallel_num=parallel_num,
                model_name=model_name
            )

            converter = LatexConverter(parsed_file_path, hparams)
            save_path = converter.convert_to_latex()

            # 读取转换结果
            with open(save_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 更新记录，包含保存路径和内容
            await self.tex_records.update_one(
                {"_id": record_id},
                {
                    "$set": {
                        "status": "completed",
                        "content": content,
                        "save_path": save_path  # 添加保存路径
                    }
                }
            )

            return {
                "record_id": str(record_id),
                "save_path": save_path,
                "content": content  # 返回转换后的内容
            }

        except Exception as e:
            raise Exception(f"Conversion failed: {str(e)}")

    async def get_tex_records(self):
        """获取LaTeX转换历史记录"""
        try:
            cursor = self.tex_records.find().sort("created_at", -1)
            records = []
            async for record in cursor:
                records.append({
                    "record_id": str(record["_id"]),
                    "input_file": record["input_file"],
                    "status": record["status"],
                    "save_path": record.get("save_path"),
                    "content": record.get("content", ""),
                })
            return records
        except Exception as e:
            raise Exception(f"Failed to get records: {str(e)}")