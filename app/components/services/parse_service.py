from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from text_parse import parse
from utils.hparams import HyperParams
from app.components.models.mongodb import ParseRecord
import os
from typing import List


class ParseService:
    def __init__(self, db: AsyncIOMotorClient):
        self.db = db
        self.parse_records = db.llm_kit.parse_records

    async def parse_file(self, file_path: str, save_path: str, SK: List[str], AK: List[str], parallel_num: int = 4):
        try:
            # 获取文件类型
            file_type = os.path.splitext(file_path)[1].lower().replace('.', '')

            # 按照 HyperParams 的要求传入所有必需参数
            hparams = HyperParams(
                SK=SK,
                AK=AK,
                parallel_num=parallel_num,
                file_path=file_path,
                save_path=save_path
            )

            # 读取并解析文件
            parsed_file_path = parse.parse(hparams)

            # 读取解析后的文件内容
            with open(parsed_file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 创建记录时包含所有必需字段
            parse_record = ParseRecord(
                input_file=file_path,
                content=content,  # 存储解析后的文件内容
                parsed_file_path=parsed_file_path,  # 使用实际的解析文件路径
                status="processing",
                file_type=file_type,
                save_path=save_path
            )

            result = await self.parse_records.insert_one(
                parse_record.dict(by_alias=True)
            )

            return {
                "record_id": str(result.inserted_id),
                "content": content
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
                    "content": record.get("content", "")[:1200] + "..." if record.get("content", "") else "",
                })
            return records
        except Exception as e:
            raise Exception(f"Failed to get records: {str(e)}")