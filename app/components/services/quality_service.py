from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from quality_control.quality_control import QAQualityGenerator
from utils.hparams import HyperParams
from app.components.models.mongodb import QAQualityRecord, QualityControlGeneration, PyObjectId
import json
import os
from typing import List, Optional
import asyncio
from concurrent.futures import ThreadPoolExecutor
import logging
from bson import ObjectId

logger = logging.getLogger(__name__)

class QualityService:
    def __init__(self, db: AsyncIOMotorClient):
        self.db = db
        self.quality_generations = db.llm_kit.quality_generations
        self.quality_records = db.llm_kit.quality_records
        self.error_logs = db.llm_kit.error_logs  # Add error log collection
        self.qa_generations = db.llm_kit.qa_generations  # Add reference to qa_generations
        self.qa_pairs = db.llm_kit.qa_pairs  # Add reference to qa_pairs
        self.dataset_entries = db.llm_kit.dataset_entries  # Add reference to dataset_entries

    async def _log_error(self, error_message: str, source: str, stack_trace: str = None):
        error_log = {
            "timestamp": datetime.utcnow(),
            "error_message": error_message,
            "source": source,
            "stack_trace": stack_trace
        }
        await self.error_logs.insert_one(error_log)

    def process_single_qa_with_api(self, qa: dict, index: int, total_content: List[dict],
                                   ak: str, sk: str, model_name: str, domain: str,
                                   similarity_rate: float, coverage_rate: float, max_attempts: int):
        """Synchronously process a single QA pair using actual quality control logic"""
        try:
            # Store original QA for comparison
            original_qa = qa.copy()

            # Get nearby QAs for context (similar to quality_control implementation)
            nearby_qas = self._get_nearby_qas(total_content, index)

            # Apply quality evaluation and regeneration logic
            optimized_qa = self._evaluate_qa_and_regenerate(qa, nearby_qas, ak, sk, model_name, domain, similarity_rate, max_attempts)

            if optimized_qa:
                # Apply coverage check and potentially generate more QAs
                final_qa = self._check_coverage_and_regenerate(optimized_qa, nearby_qas, ak, sk, model_name, domain, coverage_rate, max_attempts)

                if final_qa:
                    # Calculate actual scores
                    similarity_score = self._calculate_similarity_score(final_qa)
                    coverage_score = self._calculate_coverage_score(final_qa, nearby_qas)

                    # Return optimized QA with scores
                    return {
                        "question": final_qa["question"],
                        "answer": final_qa["answer"],
                        "text": final_qa.get("text", ""),
                        "original_question": original_qa["question"],
                        "original_answer": original_qa["answer"],
                        "optimized": True,
                        "similarity_score": similarity_score,
                        "coverage_score": coverage_score,
                        "index": index
                    }

            # If optimization failed, return original QA with calculated scores
            similarity_score = self._calculate_similarity_score(original_qa)
            coverage_score = self._calculate_coverage_score(original_qa, nearby_qas)

            return {
                "question": original_qa["question"],
                "answer": original_qa["answer"],
                "text": original_qa.get("text", ""),
                "original_question": original_qa["question"],
                "original_answer": original_qa["answer"],
                "optimized": False,
                "similarity_score": similarity_score,
                "coverage_score": coverage_score,
                "index": index
            }

        except Exception as e:
            logger.error(f"处理QA对时出错: {str(e)}")
            # If processing fails, return original QA with error info
            return {
                "question": qa["question"],
                "answer": qa["answer"],
                "text": qa.get("text", ""),
                "original_question": qa["question"],
                "original_answer": qa["answer"],
                "optimized": False,
                "error": str(e),
                "similarity_score": 0.0,
                "coverage_score": 0.0,
                "index": index
            }

    def _get_nearby_qas(self, qas: List[dict], index: int) -> List[dict]:
        """Get nearby QA pairs based on text similarity (from quality_control.py)"""
        if index >= len(qas):
            return []

        target_text = qas[index].get('text', '')
        nearby_qas = []
        nearby_qas.append(qas[index])

        # Check backward
        j = index - 1
        while j >= 0 and target_text in qas[j].get('text', ''):
            nearby_qas.append(qas[j])
            j -= 1

        # Check forward
        j = index + 1
        while j < len(qas) and target_text in qas[j].get('text', ''):
            nearby_qas.append(qas[j])
            j += 1

        return nearby_qas

    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """Calculate similarity between two strings using Levenshtein ratio"""
        try:
            from Levenshtein import ratio
            return ratio(str1, str2)
        except ImportError:
            # Fallback to simple character-based similarity if Levenshtein is not available
            if not str1 or not str2:
                return 0.0
            set1, set2 = set(str1.lower()), set(str2.lower())
            intersection = len(set1.intersection(set2))
            union = len(set1.union(set2))
            return intersection / union if union > 0 else 0.0

    def _calculate_similarity_score(self, qa: dict) -> float:
        """Calculate similarity score between answer and text"""
        try:
            answer = qa.get('answer', '')
            text = qa.get('text', '')

            if not answer or not text:
                return 0.0

            # Split by Chinese period as in original implementation
            answer_list = answer.split('。')
            text_list = text.split('。')

            # Calculate maximum similarity between any answer part and text part
            max_ratio = 0.0
            for answer_part in answer_list:
                for text_part in text_list:
                    if answer_part.strip() and text_part.strip():
                        ratio = self._calculate_similarity(answer_part.strip(), text_part.strip())
                        max_ratio = max(max_ratio, ratio)

            return max_ratio
        except Exception as e:
            logger.error(f"Error calculating similarity score: {str(e)}")
            return 0.0

    def _calculate_coverage_score(self, qa: dict, nearby_qas: List[dict]) -> float:
        """Calculate coverage score using token-based approach"""
        try:
            import tiktoken
            tokenizer = tiktoken.encoding_for_model("gpt-3.5-turbo")

            text = qa.get('text', '')
            if not text:
                return 0.0

            text_tokens = set(tokenizer.encode(text))
            answer_tokens = set()

            # Collect tokens from nearby QA answers
            for nearby_qa in nearby_qas:
                answer = nearby_qa.get('answer', '')
                if answer:
                    answer_tokens.update(tokenizer.encode(answer))

            if not text_tokens:
                return 0.0

            remaining_tokens = text_tokens - answer_tokens
            coverage = 1 - len(remaining_tokens) / len(text_tokens)
            return max(0.0, min(1.0, coverage))

        except Exception as e:
            logger.error(f"Error calculating coverage score: {str(e)}")
            return 0.0

    def _is_relative(self, question: str, ak: str, sk: str, model_name: str, domain: str) -> bool:
        """Check if question is relative to the domain"""
        try:
            from utils.helper import generate
            from model_api.prompts import PROMPT_DICT

            # Replace domain placeholder in prompt
            prompt_template = PROMPT_DICT.get('RELATIVE',
                "Please determine whether the given question <question> is relative to the 'domain'. Based on the following two conditions, provide <reply>: If it is likely, <reply> should be 1; if it is unlikely, <reply> should be 0.\n<question>: {}\n<reply>:")
            prompt_template = prompt_template.replace("'domain'", domain)

            response = generate(question, model_name, 'RELATIVE', ak, sk)
            # Count occurrences of '1' vs '0' in response
            return response.count('1') > response.count('0')
        except Exception as e:
            logger.error(f"Error checking domain relevance: {str(e)}")
            return True  # Default to True if check fails

    def _is_explicit(self, question: str, ak: str, sk: str, model_name: str) -> bool:
        """Check if question is explicit and specific"""
        try:
            from utils.helper import generate

            response = generate(question, model_name, 'EXPLICIT', ak, sk)
            # Count occurrences of '1' vs '0' in response
            return response.count('1') > response.count('0')
        except Exception as e:
            logger.error(f"Error checking question explicitness: {str(e)}")
            return True  # Default to True if check fails

    def _regenerate_qa(self, qa: dict, nearby_qas: List[dict], ak: str, sk: str, model_name: str) -> Optional[dict]:
        """Regenerate QA pair using API"""
        try:
            from utils.helper import generate, extract_qa

            text = qa.get('text', '')
            if not text:
                return None

            response = generate(text, model_name, 'ToQA', ak, sk)
            if response:
                new_qas = extract_qa(response)
                if new_qas:
                    # Find the most suitable QA from generated ones
                    selected_qa = self._find_suitable_qa(new_qas, nearby_qas) if len(new_qas) > 1 else new_qas[0]
                    selected_qa['text'] = text
                    return selected_qa
        except Exception as e:
            logger.error(f"Error regenerating QA pair: {str(e)}")
        return None

    def _find_suitable_qa(self, new_qas: List[dict], nearby_qas: List[dict]) -> dict:
        """Find the most suitable QA from generated ones"""
        if not new_qas:
            return {}

        if not nearby_qas:
            return new_qas[0]

        best_index = 0
        min_similarity = 1.0

        for i, new_qa in enumerate(new_qas):
            new_question = new_qa.get('question', '')
            for old_qa in nearby_qas:
                old_question = old_qa.get('question', '')
                if new_question and old_question:
                    similarity = self._calculate_similarity(new_question, old_question)
                    if similarity < min_similarity:
                        min_similarity = similarity
                        best_index = i

        return new_qas[best_index]

    def _evaluate_qa_and_regenerate(self, qa: dict, nearby_qas: List[dict], ak: str, sk: str,
                                   model_name: str, domain: str, similarity_rate: float, max_attempts: int) -> Optional[dict]:
        """Evaluate QA pair and regenerate if needed"""
        current_qa = qa.copy()

        for attempt in range(max_attempts):
            try:
                # Calculate similarity score
                similarity_score = self._calculate_similarity_score(current_qa)
                current_qa['ratio'] = similarity_score

                # Check if question is explicit and domain-relevant
                is_explicit = self._is_explicit(current_qa.get('question', ''), ak, sk, model_name)
                is_relevant = self._is_relative(current_qa.get('question', ''), ak, sk, model_name, domain)

                # If QA meets quality criteria, return it
                if (similarity_score >= similarity_rate and is_explicit and is_relevant):
                    return current_qa

                # Otherwise, try to regenerate
                regenerated_qa = self._regenerate_qa(current_qa, nearby_qas, ak, sk, model_name)
                if regenerated_qa:
                    current_qa = regenerated_qa
                else:
                    break  # If regeneration fails, stop trying

            except Exception as e:
                logger.error(f"Error during quality evaluation attempt {attempt + 1}: {str(e)}")
                break

        return current_qa

    def _generate_more_qas(self, qa: dict, ak: str, sk: str, model_name: str, max_attempts: int) -> Optional[List[dict]]:
        """Generate more QA pairs for better coverage"""
        try:
            from utils.helper import generate, extract_qa

            text = qa.get('text', '')
            if not text:
                return None

            for attempt in range(max_attempts):
                try:
                    response = generate(text, model_name, 'MORE_QA', ak, sk)
                    if response:
                        new_qas = extract_qa(response)
                        if new_qas:
                            # Add text to each generated QA
                            for new_qa in new_qas:
                                new_qa['text'] = text
                            return new_qas
                except Exception as e:
                    logger.error(f"Error generating more QAs attempt {attempt + 1}: {str(e)}")

        except Exception as e:
            logger.error(f"Error in generate_more_qas: {str(e)}")
        return None

    def _check_coverage_and_regenerate(self, qa: dict, nearby_qas: List[dict], ak: str, sk: str,
                                     model_name: str, domain: str, coverage_rate: float, max_attempts: int) -> dict:
        """Check coverage and regenerate more QAs if needed"""
        try:
            coverage_score = self._calculate_coverage_score(qa, nearby_qas)

            if coverage_score < coverage_rate:
                more_qas = self._generate_more_qas(qa, ak, sk, model_name, max_attempts)
                if more_qas and len(more_qas) > 0:
                    # Return the first generated QA or the best one
                    return more_qas[0]

        except Exception as e:
            logger.error(f"Error checking coverage: {str(e)}")

        return qa

    async def evaluate_and_optimize_qa(
            self,
            content: List[dict],
            filename: str,
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
            existing_record = await self.quality_generations.find_one({
                "input_file": filename,
                "status": {"$in": ["processing", "completed", "aborted", "failed"]}
            })

            if existing_record:
                await self.quality_generations.update_one(
                    {"_id": existing_record["_id"]},
                    {
                        "$set": {
                            "status": "processing",
                            "progress": 0,
                            "model_name": model_name,
                            "source_text": json.dumps(content, ensure_ascii=False),
                            "start_time": datetime.now(timezone.utc),
                            "item_info": {
                                "total_items": len(content),
                                "processed_items": 0
                            }
                        }
                    }
                )
                generation_id = existing_record["_id"]
                logger.info(f"重新使用现有的质量评估记录，ID: {generation_id}")
            else:
                # Create new record using dictionary to avoid model validation issues
                generation_data = {
                    "input_file": filename,
                    "model_name": model_name,
                    "status": "processing",
                    "source_text": json.dumps(content, ensure_ascii=False),
                    "progress": 0,
                    "start_time": datetime.now(timezone.utc),
                    "created_at": datetime.now(timezone.utc),
                    "item_info": {
                        "total_items": len(content),
                        "processed_items": 0
                    }
                }
                result = await self.quality_generations.insert_one(generation_data)
                generation_id = result.inserted_id
                logger.info(f"创建了新的质量评估记录，ID: {generation_id}")

            try:
                # Initialization phase - 10%
                await self.quality_generations.update_one(
                    {"_id": generation_id},
                    {"$set": {"progress": 10}}
                )

                # Create save directory
                total_qas = len(content)
                processed_qas = 0

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
                            self.process_single_qa_with_api,
                            qa,
                            i,
                            content,
                            AK[i % len(AK)],
                            SK[i % len(SK)],
                            model_name,
                            domain,
                            similarity_rate,
                            coverage_rate,
                            max_attempts
                        )
                        futures.append(future)

                    # Processing phase - 20% to 80%
                    optimized_qas = []
                    start_time = datetime.now(timezone.utc)
                    
                    for i, future in enumerate(asyncio.as_completed(futures)):
                        # 定期检查任务是否被中止
                        record_check = await self.quality_generations.find_one({"_id": generation_id})
                        if record_check.get("status") == "aborted":
                            logger.info(f"质量评估任务 {generation_id} 被用户中止")
                            raise Exception("Task was manually aborted by user")
                            
                        try:
                            result = await future
                            if result:
                                optimized_qas.append(result)

                            # Update progress
                            processed_qas += 1
                            
                            # 更新进度 - 特殊处理小数据
                            if total_qas == 1:
                                # 单个QA的进度点
                                progress_steps = [30, 40, 50, 60, 70]
                                progress = progress_steps[min(len(progress_steps)-1, i)]
                            else:
                                # 多个QA的正常进度计算
                                progress = int(20 + (processed_qas / total_qas * 60))
                                
                            # 计算预估完成时间
                            elapsed_time = (datetime.now(timezone.utc) - start_time).total_seconds()
                            if processed_qas > 0 and processed_qas < total_qas:
                                # 基于已处理的QA和已用时间估计总时间
                                avg_time_per_qa = elapsed_time / processed_qas
                                remaining_qas = total_qas - processed_qas
                                remaining_seconds = avg_time_per_qa * remaining_qas
                                estimated_completion = datetime.now(timezone.utc) + timedelta(seconds=remaining_seconds)
                                
                                # 更新进度信息
                                await self.quality_generations.update_one(
                                    {"_id": generation_id},
                                    {"$set": {
                                        "progress": progress,
                                        "estimated_completion_time": estimated_completion,
                                        "item_info": {
                                            "total_items": total_qas,
                                            "processed_items": processed_qas
                                        }
                                    }}
                                )
                            else:
                                # 更新进度（无估计时间）
                                await self.quality_generations.update_one(
                                    {"_id": generation_id},
                                    {"$set": {
                                        "progress": progress,
                                        "item_info": {
                                            "total_items": total_qas,
                                            "processed_items": processed_qas
                                        }
                                    }}
                                )
                        except Exception as e:
                            logger.error(f"处理QA对失败: {str(e)}")
                            continue

                    # Save preparation phase - 90%
                    await self.quality_generations.update_one(
                        {"_id": generation_id},
                        {"$set": {"progress": 90}}
                    )

                    if not optimized_qas:
                        raise Exception("No optimized QA pairs were generated")

                    # 将QA对序列化为JSON字符串
                    qa_json = json.dumps(optimized_qas, ensure_ascii=False)
                    
                
   

                    # 将结果保存到数据库中的dataset_entries集合
                    dataset_entry = {
                        "name": f"QA-Optimized-{base_filename}",
                        "description": f"Quality optimized QA from {filename} using {model_name}",
                        "pool_id": 3,  # 假设这是质量评估池ID
                        "kind": 3,     # 表示这是质量评估数据集
                        "file_data": qa_json,
                        "created_at": datetime.now(timezone.utc),
                        "model_name": model_name,
                        "domain": domain,
                        "is_qa": True
                    }
                    
                    # 插入数据集
                    dataset_result = await self.dataset_entries.insert_one(dataset_entry)
                    dataset_id = str(dataset_result.inserted_id)
                    
                    # 更新记录状态，添加数据集ID
                    await self.quality_generations.update_one(
                        {"_id": generation_id},
                        {
                            "$set": {
                                "status": "completed",
                                "progress": 100,
                                "content": qa_json,
                                "dataset_id": dataset_id,
                                "item_info": {
                                    "total_items": total_qas,
                                    "processed_items": total_qas
                                }
                            }
                        }
                    )

                    return {
                        "generation_id": str(generation_id),
                        "dataset_id": dataset_id,
                        "filename": os.path.basename(filename),
                        "qa_pairs": optimized_qas,
                        "source_text": json.dumps(content, ensure_ascii=False)
                    }

            except Exception as e:
                # When an error occurs, only update status, maintain current progress
                current_progress = await self.quality_generations.find_one(
                    {"_id": generation_id},
                    {"progress": 1}
                )
                
                await self.quality_generations.update_one(
                    {"_id": generation_id},
                    {"$set": {
                        "status": "failed" if "aborted" not in str(e) else "aborted",
                        "error_message": str(e),
                        "progress": current_progress.get("progress", 0)
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
        """Get the most recent quality control history records"""
        try:
            # Get all records, sorted by creation time
            cursor = self.quality_generations.find(
                {"status": {"$in": ["completed", "failed", "aborted"]}}
            ).sort("created_at", -1)
            
            records = []
            async for record in cursor:
                # For each record, get content if available
                qa_pairs = []
                if "content" in record and record["content"]:
                    try:
                        if isinstance(record["content"], str):
                            qa_pairs = json.loads(record["content"])
                        else:
                            qa_pairs = record["content"]
                    except json.JSONDecodeError:
                        qa_pairs = []
                
                # Format the record
                records.append({
                    "generation_id": str(record["_id"]),
                    "input_file": record["input_file"],
                    "dataset_id": record.get("dataset_id", ""),
                    "model_name": record["model_name"],
                    "status": record["status"],
                    "qa_count": len(qa_pairs),
                    "created_at": record["created_at"]
                })
                
                # 限制返回记录数量
                if len(records) >= 10:
                    break
            
            return records
        except Exception as e:
            await self._log_error(str(e), "get_quality_records")
            raise Exception(f"Failed to get records: {str(e)}")

    async def get_all_qa_files(self):
        """Get a list of all generated QA pair files, including optimized ones"""
        try:
            # 首先从dataset_entries中获取质量评估的数据集
            cursor = self.dataset_entries.find(
                {"is_qa": True}
            ).sort("created_at", -1)
            
            files = []
            async for entry in cursor:
                file_id = str(entry["_id"])
                filename = entry["name"]
                created_at = entry["created_at"]
                
                # 添加到文件列表
                files.append({
                    "id": file_id,
                    "filename": filename,
                    "created_at": created_at.isoformat() if isinstance(created_at, datetime) else str(created_at)
                })
            
            # # 然后从quality_generations中获取记录
            # cursor = self.quality_generations.find(
            #     {"status": "completed"}
            # ).sort("created_at", -1)
            
            # async for record in cursor:
            #     # 如果已经有对应的数据集ID，跳过（避免重复）
            #     if "dataset_id" in record and any(f["id"] == record["dataset_id"] for f in files):
            #         continue
                
            #     file_id = str(record["_id"])
            #     filename = record["input_file"]
            #     created_at = record["created_at"]
                
            #     # 添加到文件列表
            #     files.append({
            #         "id": file_id,
            #         "filename": f"{filename}_optimized",
            #         "created_at": created_at.isoformat() if isinstance(created_at, datetime) else str(created_at)
            #     })
            
            # # 还可以添加原始QA文件（未优化的）
            # qa_cursor = self.qa_generations.find(
            #     {"status": "completed"}
            # ).sort("created_at", -1)
            
            # async for qa_record in qa_cursor:
            #     file_id = str(qa_record["_id"])
            #     filename = qa_record["input_file"]
            #     created_at = qa_record["created_at"]
                
            #     # 添加到文件列表
            #     files.append({
            #         "id": file_id,
            #         "filename": filename,
            #         "created_at": created_at.isoformat() if isinstance(created_at, datetime) else str(created_at)
            #     })
                
            #     # 限制返回文件数量
            #     if len(files) >= 30:
            #         break
            
            return files
        except Exception as e:
            await self._log_error(str(e), "get_all_qa_files")
            raise Exception(f"Failed to get QA pair file list: {str(e)}")

    async def get_qa_content_by_id(self, record_id: str):
        """Get QA pair content based on record ID"""
        try:
            # 首先检查是否是dataset_entries中的记录
            try:
                obj_id = ObjectId(record_id)
                dataset = await self.dataset_entries.find_one({"_id": obj_id})
                
                if dataset:
                    # 从dataset_entries中获取内容
                    if "file_data" in dataset:
                        content = dataset["file_data"]
                        if isinstance(content, str):
                            qa_pairs = json.loads(content)
                        else:
                            qa_pairs = content
                        
                        return {
                            "id": record_id,
                            "filename": dataset["name"],
                            "created_at": dataset["created_at"],
                            "qa_pairs": qa_pairs,
                            "content": qa_pairs
                        }
            except:
                pass
            
            # 然后尝试quality_generations
            record = await self.quality_generations.find_one({"_id": ObjectId(record_id)})
            
            if not record:
                # 最后尝试qa_generations
                record = await self.qa_generations.find_one({"_id": ObjectId(record_id)})
                
                if not record:
                    raise Exception("Record does not exist")
            
            if record["status"] != "completed":
                raise Exception("This record has not completed generation")
            
            # 获取QA内容
            qa_pairs = []
            if "content" in record and record["content"]:
                if isinstance(record["content"], str):
                    try:
                        qa_pairs = json.loads(record["content"])
                    except json.JSONDecodeError:
                        qa_pairs = []
                else:
                    qa_pairs = record["content"]
            
            # 如果内容为空，尝试从文件读取
          
            
            return {
                "id": record_id,
                "filename": record["input_file"],
                "created_at": record["created_at"],
                "qa_pairs": qa_pairs,
                "content": qa_pairs
            }
        except Exception as e:
            await self._log_error(str(e), "get_qa_content_by_id")
            raise Exception(f"Failed to get QA content: {str(e)}")