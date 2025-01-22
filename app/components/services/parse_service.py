from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from text_parse import parse
from utils.hparams import HyperParams
from app.components.models.mongodb import ParseRecord
import os


class ParseService:
    def __init__(self, db: AsyncIOMotorClient):
        self.db = db
        self.parse_records = db.llm_kit.parse_records

    async def parse_file(self, file_path: str, save_path: str):
        try:
            # 创建记录
            record = ParseRecord(
                input_file=file_path,
                file_type=file_path.split('.')[-1].lower(),
                save_path=save_path,
                status="processing",
            )

            result = await self.parse_records.insert_one(record.dict(by_alias=True))
            record_id = result.inserted_id

            # 解析文件
            hparams = HyperParams(
                file_path=file_path,
                save_path=save_path
            )

            parsed_file_path = parse(hparams)

            # 读取解析后的内容
            with open(parsed_file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 更新记录
            await self.parse_records.update_one(
                {"_id": record_id},
                {
                    "$set": {
                        "status": "completed",
                        "parsed_file_path": parsed_file_path,
                        "content": content
                    }
                }
            )

            return {
                "record_id": str(record_id),
                "content": content[:200] + "..." if len(content) > 200 else content
            }

        except Exception as e:
            raise Exception(f"Parse failed: {str(e)}")

    async def get_parse_records(self):
        """获取解析历史记录"""
        try:
            cursor = self.parse_records.find().sort("created_at", -1)
            records = []
            async for record in cursor:
                records.append({
                    "record_id": str(record["_id"]),
                    "input_file": record["input_file"],
                    "status": record["status"],
                    "content": record.get("content", "")[:200] + "..." if record.get("content", "") else "",
                })
            return records
        except Exception as e:
            raise Exception(f"Failed to get records: {str(e)}")