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
import asyncio

logger = logging.getLogger(__name__)

class ToTexService:
    def __init__(self, db: AsyncIOMotorClient):
        self.db = db
        self.tex_records = db.llm_kit.tex_records
        self.parse_records = db.llm_kit.parse_records
        self.error_logs = db.llm_kit.error_logs

    async def _log_error(self, error_message: str, source: str, stack_trace: str = None):
        """Log error to database"""
        error_log = {
            "timestamp": datetime.utcnow(),
            "error_message": error_message,
            "source": source,
            "stack_trace": stack_trace
        }
        await self.error_logs.insert_one(error_log)

    def _process_chunk_with_api(self, chunk: str, ak: str, sk: str, model_name: str, max_tokens: int = 650) -> list:
        """Synchronously process a single text chunk"""
        sub_chunks = split_chunk_by_tokens(chunk, max_tokens)
        results = []

        for sub_chunk in sub_chunks:
            for attempt in range(3):
                try:
                    # Directly call the synchronous generate function
                    tex_text = generate(sub_chunk, model_name, 'ToTex', ak, sk)
                    results.append(self._clean_result(tex_text))
                    break
                except Exception as e:
                    if attempt == 2:
                        raise Exception(f"Failed to process text chunk: {str(e)}")
        return results

    def _clean_result(self, text: str) -> str:
        """Clean up API response result"""
        start_index = max(text.find('```') + 3 if '```' in text else -1, 0)
        end_index = text.rfind('```')
        return text[start_index:end_index].strip()

    async def get_parsed_files(self):
        """Get a list of all parsed files (only returns the latest for files with the same name)"""
        try:
            # Use aggregation pipeline to group by filename and get the latest record for each group
            pipeline = [
                # Only look for completed records
                {"$match": {"status": "completed"}},

                # Group by filename, keep the latest record
                {"$group": {
                    "_id": "$input_file",
                    "created_at": {"$max": "$created_at"},
                    "file_type": {"$first": "$file_type"},
                    "latest_doc": {"$first": "$$ROOT"}
                }},

                # Sort by creation time in descending order
                {"$sort": {"created_at": -1}},

                # Reformat output
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
            logger.error(f"Failed to retrieve parsed file list: {str(e)}")
            raise Exception(f"Failed to retrieve parsed file list: {str(e)}")

    async def get_parsed_content(self, file_id: str):
        """Get parsed content based on file ID"""
        try:
            # Find completed record with the specified ID
            record = await self.parse_records.find_one(
                {
                    "_id": ObjectId(file_id),
                    "status": "completed"
                }
            )

            if not record:
                raise Exception(f"Parse record with ID {file_id} not found")

            if not record.get("content"):
                raise Exception(f"Parse content for ID {file_id} is empty")

            return {
                "content": record["content"],
                "filename": record["input_file"],
                "created_at": record["created_at"],
                "file_type": record["file_type"]
            }
        except Exception as e:
            logger.error(f"Failed to retrieve parsed content: {str(e)}")
            raise Exception(f"Failed to retrieve parsed content: {str(e)}")

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
        # Use context manager to create thread pool
        with ThreadPoolExecutor(max_workers=min(10, parallel_num)) as executor:
            try:
                # Initialize progress to 0
                await self.tex_records.update_one(
                    {"input_file": filename},
                    {"$set": {
                        "status": "processing",
                        "progress": 0
                    }},
                    upsert=True
                )

                # Validate input
                assert len(AK) >= parallel_num, 'Please provide enough AK and SK'

                # Create save directory
                os.makedirs(save_path, exist_ok=True)

                # Get filename without extension
                base_filename = filename.rsplit('.', 1)[0]

                # Check if record already exists, if so, reset progress
                existing_record = await self.tex_records.find_one({"input_file": filename})
                if existing_record:
                    await self.tex_records.update_one(
                        {"_id": existing_record["_id"]},
                        {"$set": {"status": "processing", "progress": 0}}
                    )
                else:
                    # Create new record
                    record = TexConversionRecord(
                        input_file=filename,
                        status="processing",
                        model_name=model_name,
                        save_path=save_path,
                        progress=0  # Initialize progress to 0
                    )
                    result = await self.tex_records.insert_one(record.dict(by_alias=True))
                    record_id = result.inserted_id

                try:
                    # Text preprocessing stage - 10%
                    await self.tex_records.update_one(
                        {"input_file": filename},
                        {"$set": {"progress": 10}}
                    )

                    # Split text
                    text_chunks = split_text_into_chunks(parallel_num, content)
                    total_chunks = len(text_chunks)
                    processed_chunks = 0

                    # Create task list - 20%
                    await self.tex_records.update_one(
                        {"input_file": filename},
                        {"$set": {"progress": 20}}
                    )

                    # Use thread pool to execute tasks asynchronously
                    results = []
                    loop = asyncio.get_event_loop()

                    # Create task list
                    futures = []
                    for i, chunk in enumerate(text_chunks):
                        future = loop.run_in_executor(
                            executor,
                            self._process_chunk_with_api,
                            chunk,
                            AK[i % len(AK)],
                            SK[i % len(SK)],
                            model_name
                        )
                        futures.append(future)

                    # Text processing stage - 20% to 80%
                    for i, future in enumerate(asyncio.as_completed(futures)):
                        try:
                            chunk_result = await future
                            results.extend(chunk_result)

                            # Update progress - even with just one chunk there will be progressive progress
                            processed_chunks += 1
                            if total_chunks == 1:
                                # If there's only one chunk, show progress in multiple steps
                                progress_steps = [30, 40, 50, 60, 70]
                                progress = progress_steps[min(len(progress_steps)-1, i)]
                            else:
                                # Normal progress calculation for multiple chunks
                                progress = int(20 + (processed_chunks / total_chunks * 60))

                            await self.tex_records.update_one(
                                {"input_file": filename},
                                {"$set": {"progress": progress}}
                            )
                        except Exception as e:
                            logger.error(f"Failed to process chunk: {str(e)}")
                            # Continue processing other chunks
                            continue

                    # Prepare to save - 90%
                    await self.tex_records.update_one(
                        {"input_file": filename},
                        {"$set": {"progress": 90}}
                    )

                    # Combine all LaTeX content
                    combined_tex = '\n'.join(results)

                    # Prepare data format for saving
                    data_to_save = [
                        {"id": i + 1, "chunk": result}
                        for i, result in enumerate(results)
                    ]

                    # Generate simplified save path
                    tex_file_path = os.path.join(
                        save_path,
                        'tex_files',
                        f'{base_filename}.json'  # Changed to .json extension
                    )
                    os.makedirs(os.path.dirname(tex_file_path), exist_ok=True)

                    # Save as JSON format
                    with open(tex_file_path, 'w', encoding='utf-8') as json_file:
                        json.dump(data_to_save, json_file, ensure_ascii=False, indent=4)

                    # Complete - 100%
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

                    # Update uploaded file status to completed
                    await self.db.llm_kit.uploaded_files.update_one(
                        {"filename": filename},
                        {"$set": {"status": "completed"}}
                    )

                    # Also update the status in the binary file collection (if it exists)
                    await self.db.llm_kit.uploaded_binary_files.update_one(
                        {"filename": filename},
                        {"$set": {"status": "completed"}}
                    )

                    # Add a new record using the simplified filename
                    saved_file_record = {
                        "input_file": os.path.basename(tex_file_path),
                        "original_file": filename,
                        "status": "completed",
                        "content": data_to_save,  # Use JSON format data
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
                    # When an error occurs, maintain the current progress, only update the status
                    await self.tex_records.update_one(
                        {"input_file": filename},
                        {"$set": {"status": "failed", "error_message": str(e)}}
                    )

                    # Update uploaded file status to failed
                    await self.db.llm_kit.uploaded_files.update_one(
                        {"filename": filename},
                        {"$set": {"status": "failed"}}
                    )

                    # Also update the binary file status (if it exists)
                    await self.db.llm_kit.uploaded_binary_files.update_one(
                        {"filename": filename},
                        {"$set": {"status": "failed"}}
                    )

                    raise e

            except Exception as e:
                import traceback
                await self._log_error(str(e), "convert_to_latex", traceback.format_exc())
                raise Exception(f"Conversion failed: {str(e)}")

    async def get_tex_records(self):
        """Get the most recent LaTeX conversion history record"""
        try:
            # Only get the latest record
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