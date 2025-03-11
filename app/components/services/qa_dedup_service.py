from deduplication.qa_deduplication import QADeduplication
from utils.hparams import DedupParams
from motor.motor_asyncio import AsyncIOMotorClient
from app.components.models.mongodb import DedupRecord, KeptQAPair, DeletedQAPair
import json
from typing import List
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
        self.executor = ThreadPoolExecutor(max_workers=10)  # 添加线程池

    async def _log_error(self, error_message: str, source: str, stack_trace: str = None):
        error_log = {
            "timestamp": datetime.utcnow(),
            "error_message": error_message,
            "source": source,
            "stack_trace": stack_trace
        }
        await self.error_logs.insert_one(error_log)

    def _generate_output_paths(self, timestamp: datetime):
        """生成输出文件路径"""
        date_str = timestamp.strftime("%Y%m%d_%H%M%S")
        output_file = os.path.join(self.base_output_dir, f"dedup_result_{date_str}.json")
        deleted_file = os.path.join(self.base_output_dir, f"deleted_pairs_{date_str}.json")
        return output_file, deleted_file

    async def update_progress(self, record_id: str, progress: int):
        """更新进度（带节流控制）"""
        current_time = time.time()
        last_update = self.last_progress_update.get(record_id, 0)
        
        # 每0.5秒最多更新一次进度
        if current_time - last_update >= 0.5:
            await self.dedup_records.update_one(
                {"_id": ObjectId(record_id)},
                {"$set": {"progress": progress}}
            )
            self.last_progress_update[record_id] = current_time

    async def get_quality_content(self, file_id: str):
        """根据文件ID获取quality文件内容"""
        try:
            # 查找指定ID的quality记录
            record = await self.quality_generations.find_one({"_id": ObjectId(file_id)})
            
            if not record:
                raise Exception(f"未找到ID为 {file_id} 的quality记录")
            
            if not record.get("save_path") or not os.path.exists(record["save_path"]):
                raise Exception(f"文件路径不存在: {record.get('save_path')}")
            
            # 读取文件内容
            with open(record["save_path"], 'r', encoding='utf-8') as f:
                content = json.load(f)
            
            return {
                "filename": record["input_file"],
                "content": content,
                "created_at": record["created_at"]
            }
        except Exception as e:
            await self._log_error(str(e), "get_quality_content")
            raise Exception(f"获取quality文件内容失败: {str(e)}")

    async def get_dedup_content(self, file_id: str):
        """根据文件ID获取去重后的文件内容"""
        try:
            # 查找指定ID的去重记录
            record = await self.dedup_records.find_one({"_id": ObjectId(file_id)})
            
            if not record:
                raise Exception(f"未找到ID为 {file_id} 的去重记录")
            
            if not record.get("output_file") or not os.path.exists(record["output_file"]):
                raise Exception(f"文件路径不存在: {record.get('output_file')}")
            
            # 读取文件内容
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
            raise Exception(f"获取去重文件内容失败: {str(e)}")

    async def get_quality_content_by_filename(self, filename: str):
        """根据文件名获取quality文件内容"""
        try:
            # 查找指定文件名的quality记录
            record = await self.quality_generations.find_one({"input_file": filename})
            
            if not record:
                raise Exception(f"未找到文件名为 {filename} 的quality记录")
            
            if not record.get("save_path") or not os.path.exists(record["save_path"]):
                raise Exception(f"文件路径不存在: {record.get('save_path')}")
            
            # 读取文件内容
            with open(record["save_path"], 'r', encoding='utf-8') as f:
                content = json.load(f)
            
            return {
                "filename": record["input_file"],
                "content": content,
                "created_at": record["created_at"]
            }
        except Exception as e:
            await self._log_error(str(e), "get_quality_content_by_filename")
            raise Exception(f"获取quality文件内容失败: {str(e)}")

    async def get_dedup_content_by_filename(self, filename: str):
        """根据文件名获取去重后的文件内容"""
        try:
            # 查找指定文件名的去重记录
            record = await self.dedup_records.find_one({"output_file": {"$regex": f".*{filename}.*"}})
            
            if not record:
                raise Exception(f"未找到文件名为 {filename} 的去重记录")
            
            if not record.get("output_file") or not os.path.exists(record["output_file"]):
                raise Exception(f"文件路径不存在: {record.get('output_file')}")
            
            # 读取文件内容
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
            raise Exception(f"获取去重文件内容失败: {str(e)}")

    async def deduplicate_qa(self, filenames: List[str], dedup_by_answer: bool,
                           dedup_threshold: float, min_answer_length: int = 10):
        try:
            # 获取所有文件内容
            original_pairs = []
            source_texts = []
            input_filenames = []

            for filename in filenames:
                quality_content = await self.get_quality_content_by_filename(filename)
                source_texts.append(json.dumps(quality_content["content"]))
                original_pairs.extend(quality_content["content"])
                input_filenames.append(quality_content["filename"])

            # 获取第一个文件名作为基础名
            base_filename = input_filenames[0].rsplit('.', 1)[0]

            # 使用简化的文件名格式：原文件名_dedup.json
            output_file = os.path.join(self.base_output_dir, f"{base_filename}_dedup.json")
            deleted_pairs_file = os.path.join(self.base_output_dir, f"{base_filename}_dedup_deleted.json")

            # 检查是否已有记录，如果有，重置进度
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
                # 创建去重记录，保持原有字段
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
                result = await self.dedup_records.insert_one(dedup_record.dict(by_alias=True))
                record_id = result.inserted_id

            try:
                # 初始化阶段 - 10%
                await self.dedup_records.update_one(
                    {"_id": record_id},
                    {"$set": {"progress": 10}}
                )

                # 创建临时文件保存合并的问答对
                temp_input_file = os.path.join(self.base_output_dir, f"temp_input_{str(record_id)}.json")
                with open(temp_input_file, 'w', encoding='utf-8') as f:
                    json.dump(original_pairs, f, ensure_ascii=False, indent=4)

                # 任务准备阶段 - 20%
                await self.dedup_records.update_one(
                    {"_id": record_id},
                    {"$set": {"progress": 20}}
                )

                # 创建进度更新回调
                async def progress_callback(progress: int):
                    current_time = time.time()
                    last_update = self.last_progress_update.get(str(record_id), 0)
                    
                    if current_time - last_update >= 0.5:
                        # 将原始进度(0-100)映射到处理阶段(20-80)
                        adjusted_progress = int(20 + (progress * 0.6))
                        
                        # 如果数据量小，使用预设的进度点
                        if len(original_pairs) <= 5:  # 假设5对以下算小数据量
                            progress_steps = [30, 40, 50, 60, 70]
                            step_index = min(len(progress_steps)-1, int(progress/20))
                            adjusted_progress = progress_steps[step_index]
                        
                        await self.dedup_records.update_one(
                            {"_id": record_id},
                            {"$set": {"progress": adjusted_progress}}
                        )
                        self.last_progress_update[str(record_id)] = current_time

                # 创建去重参数
                hparams = DedupParams(
                    input_file=[temp_input_file],
                    output_file=output_file,
                    dedup_by_answer=dedup_by_answer,
                    dedup_threshold=dedup_threshold,
                    min_answer_length=min_answer_length,
                    deleted_pairs_file=deleted_pairs_file,
                )

                # 创建去重器实例
                deduplicator = QADeduplication(
                    hparams,
                    progress_callback=lambda p: asyncio.run_coroutine_threadsafe(
                        progress_callback(p),
                        asyncio.get_event_loop()
                    )
                )

                # 在线程池中执行去重操作
                loop = asyncio.get_event_loop()
                kept_pairs, deleted_groups = await loop.run_in_executor(
                    self.executor,
                    deduplicator.process_qa_file,
                    hparams
                )

                # 保存准备阶段 - 90%
                await self.dedup_records.update_one(
                    {"_id": record_id},
                    {"$set": {"progress": 90}}
                )

                # 保存保留的问答对
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

                # 保存被删除的问答对
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

                # 完成 - 100%
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
                # 发生错误时只更新状态，保持当前进度
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
                # 清理临时文件
                if os.path.exists(temp_input_file):
                    os.unlink(temp_input_file)
                # 清理进度更新记录
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
        """获取最近一次的去重历史记录"""
        try:
            # 只获取最新的一条记录
            record = await self.dedup_records.find_one(
                sort=[("created_at", -1)]
            )
            
            if not record:
                return []
            
            # 获取保留的问答对
            qa_cursor = self.kept_pairs.find({"dedup_id": record["_id"]})
            kept_pairs = []
            async for qa in qa_cursor:
                kept_pairs.append({
                    "question": qa["question"],
                    "answer": qa["answer"]
                })

            # 获取被删除的问答对
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