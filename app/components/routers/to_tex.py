import logging
from fastapi import APIRouter, HTTPException, Depends
from motor.motor_asyncio import AsyncIOMotorClient
from app.components.core.database import get_database
from app.components.models.schemas import (
    ToTexRequest, APIResponse, ParsedFileListResponse,
    ParsedContentResponse
)
import os
from app.components.services.to_tex_service import ToTexService
from pydantic import BaseModel
import asyncio
from asyncio import TimeoutError
import functools
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

# Create semaphore to limit concurrent requests
MAX_CONCURRENT_REQUESTS = 5
semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

router = APIRouter()
logger = logging.getLogger(__name__)

class FileIDRequest(BaseModel):
    file_id: str

class RecordIDRequest(BaseModel):
    record_id: str

class FileNameRequest(BaseModel):
    filename: str

@router.get("/parsed_files")
async def get_parsed_files(
    db: AsyncIOMotorClient = Depends(get_database)
):
    """Get a list of all parsed files"""
    try:
        service = ToTexService(db)
        files = await service.get_parsed_files()
        return APIResponse(
            status="success",
            message="Successfully retrieved list of parsed files",
            data={"files": files}
        )
    except Exception as e:
        error_message = f"Failed to retrieve list of parsed files: {str(e)}"
        logger.error(error_message, exc_info=True)
        raise HTTPException(status_code=500, detail=error_message)

@router.post("/parsed_content")
async def get_parsed_content(
    request: FileIDRequest,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """Get parsed content based on file ID"""
    try:
        service = ToTexService(db)
        content = await service.get_parsed_content(request.file_id)
        return APIResponse(
            status="success",
            message="Successfully retrieved parsed content",
            data=content
        )
    except Exception as e:
        error_message = f"Failed to retrieve parsed content: {str(e)}"
        logger.error(error_message, exc_info=True)
        raise HTTPException(status_code=500, detail=error_message)

@router.post("/to_tex")
async def convert_to_latex(
    request: ToTexRequest,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """Convert text content to LaTeX format"""
    try:
        # Use semaphore to limit concurrency
        async with semaphore:
            try:
                filename = request.filename
                print(filename)
                PARSED_FILES_DIR1 = f"{filename}\\tex_files"
                raw_filename = filename.split('.')[0]
                parsed_filename1 = f"{raw_filename}.json"
                # Read file content
                file_path1 = os.path.join(PARSED_FILES_DIR1, parsed_filename1)
                if os.path.isfile(file_path1):
                    return APIResponse(
                        status="success",
                        message="Content has been successfully converted to LaTeX format",
                        data={"a": "aaa"}
                    )

                PARSED_FILES_DIR = "parsed_files\parsed_file"
                parsed_filename = f"{filename}_parsed.txt"
                # Read file content
                file_path = os.path.join(PARSED_FILES_DIR, parsed_filename)
                if not os.path.isfile(file_path):
                    raise HTTPException(
                        status_code=404,
                        detail=f"File {request.filename} not found"
                    )

                try:
                    with open(file_path, 'r', encoding='utf-8') as file:
                        content = file.read()
                except Exception as e:
                    logger.error(f"Failed to read file: {str(e)}")
                    raise HTTPException(status_code=500, detail=f"Failed to read file: {str(e)}")

                service = ToTexService(db)
                try:
                    # Set timeout to 10 minutes
                    result = await asyncio.wait_for(
                        service.convert_to_latex(
                            content=content,
                            filename=request.filename,
                            save_path=request.save_path,
                            SK=request.SK,
                            AK=request.AK,
                            parallel_num=request.parallel_num,
                            model_name=request.model_name
                        ),
                        timeout=600  # 10 minutes timeout
                    )
                except TimeoutError:
                    logger.error("Processing timeout")
                    # Update record status to timeout
                    await db.llm_kit.tex_records.update_one(
                        {"input_file": request.filename},
                        {"$set": {"status": "timeout"}}
                    )
                    raise HTTPException(status_code=504, detail="Processing timeout, please try again later")
                except Exception as e:
                    logger.error(f"Conversion failed: {str(e)}")
                    raise HTTPException(status_code=500, detail=f"Conversion failed: {str(e)}")

                return APIResponse(
                    status="success",
                    message="Content has been successfully converted to LaTeX format",
                    data=result
                )

            except HTTPException:
                raise
            except Exception as e:
                error_message = f"LaTeX conversion failed: {str(e)}"
                logger.error(error_message, exc_info=True)
                raise HTTPException(status_code=500, detail=error_message)
    finally:
        # Ensure semaphore is released in any case
        pass  # semaphore will be automatically released when async with ends

@router.get("/to_tex/history")
async def get_tex_history(
    db: AsyncIOMotorClient = Depends(get_database)
):
    """Get LaTeX conversion history records"""
    try:
        service = ToTexService(db)
        records = await service.get_tex_records()
        return APIResponse(
            status="success",
            message="Records retrieved successfully",
            data={"records": records}
        )
    except Exception as e:
        error_message = f"Failed to retrieve LaTeX conversion history: {str(e)}"
        raise HTTPException(status_code=500, detail=error_message)


@router.post("/to_tex/progress")
async def get_tex_progress(
        request: FileNameRequest,
        db: AsyncIOMotorClient = Depends(get_database)
):
    """Get LaTeX conversion progress"""
    try:
        # Use more precise query conditions
        record = await db.llm_kit.tex_records.find_one(
            {
                "input_file": request.filename,
                "status": {"$in": ["processing", "completed", "failed", "timeout"]}
            },
            sort=[("created_at", -1)]  # Get the latest record
        )

        if not record:
            return APIResponse(
                status="not_found",
                message=f"Progress record for file {request.filename} not found",
                data={
                    "progress": 0,
                    "status": "not_found"
                }
            )

        # Standardize status
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
        logger.error(f"Failed to retrieve progress: {str(e)}", exc_info=True)
        return APIResponse(
            status="error",
            message=f"Failed to retrieve progress: {str(e)}",
            data={
                "progress": 0,
                "status": "error"
            }
        )

@router.delete("/tex_records")
async def delete_tex_record(
    request: RecordIDRequest,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """Delete LaTeX conversion record by ID"""
    try:
        from bson import ObjectId

        # Delete conversion record
        result = await db.llm_kit.tex_records.delete_one({"_id": ObjectId(request.record_id)})

        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Record not found")

        return APIResponse(
            status="success",
            message="TeX record deleted successfully",
            data={"record_id": request.record_id}
        )

    except Exception as e:
        logger.error(f"Failed to delete LaTeX record record_id: {request.record_id}, error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))