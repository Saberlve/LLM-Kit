from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from app.components.models.mongodb import TexConversionRecord
import os
from typing import List
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils.helper import generate, split_chunk_by_tokens, split_text_into_chunks
import json
import logging
from bson import ObjectId

logger = logging.getLogger(__name__)

class ToTexService:
    def __init__(self, db: AsyncIOMotorClient):
        self.db = db
        self.tex_records = db.llm_kit.tex_records
        self.parse_records = db.llm_kit.parse_records
        self.error_logs = db.llm_kit.error_logs

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

    async def get_parsed_files(self):
        """获取所有已解析的文件列表（同名文件只返回最新的）"""
        try:
            # 使用聚合管道，按文件名分组并获取每组最新的记录
            pipeline = [
                # 只查找已完成的记录
                {"$match": {"status": "completed"}},
                
                # 按文件名分组，保留最新的记录
                {"$group": {
                    "_id": "$input_file",
                    "created_at": {"$max": "$created_at"},
                    "file_type": {"$first": "$file_type"},
                    "latest_doc": {"$first": "$$ROOT"}
                }},
                
                # 按创建时间降序排序
                {"$sort": {"created_at": -1}},
                
                # 重新格式化输出
                {"$project": {
                    "_id": 0,
                    "file_id": "$latest_doc._id",
                    "filename": "$_id",
                    "created_at": 1,
                    "file_type": 1
                }}
            ]
            
            cursor = self.parse_records.aggregate(pipeline)
            files = []
            async for record in cursor:
                files.append({
                    "file_id": str(record["file_id"]),
                    "filename": record["filename"],
                    "created_at": record["created_at"],
                    "file_type": record.get("file_type", "")
                })
            
            return files
        except Exception as e:
            logger.error(f"获取解析文件列表失败: {str(e)}")
            raise Exception(f"获取解析文件列表失败: {str(e)}")

    async def get_parsed_content(self, file_id: str):
        """根据文件ID获取解析后的内容"""
        try:
            # 查找指定ID的已完成记录
            record = await self.parse_records.find_one(
                {
                    "_id": ObjectId(file_id),
                    "status": "completed"
                }
            )
            
            if not record:
                raise Exception(f"未找到ID为 {file_id} 的解析记录")
            
            if not record.get("content"):
                raise Exception(f"ID为 {file_id} 的解析内容为空")
            
            return {
                "content": record["content"],
                "filename": record["input_file"],
                "created_at": record["created_at"],
                "file_type": record["file_type"]
            }
        except Exception as e:
            logger.error(f"获取解析内容失败: {str(e)}")
            raise Exception(f"获取解析内容失败: {str(e)}")

    async def convert_to_latex(
            self,
            content: str,
            filename: str,
            save_path: str,
            SK: List[str],
            AK: List[str],
            parallel_num: int,
            model_name: str
    ):
        try:
            # 每次开始转换时，创建或更新记录，强制设置初始进度为0
            await self.tex_records.update_one(
                {"input_file": filename},
                {
                    "$set": {
                        "status": "processing",
                        "progress": 0,
                        "model_name": model_name,
                        "save_path": save_path
                    }
                },
                upsert=True  # 如果记录不存在则创建
            )

            # 验证输入
            assert len(AK) >= parallel_num, '请提供足够的AK和SK'

            # 创建保存目录
            os.makedirs(save_path, exist_ok=True)

            # 获取不带扩展名的文件名
            base_filename = filename.rsplit('.', 1)[0]

            # 检查是否已有记录，如果有，重置进度
            existing_record = await self.tex_records.find_one({"input_file": filename})
            if existing_record:
                await self.tex_records.update_one(
                    {"_id": existing_record["_id"]},
                    {"$set": {"status": "processing", "progress": 0}}
                )
            else:
                # 创建新记录
                record = TexConversionRecord(
                    input_file=filename,
                    status="processing",
                    model_name=model_name,
                    save_path=save_path,
                    progress=0  # 初始化进度为 0
                )
                result = await self.tex_records.insert_one(record.dict(by_alias=True))
                record_id = result.inserted_id

            try:
                # 切分文本
                text_chunks = split_text_into_chunks(parallel_num, content)
                total_chunks = len(text_chunks)
                processed_chunks = 0

                # 并行处理文本块
                results = []
                with ThreadPoolExecutor(max_workers=parallel_num) as executor:
                    futures = [
                        executor.submit(
                            self._process_chunk_with_api,
                            chunk,
                            AK[i % len(AK)],
                            SK[i % len(SK)],
                            model_name
                        )
                        for i, chunk in enumerate(text_chunks)
                    ]

                    for future in as_completed(futures):
                        results.extend(future.result())
                        processed_chunks += 1
                        # 计算当前进度
                        progress = int((processed_chunks / total_chunks) * 100)
                        # 更新进度信息到数据库
                        await self.tex_records.update_one(
                            {"input_file": filename},
                            {"$set": {"progress": progress}}
                        )

                # 合并所有LaTeX内容
                combined_tex = '\n'.join(results)

                # 准备保存的数据格式
                data_to_save = [
                    {"id": i + 1, "chunk": result}
                    for i, result in enumerate(results)
                ]

                # 生成简化的保存路径
                tex_file_path = os.path.join(
                    save_path,
                    'tex_files',
                    f'{base_filename}.json'  # 修改为.json后缀
                )
                os.makedirs(os.path.dirname(tex_file_path), exist_ok=True)

                # 保存为JSON格式
                with open(tex_file_path, 'w', encoding='utf-8') as json_file:
                    json.dump(data_to_save, json_file, ensure_ascii=False, indent=4)

                # 完成时设置状态和进度
                await self.tex_records.update_one(
                    {"input_file": filename},
                    {
                        "$set": {
                            "status": "completed",
                            "content": data_to_save,
                            "save_path": tex_file_path,
                            "progress": 100
                        }
                    }
                )

                # 更新上传文件的状态为completed
                await self.db.llm_kit.uploaded_files.update_one(
                    {"filename": filename},
                    {"$set": {"status": "completed"}}
                )

                # 同时更新二进制文件集合中的状态（如果存在）
                await self.db.llm_kit.uploaded_binary_files.update_one(
                    {"filename": filename},
                    {"$set": {"status": "completed"}}
                )

                # 添加一条新记录，使用简化的文件名
                saved_file_record = {
                    "input_file": os.path.basename(tex_file_path),
                    "original_file": filename,
                    "status": "completed",
                    "content": data_to_save,  # 使用JSON格式的数据
                    "created_at": datetime.now(timezone.utc),
                    "save_path": tex_file_path,
                    "model_name": model_name
                }
                await self.tex_records.insert_one(saved_file_record)

                return {
                    "filename": os.path.basename(tex_file_path),
                    "save_path": tex_file_path,
                    "content": data_to_save
                }

            except Exception as e:
                # 发生错误时保持当前进度，只更新状态
                await self.tex_records.update_one(
                    {"input_file": filename},
                    {"$set": {"status": "failed", "error_message": str(e)}}
                )

                # 更新上传文件的状态为failed
                await self.db.llm_kit.uploaded_files.update_one(
                    {"filename": filename},
                    {"$set": {"status": "failed"}}
                )

                # 同时更新二进制文件的状态（如果存在）
                await self.db.llm_kit.uploaded_binary_files.update_one(
                    {"filename": filename},
                    {"$set": {"status": "failed"}}
                )

                raise e

        except Exception as e:
            import traceback
            await self._log_error(str(e), "convert_to_latex", traceback.format_exc())
            raise Exception(f"转换失败: {str(e)}")

    async def get_tex_records(self):
        """获取最近一次的LaTeX转换历史记录"""
        try:
            # 只获取最新的一条记录
            record = await self.tex_records.find_one(
                sort=[("created_at", -1)]
            )
            
            if not record:
                return []
            
            return [{
                "record_id": str(record["_id"]),
                "input_file": record["input_file"],
                "status": record["status"],
                "save_path": record.get("save_path"),
                "content": record.get("content", ""),
                "created_at": record["created_at"]
            }]
        except Exception as e:
            raise Exception(f"Failed to get records: {str(e)}")