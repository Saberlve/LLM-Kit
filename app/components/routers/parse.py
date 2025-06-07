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
from fastapi import FastAPI, HTTPException, Depends, APIRouter, File, UploadFile,Form,Body,status,Request, Query
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import os
from typing import List, Dict, Any
import mimetypes
from loguru import logger
from dotenv import load_dotenv
import urllib.parse
import json
import glob

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
        supported_types = ['tex', 'txt', 'json', 'pdf', 'png', 'jpg', 'jpeg']
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
    """Parse a specific uploaded file, only handling text files for now"""
    try:
        from bson import ObjectId
        file_id = request.file_id
        logger.info(f"Starting to parse file with ID: {file_id}")
        
        # Try to find in the text file collection
        text_file = await db.llm_kit.uploaded_files.find_one({"_id": ObjectId(file_id)})
        
        if not text_file:
            logger.error(f"File with ID {file_id} not found in text files collection")
            raise HTTPException(status_code=404, detail="Text file not found")
            
        logger.info(f"Processing text file: {text_file['filename']} with type: {text_file['file_type']}")

        # Create parse record
        parse_record = ParseRecord(
            input_file=text_file['filename'],
            status="processing",
            file_type=text_file.get('file_type', "unknown"),
            save_path=f"./parsed_files/{file_id}",
            task_type="parse",
            progress=0
        )
        
        # 确保parse_record可以正确序列化
        if hasattr(parse_record, "model_dump"):
            record_dict = parse_record.model_dump(by_alias=True)
        else:
            record_dict = parse_record.dict(by_alias=True)
            
        result = await db.llm_kit.parse_records.insert_one(record_dict)
        record_id = result.inserted_id
        logger.info(f"Created parse record with ID: {record_id}")

        try:
            # 简化的解析处理 - 直接将文本内容保存为文件而不调用复杂的解析服务
            # 确保目录存在
            save_dir = os.path.join("./parsed_files", "parsed_file")
            os.makedirs(save_dir, exist_ok=True)
            
            # 创建解析后的文件名
            file_name = f"{text_file['filename']}_parsed.txt"
            parsed_file_path = os.path.join(save_dir, file_name)
            
            # 写入文件内容
            with open(parsed_file_path, 'w', encoding='utf-8') as f:
                f.write(text_file["content"])
                
            logger.info(f"Saved parsed content to: {parsed_file_path}")
            
            # 更新文件状态
            await db.llm_kit.uploaded_files.update_one(
                {"_id": ObjectId(file_id)},
                {"$set": {"status": "parsed"}}
            )
            
            # 更新解析记录
            await db.llm_kit.parse_records.update_one(
                {"_id": record_id},
                {"$set": {
                    "status": "completed",
                    "progress": 100,
                    "content": text_file["content"],
                    "parsed_file_path": parsed_file_path
                }}
            )
            
            logger.info(f"Updated parse record with ID: {record_id} to completed status")
            return APIResponse(
                status="success", 
                message="File parsed successfully", 
                data={
                    "record_id": str(record_id),
                    "content": text_file["content"],
                    "parsed_file_path": parsed_file_path
                }
            )

        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            logger.error(f"Error during file parsing: {str(e)}\n{error_trace}")
            
            await db.llm_kit.parse_records.update_one(
                {"_id": record_id},
                {"$set": {
                    "status": "failed",
                    "error_message": str(e)
                }}
            )
            logger.info(f"Updated parse record with ID: {record_id} to failed status")
            raise e

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"Failed to parse file file_id: {request.file_id}, error: {str(e)}\n{error_trace}")
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

@router.get("/task/progress")
async def get_task_progress(
        record_id: str,
        db: AsyncIOMotorClient = Depends(get_database)
):
    """Get task progress by record ID"""
    try:
        from bson import ObjectId

        # Get record from database
        record = await db.llm_kit.parse_records.find_one({"_id": ObjectId(record_id)})

        if not record:
            raise HTTPException(status_code=404, detail="Record not found")

        return APIResponse(
            status="success",
            message="Progress retrieved successfully",
            data={
                "progress": record.get("progress", 0),
                "status": record.get("status", "processing"),
                "task_type": record.get("task_type", "parse")
            }
        )
    except Exception as e:
        logger.error(f"Failed to get task progress: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
        
@router.get("/ocr/progress/{record_id}")
async def get_ocr_progress(
    record_id: str,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """获取OCR处理进度"""
    try:
        from app.components.services.ocr_service import OCRService
        
        # 创建OCR服务实例
        ocr_service = OCRService(db)
        
        # 获取OCR处理进度
        progress_info = await ocr_service.get_ocr_progress(record_id)
        
        return APIResponse(
            status="success",
            message="OCR progress retrieved successfully",
            data=progress_info
        )
    except Exception as e:
        logger.error(f"Failed to get OCR progress: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
        
@router.get("/preview_parsed/{record_id}")
async def preview_parsed_content(
    record_id: str,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """预览解析后的内容（包括OCR解析结果和文本解析结果）"""
    try:
        from bson import ObjectId
        
        # 查找解析记录
        parse_record = await db.llm_kit.parse_records.find_one({"_id": ObjectId(record_id)})
        
        if not parse_record:
            logger.error(f"解析记录 {record_id} 未找到")
            raise HTTPException(status_code=404, detail=f"解析记录 {record_id} 未找到")
        
        # 检查记录是否已完成
        if parse_record.get("status") != "completed":
            logger.warning(f"解析记录 {record_id} 状态为 {parse_record.get('status', 'unknown')}，尚未完成")
            return APIResponse(
                status="pending",
                message=f"解析尚未完成，当前状态: {parse_record.get('status', 'unknown')}",
                data={
                    "status": parse_record.get("status", "unknown"),
                    "progress": parse_record.get("progress", 0),
                    "filename": parse_record.get("input_file", ""),
                    "file_type": parse_record.get("file_type", ""),
                    "task_type": parse_record.get("task_type", "parse")
                }
            )
        
        # 如果记录中有内容，则返回
        if "content" in parse_record and parse_record["content"]:
            # 确定任务类型
            task_type = parse_record.get("task_type", "parse")
            
            return APIResponse(
                status="success",
                message="解析内容获取成功",
                data={
                    "content": parse_record["content"],
                    "filename": parse_record.get("input_file", ""),
                    "file_type": parse_record.get("file_type", ""),
                    "task_type": task_type,
                    "created_at": parse_record.get("created_at", datetime.utcnow()).isoformat(),
                    "is_ocr_result": task_type == "ocr",
                    "is_pdf_text": task_type == "pdf_text"
                }
            )
        else:
            # 如果记录中没有内容，则检查是否有文件路径
            if "parsed_file_path" in parse_record and parse_record["parsed_file_path"]:
                # 尝试从文件中读取内容
                try:
                    with open(parse_record["parsed_file_path"], 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    return APIResponse(
                        status="success",
                        message="从文件读取解析内容成功",
                        data={
                            "content": content,
                            "filename": parse_record.get("input_file", ""),
                            "file_type": parse_record.get("file_type", ""),
                            "task_type": parse_record.get("task_type", "parse"),
                            "created_at": parse_record.get("created_at", datetime.utcnow()).isoformat(),
                            "is_ocr_result": parse_record.get("task_type") == "ocr"
                        }
                    )
                except Exception as e:
                    logger.error(f"从文件读取内容失败: {str(e)}", exc_info=True)
                    raise HTTPException(status_code=500, detail=f"读取解析文件失败: {str(e)}")
            else:
                # 如果既没有内容也没有文件路径，返回错误
                logger.error(f"解析记录 {record_id} 不包含内容或文件路径")
                raise HTTPException(status_code=404, detail=f"解析记录 {record_id} 不包含内容")
                
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"预览解析内容失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/records/{record_id}")
async def update_record(
    record_id: str,
    update_data: dict = Body(...),
    db: AsyncIOMotorClient = Depends(get_database)
):
    """更新解析记录的特定字段"""
    try:
        from bson import ObjectId
        
        # 验证记录ID是否存在
        record = await db.llm_kit.parse_records.find_one({"_id": ObjectId(record_id)})
        if not record:
            raise HTTPException(status_code=404, detail="Record not found")
            
        # 更新记录
        result = await db.llm_kit.parse_records.update_one(
            {"_id": ObjectId(record_id)},
            {"$set": update_data}
        )
        
        if result.modified_count == 0:
            return APIResponse(
                status="success",
                message="No changes were made to the record",
                data={"updated": False}
            )
            
        return APIResponse(
            status="success",
            message="Record updated successfully",
            data={"updated": True}
        )
    except Exception as e:
        logger.error(f"Failed to update record: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/preview_raw/{filename}")
async def preview_raw_file(
    filename: str,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """预览原始文件内容"""
    try:
        # URL解码文件名
        decoded_filename = urllib.parse.unquote(filename)
        logger.info(f"预览文件: 原始文件名={filename}, 解码后文件名={decoded_filename}")
        
        # 首先从数据库中查找文件
        file_record = await db.llm_kit.uploaded_files.find_one({"filename": decoded_filename})
        logger.info(f"数据库查询结果: {'找到文件' if file_record else '未找到文件'}")
        
        if file_record and "content" in file_record:
            # 如果在文本文件集合中找到
            logger.info(f"在文本文件集合中找到文件: {decoded_filename}")
            return {
                "status": "success",
                "message": "文件内容获取成功",
                "data": {
                    "content": file_record["content"],
                    "file_type": file_record.get("file_type", "txt"),
                    "size": file_record.get("size", len(file_record["content"].encode("utf-8"))),
                    "created_at": file_record.get("created_at", datetime.utcnow()).isoformat()
                }
            }
        
        # 尝试在二进制文件集合中查找
        binary_file_record = await db.llm_kit.uploaded_binary_files.find_one({"filename": decoded_filename})
        if binary_file_record:
            # 对于二进制文件，我们只返回元数据，不返回二进制内容
            logger.info(f"在二进制文件集合中找到文件: {decoded_filename}")
            
            # 查找是否有对应的OCR解析记录
            parse_record = await db.llm_kit.parse_records.find_one(
                {
                    "input_file": decoded_filename,
                    "status": "completed",
                    "task_type": "ocr"
                },
                sort=[("created_at", -1)]
            )
            
            if parse_record and "content" in parse_record:
                # 如果找到OCR解析记录，返回解析后的内容
                logger.info(f"找到文件 {decoded_filename} 的OCR解析结果")
                return {
                    "status": "success",
                    "message": "OCR解析内容获取成功",
                    "data": {
                        "content": parse_record["content"],
                        "file_type": binary_file_record.get("file_type", "binary"),
                        "mime_type": binary_file_record.get("mime_type", "application/octet-stream"),
                        "size": binary_file_record.get("size", 0),
                        "created_at": binary_file_record.get("created_at", datetime.utcnow()).isoformat(),
                        "is_ocr_result": True
                    }
                }
            else:
                # 如果没有找到OCR解析记录，返回元数据
                return {
                    "status": "success",
                    "message": "文件元数据获取成功",
                    "data": {
                        "content": "二进制文件，无法直接预览内容",
                        "file_type": binary_file_record.get("file_type", "binary"),
                        "mime_type": binary_file_record.get("mime_type", "application/octet-stream"),
                        "size": binary_file_record.get("size", 0),
                        "created_at": binary_file_record.get("created_at", datetime.utcnow()).isoformat()
                    }
                }
        
        # 尝试使用文件ID查找
        try:
            from bson import ObjectId
            # 检查filename是否为有效的ObjectId
            if len(decoded_filename) == 24:
                try:
                    obj_id = ObjectId(decoded_filename)
                    # 尝试用ObjectId查找
                    file_record = await db.llm_kit.uploaded_files.find_one({"_id": obj_id})
                    if file_record and "content" in file_record:
                        logger.info(f"通过ID在文本文件集合中找到文件: {decoded_filename}")
                        return {
                            "status": "success",
                            "message": "文件内容获取成功",
                            "data": {
                                "content": file_record["content"],
                                "file_type": file_record.get("file_type", "txt"),
                                "size": file_record.get("size", len(file_record["content"].encode("utf-8"))),
                                "created_at": file_record.get("created_at", datetime.utcnow()).isoformat()
                            }
                        }
                    
                    # 也尝试在二进制文件集合中查找
                    binary_file_record = await db.llm_kit.uploaded_binary_files.find_one({"_id": obj_id})
                    if binary_file_record:
                        logger.info(f"通过ID在二进制文件集合中找到文件: {decoded_filename}")
                        
                        # 查找是否有对应的OCR解析记录
                        parse_record = await db.llm_kit.parse_records.find_one(
                            {
                                "original_file_id": str(obj_id),
                                "status": "completed",
                                "task_type": "ocr"
                            },
                            sort=[("created_at", -1)]
                        )
                        
                        if parse_record and "content" in parse_record:
                            # 如果找到OCR解析记录，返回解析后的内容
                            logger.info(f"找到文件ID {decoded_filename} 的OCR解析结果")
                            return {
                                "status": "success",
                                "message": "OCR解析内容获取成功",
                                "data": {
                                    "content": parse_record["content"],
                                    "file_type": binary_file_record.get("file_type", "binary"),
                                    "mime_type": binary_file_record.get("mime_type", "application/octet-stream"),
                                    "size": binary_file_record.get("size", 0),
                                    "created_at": binary_file_record.get("created_at", datetime.utcnow()).isoformat(),
                                    "is_ocr_result": True
                                }
                            }
                        else:
                            # 如果没有找到OCR解析记录，返回元数据
                            return {
                                "status": "success",
                                "message": "文件元数据获取成功",
                                "data": {
                                    "content": "二进制文件，无法直接预览内容",
                                    "file_type": binary_file_record.get("file_type", "binary"),
                                    "mime_type": binary_file_record.get("mime_type", "application/octet-stream"),
                                    "size": binary_file_record.get("size", 0),
                                    "created_at": binary_file_record.get("created_at", datetime.utcnow()).isoformat()
                                }
                            }
                except:
                    pass
                    
                # 直接查找是否是解析记录ID
                parse_record = await db.llm_kit.parse_records.find_one({"_id": obj_id})
                if parse_record and "content" in parse_record:
                    logger.info(f"直接通过ID在解析记录中找到内容: {decoded_filename}")
                    return {
                        "status": "success",
                        "message": "解析内容获取成功",
                        "data": {
                            "content": parse_record["content"],
                            "file_type": parse_record.get("file_type", "txt"),
                            "task_type": parse_record.get("task_type", "parse"),
                            "created_at": parse_record.get("created_at", datetime.utcnow()).isoformat(),
                            "is_parsed_result": True
                        }
                    }
        except Exception as e:
            logger.warning(f"尝试通过ID查找文件时出错: {str(e)}")
        
        # 如果都没有找到
        logger.error(f"文件 {decoded_filename} 未找到，在数据库中未找到")
        raise HTTPException(status_code=404, detail=f"文件 {decoded_filename} 在数据库中未找到")
        
    except HTTPException as e:
        logger.error(f"预览文件HTTP异常: {str(e)}")
        raise e
    except Exception as e:
        logger.error(f"预览文件失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/upload_binary")
async def upload_binary_file(
        file: UploadFile = File(...),
        db: AsyncIOMotorClient = Depends(get_database)
):
    """保存上传的二进制文件（PDF或图像）到数据库"""
    try:
        # 获取文件名和类型
        filename = file.filename
        file_type = filename.split('.')[-1].lower()
        
        # 验证文件类型
        supported_types = ['pdf', 'png', 'jpg', 'jpeg']
        if file_type not in supported_types:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件类型: {file_type}。支持的类型有: {', '.join(supported_types)}"
            )
        
        # 获取MIME类型
        mime_type = file.content_type or f"application/{file_type}"
        
        # 读取文件内容
        content = await file.read()
        
        # 检查是否存在同名同内容的文件
        existing_file = await db.llm_kit.uploaded_binary_files.find_one({
            "filename": filename
        })
        
        if existing_file:
            return APIResponse(
                status="success",
                message="文件已存在",
                data={"file_id": str(existing_file["_id"])}
            )
        
        # 创建二进制文件记录
        uploaded_file = UploadedBinaryFile(
            filename=filename,
            content=content,
            file_type=file_type,
            mime_type=mime_type,
            size=len(content),
            status="pending"
        )
        
        if hasattr(uploaded_file, "model_dump"):
            record_dict = uploaded_file.model_dump(by_alias=True)
        else:
            record_dict = uploaded_file.dict(by_alias=True)
        
        result = await db.llm_kit.uploaded_binary_files.insert_one(record_dict)
        
        return APIResponse(
            status="success",
            message="文件上传成功",
            data={"file_id": str(result.inserted_id)}
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"文件上传失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/parse_binary")
async def parse_binary_file(
        request: FileIDRequest,
        db: AsyncIOMotorClient = Depends(get_database)
):
    """解析已上传的二进制文件（PDF或图像）并保存结果"""
    try:
        from bson import ObjectId
        file_id = request.file_id
        logger.info(f"开始解析二进制文件ID: {file_id}")
        
        # 查找二进制文件记录
        binary_file = await db.llm_kit.uploaded_binary_files.find_one({"_id": ObjectId(file_id)})
        
        if not binary_file:
            logger.error(f"ID为 {file_id} 的二进制文件未找到")
            raise HTTPException(status_code=404, detail="二进制文件未找到")
        
        logger.info(f"处理二进制文件: {binary_file['filename']} 类型: {binary_file['file_type']}")
        
        # 创建解析记录
        parse_record = ParseRecord(
            input_file=binary_file['filename'],
            status="processing",
            file_type=binary_file.get('file_type', "unknown"),
            save_path=f"./parsed_files/{file_id}",
            task_type="ocr",
            progress=0
        )
        
        # 确保parse_record可以正确序列化
        if hasattr(parse_record, "model_dump"):
            record_dict = parse_record.model_dump(by_alias=True)
        else:
            record_dict = parse_record.dict(by_alias=True)
        
        result = await db.llm_kit.parse_records.insert_one(record_dict)
        record_id = result.inserted_id
        logger.info(f"创建解析记录ID: {record_id}")
        
        try:
            # 解析文件
            file_type = binary_file['file_type']
            file_content = binary_file.get('content', b'')
            filename = binary_file['filename']
            
            if file_type in ['pdf', 'png', 'jpg', 'jpeg']:
                # 使用OCR服务处理PDF或图像
                from app.components.services.ocr_service import OCRService
                ocr_service = OCRService(db)
                
                if file_type == 'pdf':
                    content = await ocr_service.process_pdf(file_content, filename, str(record_id))
                else:
                    content = await ocr_service.process_image(file_content, filename, str(record_id))
                
                # 更新文件状态
                await db.llm_kit.uploaded_binary_files.update_one(
                    {"_id": ObjectId(file_id)},
                    {"$set": {"status": "parsed"}}
                )
                
                # 更新解析记录 - 直接存储在数据库中，不再保存到本地文件
                await db.llm_kit.parse_records.update_one(
                    {"_id": record_id},
                    {"$set": {
                        "status": "completed",
                        "progress": 100,
                        "content": content,
                        "original_file_id": file_id,
                        "original_file_type": file_type
                    }}
                )
                
                logger.info(f"更新解析记录ID: {record_id} 状态为已完成")
                return APIResponse(
                    status="success",
                    message="文件解析成功",
                    data={
                        "record_id": str(record_id),
                        "content": content
                    }
                )
            else:
                raise HTTPException(status_code=400, detail=f"不支持的文件类型: {file_type}")
                
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            logger.error(f"解析过程中出错: {str(e)}\n{error_trace}")
            
            await db.llm_kit.parse_records.update_one(
                {"_id": record_id},
                {"$set": {
                    "status": "failed",
                    "error_message": str(e)
                }}
            )
            logger.info(f"更新解析记录ID: {record_id} 状态为失败")
            raise e
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"解析二进制文件ID: {request.file_id} 失败, 错误: {str(e)}\n{error_trace}")
        raise HTTPException(status_code=500, detail=str(e))
