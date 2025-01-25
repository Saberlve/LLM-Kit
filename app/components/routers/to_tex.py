import logging
from fastapi import APIRouter, HTTPException, Depends
from motor.motor_asyncio import AsyncIOMotorClient
from app.components.core.database import get_database
from app.components.models.schemas import (
    ToTexRequest, APIResponse, ParsedFileListResponse, 
    ParsedContentResponse
)
from app.components.services.to_tex_service import ToTexService

router = APIRouter()
logger = logging.getLogger(__name__)

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

@router.get("/parsed_content/{filename}")
async def get_parsed_content(
    filename: str,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """根据文件名获取解析后的内容"""
    try:
        service = ToTexService(db)
        content = await service.get_parsed_content(filename)
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
        service = ToTexService(db)
        result = await service.convert_to_latex(
            content=request.content,
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