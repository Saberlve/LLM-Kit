import logging
import os
from fastapi import APIRouter, HTTPException, Depends, File, UploadFile
from motor.motor_asyncio import AsyncIOMotorClient
from app.components.core.database import get_database
from app.components.models.schemas import ParseRequest, APIResponse, OCRRequest, FileUploadRequest
from app.components.services.parse_service import ParseService
from text_parse.parse import single_ocr
from app.components.models.mongodb import UploadedFile, UploadedBinaryFile, ParseRecord
import mimetypes
from typing import List, Union
from fastapi import FastAPI, HTTPException, Depends, APIRouter, File, UploadFile
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import os
import mimetypes
from loguru import logger

router = APIRouter()
logger = logging.getLogger(__name__)
import os

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

@router.post("/upload")
async def upload_file(
        request: FileUploadRequest,
        db: AsyncIOMotorClient = Depends(get_database)
):
    """保存上传的文件到数据库"""
    try:
        # 验证文件类型
        supported_types = ['tex', 'txt', 'json', 'pdf']
        if request.file_type not in supported_types:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {request.file_type}. Supported types are: {', '.join(supported_types)}"
            )

        # 检查是否存在相同文件名和内容的文件
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
        logger.error(f"上传文件失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/parse")
async def parse_file(
        request: ParseRequest,
        db: AsyncIOMotorClient = Depends(get_database)
):
    """解析最近上传的文件并保存记录"""
    try:
        # 获取最近上传的文件
        latest_file = await db.llm_kit.uploaded_files.find_one(
            {"status": "pending"},
            sort=[("created_at", -1)]
        )

        if not latest_file:
            raise HTTPException(status_code=404, detail="No pending file found")

        # 创建初始记录
        parse_record = ParseRecord(
            input_file=latest_file['filename'],
            status="processing",
            file_type=latest_file['file_type'],
            save_path=request.save_path,
            task_type="parse",
            progress=0
        )
        result = await db.llm_kit.parse_records.insert_one(
            parse_record.dict(by_alias=True)
        )
        record_id = result.inserted_id

        try:
            # 1. 更新文件准备进度
            await db.llm_kit.parse_records.update_one(
                {"_id": record_id},
                {"$set": {"progress": 20}}
            )

            # 2. 构建完整的文件名
            filename = f"{latest_file['filename']}.{latest_file['file_type']}"

            # 3. 准备解析服务
            service = ParseService(db)

            # 4. 执行解析（解析过程中会更新进度）
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

            # 5. 更新文件状态和进度
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
            # 更新失败状态
            await db.llm_kit.parse_records.update_one(
                {"_id": record_id},
                {"$set": {"status": "failed"}}
            )
            raise e

    except Exception as e:
        logger.error(f"解析文件失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/check-parsed-file")
async def check_parsed_file(
    request: FileIDRequest,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """检查解析文件是否存在"""
    try:
        from bson import ObjectId
        
        # 先在数据库中查找记录
        file_record = await db.llm_kit.uploaded_files.find_one(
            {"_id": ObjectId(request.file_id)}
        )
        
        if not file_record:
            # 如果在文本文件集合中找不到，尝试在二进制文件集合中查找
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
        logger.error(f"检查文件是否存在失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/files/all")
async def list_all_files(db: AsyncIOMotorClient = Depends(get_database)):
    """获取所有上传的文件(文本和二进制)并按时间降序排序, 包含文件ID"""
    try:
        text_files_cursor = db.llm_kit.uploaded_files.find(projection={"content": 0})
        binary_files_cursor = db.llm_kit.uploaded_binary_files.find(projection={"content": 0})
        text_files = []
        async for doc in text_files_cursor:
            text_files.append({
                "file_id": str(doc.get("_id")), # 添加 file_id
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
                "file_id": str(doc.get("_id")), # 添加 file_id
                "filename": doc.get("filename"),
                "file_type": doc.get("file_type"),
                "mime_type": doc.get("mime_type"),
                "size": doc.get("size"),
                "status": doc.get("status"),
                "created_at": doc.get("created_at"),
                "type": "binary"
            })

        #合并列表并按照时间排序
        all_files = sorted(text_files + binary_files, key=lambda file: file["created_at"], reverse=True)
        return UnifiedFileListResponse(
            status="success",
            message="All files retrieved successfully",
            data=all_files
        )
    except Exception as e:
        logger.error(f"获取所有文件失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/parse/history")
async def get_parse_history(
        db: AsyncIOMotorClient = Depends(get_database)
):
    """获取解析历史记录"""
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
    """解析指定的上传文件，根据文件类型自动选择解析方式"""
    try:
        from bson import ObjectId
        file_id = request.file_id
        print(file_id)
        # 尝试从文本文件集合中查找
        text_file = await db.llm_kit.uploaded_files.find_one({"_id": ObjectId(file_id)})
        binary_file = None
        file_source = "text"

        if not text_file:
            # 如果没找到，尝试从二进制文件集合中查找
            binary_file = await db.llm_kit.uploaded_binary_files.find_one({"_id": ObjectId(file_id)})
            if not binary_file:
                raise HTTPException(status_code=404, detail="File not found")
            file_source = "binary"
            file = binary_file
        else:
            file = text_file


        # 创建解析记录
        parse_record = ParseRecord(
            input_file=file['filename'],
            status="processing",
            file_type=file.get('file_type') or file.get('mime_type') or "unknown", # Handle both text and binary
            save_path=f"./parsed_files/{file_id}", # 默认保存路径或从请求中获取
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
                    save_path="./parsed_files", # 默认保存路径或从请求中获取
                    SK="YOUR_SK",  # 从配置或请求中获取
                    AK="YOUR_AK",  # 从配置或请求中获取
                    parallel_num=1, # 或从请求中获取
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
        logger.error(f"解析文件失败 file_id: {request.file_id}, 错误: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))



@router.post("/parse/ocr/")
async def ocr_specific_file(
        request: FileIDRequest,
        db: AsyncIOMotorClient = Depends(get_database)
):
    """对指定的二进制文件进行OCR识别"""
    try:
        from bson import ObjectId
        file_id = request.file_id

        # 获取二进制文件记录
        binary_file = await db.llm_kit.uploaded_binary_files.find_one({"_id": ObjectId(file_id)})
        if not binary_file:
            raise HTTPException(status_code=404, detail="Binary file not found")

        # 创建解析记录
        parse_record = ParseRecord(
            input_file=binary_file['filename'],
            status="processing",
            file_type=binary_file['file_type'],
            save_path="./parsed_files", # 默认保存路径或从请求中获取
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
        logger.error(f"OCR 文件失败 file_id: {request.file_id}, 错误: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ocr")
async def ocr_file(
        request: OCRRequest,
        db: AsyncIOMotorClient = Depends(get_database)
):
    """对文件进行OCR识别"""
    try:
        # 确保文件存在
        if not os.path.exists(request.file_path):
            raise HTTPException(status_code=400, detail="File not found")

        # 确保保存路径存在
        os.makedirs(os.path.dirname(request.save_path), exist_ok=True)

        # 创建初始记录
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
            # OCR处理过程分为三个步骤：加载模型、处理图片、保存结果
            # 1. 更新加载模型进度
            await db.llm_kit.parse_records.update_one(
                {"_id": record_id},
                {"$set": {"progress": 30}}
            )

            # 2. 执行OCR识别
            result = single_ocr(request.file_path)
            await db.llm_kit.parse_records.update_one(
                {"_id": record_id},
                {"$set": {"progress": 70}}
            )

            # 3. 保存结果
            save_path = os.path.join(request.save_path, os.path.basename(request.file_path) + '.txt')
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write(result)

            # 更新完成状态
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
            # 更新失败状态
            await db.llm_kit.parse_records.update_one(
                {"_id": record_id},
                {"$set": {"status": "failed"}}
            )
            raise e

    except Exception as e:
        logger.error(f"OCR处理失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/upload/latest")
async def get_latest_upload(
        db: AsyncIOMotorClient = Depends(get_database)
):
    """获取最近一次上传的文件内容"""
    try:
        # 获取最近上传的文件
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
        logger.error(f"获取最近上传文件失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/upload/binary")
async def upload_binary_file(
        file: UploadFile = File(...),
        db: AsyncIOMotorClient = Depends(get_database)
):
    """上传二进制文件(图片、PDF等)到数据库"""
    try:
        # 读取文件内容
        content = await file.read()

        # 获取文件类型
        file_type = os.path.splitext(file.filename)[1].lower().replace('.', '')

        # 获取MIME类型
        mime_type, _ = mimetypes.guess_type(file.filename)
        if not mime_type:
            mime_type = file.content_type

        # 验证文件类型
        allowed_types = ['pdf', 'jpg', 'jpeg', 'png']
        if file_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type. Allowed types: {', '.join(allowed_types)}"
            )

        # 检查是否存在相同文件名和内容的文件
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

        # 创建文件记录
        uploaded_file = UploadedBinaryFile(
            filename=file.filename,
            content=content,
            file_type=file_type,
            mime_type=mime_type,
            size=len(content),
            status="pending"
        )

        # 保存到数据库
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
                "status": "pending"
            }
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"上传二进制文件失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/upload/binary/latest")
async def get_latest_binary_upload(
        db: AsyncIOMotorClient = Depends(get_database)
):
    """获取最近一次上传的二进制文件信息（不包含文件内容）"""
    try:
        # 获取最近上传的文件
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
        logger.error(f"获取最近上传的二进制文件失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/upload/binary/content/{file_id}")
async def get_binary_file_content(
        file_id: str,
        db: AsyncIOMotorClient = Depends(get_database)
):
    """通过文件ID获取二进制文件内容"""
    try:
        from bson import ObjectId

        # 获取文件记录
        file_record = await db.llm_kit.uploaded_binary_files.find_one(
            {"_id": ObjectId(file_id)}
        )

        if not file_record:
            raise HTTPException(status_code=404, detail="File not found")

        from fastapi.responses import Response

        # 返回二进制内容
        return Response(
            content=file_record["content"],
            media_type=file_record["mime_type"],
            headers={
                "Content-Disposition": f'attachment; filename="{file_record["filename"]}"'
            }
        )
    except Exception as e:
        logger.error(f"获取二进制文件内容失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/task/progress")
async def get_task_progress(
        request: RecordIDRequest,
        db: AsyncIOMotorClient = Depends(get_database)
):
    """获取任务进度"""
    try:
        from bson import ObjectId
        record_id = request.record_id
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
        logger.error(f"获取进度失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))



@router.delete("/records")
async def delete_record(
    request: RecordIDRequest,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """根据ID删除解析记录"""
    try:
        from bson import ObjectId
        record_id = request.record_id
        
        # 删除解析记录
        result = await db.llm_kit.parse_records.delete_one({"_id": ObjectId(record_id)})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Record not found")
            
        return APIResponse(
            status="success",
            message="Record deleted successfully",
            data={"record_id": record_id}
        )
        
    except Exception as e:
        logger.error(f"删除记录失败 record_id: {record_id}, 错误: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
