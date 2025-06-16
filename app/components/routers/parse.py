import logging
import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from app.components.core.database import get_database
from app.components.models.schemas import APIResponse,  FileUploadRequest

from app.components.models.mongodb import UploadedFile, UploadedBinaryFile, ParseRecord
from bson import ObjectId
from fastapi import HTTPException, Depends, APIRouter, File, UploadFile,Body,status,Request
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import os
from typing import List, Dict, Any
from loguru import logger
import urllib.parse
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



@router.post("/parse/file")
async def parse_specific_file(
        request: FileIDRequest,
        db: AsyncIOMotorClient = Depends(get_database)
):
    """Parse a specific uploaded file, handling both text and binary files"""
    try:
        from bson import ObjectId
        file_id = request.file_id
        logger.info(f"Starting to parse file with ID: {file_id}")
        
        # 尝试在文本文件集合中查找
        text_file = await db.llm_kit.uploaded_files.find_one({"_id": ObjectId(file_id)})
        file_type = None
        is_binary = False
        
        if text_file:
            logger.info(f"Processing text file: {text_file['filename']} with type: {text_file['file_type']}")
            file_content = text_file.get('content', '')
            filename = text_file['filename']
            file_type = text_file.get('file_type', 'unknown')
        else:
            # 如果在文本文件集合中未找到，尝试在二进制文件集合中查找
            binary_file = await db.llm_kit.uploaded_binary_files.find_one({"_id": ObjectId(file_id)})
            if not binary_file:
                logger.error(f"File with ID {file_id} not found in any collection")
                raise HTTPException(status_code=404, detail="File not found")
                
            logger.info(f"Processing binary file: {binary_file['filename']} with type: {binary_file['file_type']}")
            file_content = binary_file.get('content', b'')
            filename = binary_file['filename']
            file_type = binary_file.get('file_type', 'unknown')
            is_binary = True

        # 创建解析记录
        parse_record = ParseRecord(
            input_file=filename,
            status="processing",
            file_type=file_type,
            task_type="parse" if not is_binary else "ocr",
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
            # 根据文件类型选择处理方法
            if is_binary:
                # 对于二进制文件（PDF或图像）
                from app.components.services.ocr_service import OCRService
                ocr_service = OCRService(db)
                
                if file_type == 'pdf':
                    content = await ocr_service.process_pdf(file_content, filename, str(record_id))
                else:  # 图像文件
                    content = await ocr_service.process_image(file_content, filename, str(record_id))
                
                # 更新二进制文件状态
                await db.llm_kit.uploaded_binary_files.update_one(
                    {"_id": ObjectId(file_id)},
                    {"$set": {"status": "parsed"}}
                )
            else:
                # 对于文本文件，使用简化的处理                
                content = file_content
                
                # 更新文本文件状态
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
                    "content": content,
                    "original_file_id": file_id
                }}
            )
            
            logger.info(f"Updated parse record with ID: {record_id} to completed status")
            return APIResponse(
                status="success", 
                message="File parsed successfully", 
                data={
                    "record_id": str(record_id),
                    "content": content,
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
    only_delete_parse_results: bool = False  # 新增参数，默认为False表示同时删除文件和解析结果

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
    """删除上传的文件（包括数据库记录）和对应的解析结果，或仅删除解析结果"""
    file_id = request.file_id
    only_delete_parse_results = request.only_delete_parse_results
    
    logger.info(f"请求删除文件，file_id: {file_id}, 仅删除解析结果: {only_delete_parse_results}")
    
    try:
        # 验证file_id是否为有效的ObjectId
        try:
            object_id = ObjectId(file_id)
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的file_id格式")

        # 首先获取文件名，以便后续删除解析记录
        filename = None
        file_found = False
        
        # 尝试从文本文件集合中查找
        text_file = await db.llm_kit.uploaded_files.find_one({"_id": object_id})
        if text_file:
            filename = text_file.get("filename")
            file_found = True
            
            if not only_delete_parse_results:
                # 删除文本文件
                text_delete_result = await db.llm_kit.uploaded_files.delete_one({"_id": object_id})
                if text_delete_result.deleted_count > 0:
                    logger.info(f"已从文本文件集合中删除文件: {filename}")
            else:
                # 仅更新文件状态为未解析
                await db.llm_kit.uploaded_files.update_one(
                    {"_id": object_id},
                    {"$set": {"status": "unparse"}}
                )
                logger.info(f"已将文本文件 {filename} 状态更新为未解析")
        else:
            # 如果在文本文件集合中未找到，尝试在二进制文件集合中查找
            binary_file = await db.llm_kit.uploaded_binary_files.find_one({"_id": object_id})
            if binary_file:
                filename = binary_file.get("filename")
                file_found = True
                
                if not only_delete_parse_results:
                    # 删除二进制文件
                    binary_delete_result = await db.llm_kit.uploaded_binary_files.delete_one({"_id": object_id})
                    if binary_delete_result.deleted_count > 0:
                        logger.info(f"已从二进制文件集合中删除文件: {filename}")
                else:
                    # 仅更新文件状态为未解析
                    await db.llm_kit.uploaded_binary_files.update_one(
                        {"_id": object_id},
                        {"$set": {"status": "unparse"}}
                    )
                    logger.info(f"已将二进制文件 {filename} 状态更新为未解析")
            else:
                # 如果在两个集合中都未找到，返回404
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"未找到ID为'{file_id}'的文件")
        
        # 如果找到了文件名，删除对应的解析记录
        if filename:
            # 删除与该文件相关的解析记录
            parse_records_deleted = await db.llm_kit.parse_records.delete_many({
                "$or": [
                    {"input_file": filename},
                    {"original_file_id": file_id}
                ]
            })
            logger.info(f"删除文件 '{filename}' 的解析记录: {parse_records_deleted.deleted_count} 条")
            
            # 删除OCR处理进度记录
            ocr_progress_deleted = await db.llm_kit.ocr_processing_progress.delete_many({
                "task_id": {"$in": await db.llm_kit.parse_records.distinct("_id", {"input_file": filename})}
            })
            
            operation_type = "重置" if only_delete_parse_results else "删除"
            return UnifiedFileDeleteResponse(
                status="success",
                message=f"已{operation_type}文件 '{filename}' 及其 {parse_records_deleted.deleted_count} 条解析记录",
                data={
                    "filename": filename,
                    "parse_records_deleted": parse_records_deleted.deleted_count,
                    "file_deleted": not only_delete_parse_results
                }
            )
        
        # 如果没有找到文件名但删除了文件，仍然返回成功
        return UnifiedFileDeleteResponse(
            status="success",
            message=f"文件已删除，但未能删除关联的解析记录",
            data={"file_id": file_id}
        )

    except HTTPException as http_exc:  # 直接重新抛出HTTPException
        raise http_exc
    except Exception as e:
        logger.error(f"删除文件 {file_id} 失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"删除文件失败: {str(e)}")

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



class ParsedFileInfo(BaseModel):
    filename: str
    size: str
    created_at: str
    file_path: str

@router.post("/delete_files")
async def delete_files(
    request: Request,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """从数据库中删除指定文件名的解析结果，并将文件状态更新为未解析"""
    try:
        data = await request.json()
        filenames = data.get("files", [])
        
        if not filenames:
            return {"status": "failed", "message": "未提供文件名列表"}
        
        deleted_count = 0
        updated_files = 0
        
        for filename in filenames:
            # 查找并删除与该文件名相关的解析记录
            result = await db.llm_kit.parse_records.delete_many({
                "input_file": filename
            })
            deleted_count += result.deleted_count
            
            # 更新文本文件状态为未解析
            text_update = await db.llm_kit.uploaded_files.update_many(
                {"filename": filename},
                {"$set": {"status": "unparse"}}
            )
            
            # 更新二进制文件状态为未解析
            binary_update = await db.llm_kit.uploaded_binary_files.update_many(
                {"filename": filename},
                {"$set": {"status": "unparse"}}
            )
            
            updated_files += text_update.modified_count + binary_update.modified_count
            
            logger.info(f"删除文件 '{filename}' 的解析记录: {result.deleted_count} 条, 更新文件状态: {text_update.modified_count + binary_update.modified_count} 个")
        
        return {
            "status": "success",
            "message": f"成功删除 {deleted_count} 条解析记录，更新 {updated_files} 个文件状态为未解析",
            "deleted_count": deleted_count,
            "updated_files": updated_files
        }
    except Exception as e:
        logger.error(f"删除解析记录失败: {str(e)}", exc_info=True)
        return {"status": "failed", "message": f"删除解析记录失败: {str(e)}"}

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
            
            # 查找是否有对应的OCR或PDF文本提取解析记录
            # 注意：修改查询条件，包括ocr和pdf_text两种任务类型
            parse_record = await db.llm_kit.parse_records.find_one(
                {
                    "input_file": decoded_filename,
                    "status": "completed",
                    "task_type": {"$in": ["ocr", "pdf_text"]}  # 同时查询OCR和PDF文本提取结果
                },
                sort=[("created_at", -1)]
            )
            
            if parse_record and "content" in parse_record:
                # 如果找到解析记录，返回解析后的内容
                task_type = parse_record.get("task_type", "ocr")
                logger.info(f"找到文件 {decoded_filename} 的{task_type}解析结果")
                
                # 根据任务类型设置不同的标志
                is_ocr_result = task_type == "ocr"
                is_pdf_text = task_type == "pdf_text"
                
                return {
                    "status": "success",
                    "message": f"{task_type}解析内容获取成功",
                    "data": {
                        "content": parse_record["content"],
                        "file_type": binary_file_record.get("file_type", "binary"),
                        "mime_type": binary_file_record.get("mime_type", "application/octet-stream"),
                        "size": binary_file_record.get("size", 0),
                        "created_at": binary_file_record.get("created_at", datetime.utcnow()).isoformat(),
                        "is_ocr_result": is_ocr_result,
                        "is_pdf_text": is_pdf_text
                    }
                }
            else:
                # 如果没有找到解析记录，返回元数据
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
                        
                        # 查找是否有对应的OCR或PDF文本提取解析记录
                        # 注意：修改查询条件，包括ocr和pdf_text两种任务类型，同时检查original_file_id
                        parse_record = await db.llm_kit.parse_records.find_one(
                            {
                                "original_file_id": str(obj_id),
                                "status": "completed",
                                "task_type": {"$in": ["ocr", "pdf_text"]}  # 同时查询OCR和PDF文本提取结果
                            },
                            sort=[("created_at", -1)]
                        )
                        
                        if parse_record and "content" in parse_record:
                            # 如果找到解析记录，返回解析后的内容
                            task_type = parse_record.get("task_type", "ocr")
                            logger.info(f"找到文件ID {decoded_filename} 的{task_type}解析结果")
                            
                            # 根据任务类型设置不同的标志
                            is_ocr_result = task_type == "ocr"
                            is_pdf_text = task_type == "pdf_text"
                            
                            return {
                                "status": "success",
                                "message": f"{task_type}解析内容获取成功",
                                "data": {
                                    "content": parse_record["content"],
                                    "file_type": binary_file_record.get("file_type", "binary"),
                                    "mime_type": binary_file_record.get("mime_type", "application/octet-stream"),
                                    "size": binary_file_record.get("size", 0),
                                    "created_at": binary_file_record.get("created_at", datetime.utcnow()).isoformat(),
                                    "is_ocr_result": is_ocr_result,
                                    "is_pdf_text": is_pdf_text
                                }
                            }
                        else:
                            # 如果没有找到解析记录，返回元数据
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
                    
                    # 获取任务类型
                    task_type = parse_record.get("task_type", "parse")
                    
                    # 根据任务类型设置不同的标志
                    is_ocr_result = task_type == "ocr"
                    is_pdf_text = task_type == "pdf_text"
                    is_parsed_result = task_type == "parse"
                    
                    return {
                        "status": "success",
                        "message": "解析内容获取成功",
                        "data": {
                            "content": parse_record["content"],
                            "file_type": parse_record.get("file_type", "txt"),
                            "task_type": task_type,
                            "created_at": parse_record.get("created_at", datetime.utcnow()).isoformat(),
                            "is_ocr_result": is_ocr_result,
                            "is_pdf_text": is_pdf_text,
                            "is_parsed_result": is_parsed_result
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
