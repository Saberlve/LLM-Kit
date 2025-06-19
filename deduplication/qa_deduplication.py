from utils.hparams import DedupParams
from motor.motor_asyncio import AsyncIOMotorClient
import json
import re
import jieba
from typing import List, Callable, Optional, Tuple, Dict, Any
from datetime import datetime, timezone
import os
import time
import asyncio
from bson import ObjectId
from concurrent.futures import ThreadPoolExecutor
import logging
import numpy as np
from datasketch import MinHash, MinHashLSH
import uuid
from pydantic import BaseModel, Field

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

# Set log level for this module
logger = logging.getLogger(__name__)
# Uncomment the line below to enable debug logging
# logger.setLevel(logging.DEBUG)

class QADeduplication:
    """
    Class for deduplicating question-answer pairs using MinHash LSH algorithm.
    Modified to work with database operations instead of file operations.
    """
    def __init__(self, hparams: DedupParams, progress_callback: Optional[Callable[[int], None]] = None):
        """
        Initialize the QA deduplication class.

        Args:
            hparams: Deduplication parameters
            progress_callback: Optional callback function to report progress
        """
        self.threshold = hparams.dedup_threshold
        self.num_perm = hparams.dedup_num_perm
        self.lsh = MinHashLSH(threshold=self.threshold, num_perm=self.num_perm)
        self.stopwords = self._load_stopwords()
        self.priority_dict = {}
        self.progress_callback = progress_callback

    def _load_stopwords(self):
        """Load Chinese stopwords for text processing"""
        input_file_name = './utils/hit_stopwords.txt'
        try:
            with open(input_file_name, 'r', encoding='utf-8') as f:
                return f.read().splitlines()
        except FileNotFoundError:
            logger.warning(f"Stopwords file {input_file_name} not found, using empty stopwords list")
            return []

    def split_word(self, sentence):
        """Split sentence into words and remove stopwords"""
        sentence = re.sub(r'[^\w\s]', '', sentence)
        words = list(jieba.cut(sentence))
        return [word for word in words if word not in self.stopwords]

    def get_qa_pairs(self, qa_pairs_data):
        """Process QA pairs data from database instead of file"""
        qa_pairs = []
        for data in qa_pairs_data:
            qa_pairs.append({
                'question': data.get('question', ''),
                'answer': data.get('answer', ''),
                'id': data.get('id', str(uuid.uuid4()))
            })
        logger.info(f"Total data processed: {len(qa_pairs)}")
        return qa_pairs

    def set_priority_order(self, filenames):
        """
        Set priority order for filenames

        Args:
            filenames (list): List of filenames ordered by priority (high to low)

        Example:
            qa_dedup.set_priority_order(['dataset1.json', 'dataset2.json', 'dataset3.json'])
        """
        self.priority_dict = {filename: idx for idx, filename in enumerate(filenames)}

    def select_best_qa_pair(self, qa_pairs, by_answer_length=False):
        """Select the best QA pair from a group based on priority and length"""
        def sort_key(x):
            # Extract source filename from id
            try:
                # Assume id format contains source file information
                id_parts = x['id'].split('_')
                if len(id_parts) >= 2:
                    # If filename contains underscores, reconstruct it
                    filename = '_'.join(id_parts[:-1])
                    if not filename.endswith('.json'):
                        filename += '.json'
                else:
                    # Handle exception case
                    filename = id_parts[0] + '.json'

                priority = self.priority_dict.get(filename, len(self.priority_dict))
            except Exception as e:
                # If parsing fails, give lowest priority
                priority = len(self.priority_dict)

            return (
                priority,
                -len(x['answer'] if by_answer_length else x['question'])
            )

        sorted_qa_pairs = sorted(qa_pairs, key=sort_key)
        return sorted_qa_pairs[0] if sorted_qa_pairs else None

    def deduplicate_by_question(self, qa_pairs_data, min_answer_length=0):
        """Deduplicate QA pairs by question similarity"""
        start_time = datetime.now()
        qa_pairs = self.get_qa_pairs(qa_pairs_data)

        # Execute deduplication
        unique_qa_pairs, delete_qa_pairs = self._process_deduplication(qa_pairs, by_question=True)

        logger.info(f"Execution time: {datetime.now() - start_time}")
        return unique_qa_pairs, delete_qa_pairs

    def deduplicate_by_answer(self, qa_pairs_data, min_answer_length=15):
        """Deduplicate QA pairs by answer similarity"""
        start_time = datetime.now()
        qa_pairs = self.get_qa_pairs(qa_pairs_data)

        # Execute deduplication
        unique_qa_pairs, delete_qa_pairs = self._process_deduplication(
            qa_pairs,
            by_question=False,
            min_answer_length=min_answer_length
        )

        logger.info(f"Execution time: {datetime.now() - start_time}")
        return unique_qa_pairs, delete_qa_pairs

    def _process_deduplication(self, qa_pairs, by_question=True, min_answer_length=0):
        """Process deduplication logic"""
        unique_qa_pairs = []
        delete_qa_pairs = []
        processed_indices = set()
        filtered_count = 0

        # Create MinHash for all QA pairs first
        minhashes = {}
        for idx, qa_pair in enumerate(qa_pairs):
            if not by_question and len(qa_pair['answer']) < min_answer_length:
                filtered_count += 1
                continue

            text = qa_pair['question'] if by_question else qa_pair['answer']
            words = self.split_word(text)
            minhash = MinHash(num_perm=self.num_perm)
            for word in words:
                minhash.update(word.encode('utf-8'))
            minhashes[idx] = minhash

        # Process each QA pair for deduplication
        for idx, qa_pair in enumerate(qa_pairs):
            if idx in processed_indices:
                continue

            if idx not in minhashes:  # Filtered out due to length
                continue

            current_minhash = minhashes[idx]
            similar_group = [qa_pair]
            similar_indices = [idx]

            # Find all similar pairs
            for other_idx, other_qa in enumerate(qa_pairs):
                if other_idx == idx or other_idx in processed_indices or other_idx not in minhashes:
                    continue

                other_minhash = minhashes[other_idx]
                similarity = current_minhash.jaccard(other_minhash)

                if similarity >= self.threshold:
                    similar_group.append(other_qa)
                    similar_indices.append(other_idx)
                    logger.info(f"Found duplicate: '{qa_pair['question'][:30]}...' and '{other_qa['question'][:30]}...' (similarity: {similarity:.2f})")

            # Mark all similar pairs as processed
            for sim_idx in similar_indices:
                processed_indices.add(sim_idx)

            if len(similar_group) > 1:
                # Multiple similar pairs found - select the best one
                selected_pair = self.select_best_qa_pair(
                    similar_group,
                    by_answer_length=not by_question
                )
                if selected_pair:
                    unique_qa_pairs.append(selected_pair)
                    # Always add deleted groups regardless of deduplication method
                    delete_qa_pairs.append(similar_group)
                    logger.info(f"Added group with {len(similar_group)} similar QA pairs to deleted groups")
            else:
                # No similar pairs found, keep this one
                unique_qa_pairs.append(qa_pair)

        logger.info(f"Number of filtered data: {filtered_count}")
        logger.info(f"Kept {len(unique_qa_pairs)} QA pairs, deleted {len(delete_qa_pairs)} groups")
        return unique_qa_pairs, delete_qa_pairs

    def _get_similar_pairs(self, result, qa_pairs, current_idx, seen_id):
        """Get similar QA pairs from LSH query result"""
        similar_pairs = []
        for res in result:
            if res in seen_id:
                continue
            if res != f"qa_pair_{current_idx}":
                index = int(res.split('_')[2])
                similar_pair = qa_pairs[index]
                seen_id.add(res)
                if similar_pair not in similar_pairs:
                    similar_pairs.append(similar_pair)
            else:
                seen_id.add(res)
        return similar_pairs

    def process_qa_file(self, hparams: DedupParams):
        """
        Process QA file for deduplication - modified to work with database data

        Args:
            hparams: Deduplication parameters

        Returns:
            Tuple: (kept_pairs, deleted_groups)
        """
        # Load QA pairs from the temporary file (which contains database data)
        qa_pairs_data = []
        for file_path in hparams.input_file:
            with open(file_path, 'r', encoding='utf-8') as f:
                qa_pairs_data.extend(json.load(f))

        # Report progress
        if self.progress_callback:
            self.progress_callback(10)

        if hparams.dedup_by_answer:
            kept_pairs, deleted_groups = self.deduplicate_by_answer(
                qa_pairs_data,
                min_answer_length=hparams.min_answer_length
            )
        else:
            kept_pairs, deleted_groups = self.deduplicate_by_question(qa_pairs_data)

        # Report completion
        if self.progress_callback:
            self.progress_callback(100)

        return kept_pairs, deleted_groups

# Pydantic models for database records
class DedupRecord(BaseModel):
    input_file: List[str]
    output_file: str
    deleted_pairs_file: str
    dedup_by_answer: bool
    threshold: float
    min_answer_length: int
    status: str
    source_text: str
    original_count: int
    kept_count: int
    progress: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    error_message: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True
        
    def dict(self, by_alias=False):
        """兼容旧版Pydantic API"""
        if hasattr(self, "model_dump"):
            return self.model_dump(by_alias=by_alias)
        else:
            return super().dict(by_alias=by_alias)

class KeptQAPair(BaseModel):
    dedup_id: ObjectId
    qa_id: str
    question: str
    answer: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        arbitrary_types_allowed = True
        
    def dict(self, by_alias=False):
        """兼容旧版Pydantic API"""
        if hasattr(self, "model_dump"):
            return self.model_dump(by_alias=by_alias)
        else:
            return super().dict(by_alias=by_alias)

class DeletedQAPair(BaseModel):
    dedup_id: ObjectId
    qa_id: str
    question: str
    answer: str
    similar_pairs: List[Dict[str, Any]]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        arbitrary_types_allowed = True
        
    def dict(self, by_alias=False):
        """兼容旧版Pydantic API"""
        if hasattr(self, "model_dump"):
            return self.model_dump(by_alias=by_alias)
        else:
            return super().dict(by_alias=by_alias)

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
            "timestamp": datetime.now(timezone.utc),
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
        """Get quality file content based on filename"""
        try:
            # Find quality record with specified filename
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
                        kept_pair = KeptQAPair(
                            dedup_id=record_id,
                            qa_id=qa['id'],
                            question=qa['question'],
                            answer=qa['answer']
                        )
                        if hasattr(kept_pair, "model_dump"):
                            record = kept_pair.model_dump(by_alias=True)
                        else:
                            record = kept_pair.dict(by_alias=True)
                        kept_records.append(record)

                    if kept_records:
                        await self.kept_pairs.insert_many(kept_records)

                # Save deleted QA pairs
                if deleted_groups:
                    deleted_records = []
                    for group in deleted_groups:
                        main_pair = group[0]
                        similar_pairs = group[1:]
                        deleted_pair = DeletedQAPair(
                            dedup_id=record_id,
                            qa_id=main_pair['id'],
                            question=main_pair['question'],
                            answer=main_pair['answer'],
                            similar_pairs=[{
                                'qa_id': pair['id'],
                                'question': pair['question'],
                                'answer': pair['answer']
                            } for pair in similar_pairs]
                        )
                        if hasattr(deleted_pair, "model_dump"):
                            record = deleted_pair.model_dump(by_alias=True)
                        else:
                            record = deleted_pair.dict(by_alias=True)
                        deleted_records.append(record)

                    if deleted_records:
                        await self.deleted_pairs.insert_many(deleted_records)

                # Complete - 100%
                await self.dedup_records.update_one(
                    {"_id": record_id},
                    {
                        "$set": {
                            "status": "completed",
                            "original_count": len(original_pairs),
                            "kept_count": len(kept_pairs),
                            "progress": 100
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

            # Get kept QA pairs
            qa_cursor = self.kept_pairs.find({"dedup_id": record["_id"]})
            kept_pairs = []
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
                "output_file": record["output_file"],
                "deleted_pairs_file": record["deleted_pairs_file"],
                "status": record["status"],
                "source_text": record["source_text"],
                "original_count": record["original_count"],
                "kept_count": record["kept_count"],
                "kept_pairs": kept_pairs,
                "deleted_pairs": deleted_pairs,
                "created_at": record["created_at"]
            }]
        except Exception as e:
            raise Exception(f"Failed to get records: {str(e)}")