import logging
import re
import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from app.components.core.database import get_database
from app.components.models.schemas import ParseRequest, APIResponse, OCRRequest, FileUploadRequest
from app.components.services.parse_service import ParseService
from text_parse.parse import single_ocr
from app.components.models.mongodb import UploadedFile, UploadedBinaryFile, ParseRecord
from bson import ObjectId
from fastapi import FastAPI, HTTPException, Depends, APIRouter, File, UploadFile,Form,Body,status,Request
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import os
from typing import List, Dict, Any
import mimetypes
from loguru import logger

router = APIRouter()
logger = logging.getLogger(__name__)


class UploadedFile(BaseModel):
    filename: str = Field(..., alias="filename")
    content: str = Field(..., alias="content")
    file_type: str = Field(..., alias="file_type")
    size: int = Field(..., alias="size")
    status: str = Field(..., alias="status")
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow, alias="created_at")
    class Config:
        allow_population_by_field_name = True

class UploadedBinaryFile(BaseModel):
    filename: str = Field(..., alias="filename")
    content: Optional[bytes] = Field(None, alias="content")
    file_type: str = Field(..., alias="file_type")
    mime_type: str = Field(..., alias="mime_type")
    size: int = Field(..., alias="size")
    status: str = Field(..., alias="status")
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow, alias="created_at")
    class Config:
        allow_population_by_field_name = True

class FileUploadRequest(BaseModel):
    filename: str
    content: str
    file_type: str

class UnifiedFileListResponse(BaseModel):
    status: str
    message: str
    data: List[dict]

class FileIDRequest(BaseModel):
    file_id: str = Field(..., description="File ID to operate on")

class RecordIDRequest(BaseModel):
    record_id: str = Field(..., description="Record ID to retrieve progress for")

class FilenameRequest(BaseModel):
    filename: str

@router.post("/upload")
async def upload_file(
        request: FileUploadRequest,
        db: AsyncIOMotorClient = Depends(get_database)
):
    """Save uploaded file to database"""
    try:
        # Validate file type
        supported_types = ['tex', 'txt', 'json', 'pdf']
        if request.file_type not in supported_types:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {request.file_type}. Supported types are: {', '.join(supported_types)}"
            )

        # Check if a file with the same name and content exists
        existing_file = await db.llm_kit.uploaded_files.find_one({
            "filename": request.filename,
            "content": request.content,
            "file_type": request.file_type
        })

        if existing_file:
            return APIResponse(
                status="success",
                message="File already exists",
                data={"file_id": str(existing_file["_id"])}
            )

        uploaded_file = UploadedFile(
            filename=request.filename,
            content=request.content,
            file_type=request.file_type,
            size=len(request.content.encode('utf-8')),
            status="pending"
        )

        result = await db.llm_kit.uploaded_files.insert_one(
            uploaded_file.dict(by_alias=True)
        )

        return APIResponse(
            status="success",
            message="File uploaded successfully",
            data={"file_id": str(result.inserted_id)}
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"File upload failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/parse")
async def parse_file(
        request: ParseRequest,
        db: AsyncIOMotorClient = Depends(get_database)
):
    """Parse the most recently uploaded file and save the record"""
    try:
        # Get the most recently uploaded file
        latest_file = await db.llm_kit.uploaded_files.find_one(
            {"status": "pending"},
            sort=[("created_at", -1)]
        )

        if not latest_file:
            raise HTTPException(status_code=404, detail="No pending file found")

        # Create initial record
        parse_record = ParseRecord(
            input_file=latest_file['filename'],
            status="processing",
            file_type=latest_file['file_type'],
            save_path=request.save_path,
            task_type="parse",
            progress=0  # Initialize progress as 0
        )
        result = await db.llm_kit.parse_records.insert_one(
            parse_record.dict(by_alias=True)
        )
        record_id = result.inserted_id

        try:
            # 1. Update file preparation progress
            await db.llm_kit.parse_records.update_one(
                {"_id": record_id},
                {"$set": {"progress": 20}}
            )

            # 2. Build complete filename
            filename = f"{latest_file['filename']}.{latest_file['file_type']}"

            # 3. Prepare parse service
            service = ParseService(db)

            # 4. Execute parsing (progress will be updated during parsing)
            await db.llm_kit.parse_records.update_one(
                {"_id": record_id},
                {"$set": {"progress": 50}}
            )

            result = await service.parse_content(
                content=latest_file["content"],
                filename=filename,
                save_path=request.save_path,
                SK=request.SK,
                AK=request.AK,
                parallel_num=request.parallel_num,
                record_id=str(record_id)
            )

            # 5. Update file status and progress
            await db.llm_kit.uploaded_files.update_one(
                {"_id": latest_file["_id"]},
                {"$set": {"status": "processed"}}
            )

            await db.llm_kit.parse_records.update_one(
                {"_id": record_id},
                {"$set": {
                    "status": "completed",
                    "progress": 100,
                    "content": result.get("content", ""),
                    "parsed_file_path": result.get("parsed_file_path", "")
                }}
            )

            return APIResponse(
                status="success",
                message="File parsed successfully",
                data={
                    "record_id": str(record_id),
                    **result
                }
            )

        except Exception as e:
            # Update failure status
            await db.llm_kit.parse_records.update_one(
                {"_id": record_id},
                {"$set": {"status": "failed"}}
            )
            raise e

    except Exception as e:
        logger.error(f"Failed to parse file: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))




@router.post("/check-parsed-file")
async def check_parsed_file(
        request: FileIDRequest,
        db: AsyncIOMotorClient = Depends(get_database)
):
    """Check if parsed file exists"""
    try:
        from bson import ObjectId

        # First look for the record in the database
        file_record = await db.llm_kit.uploaded_files.find_one(
            {"_id": ObjectId(request.file_id)}
        )

        if not file_record:
            # If not found in the text file collection, try looking in the binary file collection
            file_record = await db.llm_kit.uploaded_binary_files.find_one(
                {"_id": ObjectId(request.file_id)}
            )

        if file_record:
            return APIResponse(
                status="success",
                message="File check completed",
                data={"exists": 1}
            )

        return APIResponse(
            status="success",
            message="File not found",
            data={"exists": 0}
        )

    except Exception as e:
        logger.error(f"Failed to check if file exists: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/files/all")
async def list_all_files(db: AsyncIOMotorClient = Depends(get_database)):
    """Get all uploaded files (text and binary) sorted by time in descending order, including file ID"""
    try:
        text_files_cursor = db.llm_kit.uploaded_files.find(projection={"content": 0})
        binary_files_cursor = db.llm_kit.uploaded_binary_files.find(projection={"content": 0})
        text_files = []
        async for doc in text_files_cursor:
            text_files.append({
                "file_id": str(doc.get("_id")), # Add file_id
                "filename": doc.get("filename"),
                "content": doc.get("content"),
                "file_type": doc.get("file_type"),
                "size": doc.get("size"),
                "status": doc.get("status"),
                "created_at": doc.get("created_at"),
                "type": "text"
            })

        binary_files = []
        async for doc in binary_files_cursor:
            binary_files.append({
                "file_id": str(doc.get("_id")), # Add file_id
                "filename": doc.get("filename"),
                "file_type": doc.get("file_type"),
                "mime_type": doc.get("mime_type"),
                "size": doc.get("size"),
                "status": doc.get("status"),
                "created_at": doc.get("created_at"),
                "type": "binary"
            })

        # Merge lists and sort by time
        all_files = sorted(text_files + binary_files, key=lambda file: file["created_at"], reverse=True)
        return UnifiedFileListResponse(
            status="success",
            message="All files retrieved successfully",
            data=all_files
        )
    except Exception as e:
        logger.error(f"Failed to retrieve all files: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/upload/history", response_model=UnifiedFileListResponse)
async def get_all_uploaded_files_info(db: AsyncIOMotorClient = Depends(get_database)):
    """
    Query information for all uploaded files, including text files and binary files, sorted by creation time in descending order.
    """
    try:
        # Query text file collection, exclude content field to avoid large data volume
        text_files_cursor = db.llm_kit.uploaded_files.find(projection={"content": 0})
        # Query binary file collection, also don't return content field
        binary_files_cursor = db.llm_kit.uploaded_binary_files.find(projection={"content": 0})

        text_files = []
        async for doc in text_files_cursor:
            text_files.append({
                "file_id": str(doc.get("_id")),
                "filename": doc.get("filename"),
                "file_type": doc.get("file_type"),
                "size": doc.get("size"),
                "status": doc.get("status"),
                "created_at": doc.get("created_at"),
                "type": "text"  # Identify as text file
            })

        binary_files = []
        async for doc in binary_files_cursor:
            binary_files.append({
                "file_id": str(doc.get("_id")),
                "filename": doc.get("filename"),
                "file_type": doc.get("file_type"),
                "mime_type": doc.get("mime_type"),
                "size": doc.get("size"),
                "status": doc.get("status"),
                "created_at": doc.get("created_at"),
                "type": "binary"  # Identify as binary file
            })

        # Merge all uploaded files and sort by creation time in descending order
        all_files = sorted(text_files + binary_files, key=lambda x: x["created_at"], reverse=True)

        return UnifiedFileListResponse(
            status="success",
            message="Successfully retrieved information for all uploaded files",
            data=all_files
        )
    except Exception as e:
        logger.error(f"Failed to retrieve file information: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/parse/history")
async def get_parse_history(
        db: AsyncIOMotorClient = Depends(get_database)
):
    """Get parsing history records"""
    try:
        service = ParseService(db)
        records = await service.get_parse_records()
        return APIResponse(
            status="success",
            message="Records retrieved successfully",
            data={"records": records}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/parse/file")
async def parse_specific_file(
        request: FileIDRequest,
        db: AsyncIOMotorClient = Depends(get_database)
):
    """Parse a specific uploaded file, automatically selecting the parsing method based on file type"""
    try:
        from bson import ObjectId
        file_id = request.file_id
        print(file_id)
        # Try to find in the text file collection
        text_file = await db.llm_kit.uploaded_files.find_one({"_id": ObjectId(file_id)})
        binary_file = None
        file_source = "text"

        if not text_file:
            # If not found, try to find in the binary file collection
            binary_file = await db.llm_kit.uploaded_binary_files.find_one({"_id": ObjectId(file_id)})
            if not binary_file:
                raise HTTPException(status_code=404, detail="File not found")
            file_source = "binary"
            file = binary_file
        else:
            file = text_file


        # Create parse record
        parse_record = ParseRecord(
            input_file=file['filename'],
            status="processing",
            file_type=file.get('file_type') or file.get('mime_type') or "unknown", # Handle both text and binary
            save_path=f"./parsed_files/{file_id}", # Default save path or get from request
            task_type="parse" if file_source == "text" else "ocr",
            progress=0
        )
        result = await db.llm_kit.parse_records.insert_one(
            parse_record.dict(by_alias=True)
        )
        record_id = result.inserted_id

        try:
            if file_source == "text":
                # Text file parsing logic (using ParseService, similar to /parse endpoint)
                service = ParseService(db)
                parse_result = await service.parse_content(
                    content=file["content"],
                    filename=file["filename"] + "." + file["file_type"],
                    save_path="./parsed_files", # Default save path or get from request
                    SK="YOUR_SK",  # Get from configuration or request
                    AK="YOUR_AK",  # Get from configuration or request
                    parallel_num=1, # Or get from request
                    record_id=str(record_id)
                )
            elif file_source == "binary":
                # Binary file OCR logic (similar to /ocr endpoint, but using content from DB)
                if binary_file and binary_file["content"]:
                    ocr_result = single_ocr(binary_file["content"]) # Adapt single_ocr to handle content directly if needed, or save to temp file and path to it.
                    save_path = os.path.join("./parsed_files", file["filename"] + '.txt') # Define save path
                    with open(save_path, 'w', encoding='utf-8') as f:
                        f.write(ocr_result)
                    parse_result = {"content": ocr_result, "parsed_file_path": save_path} # Structure to match text parse result
                else:
                    raise HTTPException(status_code=500, detail="Binary file content missing")

            # Update parse record with result and status
            await db.llm_kit.parse_records.update_one(
                {"_id": record_id},
                {"$set": {
                    "status": "completed",
                    "progress": 100,
                    "content": parse_result.get("content", ""),
                    "parsed_file_path": parse_result.get("parsed_file_path", "")
                }}
            )
            return APIResponse(status="success", message="File parsed successfully", data={"record_id": str(record_id), **parse_result})


        except Exception as e:
            await db.llm_kit.parse_records.update_one(
                {"_id": record_id},
                {"$set": {"status": "failed"}}
            )
            raise e

    except Exception as e:
        logger.error(f"Failed to parse file file_id: {request.file_id}, error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))



@router.post("/parse/ocr/")
async def ocr_specific_file(
        request: FileIDRequest,
        db: AsyncIOMotorClient = Depends(get_database)
):
    """Perform OCR recognition on a specific binary file"""
    try:
        from bson import ObjectId
        file_id = request.file_id

        # Get binary file record
        binary_file = await db.llm_kit.uploaded_binary_files.find_one({"_id": ObjectId(file_id)})
        if not binary_file:
            raise HTTPException(status_code=404, detail="Binary file not found")

        # Create parse record
        parse_record = ParseRecord(
            input_file=binary_file['filename'],
            status="processing",
            file_type=binary_file['file_type'],
            save_path="./parsed_files", # Default save path or get from request
            task_type="ocr",
            progress=0
        )
        result = await db.llm_kit.parse_records.insert_one(
            parse_record.dict(by_alias=True)
        )
        record_id = result.inserted_id

        try:
            # OCR processing
            if binary_file and binary_file["content"]:
                ocr_result = single_ocr(binary_file["content"]) # Adapt single_ocr to handle content directly if needed, or save to temp file and path to it.
                save_path = os.path.join("./parsed_files", binary_file["filename"] + '.txt')
                with open(save_path, 'w', encoding='utf-8') as f:
                    f.write(ocr_result)
                parse_result = {"content": ocr_result, "parsed_file_path": save_path}
            else:
                raise HTTPException(status_code=500, detail="Binary file content missing")


            # Update parse record
            await db.llm_kit.parse_records.update_one(
                {"_id": record_id},
                {"$set": {
                    "status": "completed",
                    "progress": 100,
                    "content": parse_result.get("content", ""),
                    "parsed_file_path": parse_result.get("parsed_file_path", "")
                }}
            )
            return APIResponse(status="success", message="OCR completed successfully", data={"record_id": str(record_id), **parse_result})


        except Exception as e:
            await db.llm_kit.parse_records.update_one(
                {"_id": record_id},
                {"$set": {"status": "failed"}}
            )
            raise e

    except Exception as e:
        logger.error(f"OCR file failed file_id: {request.file_id}, error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ocr")
async def ocr_file(
        request: OCRRequest,
        db: AsyncIOMotorClient = Depends(get_database)
):
    """Perform OCR recognition on a file"""
    try:
        # Ensure file exists
        if not os.path.exists(request.file_path):
            raise HTTPException(status_code=400, detail="File not found")

        # Ensure save path exists
        os.makedirs(os.path.dirname(request.save_path), exist_ok=True)

        # Create initial record
        parse_record = ParseRecord(
            input_file=os.path.basename(request.file_path),
            status="processing",
            file_type="ocr",
            save_path=request.save_path,
            task_type="ocr",
            progress=0
        )
        result = await db.llm_kit.parse_records.insert_one(
            parse_record.dict(by_alias=True)
        )
        record_id = result.inserted_id

        try:
            # OCR processing consists of three steps: loading the model, processing the image, and saving the results
            # 1. Update model loading progress
            await db.llm_kit.parse_records.update_one(
                {"_id": record_id},
                {"$set": {"progress": 30}}
            )

            # 2. Perform OCR recognition
            result = single_ocr(request.file_path)
            await db.llm_kit.parse_records.update_one(
                {"_id": record_id},
                {"$set": {"progress": 70}}
            )

            # 3. Save results
            save_path = os.path.join(request.save_path, os.path.basename(request.file_path) + '.txt')
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write(result)

            # Update completion status
            await db.llm_kit.parse_records.update_one(
                {"_id": record_id},
                {"$set": {
                    "status": "completed",
                    "progress": 100,
                    "content": result,
                    "parsed_file_path": save_path
                }}
            )

            return APIResponse(
                status="success",
                message="OCR completed successfully",
                data={
                    "record_id": str(record_id),
                    "result": result,
                    "save_path": save_path
                }
            )
        except Exception as e:
            # Update failure status
            await db.llm_kit.parse_records.update_one(
                {"_id": record_id},
                {"$set": {"status": "failed"}}
            )
            raise e

    except Exception as e:
        logger.error(f"OCR processing failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/upload/latest")
async def get_latest_upload(
        db: AsyncIOMotorClient = Depends(get_database)
):
    """Get the content of the most recently uploaded file"""
    try:
        # Get the most recently uploaded file
        latest_file = await db.llm_kit.uploaded_files.find_one(
            sort=[("created_at", -1)]
        )

        if not latest_file:
            return APIResponse(
                status="success",
                message="No uploaded files found",
                data=None
            )

        return APIResponse(
            status="success",
            message="Latest file retrieved successfully",
            data={
                "file_id": str(latest_file["_id"]),
                "filename": latest_file["filename"],
                "content": latest_file["content"],
                "file_type": latest_file["file_type"],
                "size": latest_file["size"],
                "status": latest_file["status"],
                "created_at": latest_file["created_at"]
            }
        )
    except Exception as e:
        logger.error(f"Failed to get the most recently uploaded file: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/upload/binary")
async def upload_binary_file(
        file: UploadFile = File(...),
        db: AsyncIOMotorClient = Depends(get_database)
):
    """Upload binary files (images, PDFs, etc.) to the database"""
    try:
        # Read file content
        content = await file.read()

        # Get file type
        file_type = os.path.splitext(file.filename)[1].lower().replace('.', '')

        # Get MIME type
        mime_type, _ = mimetypes.guess_type(file.filename)
        if not mime_type:
            mime_type = file.content_type

        # Validate file type
        allowed_types = ['pdf', 'jpg', 'jpeg', 'png']
        if file_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type. Allowed types: {', '.join(allowed_types)}"
            )

        # Check if a file with the same name and content exists
        existing_file = await db.llm_kit.uploaded_binary_files.find_one({
            "filename": file.filename,
            "content": content,
            "file_type": file_type
        })

        if existing_file:
            return APIResponse(
                status="success",
                message="File already exists",
                data={
                    "file_id": str(existing_file["_id"]),
                    "filename": existing_file["filename"],
                    "file_type": existing_file["file_type"],
                    "mime_type": existing_file["mime_type"],
                    "size": existing_file["size"],
                    "status": existing_file["status"]
                }
            )

        # Create file record
        uploaded_file = UploadedBinaryFile(
            filename=file.filename,
            content=content,
            file_type=file_type,
            mime_type=mime_type,
            size=len(content),
            status="to_parse"
        )

        # Save to database
        result = await db.llm_kit.uploaded_binary_files.insert_one(
            uploaded_file.dict(by_alias=True)
        )

        return APIResponse(
            status="success",
            message="Binary file uploaded successfully",
            data={
                "file_id": str(result.inserted_id),
                "filename": file.filename,
                "file_type": file_type,
                "mime_type": mime_type,
                "size": len(content),
                "status": "to_parse"
            }
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Failed to upload binary file: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/upload/binary/latest")
async def get_latest_binary_upload(
        db: AsyncIOMotorClient = Depends(get_database)
):
    """Get information about the most recently uploaded binary file (excluding file content)"""
    try:
        # Get the most recently uploaded file
        latest_file = await db.llm_kit.uploaded_binary_files.find_one(
            sort=[("created_at", -1)]
        )

        if not latest_file:
            return APIResponse(
                status="success",
                message="No uploaded binary files found",
                data=None
            )

        return APIResponse(
            status="success",
            message="Latest binary file info retrieved successfully",
            data={
                "file_id": str(latest_file["_id"]),
                "filename": latest_file["filename"],
                "file_type": latest_file["file_type"],
                "mime_type": latest_file["mime_type"],
                "size": latest_file["size"],
                "status": latest_file["status"],
                "created_at": latest_file["created_at"]
            }
        )
    except Exception as e:
        logger.error(f"Failed to get the most recently uploaded binary file: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/upload/binary/content/{file_id}")
async def get_binary_file_content(
        file_id: str,
        db: AsyncIOMotorClient = Depends(get_database)
):
    """Get binary file content by file ID"""
    try:
        from bson import ObjectId

        # Get file record
        file_record = await db.llm_kit.uploaded_binary_files.find_one(
            {"_id": ObjectId(file_id)}
        )

        if not file_record:
            raise HTTPException(status_code=404, detail="File not found")

        from fastapi.responses import Response

        # Return binary content
        return Response(
            content=file_record["content"],
            media_type=file_record["mime_type"],
            headers={
                "Content-Disposition": f'attachment; filename="{file_record["filename"]}"'
            }
        )
    except Exception as e:
        logger.error(f"Failed to get binary file content: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/parse/progress")
async def get_parse_progress(
        request: FilenameRequest,
        db: AsyncIOMotorClient = Depends(get_database)
):
    """Get parsing progress"""
    try:
        # Query progress record
        record = await db.llm_kit.parse_records.find_one({"input_file": request.filename})

        if not record:
            raise HTTPException(status_code=404, detail=f"Parse record for file {request.filename} not found")

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



@router.delete("/records")
async def delete_record(
        request: RecordIDRequest,
        db: AsyncIOMotorClient = Depends(get_database)
):
    """Delete parsing record by ID"""
    try:
        from bson import ObjectId
        record_id = request.record_id

        # Delete parsing record
        result = await db.llm_kit.parse_records.delete_one({"_id": ObjectId(record_id)})

        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Record not found")

        return APIResponse(
            status="success",
            message="Record deleted successfully",
            data={"record_id": record_id}
        )

    except Exception as e:
        logger.error(f"Failed to delete record record_id: {record_id}, error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class DeleteFileRequest(BaseModel):
    file_id: str
class UnifiedFileListResponse(BaseModel):
    status: str
    message: str
    data: List[Dict[str, Any]]

class UnifiedFileDeleteResponse(BaseModel):
    status: str
    message: str
    data: Dict[str, Any] = {}
@router.delete("/deletefiles")
async def delete_uploaded_file(
        request: DeleteFileRequest = Body(...),
        db: AsyncIOMotorClient = Depends(get_database)
):
    """Delete uploaded file (and database record) by file_id, file_id is obtained from the request body"""
    file_id = request.file_id
    print(file_id)
    try:
        # Validate if file_id is a valid ObjectId
        try:
            object_id = ObjectId(file_id)
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file_id format")

        # Try to delete from text file collection
        text_delete_result = await db.llm_kit.uploaded_files.delete_one({"_id": object_id})
        if text_delete_result.deleted_count > 0:
            return UnifiedFileDeleteResponse(
                status="success",
                message=f"File with id '{file_id}' deleted from text files."
            )

        # If not found in text file collection, try to delete from binary file collection
        binary_delete_result = await db.llm_kit.uploaded_binary_files.delete_one({"_id": object_id})
        if binary_delete_result.deleted_count > 0:
            return UnifiedFileDeleteResponse(
                status="success",
                message=f"File with id '{file_id}' deleted from binary files."
            )

        # If not found in either collection, return 404 Not Found
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"File with id '{file_id}' not found")

    except HTTPException as http_exc: # Catch HTTPException and re-raise directly
        raise http_exc
    except Exception as e:
        logger.error(f"Failed to delete file {file_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete file: {str(e)}")

class FilenameRequest(BaseModel):
    filename: str
def check_parsed_file_exist(raw_filename: str) -> int:
    """Check if the parsed result file exists"""
    parsed_dir = os.path.join("parsed_files", "parsed_file")
    parsed_filename = f"{raw_filename}_parsed.txt"
    target_path = os.path.join(parsed_dir, parsed_filename)
    return 1 if os.path.isfile(target_path) else 0


@router.post("/phistory")
async def get_parse_history(request: FilenameRequest):  
    try:
        filename = request.filename 

        exists = check_parsed_file_exist(filename)

        return {"status": "OK", "exists": exists}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def clean_filename(filename: str) -> str:
    return re.sub(r'_parsed\.txt$', '', filename)

@router.get("/parse_files")
async def get_files():
    files_info = []
    PARSED_FILES_DIR = os.path.join("parsed_files", "parsed_file")
    # Convert relative path to absolute path
    for filename in os.listdir(PARSED_FILES_DIR):
        file_path = os.path.join(PARSED_FILES_DIR, filename)

        if os.path.isfile(file_path):  # Only process files, ignore directories
            # Get file information
            stat = os.stat(file_path)

            # Clean filename
            clean_name = clean_filename(filename)

            # Get file type
            mime_type, _ = mimetypes.guess_type(filename)

            files_info.append({
                "name": clean_name,
                "size": stat.st_size,  # File size (bytes)
                "type": mime_type or "unknown",  # MIME type
                "modification_time": datetime.fromtimestamp(
                    stat.st_mtime
                ).isoformat()  # ISO format time
            })

    return files_info


class ParsedFileInfo(BaseModel):
    filename: str
    size: str
    created_at: str
    file_path: str


def _convert_size(size_bytes: int) -> str:
    """Intelligently convert file size units"""
    if size_bytes == 0:
        return "0B"

    units = ("B", "KB", "MB", "GB")
    unit_index = 0

    while size_bytes >= 1024 and unit_index < len(units)-1:
        size_bytes /= 1024
        unit_index += 1

    return f"{size_bytes:.2f} {units[unit_index]}"



@router.post("/delete_files")
async def delete_files(request: Request):
    PARSED_FILES_DIR = os.path.join("parsed_files", "parsed_file")
    files_to_delete = await request.json()
    # Process deletion logic here
    for filename in files_to_delete["files"]:
        parsed_filename = f"{filename}_parsed.txt"
        file_path = os.path.join(PARSED_FILES_DIR, parsed_filename)

        PARSED_FILES_DIR1 = os.path.join(filename, "tex_files")
        raw_filename = filename.split('.')[0]
        parsed_filename1 = f"{raw_filename}.json"
        file_path1 = os.path.join(PARSED_FILES_DIR1, parsed_filename1)


        PARSED_FILES_DIR2 = os.path.join("result", "qas")
        PARSED_FILES_DIR3 = os.path.join(filename, "tex_files")

        filename3 = filename.split('.')[0]
        parsed_filename2 = f"{filename3}_qa.json"
        file_path2 = os.path.join(PARSED_FILES_DIR2, parsed_filename2)

        parsed_filename3 = f"{filename3}.json"
        file_path3 = os.path.join(PARSED_FILES_DIR3, parsed_filename3)


        if os.path.exists(file_path1):
            os.remove(file_path1)
        if os.path.exists(file_path2):
            os.remove(file_path2)
        if os.path.exists(file_path3):
            os.remove(file_path3)
        if os.path.exists(file_path):
            os.remove(file_path)
            return {"status": "success"}
    return {"status": "failed"}
