from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from text_parse.to_tex import LatexConverter
from utils.hparams import HyperParams
from app.components.models.mongodb import TexConversionRecord
import os
from typing import List
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from utils.helper import generate, split_chunk_by_tokens, split_text_into_chunks
import json


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

    def _process_chunk_with_api(self, chunk: str, ak: str, sk: str, model_name: str, max_tokens: int = 650) -> list:
        """处理单个文本块"""
        sub_chunks = split_chunk_by_tokens(chunk, max_tokens)
        results = []

        for sub_chunk in sub_chunks:
            for attempt in range(3):  # 尝试3次
                try:
                    tex_text = generate(sub_chunk, model_name, 'ToTex', ak, sk)
                    results.append(self._clean_result(tex_text))
                    break
                except Exception as e:
                    if attempt == 2:  # 最后一次尝试失败
                        raise Exception(f"处理文本块失败: {str(e)}")
        return results

    def _clean_result(self, text: str) -> str:
        """清理API返回的结果"""
        start_index = max(text.find('```') + 3 if '```' in text else -1, 0)
        end_index = text.rfind('```')
        return text[start_index:end_index].strip()

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
            # 验证输入
            if not os.path.exists(parsed_file_path):
                raise FileNotFoundError(f"输入文件未找到: {parsed_file_path}")
            
            assert len(AK) == len(SK), 'AK和SK数量必须相同'
            assert len(AK) >= parallel_num, '请提供足够的AK和SK'

            # 创建保存目录
            os.makedirs(save_path, exist_ok=True)

            # 创建初始记录
            record = TexConversionRecord(
                input_file=parsed_file_path,
                status="processing",
                model_name=model_name,
                save_path=save_path
            )
            result = await self.tex_records.insert_one(record.dict(by_alias=True))
            record_id = result.inserted_id

            try:
                # 读取文件内容
                with open(parsed_file_path, "r", encoding="utf-8") as f:
                    text = f.read()

                # 生成保存路径
                file_name = os.path.basename(parsed_file_path)
                tex_file_path = os.path.join(
                    save_path, 'tex_files', file_name.split('.')[0] + '.json'
                )
                os.makedirs(os.path.dirname(tex_file_path), exist_ok=True)

                # 切分文本
                text_chunks = split_text_into_chunks(parallel_num, text)

                # 并行处理文本块
                results = []
                with ThreadPoolExecutor(max_workers=parallel_num) as executor:
                    futures = [
                        executor.submit(
                            self._process_chunk_with_api,
                            chunk,
                            AK[i],
                            SK[i],
                            model_name
                        )
                        for i, chunk in enumerate(text_chunks)
                    ]

                    for future in as_completed(futures):
                        results.extend(future.result())

                # 准备保存数据
                data_to_save = [
                    {"id": i + 1, "chunk": result}
                    for i, result in enumerate(results)
                ]

                # 保存结果
                with open(tex_file_path, 'w', encoding='utf-8') as json_file:
                    json.dump(data_to_save, json_file, ensure_ascii=False, indent=4)

                # 更新记录状态
                await self.tex_records.update_one(
                    {"_id": record_id},
                    {
                        "$set": {
                            "status": "completed",
                            "content": json.dumps(data_to_save),
                            "save_path": tex_file_path
                        }
                    }
                )

                return {
                    "record_id": str(record_id),
                    "save_path": tex_file_path,
                    "content": data_to_save
                }

            except Exception as e:
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
            raise Exception(f"转换失败: {str(e)}")

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