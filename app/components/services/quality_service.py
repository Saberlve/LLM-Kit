from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from quality_control.quality_control import QAQualityGenerator
from utils.hparams import HyperParams
from app.components.models.mongodb import QAQualityRecord, QualityControlGeneration, PyObjectId
import json
import os
from typing import List
import asyncio
from concurrent.futures import ThreadPoolExecutor
import logging

logger = logging.getLogger(__name__)

class QualityService:
    def __init__(self, db: AsyncIOMotorClient):
        self.db = db
        self.quality_generations = db.llm_kit.quality_generations
        self.quality_records = db.llm_kit.quality_records
        self.error_logs = db.llm_kit.error_logs  # Add error log collection
        self.qa_generations = db.llm_kit.qa_generations  # Add reference to qa_generations
        self.qa_pairs = db.llm_kit.qa_pairs  # Add reference to qa_pairs

    async def _log_error(self, error_message: str, source: str, stack_trace: str = None):
        error_log = {
            "timestamp": datetime.utcnow(),
            "error_message": error_message,
            "source": source,
            "stack_trace": stack_trace
        }
        await self.error_logs.insert_one(error_log)

    async def evaluate_and_optimize_qa(
            self,
            content: List[dict],
            filename: str,
            save_path: str,
            SK: list,
            AK: list,
            parallel_num: int,
            model_name: str,
            similarity_rate: float,
            coverage_rate: float,
            max_attempts: int,
            domain: str
    ):
        generation_id = None
        try:
            # Get filename without extension
            base_filename = filename.rsplit('.', 1)[0]

            # Check if record already exists, if so, reset progress
            existing_record = await self.quality_generations.find_one({"input_file": filename})
            if existing_record:
                await self.quality_generations.update_one(
                    {"_id": existing_record["_id"]},
                    {
                        "$set": {
                            "status": "processing",
                            "progress": 0,
                            "model_name": model_name,
                            "save_path": save_path
                        }
                    }
                )
                generation_id = existing_record["_id"]
            else:
                # Create new record
                generation = QualityControlGeneration(
                    input_file=filename,
                    save_path=save_path,
                    model_name=model_name,
                    status="processing",
                    source_text=json.dumps(content, ensure_ascii=False),
                    progress=0  # Initialize progress to 0
                )
                result = await self.quality_generations.insert_one(generation.dict(by_alias=True))
                generation_id = result.inserted_id

            try:
                # Initialization phase - 10%
                await self.quality_generations.update_one(
                    {"_id": generation_id},
                    {"$set": {"progress": 10}}
                )

                # Create save directory
                os.makedirs(save_path, exist_ok=True)
                total_qas = len(content)
                processed_qas = 0

                # Create hparams object
                hparams = HyperParams(
                    file_path=filename,
                    save_path=save_path,
                    SK=SK,
                    AK=AK,
                    parallel_num=parallel_num,
                    model_name=model_name,
                    similarity_rate=similarity_rate,
                    coverage_rate=coverage_rate,
                    max_attempts=max_attempts,
                    domain=domain
                )

                # Create quality controller instance
                quality_generator = QAQualityGenerator(content, hparams)

                # Task preparation phase - 20%
                await self.quality_generations.update_one(
                    {"_id": generation_id},
                    {"$set": {"progress": 20}}
                )

                # Use context manager to create thread pool
                with ThreadPoolExecutor(max_workers=min(10, parallel_num)) as executor:
                    loop = asyncio.get_event_loop()
                    futures = []

                    # Create task list
                    for i, qa in enumerate(content):
                        future = loop.run_in_executor(
                            executor,
                            quality_generator.process_single_qa,
                            qa,
                            i,
                            content,
                            AK[i % len(AK)],
                            SK[i % len(SK)]
                        )
                        futures.append(future)

                    # Processing phase - 20% to 80%
                    optimized_qas = []
                    for i, future in enumerate(asyncio.as_completed(futures)):
                        try:
                            result = await future
                            if result:
                                if isinstance(result, list):
                                    optimized_qas.extend(result)
                                else:
                                    optimized_qas.append(result)

                            # Update progress - special handling for small data
                            processed_qas += 1
                            if total_qas == 1:
                                # Progress points for single QA
                                progress_steps = [30, 40, 50, 60, 70]
                                progress = progress_steps[min(len(progress_steps)-1, i)]
                            else:
                                # Normal progress calculation for multiple QAs
                                progress = int(20 + (processed_qas / total_qas * 60))

                            await self.quality_generations.update_one(
                                {"_id": generation_id},
                                {"$set": {"progress": progress}}
                            )
                        except Exception as e:
                            logger.error(f"Failed to process QA pair: {str(e)}")
                            continue

                    # Save preparation phase - 90%
                    await self.quality_generations.update_one(
                        {"_id": generation_id},
                        {"$set": {"progress": 90}}
                    )

                    if not optimized_qas:
                        raise Exception("No optimized QA pairs were generated")

                    # Use simplified filename format: original_filename_quality.json
                    final_save_path = os.path.join(
                        save_path,
                        f"{base_filename}_quality.json"
                    )

                    # Save final results
                    with open(final_save_path, 'w', encoding='utf-8') as f:
                        json.dump(optimized_qas, f, ensure_ascii=False, indent=4)

                    # Complete - 100%
                    await self.quality_generations.update_one(
                        {"_id": generation_id},
                        {
                            "$set": {
                                "status": "completed",
                                "save_path": final_save_path,
                                "progress": 100
                            }
                        }
                    )

                    return {
                        "generation_id": str(generation_id),
                        "filename": os.path.basename(final_save_path),
                        "qa_pairs": optimized_qas,
                        "source_text": json.dumps(content, ensure_ascii=False),
                        "save_path": final_save_path
                    }

            except Exception as e:
                # When an error occurs, only update status, maintain current progress
                await self.quality_generations.update_one(
                    {"_id": generation_id},
                    {"$set": {
                        "status": "failed",
                        "error_message": str(e)
                    }}
                )
                raise e

        except Exception as e:
            import traceback
            await self._log_error(str(e), "evaluate_and_optimize_qa", traceback.format_exc())
            if generation_id:
                await self.quality_generations.update_one(
                    {"_id": generation_id},
                    {
                        "$set": {
                            "status": "failed",
                            "error_message": str(e)
                        }
                    }
                )
            raise Exception(f"Quality control failed: {str(e)}")

    async def get_quality_records(self):
        """Get the most recent quality control history record"""
        try:
            # Only get the latest record
            record = await self.quality_generations.find_one(
                sort=[("created_at", -1)]
            )

            if not record:
                return []

            # Get all QA pairs corresponding to this record
            qa_cursor = self.quality_records.find({"generation_id": record["_id"]})
            qa_pairs = []
            async for qa in qa_cursor:
                qa_pairs.append({
                    "question": qa["question"],
                    "answer": qa["answer"],
                    "similarity_score": qa["similarity_score"],
                    "coverage_rate": qa["coverage_rate"],
                    "status": qa["status"]
                })

            # Modification: If source_text is a JSON string, parse it
            source_text = record["source_text"]
            try:
                source_text = json.loads(source_text)
            except:
                pass  # If parsing fails, keep as is

            return [{
                "generation_id": str(record["_id"]),
                "input_file": record["input_file"],
                "output_file": record.get("output_file", ""),
                "model_name": record["model_name"],
                "status": record["status"],
                "source_text": source_text,  # Use parsed source_text
                "qa_pairs": qa_pairs,
                "created_at": record["created_at"]
            }]
        except Exception as e:
            raise Exception(f"Failed to get records: {str(e)}")

    async def get_all_qa_files(self):
        """Get a list of all generated QA pair files, only returning the latest record for files with the same name"""
        try:
            # Get all completed records
            records = await self.qa_generations.find(
                {"status": "completed"},
                {"save_path": 1, "created_at": 1, "_id": 1}
            ).to_list(None)

            # Group by filename, keep the latest record
            filename_dict = {}  # {filename: {"id": id, "filename": filename, "created_at": created_at}}

            for record in records:
                if not record.get("save_path"):
                    continue

                # Extract filename from save_path
                filename = os.path.basename(record["save_path"])
                created_at = record["created_at"]
                record_id = str(record["_id"])

                # If filename already exists, compare creation time
                if filename in filename_dict:
                    if created_at > filename_dict[filename]["created_at"]:
                        filename_dict[filename] = {
                            "id": record_id,
                            "filename": filename,
                            "created_at": created_at
                        }
                else:
                    filename_dict[filename] = {
                        "id": record_id,
                        "filename": filename,
                        "created_at": created_at
                    }

            # Convert to list and sort by creation time in descending order
            files = list(filename_dict.values())
            files.sort(key=lambda x: x["created_at"], reverse=True)

            return files

        except Exception as e:
            await self._log_error(str(e), "get_all_qa_files")
            raise Exception(f"Failed to get QA pair file list: {str(e)}")

    async def get_qa_content(self, filename: str):
        """Get QA pair content based on filename"""
        try:
            # Find the latest completed record for the specified filename
            record = await self.qa_generations.find_one(
                {
                    "input_file": filename,  # Query using the saved filename
                    "status": "completed"
                },
                sort=[("created_at", -1)]
            )

            if not record:
                raise Exception("File does not exist or generation not completed")

            # Get QA pair content directly from the record
            if record.get("content"):
                qa_pairs = json.loads(record["content"])
            else:
                # If there's no content in the record, read from the file
                try:
                    with open(record["save_path"], 'r', encoding='utf-8') as f:
                        qa_pairs = json.load(f)
                except Exception as e:
                    raise Exception(f"Failed to read QA pair file: {str(e)}")

            return {
                "filename": filename,
                "created_at": record["created_at"],
                "qa_pairs": qa_pairs,
                "save_path": record.get("save_path", "")
            }
        except Exception as e:
            await self._log_error(str(e), "get_qa_content")
            raise Exception(f"Failed to get QA pair content: {str(e)}")

    async def get_qa_content_by_id(self, record_id: str):
        """Get QA pair content based on record ID"""
        try:
            # Convert string ID to ObjectId
            from bson import ObjectId
            record = await self.qa_generations.find_one({"_id": ObjectId(record_id)})

            if not record:
                raise Exception("Record does not exist")

            if record["status"] != "completed":
                raise Exception("This record has not completed generation")

            # Get QA pair content directly from the record
            if record.get("content"):
                qa_pairs = json.loads(record["content"])
            else:
                # If there's no content in the record, read from the file
                try:
                    with open(record["save_path"], 'r', encoding='utf-8') as f:
                        qa_pairs = json.load(f)
                except Exception as e:
                    raise Exception(f"Failed to read QA pair file: {str(e)}")

            return {
                "id": str(record["_id"]),
                "filename": os.path.basename(record["save_path"]),
                "created_at": record["created_at"],
                "qa_pairs": qa_pairs,
                "save_path": record.get("save_path", "")
            }
        except Exception as e:
            await self._log_error(str(e), "get_qa_content_by_id")
            raise Exception(f"Failed to get QA pair content: {str(e)}")