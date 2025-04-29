from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from generate_qas.qa_generator import QAGenerator
from utils.hparams import HyperParams
from app.components.models.mongodb import QAGeneration, QAPairDB, PyObjectId
from utils.helper import generate, extract_qa
import json
import os
from bson import ObjectId
from concurrent.futures import ThreadPoolExecutor
import asyncio
import logging

logger = logging.getLogger(__name__)

class QAGenerateService:
    def __init__(self, db: AsyncIOMotorClient):
        self.db = db
        self.qa_generations = db.llm_kit.qa_generations
        self.qa_pairs = db.llm_kit.qa_pairs
        self.error_logs = db.llm_kit.error_logs
        self.tex_records = db.llm_kit.tex_records

    async def _log_error(self, error_message: str, source: str, stack_trace: str = None):
        error_log = {
            "timestamp": datetime.utcnow(),
            "error_message": error_message,
            "source": source,
            "stack_trace": stack_trace
        }
        await self.error_logs.insert_one(error_log)

    def process_chunk_with_api(self, text: str, ak: str, sk: str, model_name: str, domain: str):
        """Synchronously process a single text chunk"""
        qa_pairs = []
        max_retries = 5

        for attempt in range(max_retries):
            try:
                response = generate(text, model_name, 'ToQA', ak, sk)
                qas = extract_qa(response)
                for qa_pair in qas:
                    qa_pair["text"] = text
                    qa_pairs.append(qa_pair)
                break
            except Exception as e:
                if attempt == max_retries - 1:
                    print(f"Failed to process text chunk: {str(e)}")
        return qa_pairs

    async def process_chunks_parallel(self, chunks: list, ak_list: list, sk_list: list,
                                    parallel_num: int, model_name: str, domain: str, generation_id: ObjectId):
        """Process multiple text chunks in parallel"""
        qa_pairs = []
        total_chunks = len(chunks)
        processed_chunks = 0

        # Use context manager to create thread pool
        with ThreadPoolExecutor(max_workers=min(10, parallel_num)) as executor:
            try:
                # Initialization phase - 10%
                await self.qa_generations.update_one(
                    {"_id": generation_id},
                    {"$set": {"progress": 10}}
                )

                # Task preparation - 20%
                loop = asyncio.get_event_loop()
                futures = []

                for i, chunk in enumerate(chunks):
                    ak = ak_list[i % len(ak_list)]
                    sk = sk_list[i % len(sk_list)]
                    future = loop.run_in_executor(
                        executor,
                        self.process_chunk_with_api,
                        chunk, ak, sk, model_name, domain
                    )
                    futures.append(future)

                await self.qa_generations.update_one(
                    {"_id": generation_id},
                    {"$set": {"progress": 20}}
                )

                # Processing phase - 20% to 80%
                for i, future in enumerate(asyncio.as_completed(futures)):
                    try:
                        result = await future
                        if result:
                            qa_pairs.extend(result)

                        # Update progress - special handling for small text
                        processed_chunks += 1
                        if total_chunks == 1:
                            # Progress points for single chunk
                            progress_steps = [30, 40, 50, 60, 70]
                            progress = progress_steps[min(len(progress_steps)-1, i)]
                        else:
                            # Normal progress calculation for multiple chunks
                            progress = int(20 + (processed_chunks / total_chunks * 60))

                        await self.qa_generations.update_one(
                            {"_id": generation_id},
                            {"$set": {"progress": progress}}
                        )
                    except Exception as e:
                        logger.error(f"Failed to process chunk: {str(e)}")
                        continue

                # Save preparation - 90%
                await self.qa_generations.update_one(
                    {"_id": generation_id},
                    {"$set": {"progress": 90}}
                )

                if not qa_pairs:
                    raise Exception("No QA pairs were generated")

                return qa_pairs

            except Exception as e:
                logger.error(f"Parallel processing failed: {str(e)}")
                raise e

    async def get_all_tex_files(self):
        """Get all converted tex file records, only return the latest record for files with the same name"""
        try:
            # Get all completed records
            records = await self.tex_records.find(
                {"status": "completed"},
                {"_id": 1, "save_path": 1, "created_at": 1}
            ).to_list(None)

            # Group by filename, keep the latest record
            filename_dict = {}  # {filename: {"file_id": id, "filename": filename, "created_at": created_at}}

            for record in records:
                if not record.get("save_path"):
                    continue

                # Extract filename from save_path
                filename = os.path.basename(record["save_path"])
                created_at = record["created_at"]

                # If filename already exists, compare creation time
                if filename in filename_dict:
                    if created_at > filename_dict[filename]["created_at"]:
                        filename_dict[filename] = {
                            "file_id": str(record["_id"]),
                            "filename": filename,
                            "created_at": created_at
                        }
                else:
                    filename_dict[filename] = {
                        "file_id": str(record["_id"]),
                        "filename": filename,
                        "created_at": created_at
                    }

            # Convert to list and sort by creation time in descending order
            files = list(filename_dict.values())
            files.sort(key=lambda x: x["created_at"], reverse=True)

            return files

        except Exception as e:
            await self._log_error(str(e), "get_all_tex_files")
            raise Exception(f"Failed to get tex file list: {str(e)}")

    async def get_tex_content(self, file_id: str):
        """Get tex converted content by file ID"""
        try:
            # Find record with specified ID
            record = await self.tex_records.find_one(
                {
                    "_id": ObjectId(file_id),
                    "status": "completed"
                }
            )

            if not record:
                raise Exception("File does not exist or conversion not completed")

            if not record.get("content"):
                raise Exception("File content is empty")

            # Ensure content is in JSON array format
            content = record["content"]
            if not isinstance(content, str):
                content = json.dumps(content)

            return {
                "content": content,
                "created_at": record["created_at"]
            }
        except Exception as e:
            await self._log_error(str(e), "get_tex_content")
            raise Exception(f"Failed to get tex content: {str(e)}")

    async def generate_qa_pairs(
            self,
            content: str,
            filename: str,
            save_path: str,
            SK: list,
            AK: list,
            parallel_num: int,
            model_name: str,
            domain: str
    ):
        generation_id = None
        try:
            # Get filename without extension
            base_filename = filename.rsplit('.', 1)[0]

            # Check if record already exists, if so, reset progress
            existing_record = await self.qa_generations.find_one({"input_file": filename})
            if existing_record:
                await self.qa_generations.update_one(
                    {"_id": existing_record["_id"]},
                    {"$set": {
                        "status": "processing",
                        "progress": 0,
                        "model_name": model_name,
                        "domain": domain
                    }}
                )
                generation_id = existing_record["_id"]
            else:
                # Create new record
                generation = QAGeneration(
                    input_file=filename,
                    save_path=save_path,
                    model_name=model_name,
                    domain=domain,
                    status="processing",
                    source_text=content,
                    progress=0  # Initialize progress to 0
                )
                result = await self.qa_generations.insert_one(generation.dict(by_alias=True))
                generation_id = result.inserted_id

            # Update original file status to processing
            await self.db.llm_kit.uploaded_files.update_one(
                {"filename": filename},
                {"$set": {"status": "processing"}}
            )
            # Also update status in binary file collection (if exists)
            await self.db.llm_kit.uploaded_binary_files.update_one(
                {"filename": filename},
                {"$set": {"status": "processing"}}
            )

            try:
                chunks = json.loads(content)
                # Use modified parallel processing function
                qa_pairs = await self.process_chunks_parallel(
                    [chunk.get("chunk", "") for chunk in chunks],
                    AK,
                    SK,
                    parallel_num,
                    model_name,
                    domain,
                    generation_id
                )

                if not qa_pairs:
                    raise Exception("No QA pairs generated")

                # Build simplified save path and filename
                save_dir_path = os.path.join('result', 'qas')
                os.makedirs(save_dir_path, exist_ok=True)

                # Use simplified filename format: original_filename_qa.json
                final_save_path = os.path.join(
                    save_dir_path,
                    f"{base_filename}_qa.json"
                )

                # Save QA pairs to file
                try:
                    with open(final_save_path, 'w', encoding='utf-8') as f:
                        json.dump(qa_pairs, f, ensure_ascii=False, indent=4)
                except Exception as e:
                    raise Exception(f"Failed to save QA pairs to file: {str(e)}")

                # Update original record status
                await self.qa_generations.update_one(
                    {"_id": generation_id},
                    {"$set": {
                        "status": "completed",
                        "save_path": final_save_path,
                        "progress": 100  # Processing complete, set progress to 100%
                    }}
                )

                # Update original file status to completed
                await self.db.llm_kit.uploaded_files.update_one(
                    {"filename": filename},
                    {"$set": {"status": "completed"}}
                )
                # Also update status in binary file collection (if exists)
                await self.db.llm_kit.uploaded_binary_files.update_one(
                    {"filename": filename},
                    {"$set": {"status": "completed"}}
                )

                # Add a new record using simplified filename
                saved_file_record = {
                    "input_file": os.path.basename(final_save_path),
                    "original_file": filename,
                    "status": "completed",
                    "content": json.dumps(qa_pairs),
                    "created_at": datetime.now(timezone.utc),
                    "save_path": final_save_path,
                    "model_name": model_name,
                    "domain": domain
                }
                await self.qa_generations.insert_one(saved_file_record)

                # Save QA pairs to database
                # First delete previous QA pair records with the same filename
                await self.qa_pairs.delete_many({
                    "generation_id": {
                        "$in": [
                            doc["_id"] for doc in await self.qa_generations.find(
                                {"input_file": filename, "_id": {"$ne": generation_id}}
                            ).to_list(None)
                        ]
                    }
                })

                qa_records = []
                for qa in qa_pairs:
                    qa_record = QAPairDB(
                        generation_id=PyObjectId(generation_id),
                        question=qa["question"],
                        answer=qa["answer"]
                    )
                    qa_records.append(qa_record.dict(by_alias=True))

                if qa_records:
                    await self.qa_pairs.insert_many(qa_records)

                # Update generation record status
                await self.qa_generations.update_many(
                    {"input_file": filename, "_id": {"$ne": generation_id}},
                    {"$set": {"status": "overwritten"}}
                )

                await self.qa_generations.update_one(
                    {"_id": generation_id},
                    {"$set": {"status": "completed"}}
                )

                return {
                    "generation_id": str(generation_id),
                    "filename": os.path.basename(final_save_path),
                    "qa_pairs": qa_pairs,
                    "source_text": content
                }

            except Exception as e:
                # When an error occurs, only update status, maintain current progress
                await self.qa_generations.update_one(
                    {"_id": generation_id},
                    {"$set": {
                        "status": "failed",
                        "error_message": str(e)
                    }}
                )

                # Maintain original error handling logic
                await self.db.llm_kit.uploaded_files.update_one(
                    {"filename": filename},
                    {"$set": {"status": "failed"}}
                )
                await self.db.llm_kit.uploaded_binary_files.update_one(
                    {"filename": filename},
                    {"$set": {"status": "failed"}}
                )
                raise e

        except Exception as e:
            import traceback
            await self._log_error(str(e), "generate_qa_pairs", traceback.format_exc())
            if generation_id:
                try:
                    await self.qa_generations.update_one(
                        {"_id": generation_id},
                        {"$set": {
                            "status": "failed",
                            "error_message": str(e)
                        }}
                    )
                except Exception as db_error:
                    print(f"Failed to update generation status: {str(db_error)}")
            raise Exception(f"QA generation failed: {str(e)}")

    async def get_qa_records(self):
        """Get the most recent QA pair generation history record"""
        try:
            # Only get the latest record
            record = await self.qa_generations.find_one(
                {"status": "completed"},  # Only get completed records
                sort=[("created_at", -1)]
            )

            if not record:
                return []

            # Get all QA pairs corresponding to this record
            qa_pairs = []
            if record.get("content"):
                # If the record has a content field, use it directly
                qa_pairs = json.loads(record["content"])
            else:
                # Otherwise get from qa_pairs collection
                qa_cursor = self.qa_pairs.find({"generation_id": record["_id"]})
                async for qa in qa_cursor:
                    qa_pairs.append({
                        "question": qa["question"],
                        "answer": qa["answer"]
                    })

            return [{
                "generation_id": str(record["_id"]),
                "input_file": record["input_file"],
                "save_path": record.get("save_path", ""),
                "model_name": record.get("model_name", ""),
                "domain": record.get("domain", ""),
                "status": record["status"],
                "qa_pairs": qa_pairs,
                "created_at": record["created_at"]
            }]
        except Exception as e:
            await self._log_error(str(e), "get_qa_records")
            raise Exception(f"Failed to get records: {str(e)}")