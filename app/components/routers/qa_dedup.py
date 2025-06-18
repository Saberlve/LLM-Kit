import logging
from fastapi import APIRouter, HTTPException, Depends, Response
from motor.motor_asyncio import AsyncIOMotorClient
from app.components.core.database import get_database
from app.components.models.schemas import DedupRequest, FileSelection, APIResponse
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
    """Perform QA pair deduplication with priority-based file selection"""
    try:
        service = QADedupService(db)

        # Check if using new format with selected_files
        if hasattr(request, 'selected_files') and request.selected_files:
            # New format with file selection and priority
            result = await service.deduplicate_qa_with_priority(
                selected_files=request.selected_files,
                dedup_by_answer=request.dedup_by_answer,
                dedup_threshold=request.dedup_threshold,
                min_answer_length=request.min_answer_length,
            )
        else:
            # Fallback to old format for backward compatibility
            result = await service.deduplicate_qa(
                filenames=getattr(request, 'quality_filenames', []),
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

@router.get("/preview/{dedup_id}")
async def preview_dedup_result(
    dedup_id: str,
    page: int = 1,
    page_size: int = 10,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """Preview deduplication results with pagination"""
    try:
        service = QADedupService(db)
        result = await service.get_dedup_preview(dedup_id, page, page_size)
        return APIResponse(
            status="success",
            message="Deduplication preview retrieved successfully",
            data=result
        )
    except Exception as e:
        logger.error(f"Failed to get deduplication preview: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/download/{dedup_id}")
async def download_dedup_result(
    dedup_id: str,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """Download complete deduplication results"""
    try:
        service = QADedupService(db)
        result = await service.download_dedup_result(dedup_id)

        # Return JSON response for download
        response = Response(
            content=json.dumps(result["content"], ensure_ascii=False, indent=2),
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename={result['filename']}"
            }
        )
        return response

    except Exception as e:
        logger.error(f"Failed to download deduplication result: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/available_files")
async def get_available_files(
    db: AsyncIOMotorClient = Depends(get_database)
):
    """Get list of available QA files for deduplication (both optimized and unoptimized)"""
    try:
        # Get optimized files from quality_generations
        optimized_cursor = db.llm_kit.quality_generations.find(
            {"status": "completed"},
            {"_id": 1, "input_file": 1, "created_at": 1, "content": 1}
        ).sort("created_at", -1)

        optimized_files = []
        async for record in optimized_cursor:
            # Count QA pairs
            qa_count = 0
            if record.get("content"):
                if isinstance(record["content"], str):
                    try:
                        content = json.loads(record["content"])
                        qa_count = len(content) if isinstance(content, list) else 0
                    except:
                        qa_count = 0
                elif isinstance(record["content"], list):
                    qa_count = len(record["content"])

            optimized_files.append({
                "file_id": str(record["_id"]),
                "filename": record["input_file"],
                "file_type": "optimized",
                "created_at": record["created_at"],
                "qa_count": qa_count
            })

        # Get unoptimized files from qa_generations
        unoptimized_cursor = db.llm_kit.qa_generations.find(
            {"status": "completed"},
            {"_id": 1, "input_file": 1, "created_at": 1, "content": 1}
        ).sort("created_at", -1)

        unoptimized_files = []
        async for record in unoptimized_cursor:
            # Count QA pairs
            qa_count = 0
            if record.get("content"):
                if isinstance(record["content"], str):
                    try:
                        content = json.loads(record["content"])
                        qa_count = len(content) if isinstance(content, list) else 0
                    except:
                        qa_count = 0
                elif isinstance(record["content"], list):
                    qa_count = len(record["content"])

            unoptimized_files.append({
                "file_id": str(record["_id"]),
                "filename": record["input_file"],
                "file_type": "unoptimized",
                "created_at": record["created_at"],
                "qa_count": qa_count
            })

        return APIResponse(
            status="success",
            message="Available files retrieved successfully",
            data={
                "optimized_files": optimized_files,
                "unoptimized_files": unoptimized_files
            }
        )

    except Exception as e:
        logger.error(f"Failed to get available files: {str(e)}", exc_info=True)
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