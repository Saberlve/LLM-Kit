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
        self.error_logs = db.llm_kit.error_logs  # 添加错误日志集合
        self.qa_generations = db.llm_kit.qa_generations  # 添加对qa_generations的引用
        self.qa_pairs = db.llm_kit.qa_pairs  # 添加对qa_pairs的引用
        self.executor = ThreadPoolExecutor(max_workers=10)  # 添加线程池

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
            # 获取不带扩展名的文件名
            base_filename = filename.rsplit('.', 1)[0]

            # 检查是否已有记录，如果有，重置进度
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
                # 创建新记录
                generation = QualityControlGeneration(
                    input_file=filename,
                    save_path=save_path,
                    model_name=model_name,
                    status="processing",
                    source_text=json.dumps(content, ensure_ascii=False),
                    progress=0  # 初始化进度为 0
                )
                result = await self.quality_generations.insert_one(generation.dict(by_alias=True))
                generation_id = result.inserted_id

            try:
                # 初始化阶段 - 10%
                await self.quality_generations.update_one(
                    {"_id": generation_id},
                    {"$set": {"progress": 10}}
                )

                # 创建保存目录
                os.makedirs(save_path, exist_ok=True)
                total_qas = len(content)
                processed_qas = 0
                loop = asyncio.get_event_loop()

                # 创建 hparams 对象
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

                # 创建质量控制器实例
                quality_generator = QAQualityGenerator(content, hparams)

                # 任务准备阶段 - 20%
                await self.quality_generations.update_one(
                    {"_id": generation_id},
                    {"$set": {"progress": 20}}
                )

                # 创建任务列表
                tasks = []
                for i, qa in enumerate(content):
                    task = loop.run_in_executor(
                        self.executor,
                        quality_generator.process_single_qa,
                        qa,
                        i,
                        content,
                        AK[0],
                        SK[0]
                    )
                    tasks.append(task)

                # 处理阶段 - 20% to 80%
                optimized_qas = []
                for i, future in enumerate(asyncio.as_completed(tasks)):
                    try:
                        result = await future
                        if result:
                            if isinstance(result, list):
                                optimized_qas.extend(result)
                            else:
                                optimized_qas.append(result)
                        
                        # 更新进度 - 处理小数据时的特殊处理
                        processed_qas += 1
                        if total_qas == 1:
                            # 单个QA时的进度点
                            progress_steps = [30, 40, 50, 60, 70]
                            progress = progress_steps[min(len(progress_steps)-1, i)]
                        else:
                            # 多个QA的正常进度计算
                            progress = int(20 + (processed_qas / total_qas * 60))
                        
                        await self.quality_generations.update_one(
                            {"_id": generation_id},
                            {"$set": {"progress": progress}}
                        )
                    except Exception as e:
                        logger.error(f"处理QA对失败: {str(e)}")
                        continue

                # 保存准备阶段 - 90%
                await self.quality_generations.update_one(
                    {"_id": generation_id},
                    {"$set": {"progress": 90}}
                )

                # 使用简化的文件名格式：原文件名_quality.json
                final_save_path = os.path.join(
                    save_path,
                    f"{base_filename}_quality.json"
                )

                # 保存最终结果
                with open(final_save_path, 'w', encoding='utf-8') as f:
                    json.dump(optimized_qas, f, ensure_ascii=False, indent=4)

                # 先删除之前同文件名的质量控制记录
                await self.quality_records.delete_many({
                    "generation_id": {
                        "$in": [
                            doc["_id"] for doc in await self.quality_generations.find(
                                {"input_file": filename, "_id": {"$ne": generation_id}}
                            ).to_list(None)
                        ]
                    }
                })

                # 保存问答对到数据库
                qa_records = []
                for qa in optimized_qas:
                    if not isinstance(qa, dict) or "question" not in qa or "answer" not in qa:
                        raise Exception(f"Invalid QA pair format: {qa}")

                    qa_record = QAQualityRecord(
                        generation_id=PyObjectId(generation_id),
                        question=qa["question"],
                        answer=qa["answer"],
                        similarity_score=qa.get("similarity_score", 0.0),
                        is_explicit=qa.get("is_explicit", False),
                        is_domain_relative=qa.get("is_domain_relative", False),
                        coverage_rate=qa.get("coverage_rate", 0.0),
                        status="passed"
                    )
                    qa_records.append(qa_record.dict(by_alias=True))

                if qa_records:
                    await self.quality_records.insert_many(qa_records)

                # 更新旧记录状态为已覆盖
                await self.quality_generations.update_many(
                    {"input_file": filename, "_id": {"$ne": generation_id}},
                    {"$set": {"status": "overwritten"}}
                )

                # 完成 - 100%
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
                # 发生错误时只更新状态，保持当前进度
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
        """获取最近一次的质量控制历史记录"""
        try:
            # 只获取最新的一条记录
            record = await self.quality_generations.find_one(
                sort=[("created_at", -1)]
            )
            
            if not record:
                return []
            
            # 获取该记录对应的所有问答对
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

            # 修改：如果source_text是JSON字符串，解析它
            source_text = record["source_text"]
            try:
                source_text = json.loads(source_text)
            except:
                pass  # 如果解析失败，保持原样

            return [{
                "generation_id": str(record["_id"]),
                "input_file": record["input_file"],
                "output_file": record.get("output_file", ""),
                "model_name": record["model_name"],
                "status": record["status"],
                "source_text": source_text,  # 使用解析后的source_text
                "qa_pairs": qa_pairs,
                "created_at": record["created_at"]
            }]
        except Exception as e:
            raise Exception(f"Failed to get records: {str(e)}")

    async def get_all_qa_files(self):
        """获取所有已生成的问答对文件列表，同名文件只返回最新的记录"""
        try:
            # 获取所有已完成的记录
            records = await self.qa_generations.find(
                {"status": "completed"},
                {"save_path": 1, "created_at": 1, "_id": 1}
            ).to_list(None)
            
            # 按文件名分组，保留最新的记录
            filename_dict = {}  # {filename: {"id": id, "filename": filename, "created_at": created_at}}
            
            for record in records:
                if not record.get("save_path"):
                    continue
                    
                # 从save_path中提取文件名
                filename = os.path.basename(record["save_path"])
                created_at = record["created_at"]
                record_id = str(record["_id"])
                
                # 如果文件名已存在，比较创建时间
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
            
            # 转换为列表并按创建时间降序排序
            files = list(filename_dict.values())
            files.sort(key=lambda x: x["created_at"], reverse=True)
            
            return files
            
        except Exception as e:
            await self._log_error(str(e), "get_all_qa_files")
            raise Exception(f"获取问答对文件列表失败: {str(e)}")

    async def get_qa_content(self, filename: str):
        """根据文件名获取问答对内容"""
        try:
            # 查找指定文件名的最新已完成记录
            record = await self.qa_generations.find_one(
                {
                    "input_file": filename,  # 使用保存的文件名查询
                    "status": "completed"
                },
                sort=[("created_at", -1)]
            )
            
            if not record:
                raise Exception("文件不存在或未完成生成")
            
            # 直接从记录中获取问答对内容
            if record.get("content"):
                qa_pairs = json.loads(record["content"])
            else:
                # 如果记录中没有内容，从文件中读取
                try:
                    with open(record["save_path"], 'r', encoding='utf-8') as f:
                        qa_pairs = json.load(f)
                except Exception as e:
                    raise Exception(f"读取问答对文件失败: {str(e)}")
                
            return {
                "filename": filename,
                "created_at": record["created_at"],
                "qa_pairs": qa_pairs,
                "save_path": record.get("save_path", "")
            }
        except Exception as e:
            await self._log_error(str(e), "get_qa_content")
            raise Exception(f"获取问答对内容失败: {str(e)}")

    async def get_qa_content_by_id(self, record_id: str):
        """根据记录ID获取问答对内容"""
        try:
            # 将字符串ID转换为ObjectId
            from bson import ObjectId
            record = await self.qa_generations.find_one({"_id": ObjectId(record_id)})
            
            if not record:
                raise Exception("记录不存在")
            
            if record["status"] != "completed":
                raise Exception("该记录尚未完成生成")
            
            # 直接从记录中获取问答对内容
            if record.get("content"):
                qa_pairs = json.loads(record["content"])
            else:
                # 如果记录中没有内容，从文件中读取
                try:
                    with open(record["save_path"], 'r', encoding='utf-8') as f:
                        qa_pairs = json.load(f)
                except Exception as e:
                    raise Exception(f"读取问答对文件失败: {str(e)}")
                
            return {
                "id": str(record["_id"]),
                "filename": os.path.basename(record["save_path"]),
                "created_at": record["created_at"],
                "qa_pairs": qa_pairs,
                "save_path": record.get("save_path", "")
            }
        except Exception as e:
            await self._log_error(str(e), "get_qa_content_by_id")
            raise Exception(f"获取问答对内容失败: {str(e)}")