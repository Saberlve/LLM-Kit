import logging
from fastapi import APIRouter, HTTPException, Depends
from motor.motor_asyncio import AsyncIOMotorClient
from app.components.core.database import get_database
from app.components.models.schemas import QualityControlRequest, APIResponse
from app.components.services.quality_service import QualityService
from pydantic import BaseModel
from datetime import datetime, timezone

router = APIRouter()
logger = logging.getLogger(__name__)

class FilenameRequest(BaseModel):
    filename: str

class RecordIDRequest(BaseModel):
    record_id: str

class FilenameRequest(BaseModel):
    filename: str

@router.post("/quality")
async def evaluate_and_optimize_qa(
    request: QualityControlRequest,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """Evaluate and optimize QA pairs"""
    try:
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

@router.get("/quality/history")
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


@router.post("/quality/progress")
async def get_quality_progress(
        request: FilenameRequest,
        db: AsyncIOMotorClient = Depends(get_database)
):
    """Get quality control progress"""
    try:
        # Use more precise query conditions
        record = await db.llm_kit.quality_generations.find_one(
            {
                "input_file": request.filename,
                "status": {"$in": ["processing", "completed", "failed", "timeout"]}
            },
            sort=[("created_at", -1)]  # Get the most recent record
        )

        if not record:
            return APIResponse(
                status="not_found",
                message=f"Quality control record for file {request.filename} not found",
                data={
                    "progress": 0,
                    "status": "not_found"
                }
            )

        # Normalize status
        status = record.get("status", "processing")
        progress = record.get("progress", 0)

        # If status is completed, ensure progress is 100%
        if status == "completed":
            progress = 100
        # If status is failed or timeout, maintain current progress
        elif status in ["failed", "timeout"]:
            progress = progress

        return APIResponse(
            status="success",
            message="Progress retrieved successfully",
            data={
                "progress": progress,
                "status": status,
                "error_message": record.get("error_message", ""),  # Add error message
                "last_update": record.get("created_at", datetime.now(timezone.utc)).isoformat()  # Add last update time
            }
        )
    except Exception as e:
        logger.error(f"Failed to get progress: {str(e)}", exc_info=True)
        return APIResponse(
            status="error",
            message=f"Failed to get progress: {str(e)}",
            data={
                "progress": 0,
                "status": "error"
            }
        )

@router.delete("/quality_records")
async def delete_quality_record(
    request: RecordIDRequest,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """Delete quality control record and related quality assessment records by ID"""
    try:
        from bson import ObjectId

        # Delete quality control record
        result = await db.llm_kit.quality_generations.delete_one({"_id": ObjectId(request.record_id)})

        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Record not found")

        # Delete related quality assessment records
        await db.llm_kit.quality_records.delete_many({"generation_id": ObjectId(request.record_id)})

        return APIResponse(
            status="success",
            message="Quality control record and related assessments deleted successfully",
            data={"record_id": request.record_id}
        )

    except Exception as e:
        logger.error(f"Failed to delete quality control record, record_id: {request.record_id}, error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))