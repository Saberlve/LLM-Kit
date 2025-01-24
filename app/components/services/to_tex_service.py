from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from text_parse.to_tex import LatexConverter
from utils.hparams import HyperParams
from app.components.models.mongodb import TexConversionRecord
import os
from typing import List


class ToTexService:
    def __init__(self, db: AsyncIOMotorClient):
        self.db = db
        self.tex_records = db.llm_kit.tex_records
        self.error_logs = db.llm_kit.error_logs  # 添加错误日志集合

    async def _log_error(self, error_message: str, source: str, stack_trace: str = None):
        error_log = {
            "timestamp": datetime.utcnow(),
            "error_message": error_message,
            "source": source,
            "stack_trace": stack_trace
        }
        await self.error_logs.insert_one(error_log)

    async def convert_to_latex(
            self,
            parsed_file_path: str,
            save_path: str,
            SK: List[str],
            AK: List[str],
            parallel_num: int,
            model_name: str
    ):
        try:
            # 验证输入文件是否存在
            if not os.path.exists(parsed_file_path):
                raise FileNotFoundError(f"Input file not found: {parsed_file_path}")

            # 确保保存路径存在
            os.makedirs(save_path, exist_ok=True)

            # 1. 创建初始记录
            record = TexConversionRecord(
                input_file=parsed_file_path,
                status="processing",
                model_name=model_name,
                save_path=save_path  # 添加初始保存路径
            )
            result = await self.tex_records.insert_one(record.dict(by_alias=True))
            record_id = result.inserted_id

            try:
                # 2. 配置转换参数
                hparams = HyperParams(
                    file_path=parsed_file_path,
                    save_path=save_path,
                    SK=SK,
                    AK=AK,
                    parallel_num=parallel_num,
                    model_name=model_name
                )

                # 3. 执行转换
                converter = LatexConverter(parsed_file_path, hparams)
                tex_file_path = converter.convert_to_latex()

                if not tex_file_path or not os.path.exists(tex_file_path):
                    raise FileNotFoundError("LaTeX conversion failed: output file not created")

                # 4. 读取转换结果
                with open(tex_file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # 5. 更新记录
                await self.tex_records.update_one(
                    {"_id": record_id},
                    {
                        "$set": {
                            "status": "completed",
                            "content": content,
                            "save_path": tex_file_path
                        }
                    }
                )

                return {
                    "record_id": str(record_id),
                    "save_path": tex_file_path,
                    "content": content
                }

            except Exception as e:
                # 6. 更新失败状态
                await self.tex_records.update_one(
                    {"_id": record_id},
                    {"$set": {
                        "status": "failed",
                        "error_message": str(e)
                    }}
                )
                raise e

        except Exception as e:
            import traceback
            await self._log_error(str(e), "convert_to_latex", traceback.format_exc())
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