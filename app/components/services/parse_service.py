from datetime import datetime

from motor.motor_asyncio import AsyncIOMotorClient

from text_parse import parse

from utils.hparams import HyperParams

from app.components.models.mongodb import ParseRecord

import os

from typing import List

import tempfile

from bson import ObjectId

import asyncio

import time


class ParseService:

    def __init__(self, db: AsyncIOMotorClient):

        self.db = db

        self.parse_records = db.llm_kit.parse_records

        self.error_logs = db.llm_kit.error_logs  # 添加错误日志集合

        self.last_progress_update = {}  # 用于存储每个任务的最后更新时间

    async def _log_error(self, error_message: str, source: str, stack_trace: str = None):

        """记录错误到数据库"""

        error_log = {

            "timestamp": datetime.utcnow(),

            "error_message": error_message,

            "source": source,

            "stack_trace": stack_trace

        }

        await self.error_logs.insert_one(error_log)

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

                input_file=os.path.basename(file_path),  # 只存储文件名

                content=content,  # 存储解析后的文件内容

                parsed_file_path=parsed_file_path,

                status="completed",  # 直接设置为completed

                file_type=file_type,

                save_path=save_path

            )

            result = await self.parse_records.insert_one(

                parse_record.model_dump(by_alias=True)

            )

            return {

                "record_id": str(result.inserted_id),

                "content": content

            }

        except Exception as e:

            import traceback

            await self._log_error(str(e), "parse_file", traceback.format_exc())

            raise Exception(f"Parse failed: {str(e)}")

    async def get_parse_records(self):

        """获取最近一次的解析历史记录"""

        try:

            # 只获取最新的一条记录

            record = await self.parse_records.find_one(

                sort=[("created_at", -1)]

            )

            if not record:
                return []

            return [{

                "record_id": str(record["_id"]),

                "input_file": record["input_file"],

                "parsed_file_path": record.get("parsed_file_path", ""),

                "status": record["status"],

                "file_type": record["file_type"],

                "save_path": record["save_path"],

                "content": record.get("content", ""),

                "progress": record.get("progress", 0),  # 添加进度信息

                "task_type": record.get("task_type", "parse"),  # 添加任务类型

                "created_at": record["created_at"]

            }]

        except Exception as e:

            import traceback

            await self._log_error(str(e), "get_parse_records", traceback.format_exc())

            raise Exception(f"Failed to get records: {str(e)}")

    async def parse_content(self, content: str, filename: str, save_path: str, SK: List[str], AK: List[str],
                          parallel_num: int = 4, record_id: str = None):
        """解析文件内容"""
        try:
            # 获取文件类型并验证
            file_type = filename.split('.')[-1].lower()
            base_filename = filename.rsplit('.', 1)[0]  # 获取不带扩展名的文件名
            print(f"Processing file type: {file_type}")
            
            supported_types = ['tex', 'txt', 'json', 'pdf']
            if not file_type:
                raise ValueError("File type is missing")
            if file_type not in supported_types:
                raise ValueError(
                    f"Unsupported file type: {file_type}. Supported types are: {', '.join(supported_types)}")

            # 创建临时文件
            with tempfile.NamedTemporaryFile(mode='w', suffix=f'.{file_type}', delete=False,
                                           encoding='utf-8') as temp_file:
                temp_file.write(content)
                temp_file_path = temp_file.name

            # 修改进度更新逻辑
            async def update_progress(progress: int):
                """异步更新进度（优化的节流控制）"""
                if record_id:
                    try:
                        current_time = time.time()
                        last_update = self.last_progress_update.get(record_id, 0)
                        
                        # 对于小文件，减少进度更新频率
                        content_length = len(content)
                        if content_length < 1024:  # 小于1KB的文件
                            update_interval = 0.1  # 降低更新频率
                            progress_steps = [0, 50, 100]  # 只在关键节点更新进度
                        else:
                            update_interval = 0.5
                            progress_steps = range(0, 101, 10)  # 正常每10%更新一次
                        
                        # 只在指定的进度点和时间间隔更新
                        if (progress in progress_steps and 
                            current_time - last_update >= update_interval):
                            actual_progress = min(20 + int(progress * 0.8), 100)
                            await self.parse_records.update_one(
                                {"_id": ObjectId(record_id)},
                                {"$set": {"progress": actual_progress}}
                            )
                            self.last_progress_update[record_id] = current_time
                    except Exception as e:
                        print(f"Progress update failed: {str(e)}")
                        # 进度更新失败不影响主流程

            try:
                # 使用现有的解析逻辑
                hparams = HyperParams(
                    SK=SK,
                    AK=AK,
                    parallel_num=parallel_num,
                    file_path=temp_file_path,
                    save_path=save_path
                )

                # 立即设置初始进度并更新状态为解析中
                await update_progress(0)
                await self.db.llm_kit.uploaded_files.update_one(
                    {"filename": base_filename + "." + file_type},
                    {"$set": {"status": "pending"}}
                )
                await self.db.llm_kit.uploaded_binary_files.update_one(
                    {"filename": base_filename + "." + file_type},
                    {"$set": {"status": "pending"}}
                )

                # 执行解析，传入进度回调
                parsed_file_path = parse.parse(
                    hparams,
                    progress_callback=lambda p: asyncio.create_task(update_progress(p))
                )

                # 读取解析后的文件内容
                with open(parsed_file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # 创建新的简化文件名
                new_filename = f"{base_filename}_parsed.txt"
                new_file_path = os.path.join(os.path.dirname(parsed_file_path), new_filename)
                
                # 重命名文件
                if os.path.exists(parsed_file_path):
                    os.rename(parsed_file_path, new_file_path)
                    parsed_file_path = new_file_path

                # 确保设置最终进度
                await update_progress(100)

                # 更新原始文件状态为finish
                await self.db.llm_kit.uploaded_files.update_one(
                    {"filename": base_filename + "." + file_type},
                    {"$set": {"status": "finish"}}
                )

                # 同时更新二进制文件集合中的状态（如果存在）
                await self.db.llm_kit.uploaded_binary_files.update_one(
                    {"filename": base_filename + "." + file_type},
                    {"$set": {"status": "finish"}}
                )

                return {
                    "content": content,
                    "parsed_file_path": parsed_file_path
                }

            finally:
                # 清理临时文件
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
                # 清理进度更新记录
                if record_id in self.last_progress_update:
                    del self.last_progress_update[record_id]

        except Exception as e:
            # 发生错误时更新状态为failed
            await self.db.llm_kit.uploaded_files.update_one(
                {"filename": base_filename + "." + file_type},
                {"$set": {"status": "failed"}}
            )
            await self.db.llm_kit.uploaded_binary_files.update_one(
                {"filename": base_filename + "." + file_type},
                {"$set": {"status": "failed"}}
            )
            
            import traceback
            await self._log_error(str(e), "parse_content", traceback.format_exc())
            raise Exception(f"Parse content failed: {str(e)}")
