from deduplication.qa_deduplication import QADeduplication, DedupRecord, KeptQAPair, DeletedQAPair
from utils.hparams import DedupParams
from motor.motor_asyncio import AsyncIOMotorClient
import json
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import os
import time
import asyncio
from bson import ObjectId
from concurrent.futures import ThreadPoolExecutor
import logging

logger = logging.getLogger(__name__)

class QADedupService:
    def __init__(self, db: AsyncIOMotorClient):
        self.db = db
        self.dedup_records = db.llm_kit.dedup_records
        self.kept_pairs = db.llm_kit.kept_pairs
        self.error_logs = db.llm_kit.error_logs
        self.deleted_pairs = db.llm_kit.deleted_pairs
        self.quality_generations = db.llm_kit.quality_generations
        self.base_output_dir = "results/dedup"
        os.makedirs(self.base_output_dir, exist_ok=True)
        self.last_progress_update = {}
        self.executor = ThreadPoolExecutor(max_workers=10)  # Add thread pool

    async def _log_error(self, error_message: str, source: str, stack_trace: str = None):
        error_log = {
            "timestamp": datetime.utcnow(),
            "error_message": error_message,
            "source": source,
            "stack_trace": stack_trace
        }
        await self.error_logs.insert_one(error_log)

    def _generate_output_paths(self, timestamp: datetime):
        """Generate output file paths"""
        date_str = timestamp.strftime("%Y%m%d_%H%M%S")
        output_file = os.path.join(self.base_output_dir, f"dedup_result_{date_str}.json")
        deleted_file = os.path.join(self.base_output_dir, f"deleted_pairs_{date_str}.json")
        return output_file, deleted_file

    async def update_progress(self, record_id: str, progress: int):
        """Update progress (with throttling control)"""
        current_time = time.time()
        last_update = self.last_progress_update.get(record_id, 0)

        # Update progress at most once every 0.5 seconds
        if current_time - last_update >= 0.5:
            await self.dedup_records.update_one(
                {"_id": ObjectId(record_id)},
                {"$set": {"progress": progress}}
            )
            self.last_progress_update[record_id] = current_time

    async def get_quality_content(self, file_id: str):
        """Get quality file content based on file ID"""
        try:
            # Find quality record with specified ID
            record = await self.quality_generations.find_one({"_id": ObjectId(file_id)})

            if not record:
                raise Exception(f"Quality record with ID {file_id} not found")

            if not record.get("save_path") or not os.path.exists(record["save_path"]):
                raise Exception(f"File path does not exist: {record.get('save_path')}")

            # Read file content
            with open(record["save_path"], 'r', encoding='utf-8') as f:
                content = json.load(f)

            return {
                "filename": record["input_file"],
                "content": content,
                "created_at": record["created_at"]
            }
        except Exception as e:
            await self._log_error(str(e), "get_quality_content")
            raise Exception(f"Failed to get quality file content: {str(e)}")

    async def get_dedup_content(self, file_id: str):
        """Get deduplicated file content based on file ID"""
        try:
            # Find the deduplication record with the specified ID
            record = await self.dedup_records.find_one({"_id": ObjectId(file_id)})

            if not record:
                raise Exception(f"Deduplication record with ID {file_id} not found")

            # If content is stored directly in the database
            if record.get("content"):
                return {
                    "filename": f"dedup_result_{file_id}.json",
                    "content": record["content"],
                    "created_at": record["created_at"],
                    "original_count": record["original_count"],
                    "kept_count": record["kept_count"]
                }
            
            # Otherwise, read from file
            if not record.get("output_file") or not os.path.exists(record["output_file"]):
                raise Exception(f"File path does not exist: {record.get('output_file')}")

            # Read file content
            with open(record["output_file"], 'r', encoding='utf-8') as f:
                content = json.load(f)

            return {
                "filename": os.path.basename(record["output_file"]),
                "content": content,
                "created_at": record["created_at"],
                "original_count": record["original_count"],
                "kept_count": record["kept_count"]
            }
        except Exception as e:
            await self._log_error(str(e), "get_dedup_content")
            raise Exception(f"Failed to get deduplicated file content: {str(e)}")

    async def get_quality_content_by_filename(self, filename: str):
        """Get quality file content based on filename or ID"""
        try:
            # First try to find by ID (for new frontend)
            try:
                # Check if filename is a valid ObjectId
                if ObjectId.is_valid(filename):
                    return await self.get_quality_content(filename)
            except Exception:
                pass
                
            # If not found or not valid ObjectId, try by filename (for backward compatibility)
            record = await self.quality_generations.find_one({"input_file": filename})

            if not record:
                raise Exception(f"Quality record with filename {filename} not found")

            if not record.get("save_path") or not os.path.exists(record["save_path"]):
                raise Exception(f"File path does not exist: {record.get('save_path')}")

            # Read file content
            with open(record["save_path"], 'r', encoding='utf-8') as f:
                content = json.load(f)

            return {
                "filename": record["input_file"],
                "content": content,
                "created_at": record["created_at"]
            }
        except Exception as e:
            await self._log_error(str(e), "get_quality_content_by_filename")
            raise Exception(f"Failed to get quality file content: {str(e)}")

    async def get_dedup_content_by_filename(self, filename: str):
        """Get deduplicated file content based on filename"""
        try:
            # Find deduplication record with the specified filename
            record = await self.dedup_records.find_one({"output_file": {"$regex": f".*{filename}.*"}})

            if not record:
                raise Exception(f"Deduplication record with filename {filename} not found")

            # If content is stored directly in the database
            if record.get("content"):
                return {
                    "filename": f"dedup_result_{record['_id']}.json",
                    "content": record["content"],
                    "created_at": record["created_at"],
                    "original_count": record["original_count"],
                    "kept_count": record["kept_count"]
                }
                
            # Otherwise, read from file
            if not record.get("output_file") or not os.path.exists(record["output_file"]):
                raise Exception(f"File path does not exist: {record.get('output_file')}")

            # Read file content
            with open(record["output_file"], 'r', encoding='utf-8') as f:
                content = json.load(f)

            return {
                "filename": os.path.basename(record["output_file"]),
                "content": content,
                "created_at": record["created_at"],
                "original_count": record["original_count"],
                "kept_count": record["kept_count"]
            }
        except Exception as e:
            await self._log_error(str(e), "get_dedup_content_by_filename")
            raise Exception(f"Failed to get deduplicated file content: {str(e)}")

    async def deduplicate_qa(self, filenames: List[str], dedup_by_answer: bool,
                           dedup_threshold: float, min_answer_length: int = 10):
        try:
            # Get all file contents
            original_pairs = []
            source_texts = []
            input_filenames = []
            record_id = None

            for filename in filenames:
                quality_content = await self.get_quality_content_by_filename(filename)
                source_texts.append(json.dumps(quality_content["content"]))
                original_pairs.extend(quality_content["content"])
                input_filenames.append(quality_content["filename"])

            # Get first filename as base name
            base_filename = input_filenames[0].rsplit('.', 1)[0]

            # Use simplified filename format: original_filename_dedup.json
            output_file = os.path.join(self.base_output_dir, f"{base_filename}_dedup.json")
            deleted_pairs_file = os.path.join(self.base_output_dir, f"{base_filename}_dedup_deleted.json")

            # Check if record already exists, if so, reset progress
            existing_record = await self.dedup_records.find_one({"input_file": input_filenames})
            if existing_record:
                await self.dedup_records.update_one(
                    {"_id": existing_record["_id"]},
                    {
                        "$set": {
                            "status": "processing",
                            "progress": 0,
                            "dedup_by_answer": dedup_by_answer,
                            "threshold": dedup_threshold,
                            "min_answer_length": min_answer_length
                        }
                    }
                )
                record_id = existing_record["_id"]
            else:
                # Create deduplication record, keep original fields
                dedup_record = DedupRecord(
                    input_file=input_filenames,
                    output_file=output_file,
                    deleted_pairs_file=deleted_pairs_file,
                    dedup_by_answer=dedup_by_answer,
                    threshold=dedup_threshold,
                    min_answer_length=min_answer_length,
                    status="processing",
                    source_text="\n".join(source_texts),
                    original_count=len(original_pairs),
                    kept_count=0,
                    progress=0
                )
                if hasattr(dedup_record, "model_dump"):
                    record_dict = dedup_record.model_dump(by_alias=True)
                else:
                    record_dict = dedup_record.dict(by_alias=True)
                result = await self.dedup_records.insert_one(record_dict)
                record_id = result.inserted_id

            try:
                # Initialization phase - 10%
                await self.dedup_records.update_one(
                    {"_id": record_id},
                    {"$set": {"progress": 10}}
                )

                # Create temporary file to save merged QA pairs
                temp_input_file = os.path.join(self.base_output_dir, f"temp_input_{str(record_id)}.json")
                with open(temp_input_file, 'w', encoding='utf-8') as f:
                    json.dump(original_pairs, f, ensure_ascii=False, indent=4)

                # Task preparation phase - 20%
                await self.dedup_records.update_one(
                    {"_id": record_id},
                    {"$set": {"progress": 20}}
                )

                # Create progress update callback
                async def progress_callback(progress: int):
                    current_time = time.time()
                    last_update = self.last_progress_update.get(str(record_id), 0)

                    if current_time - last_update >= 0.5:
                        # Map original progress (0-100) to processing phase (20-80)
                        adjusted_progress = int(20 + (progress * 0.6))

                        # If data volume is small, use preset progress points
                        if len(original_pairs) <= 5:  # Assume 5 pairs or less is small data volume
                            progress_steps = [30, 40, 50, 60, 70]
                            step_index = min(len(progress_steps)-1, int(progress/20))
                            adjusted_progress = progress_steps[step_index]

                        await self.dedup_records.update_one(
                            {"_id": record_id},
                            {"$set": {"progress": adjusted_progress}}
                        )
                        self.last_progress_update[str(record_id)] = current_time

                # Create deduplication parameters
                hparams = DedupParams(
                    input_file=[temp_input_file],
                    output_file=output_file,
                    dedup_by_answer=dedup_by_answer,
                    dedup_threshold=dedup_threshold,
                    min_answer_length=min_answer_length,
                    deleted_pairs_file=deleted_pairs_file,
                )

                # Create deduplicator instance
                deduplicator = QADeduplication(
                    hparams,
                    progress_callback=lambda p: asyncio.run_coroutine_threadsafe(
                        progress_callback(p),
                        asyncio.get_event_loop()
                    )
                )

                # Set priority order for file selection (use input filenames order)
                deduplicator.set_priority_order(input_filenames)

                # Execute deduplication operation in thread pool
                loop = asyncio.get_event_loop()
                kept_pairs, deleted_groups = await loop.run_in_executor(
                    self.executor,
                    deduplicator.process_qa_file,
                    hparams
                )

                # Save preparation phase - 90%
                await self.dedup_records.update_one(
                    {"_id": record_id},
                    {"$set": {"progress": 90}}
                )

                # Save kept QA pairs
                if kept_pairs:
                    kept_records = []
                    for qa in kept_pairs:
                        record = KeptQAPair(
                            dedup_id=record_id,
                            qa_id=qa['id'],
                            question=qa['question'],
                            answer=qa['answer']
                        ).dict(by_alias=True)
                        kept_records.append(record)

                    if kept_records:
                        await self.kept_pairs.insert_many(kept_records)

                # Save deleted QA pairs
                if deleted_groups:
                    deleted_records = []
                    for group in deleted_groups:
                        main_pair = group[0]
                        similar_pairs = group[1:]
                        record = DeletedQAPair(
                            dedup_id=record_id,
                            qa_id=main_pair['id'],
                            question=main_pair['question'],
                            answer=main_pair['answer'],
                            similar_pairs=[{
                                'qa_id': pair['id'],
                                'question': pair['question'],
                                'answer': pair['answer']
                            } for pair in similar_pairs]
                        ).dict(by_alias=True)
                        deleted_records.append(record)

                    if deleted_records:
                        await self.deleted_pairs.insert_many(deleted_records)

                # Store content directly in database for easier access
                await self.dedup_records.update_one(
                    {"_id": record_id},
                    {
                        "$set": {
                            "status": "completed",
                            "original_count": len(original_pairs),
                            "kept_count": len(kept_pairs),
                            "progress": 100,
                            "content": kept_pairs  # Store content directly in database
                        }
                    }
                )

                return {
                    "dedup_id": str(record_id),
                    "output_file": output_file,
                    "deleted_pairs_file": deleted_pairs_file,
                    "kept_pairs": kept_pairs,
                    "original_count": len(original_pairs),
                    "kept_count": len(kept_pairs),
                    "deleted_count": len(original_pairs) - len(kept_pairs)
                }

            except Exception as e:
                # When an error occurs, only update status, maintain current progress
                await self.dedup_records.update_one(
                    {"_id": record_id},
                    {
                        "$set": {
                            "status": "failed",
                            "error_message": str(e)
                        }
                    }
                )
                raise e

            finally:
                # Clean up temporary files
                if os.path.exists(temp_input_file):
                    os.unlink(temp_input_file)
                # Clean up progress update records
                if str(record_id) in self.last_progress_update:
                    del self.last_progress_update[str(record_id)]

        except Exception as e:
            import traceback
            await self._log_error(str(e), "deduplicate_qa", traceback.format_exc())
            if record_id:
                await self.dedup_records.update_one(
                    {"_id": record_id},
                    {
                        "$set": {
                            "status": "failed",
                            "error_message": str(e)
                        }
                    }
                )
            raise Exception(f"Deduplication failed: {str(e)}")

    async def get_dedup_records(self):
        """Get the most recent deduplication history record"""
        try:
            # Only get the latest record
            record = await self.dedup_records.find_one(
                sort=[("created_at", -1)]
            )

            if not record:
                return []

            # Get kept QA pairs - either from content field or from kept_pairs collection
            kept_pairs = []
            if record.get("content"):
                kept_pairs = record["content"]
            else:
                qa_cursor = self.kept_pairs.find({"dedup_id": record["_id"]})
                async for qa in qa_cursor:
                    kept_pairs.append({
                        "question": qa["question"],
                        "answer": qa["answer"]
                    })

            # Get deleted QA pairs
            deleted_cursor = self.deleted_pairs.find({"dedup_id": record["_id"]})
            deleted_pairs = []
            async for deleted in deleted_cursor:
                deleted_pairs.append({
                    "main_pair": {
                        "question": deleted["question"],
                        "answer": deleted["answer"]
                    },
                    "similar_pairs": deleted["similar_pairs"]
                })

            return [{
                "dedup_id": str(record["_id"]),
                "input_file": record["input_file"],
                "output_file": record.get("output_file", ""),
                "deleted_pairs_file": record.get("deleted_pairs_file", ""),
                "status": record["status"],
                "source_text": record["source_text"],
                "original_count": record["original_count"],
                "kept_count": record["kept_count"],
                "kept_pairs": kept_pairs[:10],  # Only return first 10 pairs for preview
                "deleted_pairs": deleted_pairs[:10],  # Only return first 10 pairs for preview
                "created_at": record["created_at"]
            }]
        except Exception as e:
            raise Exception(f"Failed to get records: {str(e)}")

    async def get_unoptimized_content(self, file_id: str):
        """Get unoptimized QA content based on file ID"""
        try:
            # Find QA generation record with specified ID
            record = await self.db.llm_kit.qa_generations.find_one({"_id": ObjectId(file_id)})

            if not record:
                raise Exception(f"QA generation record with ID {file_id} not found")

            # Get content from record
            content = []
            if "content" in record and record["content"]:
                if isinstance(record["content"], str):
                    try:
                        content = json.loads(record["content"])
                    except json.JSONDecodeError:
                        raise Exception("Invalid JSON format in content")
                elif isinstance(record["content"], list):
                    content = record["content"]
            else:
                raise Exception("No content found in record")

            return {
                "filename": record["input_file"],
                "content": content,
                "created_at": record["created_at"]
            }
        except Exception as e:
            await self._log_error(str(e), "get_unoptimized_content")
            raise Exception(f"Failed to get unoptimized content: {str(e)}")

    async def get_optimized_content(self, file_id: str):
        """Get optimized QA content based on file ID"""
        try:
            # Find quality generation record with specified ID
            record = await self.quality_generations.find_one({"_id": ObjectId(file_id)})

            if not record:
                raise Exception(f"Quality generation record with ID {file_id} not found")

            # Get content from record
            content = []
            if "content" in record and record["content"]:
                if isinstance(record["content"], str):
                    try:
                        content = json.loads(record["content"])
                    except json.JSONDecodeError:
                        raise Exception("Invalid JSON format in content")
                elif isinstance(record["content"], list):
                    content = record["content"]
            else:
                raise Exception("No content found in record")

            return {
                "filename": record["input_file"],
                "content": content,
                "created_at": record["created_at"]
            }
        except Exception as e:
            await self._log_error(str(e), "get_optimized_content")
            raise Exception(f"Failed to get optimized content: {str(e)}")

    async def deduplicate_qa_with_priority(self, selected_files: List[dict], dedup_by_answer: bool,
                                         dedup_threshold: float, min_answer_length: int = 10):
        """
        Perform QA deduplication with file selection and priority ordering

        Args:
            selected_files: List of file selections with priority ordering
            dedup_by_answer: Whether to deduplicate by answer
            dedup_threshold: Similarity threshold for deduplication
            min_answer_length: Minimum answer length
        """
        record_id = None
        try:
            # Sort files by priority (1 = highest priority)
            sorted_files = sorted(selected_files, key=lambda x: x.get('priority', 1) if isinstance(x, dict) else getattr(x, 'priority', 1))

            # Get all file contents with priority order
            original_pairs = []
            source_texts = []
            input_filenames = []

            for file_selection in sorted_files:
                # Handle both dict and object types
                if isinstance(file_selection, dict):
                    file_id = file_selection['file_id']
                    file_type = file_selection['file_type']
                    filename = file_selection['filename']
                    priority = file_selection['priority']
                else:
                    file_id = file_selection.file_id
                    file_type = file_selection.file_type
                    filename = file_selection.filename
                    priority = file_selection.priority

                # Get content based on file type
                if file_type == "optimized":
                    file_content = await self.get_optimized_content(file_id)
                else:  # unoptimized
                    file_content = await self.get_unoptimized_content(file_id)

                source_texts.append(json.dumps(file_content["content"]))

                # Add priority information to each QA pair for tracking
                for qa_pair in file_content["content"]:
                    qa_pair['source_file'] = filename
                    qa_pair['source_priority'] = priority
                    qa_pair['source_type'] = file_type

                original_pairs.extend(file_content["content"])
                input_filenames.append(filename)

            # Generate output file names
            base_filename = f"merged_dedup_{int(time.time())}"
            output_file = os.path.join(self.base_output_dir, f"{base_filename}.json")
            deleted_pairs_file = os.path.join(self.base_output_dir, f"{base_filename}_deleted.json")

            # Create deduplication record
            dedup_record = DedupRecord(
                input_file=input_filenames,
                output_file=output_file,
                deleted_pairs_file=deleted_pairs_file,
                dedup_by_answer=dedup_by_answer,
                threshold=dedup_threshold,
                min_answer_length=min_answer_length,
                status="processing",
                source_text="\n".join(source_texts),
                original_count=len(original_pairs),
                kept_count=0,
                progress=0
            )

            if hasattr(dedup_record, "model_dump"):
                record_dict = dedup_record.model_dump(by_alias=True)
            else:
                record_dict = dedup_record.dict(by_alias=True)
            result = await self.dedup_records.insert_one(record_dict)
            record_id = result.inserted_id

            try:
                # Initialization phase - 10%
                await self.dedup_records.update_one(
                    {"_id": record_id},
                    {"$set": {"progress": 10}}
                )

                # Create temporary file to save merged QA pairs
                temp_input_file = os.path.join(self.base_output_dir, f"temp_input_{str(record_id)}.json")
                with open(temp_input_file, 'w', encoding='utf-8') as f:
                    json.dump(original_pairs, f, ensure_ascii=False, indent=4)

                # Task preparation phase - 20%
                await self.dedup_records.update_one(
                    {"_id": record_id},
                    {"$set": {"progress": 20}}
                )

                # Create progress update callback
                def sync_progress_callback(progress: int):
                    """Synchronous progress callback for thread pool execution"""
                    try:
                        current_time = time.time()
                        last_update = self.last_progress_update.get(str(record_id), 0)

                        if current_time - last_update >= 0.5:
                            # Map original progress (0-100) to processing phase (20-80)
                            adjusted_progress = int(20 + (progress * 0.6))
                            # Store progress for later update
                            self.last_progress_update[str(record_id)] = current_time
                            # We'll update the database after the thread execution
                    except Exception as e:
                        print(f"Progress callback error: {e}")

                # Create deduplication parameters
                hparams = DedupParams(
                    input_file=[temp_input_file],
                    output_file=output_file,
                    dedup_by_answer=dedup_by_answer,
                    dedup_threshold=dedup_threshold,
                    min_answer_length=min_answer_length,
                    deleted_pairs_file=deleted_pairs_file,
                )

                # Create deduplicator instance
                deduplicator = QADeduplication(
                    hparams,
                    progress_callback=sync_progress_callback
                )

                # Set priority order for file selection
                priority_filenames = []
                for f in sorted_files:
                    if isinstance(f, dict):
                        priority_filenames.append(f['filename'])
                    else:
                        priority_filenames.append(f.filename)
                deduplicator.set_priority_order(priority_filenames)

                # Execute deduplication operation in thread pool
                loop = asyncio.get_event_loop()
                kept_pairs, deleted_groups = await loop.run_in_executor(
                    self.executor,
                    deduplicator.process_qa_file,
                    hparams
                )

                # Save preparation phase - 90%
                await self.dedup_records.update_one(
                    {"_id": record_id},
                    {"$set": {"progress": 90}}
                )

                # Save kept QA pairs
                if kept_pairs:
                    kept_records = []
                    for qa in kept_pairs:
                        record = KeptQAPair(
                            dedup_id=record_id,
                            qa_id=qa['id'],
                            question=qa['question'],
                            answer=qa['answer']
                        ).dict(by_alias=True)
                        kept_records.append(record)

                    if kept_records:
                        await self.kept_pairs.insert_many(kept_records)

                # Save deleted QA pairs
                if deleted_groups:
                    deleted_records = []
                    for group in deleted_groups:
                        main_pair = group[0]
                        similar_pairs = group[1:]
                        record = DeletedQAPair(
                            dedup_id=record_id,
                            qa_id=main_pair['id'],
                            question=main_pair['question'],
                            answer=main_pair['answer'],
                            similar_pairs=[{
                                'qa_id': pair['id'],
                                'question': pair['question'],
                                'answer': pair['answer']
                            } for pair in similar_pairs]
                        ).dict(by_alias=True)
                        deleted_records.append(record)

                    if deleted_records:
                        await self.deleted_pairs.insert_many(deleted_records)

                # Store content directly in database for easier access
                await self.dedup_records.update_one(
                    {"_id": record_id},
                    {
                        "$set": {
                            "status": "completed",
                            "original_count": len(original_pairs),
                            "kept_count": len(kept_pairs),
                            "progress": 100,
                            "content": kept_pairs  # Store content directly in database
                        }
                    }
                )

                return {
                    "dedup_id": str(record_id),
                    "output_file": output_file,
                    "deleted_pairs_file": deleted_pairs_file,
                    "kept_pairs": kept_pairs,
                    "original_count": len(original_pairs),
                    "kept_count": len(kept_pairs),
                    "deleted_count": len(original_pairs) - len(kept_pairs)
                }

            except Exception as e:
                # When an error occurs, only update status, maintain current progress
                await self.dedup_records.update_one(
                    {"_id": record_id},
                    {
                        "$set": {
                            "status": "failed",
                            "error_message": str(e)
                        }
                    }
                )
                raise e

            finally:
                # Clean up temporary files
                if os.path.exists(temp_input_file):
                    os.unlink(temp_input_file)
                # Clean up progress update records
                if str(record_id) in self.last_progress_update:
                    del self.last_progress_update[str(record_id)]

        except Exception as e:
            import traceback
            await self._log_error(str(e), "deduplicate_qa_with_priority", traceback.format_exc())
            if record_id:
                await self.dedup_records.update_one(
                    {"_id": record_id},
                    {
                        "$set": {
                            "status": "failed",
                            "error_message": str(e)
                        }
                    }
                )
            raise Exception(f"Deduplication failed: {str(e)}")

    async def get_dedup_preview(self, dedup_id: str, page: int = 1, page_size: int = 10, deleted_preview_size: int = 10):
        """Get preview of deduplication results"""
        try:
            # Find deduplication record
            record = await self.dedup_records.find_one({"_id": ObjectId(dedup_id)})

            if not record:
                raise Exception(f"Deduplication record with ID {dedup_id} not found")

            if record["status"] != "completed":
                raise Exception("Deduplication not completed yet")

            # Get kept pairs with pagination
            kept_pairs = []
            if record.get("content"):
                kept_pairs = record["content"]
            else:
                qa_cursor = self.kept_pairs.find({"dedup_id": ObjectId(dedup_id)})
                async for qa in qa_cursor:
                    kept_pairs.append({
                        "id": qa["qa_id"],
                        "question": qa["question"],
                        "answer": qa["answer"]
                    })

            # Apply pagination to kept pairs
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            paginated_kept_pairs = kept_pairs[start_idx:end_idx]

            # Get deleted pairs (show more for preview)
            deleted_cursor = self.deleted_pairs.find({"dedup_id": ObjectId(dedup_id)})
            deleted_groups = []
            async for deleted in deleted_cursor:
                deleted_groups.append({
                    "main_pair": {
                        "id": deleted["qa_id"],
                        "question": deleted["question"],
                        "answer": deleted["answer"]
                    },
                    "similar_pairs": deleted["similar_pairs"],
                    "group_size": len(deleted["similar_pairs"]) + 1
                })

            return {
                "dedup_id": dedup_id,
                "original_count": record["original_count"],
                "kept_count": record["kept_count"],
                "deleted_count": record["original_count"] - record["kept_count"],
                "kept_pairs": paginated_kept_pairs,
                "deleted_groups": deleted_groups[:deleted_preview_size],  # Show configurable number of deleted groups
                "total_deleted_groups": len(deleted_groups),
                "created_at": record["created_at"],
                "status": record["status"],
                "total_pages": (len(kept_pairs) + page_size - 1) // page_size,
                "current_page": page,
                "page_size": page_size
            }

        except Exception as e:
            await self._log_error(str(e), "get_dedup_preview")
            raise Exception(f"Failed to get deduplication preview: {str(e)}")

    async def download_dedup_result(self, dedup_id: str):
        """Get full deduplication result for download"""
        try:
            # Find deduplication record
            record = await self.dedup_records.find_one({"_id": ObjectId(dedup_id)})

            if not record:
                raise Exception(f"Deduplication record with ID {dedup_id} not found")

            if record["status"] != "completed":
                raise Exception("Deduplication not completed yet")

            # Get all kept pairs
            kept_pairs = []
            if record.get("content"):
                kept_pairs = record["content"]
            else:
                qa_cursor = self.kept_pairs.find({"dedup_id": ObjectId(dedup_id)})
                async for qa in qa_cursor:
                    kept_pairs.append({
                        "id": qa["qa_id"],
                        "question": qa["question"],
                        "answer": qa["answer"]
                    })

            return {
                "filename": f"dedup_result_{dedup_id}.json",
                "content": kept_pairs,
                "original_count": record["original_count"],
                "kept_count": record["kept_count"],
                "deleted_count": record["original_count"] - record["kept_count"],
                "created_at": record["created_at"]
            }

        except Exception as e:
            await self._log_error(str(e), "download_dedup_result")
            raise Exception(f"Failed to get deduplication result for download: {str(e)}")

    async def get_deleted_pairs(self, dedup_id: str, page: int = 1, page_size: int = 10):
        """Get deleted QA pairs with pagination"""
        try:
            # Find deduplication record
            record = await self.dedup_records.find_one({"_id": ObjectId(dedup_id)})

            if not record:
                raise Exception(f"Deduplication record with ID {dedup_id} not found")

            if record["status"] != "completed":
                raise Exception("Deduplication not completed yet")

            # Get all deleted pairs
            deleted_cursor = self.deleted_pairs.find({"dedup_id": ObjectId(dedup_id)})
            all_deleted_groups = []
            async for deleted in deleted_cursor:
                all_deleted_groups.append({
                    "main_pair": {
                        "id": deleted["qa_id"],
                        "question": deleted["question"],
                        "answer": deleted["answer"]
                    },
                    "similar_pairs": deleted["similar_pairs"],
                    "group_size": len(deleted["similar_pairs"]) + 1  # +1 for main pair
                })

            # Apply pagination
            total_groups = len(all_deleted_groups)
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            paginated_deleted_groups = all_deleted_groups[start_idx:end_idx]

            return {
                "dedup_id": dedup_id,
                "deleted_groups": paginated_deleted_groups,
                "total_deleted_groups": total_groups,
                "total_deleted_pairs": sum(group["group_size"] for group in all_deleted_groups),
                "current_page": page,
                "page_size": page_size,
                "total_pages": (total_groups + page_size - 1) // page_size,
                "created_at": record["created_at"],
                "status": record["status"]
            }

        except Exception as e:
            await self._log_error(str(e), "get_deleted_pairs")
            raise Exception(f"Failed to get deleted pairs: {str(e)}")

    async def download_deleted_pairs(self, dedup_id: str):
        """Get all deleted QA pairs for download"""
        try:
            # Find deduplication record
            record = await self.dedup_records.find_one({"_id": ObjectId(dedup_id)})

            if not record:
                raise Exception(f"Deduplication record with ID {dedup_id} not found")

            if record["status"] != "completed":
                raise Exception("Deduplication not completed yet")

            # Get all deleted pairs
            deleted_cursor = self.deleted_pairs.find({"dedup_id": ObjectId(dedup_id)})
            deleted_groups = []
            async for deleted in deleted_cursor:
                deleted_groups.append({
                    "main_pair": {
                        "id": deleted["qa_id"],
                        "question": deleted["question"],
                        "answer": deleted["answer"]
                    },
                    "similar_pairs": deleted["similar_pairs"],
                    "group_size": len(deleted["similar_pairs"]) + 1
                })

            return {
                "filename": f"deleted_pairs_{dedup_id}.json",
                "content": deleted_groups,
                "total_deleted_groups": len(deleted_groups),
                "total_deleted_pairs": sum(group["group_size"] for group in deleted_groups),
                "created_at": record["created_at"]
            }

        except Exception as e:
            await self._log_error(str(e), "download_deleted_pairs")
            raise Exception(f"Failed to get deleted pairs for download: {str(e)}")