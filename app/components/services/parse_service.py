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

import logging

logger = logging.getLogger(__name__)


class ParseService:

    def __init__(self, db: AsyncIOMotorClient):

        self.db = db

        self.parse_records = db.llm_kit.parse_records

        self.error_logs = db.llm_kit.error_logs  # Add error log collection

        self.last_progress_update = {}  # Used to store the last update time for each task

    async def _log_error(self, error_message: str, source: str, stack_trace: str = None):

        """Log errors to the database"""

        error_log = {

            "timestamp": datetime.utcnow(),

            "error_message": error_message,

            "source": source,

            "stack_trace": stack_trace

        }

        await self.error_logs.insert_one(error_log)

    async def parse_file(self, file_path: str, save_path: str, SK: List[str], AK: List[str], parallel_num: int = 4):

        try:

            # Get file type

            file_type = os.path.splitext(file_path)[1].lower().replace('.', '')

            # Pass all required parameters according to HyperParams requirements

            hparams = HyperParams(

                SK=SK,

                AK=AK,

                parallel_num=parallel_num,

                file_path=file_path,

                save_path=save_path

            )

            # Read and parse the file

            parsed_file_path = parse.parse(hparams)

            # Read the parsed file content

            with open(parsed_file_path, 'r', encoding='utf-8') as f:

                content = f.read()

            # Include all required fields when creating the record

            parse_record = ParseRecord(

                input_file=os.path.basename(file_path),  # Only store the filename

                content=content,  # Store the parsed file content

                parsed_file_path=parsed_file_path,

                status="completed",  # Set directly to completed

                file_type=file_type,

                save_path=save_path

            )

            if hasattr(parse_record, "model_dump"):
                record_dict = parse_record.model_dump(by_alias=True)
            else:
                record_dict = parse_record.dict(by_alias=True)

            result = await self.parse_records.insert_one(record_dict)

            return {

                "record_id": str(result.inserted_id),

                "content": content

            }

        except Exception as e:

            import traceback

            await self._log_error(str(e), "parse_file", traceback.format_exc())

            raise Exception(f"Parse failed: {str(e)}")

   

    async def parse_content(self, content: str, filename: str, save_path: str, SK: List[str], AK: List[str],
                            parallel_num: int = 4, record_id: str = None):
        """Parse file content"""
        try:
                            # Get and validate file type
            file_type = filename.split('.')[-1].lower()
            base_filename = filename.rsplit('.', 1)[0]

            # Check if there is an existing record, if so, reset the progress
            if record_id:
                await self.parse_records.update_one(
                    {"_id": ObjectId(record_id)},
                    {
                        "$set": {
                            "status": "processing",
                            "progress": 0,
                            "file_type": file_type,
                            "save_path": save_path
                        }
                    }
                )

            supported_types = ['tex', 'txt', 'json', 'pdf', 'png', 'jpg', 'jpeg']
            if not file_type:
                raise ValueError("File type is missing")
            if file_type not in supported_types:
                raise ValueError(
                    f"Unsupported file type: {file_type}. Supported types are: {', '.join(supported_types)}")

            # 判断是文本文件还是二进制文件
            is_binary = file_type in ['pdf', 'png', 'jpg', 'jpeg']
            temp_file_path = ""
            
            # Create temporary file
            if is_binary:
                # 对于二进制文件，需要以二进制模式写入
                import base64
                try:
                    with tempfile.NamedTemporaryFile(mode='wb', suffix=f'.{file_type}', delete=False) as temp_file:
                        # 尝试解码base64内容
                        if isinstance(content, str) and content.startswith(('data:', 'data:image', 'data:application')):
                            # 处理可能的data URI格式
                            header, encoded = content.split(",", 1)
                            content_bytes = base64.b64decode(encoded)
                        else:
                            # 如果不是data URI，直接解码
                            content_bytes = base64.b64decode(content)
                        temp_file.write(content_bytes)
                        temp_file_path = temp_file.name
                except Exception as e:
                    logger.error(f"Base64解码失败: {str(e)}")
                    with tempfile.NamedTemporaryFile(mode='wb', suffix=f'.{file_type}', delete=False) as temp_file:
                        if isinstance(content, bytes):
                            # 已经是二进制内容，直接写入
                            temp_file.write(content)
                        else:
                            # 作为文本写入（可能不是正确的格式）
                            temp_file.write(content.encode('utf-8'))
                        temp_file_path = temp_file.name
            else:
                # 对于文本文件，使用原来的方式处理
                with tempfile.NamedTemporaryFile(mode='w', suffix=f'.{file_type}', delete=False,
                                                encoding='utf-8') as temp_file:
                    temp_file.write(content)
                    temp_file_path = temp_file.name

                # Modify progress update logic
                async def update_progress(progress: int):
                    """Asynchronously update progress (optimized throttling control)"""
                    if record_id:
                        try:
                            current_time = time.time()
                            last_update = self.last_progress_update.get(record_id, 0)
                            content_length = len(content)

                            # Progress handling for small files (less than 1KB)
                            if content_length < 1024:
                                # Predefined progress points to ensure smooth transition
                                progress_steps = [
                                    10,  # Initialization
                                    20,  # File preparation
                                    30, 40, 50, 60, 70,  # Processing stage
                                    90,  # Save preparation
                                    100  # Completion
                                ]

                                # Map original progress to predefined progress points
                                step_index = min(len(progress_steps)-1, int(progress/12))
                                adjusted_progress = progress_steps[step_index]

                                # Update every 0.1 seconds
                                if current_time - last_update >= 0.1:
                                    await self.parse_records.update_one(
                                        {"_id": ObjectId(record_id)},
                                        {"$set": {"progress": adjusted_progress}}
                                    )
                                    self.last_progress_update[record_id] = current_time
                            else:
                                # Progress handling for large files
                                # Map original progress (0-100) to processing stage (20-80)
                                adjusted_progress = int(20 + (progress * 0.6))

                                # Update every 0.5 seconds
                                if current_time - last_update >= 0.5:
                                    await self.parse_records.update_one(
                                        {"_id": ObjectId(record_id)},
                                        {"$set": {"progress": adjusted_progress}}
                                    )
                                    self.last_progress_update[record_id] = current_time
                        except Exception as e:
                            logger.error(f"Progress update failed: {str(e)}")

                try:
                                # Immediately set initial progress and update status to parsing
                    await update_progress(0)
                    await self.db.llm_kit.uploaded_files.update_one(
                        {"filename": base_filename + "." + file_type},
                        {"$set": {"status": "pending"}}
                    )
                    await self.db.llm_kit.uploaded_binary_files.update_one(
                        {"filename": base_filename + "." + file_type},
                        {"$set": {"status": "pending"}}
                    )

                    parsed_file_path = ""
                    content = ""

                    # 根据文件类型选择不同的处理方法
                    if file_type in ['pdf', 'png', 'jpg', 'jpeg']:
                        # 处理PDF和图像文件
                        from app.components.services.ocr_service import OCRService
                        ocr_service = OCRService(self.db)
                        
                        # 读取文件内容
                        with open(temp_file_path, 'rb') as f:
                            file_content = f.read()
                        
                        # 根据文件类型调用OCR处理
                        if file_type == 'pdf':
                            content = await ocr_service.process_pdf(file_content, filename, record_id)
                        else:  # 图像文件
                            content = await ocr_service.process_image(file_content, filename, record_id)
                        
                        # 创建解析后的输出文件
                        os.makedirs(save_path, exist_ok=True)
                        parsed_file_path = os.path.join(save_path, f"{base_filename}_parsed.txt")
                        with open(parsed_file_path, 'w', encoding='utf-8') as f:
                            f.write(content)
                    else:
                        # 对于文本文件使用现有的解析逻辑
                        hparams = HyperParams(
                            SK=SK,
                            AK=AK,
                            parallel_num=parallel_num,
                            file_path=temp_file_path,
                            save_path=save_path
                        )

                        # Execute parsing, pass in progress callback
                        parsed_file_path = parse.parse(
                            hparams,
                            progress_callback=lambda p: asyncio.create_task(update_progress(p))
                        )

                        # Read the parsed file content
                        with open(parsed_file_path, 'r', encoding='utf-8') as f:
                            content = f.read()

                        # Create a new simplified filename
                        new_filename = f"{base_filename}_parsed.txt"
                        new_file_path = os.path.join(os.path.dirname(parsed_file_path), new_filename)

                        # Rename the file
                        if os.path.exists(parsed_file_path):
                            os.rename(parsed_file_path, new_file_path)
                            parsed_file_path = new_file_path

                        # Ensure final progress is set
                        await update_progress(100)

                        # Update original file status to finish
                        await self.db.llm_kit.uploaded_files.update_one(
                            {"filename": base_filename + "." + file_type},
                            {"$set": {"status": "finish"}}
                        )

                        # Also update the status in the binary file collection (if it exists)
                        await self.db.llm_kit.uploaded_binary_files.update_one(
                            {"filename": base_filename + "." + file_type},
                            {"$set": {"status": "finish"}}
                        )

                        # Set status and progress when completed
                        if record_id:
                            await self.parse_records.update_one(
                                {"_id": ObjectId(record_id)},
                                {
                                    "$set": {
                                        "status": "completed",
                                        "progress": 100,
                                        "content": content,
                                        "parsed_file_path": parsed_file_path
                                    }
                                }
                            )

                        return {
                            "content": content,
                            "parsed_file_path": parsed_file_path
                        }

                except Exception as e:
                    # When an error occurs, only update the status, maintain the current progress
                    if record_id:
                        await self.parse_records.update_one(
                            {"_id": ObjectId(record_id)},
                            {
                                "$set": {
                                    "status": "failed",
                                    "error_message": str(e)
                                }
                            }
                        )
                    raise e

        except Exception as e:
            import traceback
            await self._log_error(str(e), "parse_content", traceback.format_exc())
            raise Exception(f"Parse content failed: {str(e)}")
