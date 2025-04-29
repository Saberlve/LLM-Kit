import logging
from fastapi import APIRouter, HTTPException, Depends,Request,Query
from motor.motor_asyncio import AsyncIOMotorClient
from app.components.core.database import get_database
from app.components.models.schemas import (
    QAGenerateRequest, APIResponse, TexFile,
    TexContentRequest
)
import os
from app.components.services.qa_generate_service import QAGenerateService
from pydantic import BaseModel
import json
from datetime import datetime, timezone

router = APIRouter()
logger = logging.getLogger(__name__)

class FileIDRequest(BaseModel):
    file_id: str

class FilenameRequest(BaseModel):
    filename: str

class RecordIDRequest(BaseModel):
    record_id: str

class FilenameRequest(BaseModel):
    filename: str

@router.get("/tex_files", response_model=APIResponse)
async def get_tex_files(
        db: AsyncIOMotorClient = Depends(get_database)
):
    """Get all converted tex files list"""
    try:
        service = QAGenerateService(db)
        files = await service.get_all_tex_files()
        return APIResponse(
            status="success",
            message="File list retrieved successfully",
            data={"files": [TexFile(**file) for file in files]}
        )
    except Exception as e:
        logger.error(f"Failed to get tex file list: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/tex_content", response_model=APIResponse)
async def get_tex_content(
        request: TexContentRequest,
        db: AsyncIOMotorClient = Depends(get_database)
):
    """Get content of specified tex file"""
    try:
        service = QAGenerateService(db)
        content = await service.get_tex_content(request.file_id)
        return APIResponse(
            status="success",
            message="File content retrieved successfully",
            data=content
        )
    except Exception as e:
        logger.error(f"Failed to get tex file content: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/generate_qa")
async def generate_qa_pairs(
        request_body: QAGenerateRequest,
        raw_request: Request,
        db: AsyncIOMotorClient = Depends(get_database)
):

    print("Raw request body:",request_body)

    """Generate QA pairs"""
    try:
        # Verify that AK and SK counts match
        if len(request_body.AK) != len(request_body.SK):
            raise HTTPException(
                status_code=400,
                detail="The number of AK and SK must be the same"
            )

        # Verify that parallel count is reasonable
        if request_body.parallel_num > len(request_body.AK):
            raise HTTPException(
                status_code=400,
                detail="Parallel count cannot be greater than the number of API key pairs"
            )
        filename=request_body.filename
        PARSED_FILES_DIR = os.path.join(filename, "tex_files")
        raw_filename = filename.split('.')[0]
        parsed_filename = f"{raw_filename}.json"
     
        file_path = os.path.join(PARSED_FILES_DIR, parsed_filename)
        if not os.path.isfile(file_path):
            raise HTTPException(
                status_code=404,
                detail=f"File {request_body.filename} not found"
            )

        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()

       
        service = QAGenerateService(db)
        result = await service.generate_qa_pairs(
            content=content,
            filename=request_body.filename,  
            save_path=request_body.save_path,
            SK=request_body.SK,
            AK=request_body.AK,
            parallel_num=request_body.parallel_num,
            model_name=request_body.model_name,
            domain=request_body.domain
        )

        return APIResponse(
            status="success",
            message="QA pairs generated successfully",
            data=result
        )
    except Exception as e:
        logger.error(f"Failed to generate QA pairs: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/generate_qa/history")
async def get_qa_history(
        db: AsyncIOMotorClient = Depends(get_database)
):
    """Get QA generation history records"""
    try:
        service = QAGenerateService(db)
        records = await service.get_qa_records()
        return APIResponse(
            status="success",
            message="Records retrieved successfully",
            data={"records": records}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate_qa/progress")
async def get_qa_progress(
        request: FilenameRequest,
        db: AsyncIOMotorClient = Depends(get_database)
):
    """Get QA generation progress"""
    try:
        # 
        record = await db.llm_kit.qa_generations.find_one(
            {
                "input_file": request.filename,
                "status": {"$in": ["processing", "completed", "failed", "timeout"]}
            },
            sort=[("created_at", -1)]  # 
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

        # 
        status = record.get("status", "processing")
        progress = record.get("progress", 0)

        # completed，100%
        if status == "completed":
            progress = 100
        # failedtimeout，
        elif status in ["failed", "timeout"]:
            progress = progress

        return APIResponse(
            status="success",
            message="Progress retrieved successfully",
            data={
                "progress": progress,
                "status": status,
                "error_message": record.get("error_message", ""),  # 
                "last_update": record.get("created_at", datetime.now(timezone.utc)).isoformat()  # 
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

@router.delete("/qa_records")
async def delete_qa_record(
        request: RecordIDRequest,
        db: AsyncIOMotorClient = Depends(get_database)
):
    """Delete QA generation record and related QA pairs by ID"""
    try:
        from bson import ObjectId

        # 
        result = await db.llm_kit.qa_generations.delete_one({"_id": ObjectId(request.record_id)})

        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Record not found")

        # 
        await db.llm_kit.qa_pairs.delete_many({"generation_id": ObjectId(request.record_id)})

        return APIResponse(
            status="success",
            message="QA record and related pairs deleted successfully",
            data={"record_id": request.record_id}
        )

    except Exception as e:
        logger.error(f"Failed to delete QA record, record_id: {request.record_id}, error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

class FilenameRequest(BaseModel):
    filename: str
def check_parsed_file_exist(raw_filename: str) -> int:
    """Check if parsed result file exists"""
    parsed_dir = os.path.join("result", "qas")
    raw_filename = raw_filename.split('.')[0]
    parsed_filename = f"{raw_filename}_qa.json"
    target_path = os.path.join(parsed_dir, parsed_filename)
    return 1 if os.path.isfile(target_path) else 0


@router.post("/qashistory")
async def get_parse_history(request: FilenameRequest):
    try:

        filename = request.filename

        exists = check_parsed_file_exist(filename)
        print(exists)
        return {"status": "OK", "exists": exists}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/delete_file")
async def delete_files(request: FilenameRequest):
    '''Delete construction file'''
    PARSED_FILES_DIR = os.path.join("result", "qas")
    filename = request.filename
    PARSED_FILES_DIR1 = os.path.join(filename, "tex_files")

    filename = filename.split('.')[0]
    parsed_filename = f"{filename}_qa.json"
    file_path = os.path.join(PARSED_FILES_DIR, parsed_filename)

    parsed_filename1 = f"{filename}.json"
    file_path1 = os.path.join(PARSED_FILES_DIR1, parsed_filename1)

    if os.path.exists(file_path):
        os.remove(file_path)
        if os.path.exists(file_path1):
            os.remove(file_path1)
        return {"status": "success"}
    return {"status": "failed"}


@router.get("/get_qa_content")
async def get_qa_content(filename: str = Query(..., title="Filename")):
    """Get QA file content"""
    try:
        parsed_dir = os.path.join("result", "qas")
        raw_filename = filename.split('.')[0]
        parsed_filename = f"{raw_filename}_qa.json"
        target_path = os.path.join(parsed_dir, parsed_filename)
        if not os.path.isfile(target_path):
            raise HTTPException(status_code=404, detail="QA file not found")
        with open(target_path, 'r', encoding='utf-8') as f:
            content = json.load(f)
        return content
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="QA file not found")
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Failed to decode QA file content")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/get_raw_content")
async def get_raw_content(filename: str = Query(..., title="Filename")):
    """Get raw file content"""
    try:
        PARSED_FILES_DIR = "parsed_files/parsed_file"
        target_filename = f"{filename}_parsed.txt"
        target_path = os.path.join(PARSED_FILES_DIR, target_filename)
        if not os.path.isfile(target_path):
            raise HTTPException(status_code=404, detail="Raw file not found")
        with open(target_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return content
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Raw file not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))