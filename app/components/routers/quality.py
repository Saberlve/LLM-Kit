import logging
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import JSONResponse, StreamingResponse
from motor.motor_asyncio import AsyncIOMotorClient
from app.components.core.database import get_database
from app.components.models.schemas import QualityControlRequest, APIResponse
from app.components.services.quality_service import QualityService
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
import json
import io
import urllib.parse
from bson import ObjectId

router = APIRouter()
logger = logging.getLogger(__name__)

class FilenameRequest(BaseModel):
    filename: str

class RecordIDRequest(BaseModel):
    record_id: str

@router.post("/quality")
async def evaluate_and_optimize_qa(
    request: QualityControlRequest,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """Evaluate and optimize QA pairs"""
    try:
        # Verify that AK and SK counts match
        if len(request.AK) != len(request.SK):
            raise HTTPException(
                status_code=400,
                detail="The number of AK and SK must be the same"
            )

        # Verify that parallel count is reasonable
        if request.parallel_num > len(request.AK):
            raise HTTPException(
                status_code=400,
                detail="Parallel count cannot be greater than the number of API key pairs"
            )
            
        service = QualityService(db)
        result = await service.evaluate_and_optimize_qa(
            content=request.content,
            filename=request.filename,
            save_path=request.save_path,
            SK=request.SK,
            AK=request.AK,
            parallel_num=request.parallel_num,
            model_name=request.model_name,
            similarity_rate=request.similarity_rate,
            coverage_rate=request.coverage_rate,
            max_attempts=request.max_attempts,
            domain=request.domain
        )
        return APIResponse(
            status="success",
            message="QA pairs optimized successfully",
            data=result
        )
    except Exception as e:
        logger.error(f"QA pair quality evaluation and optimization failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history")
async def get_quality_history(
    db: AsyncIOMotorClient = Depends(get_database)
):
    """Get quality control history records"""
    try:
        service = QualityService(db)
        records = await service.get_quality_records()
        return APIResponse(
            status="success",
            message="Records retrieved successfully",
            data={"records": records}
        )
    except Exception as e:
        logger.error(f"Failed to get quality history: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/qa_files")
async def get_qa_files(
    db: AsyncIOMotorClient = Depends(get_database)
):
    """Get list of all generated QA pair files"""
    try:
        service = QualityService(db)
        files = await service.get_all_qa_files()
        return APIResponse(
            status="success",
            message="File list retrieved successfully",
            data={"files": files}
        )
    except Exception as e:
        logger.error(f"Failed to get QA pair file list: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/qa_content")
async def get_qa_content(
    request: RecordIDRequest,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """Get content of specified QA pair file by record ID"""
    try:
        service = QualityService(db)
        content = await service.get_qa_content_by_id(request.record_id)
        return APIResponse(
            status="success",
            message="File content retrieved successfully",
            data=content
        )
    except Exception as e:
        logger.error(f"Failed to get QA pair file content: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/progress")
async def get_quality_progress(
    request: FilenameRequest,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """获取质量评估进度信息，包括进度百分比、预估完成时间和已用时间"""
    try:
        logger.info(f"获取质量评估进度: filename={request.filename}")
        
        # 查找最新的记录
        record = await db.llm_kit.quality_generations.find_one(
            {
                "input_file": request.filename,
                "status": {"$in": ["processing", "completed", "failed", "timeout", "aborted"]}
            },
            sort=[("created_at", -1)]
        )

        if not record:
            logger.warning(f"未找到文件 {request.filename} 的质量评估进度记录")
            return APIResponse(
                status="not_found",
                message=f"Progress record for file {request.filename} not found",
                data={
                    "progress": 0,
                    "status": "not_found",
                    "elapsed_time": 0,
                    "estimated_remaining_time": 0,
                    "estimated_completion_time": None,
                    "processed_items": 0,
                    "total_items": 0,
                    "step": "quality_assessment"
                }
            )

        # 获取状态和进度
        status = record.get("status", "processing")
        progress = record.get("progress", 0)
        
        # 获取处理信息
        item_info = record.get("item_info", {"total_items": 0, "processed_items": 0})
        total_items = item_info.get("total_items", 0)
        processed_items = item_info.get("processed_items", 0)
        
        logger.info(f"质量评估进度: status={status}, progress={progress}%, processed_items={processed_items}/{total_items}")
        
        # 计算已经花费的时间（秒）
        current_time = datetime.now(timezone.utc)
        
        # 如果start_time存在，使用它，否则使用created_at
        start_time = record.get("start_time")
        if start_time and not isinstance(start_time, datetime):
            try:
                start_time = datetime.fromisoformat(str(start_time))
            except:
                start_time = None
                
        # 如果start_time为空或转换失败，使用created_at
        if not start_time:
            start_time = record.get("created_at")
            
        # 确保start_time有时区信息
        if start_time and start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
            
        if not start_time:
            start_time = current_time
        
        elapsed_seconds = int((current_time - start_time).total_seconds())
        
        # 计算预估剩余时间
        estimated_remaining_seconds = 0
        estimated_completion_time = None
        
        if status == "processing" and progress > 0:
            # 如果记录中已有预估完成时间，直接使用
            if "estimated_completion_time" in record and record["estimated_completion_time"]:
                estimated_completion_time = record["estimated_completion_time"]
                # 确保estimated_completion_time有时区信息
                if estimated_completion_time and estimated_completion_time.tzinfo is None:
                    estimated_completion_time = estimated_completion_time.replace(tzinfo=timezone.utc)
                if estimated_completion_time:
                    estimated_remaining_seconds = max(0, int((estimated_completion_time - current_time).total_seconds()))
            # 否则基于当前进度估算
            elif progress < 100 and progress > 10 and elapsed_seconds > 0:
                # 基于已完成的百分比和已用时间来估计
                total_estimated_seconds = (elapsed_seconds / progress) * 100
                estimated_remaining_seconds = max(0, int(total_estimated_seconds - elapsed_seconds))
                estimated_completion_time = current_time + timedelta(seconds=estimated_remaining_seconds)
        
        # 如果状态是已完成，设置进度为100%
        if status == "completed":
            progress = 100
            estimated_remaining_seconds = 0
            processed_items = total_items
        
        # 格式化时间显示
        formatted_elapsed_time = format_time_duration(elapsed_seconds)
        formatted_remaining_time = format_time_duration(estimated_remaining_seconds)
        formatted_completion_time = estimated_completion_time.strftime("%H:%M:%S") if estimated_completion_time else None

        response_data = {
            "progress": progress,
            "status": status,
            "error_message": record.get("error_message", ""),
            "last_update": record.get("created_at", datetime.now(timezone.utc)).isoformat(),
            "elapsed_time": elapsed_seconds,
            "formatted_elapsed_time": formatted_elapsed_time,
            "estimated_remaining_time": estimated_remaining_seconds,
            "formatted_remaining_time": formatted_remaining_time,
            "estimated_completion_time": estimated_completion_time.isoformat() if estimated_completion_time else None,
            "formatted_completion_time": formatted_completion_time,
            "processed_items": processed_items,
            "total_items": total_items,
            "step": "quality_assessment"
        }
        
        logger.info(f"返回质量评估进度数据: progress={progress}%, status={status}")
        return APIResponse(
            status="success",
            message="Progress retrieved successfully",
            data=response_data
        )
    except Exception as e:
        logger.error(f"获取质量评估进度失败: {str(e)}", exc_info=True)
        return APIResponse(
            status="error",
            message=f"Failed to get progress: {str(e)}",
            data={
                "progress": 0,
                "status": "error",
                "elapsed_time": 0,
                "estimated_remaining_time": 0,
                "estimated_completion_time": None,
                "processed_items": 0,
                "total_items": 0,
                "step": "quality_assessment"
            }
        )

def format_time_duration(seconds: int) -> str:
    """将秒数格式化为人类可读的时间格式（小时:分钟:秒）"""
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"

@router.delete("/quality_records")
async def delete_quality_record(
    request: RecordIDRequest,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """Delete quality control record and related quality assessment records by ID"""
    try:
        # Delete quality control record
        result = await db.llm_kit.quality_generations.delete_one({"_id": ObjectId(request.record_id)})

        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Record not found")

        # Delete related quality assessment records
        await db.llm_kit.quality_records.delete_many({"generation_id": ObjectId(request.record_id)})

        # Delete from dataset entries if saved there
        record = await db.llm_kit.quality_generations.find_one({"_id": ObjectId(request.record_id)})
        if record and "dataset_id" in record:
            await db.llm_kit.dataset_entries.delete_one({"_id": ObjectId(record["dataset_id"])})

        return APIResponse(
            status="success",
            message="Quality control record and related assessments deleted successfully",
            data={"record_id": request.record_id}
        )
    except Exception as e:
        logger.error(f"Failed to delete quality control record, record_id: {request.record_id}, error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/abort_quality_task")
async def abort_quality_task(
    request: FilenameRequest,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """中止正在进行的质量评估任务"""
    try:
        logger.info(f"尝试中止文件 {request.filename} 的质量评估任务")
        
        # 查找正在处理的质量评估任务
        quality_record = await db.llm_kit.quality_generations.find_one(
            {
                "input_file": request.filename,
                "status": "processing"
            },
            sort=[("created_at", -1)]
        )
        
        if quality_record:
            # 更新质量评估任务状态为中止
            await db.llm_kit.quality_generations.update_one(
                {"_id": quality_record["_id"]},
                {"$set": {
                    "status": "aborted",
                    "error_message": "Task was manually aborted by user"
                }}
            )
            
            logger.info(f"成功中止文件 {request.filename} 的质量评估任务")
            return APIResponse(
                status="success",
                message="Quality assessment task aborted successfully",
                data={"aborted": True, "task_type": "quality_assessment"}
            )
        
        # 没有找到正在进行的任务
        logger.warning(f"未找到文件 {request.filename} 的活动质量评估任务")
        return APIResponse(
            status="not_found",
            message=f"No active quality assessment task found for file {request.filename}",
            data={"aborted": False}
        )
    
    except Exception as e:
        logger.error(f"中止质量评估任务失败: {str(e)}", exc_info=True)
        return APIResponse(
            status="error",
            message=f"Failed to abort quality assessment task: {str(e)}",
            data={"aborted": False}
        )

@router.get("/preview/{dataset_id}")
async def preview_quality_dataset(
    dataset_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: AsyncIOMotorClient = Depends(get_database)
):
    """
    预览质量评估后的数据集内容
    """
    try:
        # 尝试从数据库获取内容
        dataset = None
        
        # 尝试将dataset_id当作ObjectId
        try:
            obj_id = ObjectId(dataset_id)
            dataset = await db.llm_kit.dataset_entries.find_one({"_id": obj_id})
        except:
            # 如果不是有效的ObjectId，尝试用名称查找
            dataset = await db.llm_kit.dataset_entries.find_one({"name": dataset_id})
        
        if not dataset:
            # 尝试在quality_generations集合中查找
            quality_record = await db.llm_kit.quality_generations.find_one(
                {"input_file": dataset_id, "status": "completed"},
                sort=[("created_at", -1)]
            )
            
            if quality_record and "content" in quality_record:
                # 获取QA内容
                try:
                    qa_data = []
                    if isinstance(quality_record["content"], str):
                        qa_data = json.loads(quality_record["content"])
                    else:
                        qa_data = quality_record["content"]
                        
                    # 分页处理
                    total_items = len(qa_data)
                    total_pages = (total_items + page_size - 1) // page_size
                    
                    start_idx = (page - 1) * page_size
                    end_idx = min(start_idx + page_size, total_items)
                    
                    items = qa_data[start_idx:end_idx]
                    
                    logger.info(f"从quality_generations找到QA数据，文件名: {dataset_id}")
                    return {
                        "items": items,
                        "page": page,
                        "page_size": page_size,
                        "total_items": total_items,
                        "total_pages": total_pages
                    }
                except json.JSONDecodeError:
                    raise HTTPException(status_code=500, detail="无效的QA数据格式")
            
            # 如果都找不到，返回404
            logger.warning(f"未找到QA数据集: {dataset_id}")
            raise HTTPException(status_code=404, detail=f"QA数据集未找到: {dataset_id}")
        
        # 获取QA内容
        try:
            qa_data = []
            if "file_data" in dataset:
                if isinstance(dataset["file_data"], str):
                    qa_data = json.loads(dataset["file_data"])
                else:
                    qa_data = dataset["file_data"]
        except json.JSONDecodeError:
            raise HTTPException(status_code=500, detail="无效的QA数据格式")
        
        # 分页处理
        total_items = len(qa_data)
        total_pages = (total_items + page_size - 1) // page_size
        
        start_idx = (page - 1) * page_size
        end_idx = min(start_idx + page_size, total_items)
        
        items = qa_data[start_idx:end_idx]
        
        logger.info(f"从dataset_entries找到QA数据，ID/名称: {dataset_id}")
        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total_items": total_items,
            "total_pages": total_pages
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"预览QA数据集失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"服务器错误: {str(e)}")

@router.get("/download/{dataset_id}")
async def download_quality_dataset(
    dataset_id: str,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """
    Download quality assessment dataset content from database
    """
    try:
        # Try to get content from database
        dataset = None
        
        # First try to use dataset_id as ObjectId
        try:
            obj_id = ObjectId(dataset_id)
            dataset = await db.llm_kit.dataset_entries.find_one({"_id": obj_id})
        except:
            # If not a valid ObjectId, try to find by name
            dataset = await db.llm_kit.dataset_entries.find_one({"name": dataset_id})
        
        # If not found in dataset entries, try quality_generations
        if not dataset:
            quality_record = await db.llm_kit.quality_generations.find_one(
                {"_id": ObjectId(dataset_id)},
                sort=[("created_at", -1)]
            )
            
            if not quality_record:
                quality_record = await db.llm_kit.quality_generations.find_one(
                    {"input_file": dataset_id, "status": "completed"},
                    sort=[("created_at", -1)]
                )
            
            if not quality_record:
                raise HTTPException(status_code=404, detail="Quality dataset not found")
            
            # Get content from quality record
            content = quality_record.get("content", "[]")
            filename = quality_record.get("input_file", "quality_dataset")
            
            # Ensure content is proper JSON string with UTF-8 encoding
            if isinstance(content, str):
                try:
                    json_obj = json.loads(content)
                    content = json.dumps(json_obj, ensure_ascii=False, indent=2)
                except json.JSONDecodeError:
                    content = "[]"
            else:
                content = json.dumps(content, ensure_ascii=False, indent=2)
            
            # Create safe filename
            safe_name = "".join(c for c in filename if c.isalnum() or c in '-_.')
            if not safe_name:
                safe_name = "quality_dataset"
            file_name = f"{safe_name}_optimized.json"
            
            # URL encode the filename
            encoded_filename = urllib.parse.quote(file_name)
            
            # Return file for download
            return StreamingResponse(
                io.StringIO(content),
                media_type="application/json; charset=utf-8",
                headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"}
            )
        
        # Get content from dataset entry
        file_data = dataset.get("file_data", "[]")
        
        # Ensure file_data is proper JSON string with UTF-8 encoding
        if isinstance(file_data, str):
            try:
                json_obj = json.loads(file_data)
                file_data = json.dumps(json_obj, ensure_ascii=False, indent=2)
            except json.JSONDecodeError:
                file_data = "[]"
        else:
            file_data = json.dumps(file_data, ensure_ascii=False, indent=2)
        
        # Create safe filename
        safe_name = "".join(c for c in dataset.get('name', 'quality_dataset') if c.isalnum() or c in '-_.')
        if not safe_name:
            safe_name = "quality_dataset"
        file_name = f"{safe_name}.json"
        
        # URL encode the filename
        encoded_filename = urllib.parse.quote(file_name)
        
        # Return file for download
        return StreamingResponse(
            io.StringIO(file_data),
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"}
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Failed to download quality dataset: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")