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
    """获取所有已解析的文件列表"""
    try:
        service = ToTexService(db)
        files = await service.get_parsed_files()
        return APIResponse(
            status="success",
            message="已解析文件列表获取成功",
            data={"files": files}
        )
    except Exception as e:
        error_message = f"获取解析文件列表失败: {str(e)}"
        logger.error(error_message, exc_info=True)
        raise HTTPException(status_code=500, detail=error_message)

@router.post("/parsed_content")
async def get_parsed_content(
    request: FileIDRequest,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """根据文件ID获取解析后的内容"""
    try:
        service = ToTexService(db)
        content = await service.get_parsed_content(request.file_id)
        return APIResponse(
            status="success",
            message="解析内容获取成功",
            data=content
        )
    except Exception as e:
        error_message = f"获取解析内容失败: {str(e)}"
        logger.error(error_message, exc_info=True)
        raise HTTPException(status_code=500, detail=error_message)

@router.post("/to_tex")
async def convert_to_latex(
    request: ToTexRequest,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """将文本内容转换为LaTeX格式"""
    try:

        filename=request.filename
        PARSED_FILES_DIR1 = f"{filename}\\tex_files"
        raw_filename = filename.split('.')[0]
        parsed_filename1 = f"{raw_filename}.json"
        # 读取文件内容
        file_path1 = os.path.join(PARSED_FILES_DIR1, parsed_filename1)
        if  os.path.isfile(file_path1):
            return APIResponse(
                status="success",
                message="内容已成功转换为LaTeX格式",
                data={"a":"aaa"}
            )
        PARSED_FILES_DIR = "parsed_files\parsed_file"
        parsed_filename = f"{filename}_parsed.txt"
        # 读取文件内容
        file_path = os.path.join(PARSED_FILES_DIR, parsed_filename)
        if not os.path.isfile(file_path):
            raise HTTPException(
                status_code=404,
                detail=f"文件 {request.filename} 未找到"
            )

        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        service = ToTexService(db)
        result = await service.convert_to_latex(
            content=content,
            filename=request.filename,
            save_path=request.save_path,
            SK=request.SK,
            AK=request.AK,
            parallel_num=request.parallel_num,
            model_name=request.model_name
        )
        return APIResponse(
            status="success",
            message="内容已成功转换为LaTeX格式",
            data=result
        )
    except Exception as e:
        error_message = f"LaTeX转换失败: {str(e)}"
        logger.error(error_message, exc_info=True)
        raise HTTPException(status_code=500, detail=error_message)

@router.get("/to_tex/history")
async def get_tex_history(
    db: AsyncIOMotorClient = Depends(get_database)
):
    """获取LaTeX转换历史记录"""
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
        request: FileNameRequest,  # 修改请求模型
        db: AsyncIOMotorClient = Depends(get_database)
):
    """获取LaTeX转换进度"""
    try:
        # 查询进度记录
        record = await db.llm_kit.tex_records.find_one({"input_file": request.filename})

        if not record:
            raise HTTPException(status_code=404, detail=f"文件 {request.filename} 的进度记录未找到")

        # 如果文件状态为已完成，重置进度为 0 并更新数据库
        if record.get("status") == "completed":
            await db.llm_kit.tex_records.update_one(
                {"input_file": request.filename},
                {"$set": {"status": "processing", "progress": 0}}
            )
            progress = 0
        else:
            progress = record.get("progress", 0)

        return APIResponse(
            status="success",
            message="Progress retrieved successfully",
            data={
                "progress": progress,
                "status": record.get("status", "processing")
            }
        )
    except Exception as e:
        logger.error(f"获取进度失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/tex_records")
async def delete_tex_record(
    request: RecordIDRequest,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """根据ID删除LaTeX转换记录"""
    try:
        from bson import ObjectId
        
        # 删除转换记录
        result = await db.llm_kit.tex_records.delete_one({"_id": ObjectId(request.record_id)})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Record not found")
            
        return APIResponse(
            status="success",
            message="TeX record deleted successfully",
            data={"record_id": request.record_id}
        )
        
    except Exception as e:
        logger.error(f"删除LaTeX记录失败 record_id: {request.record_id}, 错误: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))