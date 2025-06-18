import logging
from fastapi import APIRouter, HTTPException, Depends, Response
from motor.motor_asyncio import AsyncIOMotorClient
from app.components.core.database import get_database
from app.components.models.schemas import DedupRequest, APIResponse
from app.components.services.qa_dedup_service import QADedupService
from pydantic import BaseModel
import json
import os

router = APIRouter()
logger = logging.getLogger(__name__)

class FilenameRequest(BaseModel):
    filename: str

class RecordIDRequest(BaseModel):
    record_id: str

@router.post("/deduplicate_qa")
async def deduplicate_qa(
    request: DedupRequest,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """Perform QA pair deduplication"""
    try:
        service = QADedupService(db)
        result = await service.deduplicate_qa(
            filenames=request.quality_filenames,
            dedup_by_answer=request.dedup_by_answer,
            dedup_threshold=request.dedup_threshold,
            min_answer_length=request.min_answer_length,
        )
        return APIResponse(
            status="success",
            message="QA pairs deduplicated successfully",
            data=result
        )
    except Exception as e:
        logger.error(f"QA pair deduplication failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/deduplicate_qa/history")
async def get_dedup_history(
    db: AsyncIOMotorClient = Depends(get_database)
):
    """Get deduplication history records"""
    try:
        service = QADedupService(db)
        records = await service.get_dedup_records()
        return APIResponse(
            status="success",
            message="Records retrieved successfully",
            data={"records": records}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dedup/progress")
async def get_dedup_progress(
        request: FilenameRequest,
        db: AsyncIOMotorClient = Depends(get_database)
):
    """Get deduplication progress"""
    try:
        # Query deduplication record
        record = await db.llm_kit.dedup_records.find_one({"input_file": request.filename})

        if not record:
            raise HTTPException(status_code=404, detail=f"Deduplication record for file {request.filename} not found")

        return APIResponse(
            status="success",
            message="Progress retrieved successfully",
            data={
                "progress": record.get("progress", 0),
                "status": record.get("status", "processing")
            }
        )
    except Exception as e:
        logger.error(f"Failed to get progress: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/quality_content")
async def get_quality_content(
    request: FilenameRequest,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """Get content of specified quality file"""
    try:
        service = QADedupService(db)
        content = await service.get_quality_content_by_filename(request.filename)
        return APIResponse(
            status="success",
            message="File content retrieved successfully",
            data=content
        )
    except Exception as e:
        logger.error(f"Failed to get quality file content: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/dedup_content")
async def get_dedup_content(
    request: FilenameRequest,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """Get content of specified deduplication file"""
    try:
        service = QADedupService(db)
        content = await service.get_dedup_content_by_filename(request.filename)
        return APIResponse(
            status="success",
            message="File content retrieved successfully",
            data=content
        )
    except Exception as e:
        logger.error(f"Failed to get deduplication file content: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/download/{dedup_id}")
async def download_dedup_file(
    dedup_id: str,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """Download deduplicated file"""
    try:
        service = QADedupService(db)
        content = await service.get_dedup_content(dedup_id)
        
        if not content:
            raise HTTPException(status_code=404, detail=f"Deduplication file with ID {dedup_id} not found")
        
        # Convert content to JSON string
        json_content = json.dumps(content["content"], ensure_ascii=False, indent=2)
        
        # Set filename for download
        filename = f"dedup_result_{dedup_id}.json"
        
        # Return file as download
        return Response(
            content=json_content,
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
    except Exception as e:
        logger.error(f"Failed to download deduplication file: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))