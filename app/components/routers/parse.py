import logging
import os
from fastapi import APIRouter, HTTPException, Depends, File, UploadFile
from motor.motor_asyncio import AsyncIOMotorClient
from app.components.core.database import get_database
from app.components.models.schemas import ParseRequest, APIResponse, OCRRequest, FileUploadRequest
from app.components.services.parse_service import ParseService
from text_parse.parse import single_ocr
from app.components.models.mongodb import UploadedFile, UploadedBinaryFile
import mimetypes

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/upload")
async def upload_file(
    request: FileUploadRequest,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """保存上传的文件到数据库"""
    try:
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
            
        service = ParseService(db)
        result = await service.parse_content(
            content=latest_file["content"],
            filename=latest_file["filename"],
            save_path=request.save_path,
            SK=request.SK,
            AK=request.AK,
            parallel_num=request.parallel_num
        )
        
        # 更新文件状态
        await db.llm_kit.uploaded_files.update_one(
            {"_id": latest_file["_id"]},
            {"$set": {"status": "processed"}}
        )
        
        return APIResponse(
            status="success",
            message="File parsed successfully",
            data=result
        )
    except Exception as e:
        logger.error(f"解析文件失败: {str(e)}", exc_info=True)
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
        
        result = single_ocr(request.file_path)
        
        # 保存OCR记录到数据库
        parse_record = {
            "input_file": request.file_path,
            "content": result,
            "status": "completed",
            "file_type": "ocr",
            "save_path": request.save_path,
            "parsed_file_path": request.save_path  # 添加解析后的文件路径
        }
        
        await db.llm_kit.parse_records.insert_one(parse_record)
        
        # 将结果保存到文件
        save_path = os.path.join(request.save_path, os.path.basename(request.file_path) + '.txt')
        with open(save_path, 'w', encoding='utf-8') as f:
            f.write(result)
            
        return APIResponse(
            status="success",
            message="OCR completed successfully",
            data={
                "result": result,
                "save_path": save_path
            }
        )
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

@router.get("/upload/binary/{file_id}/content")
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