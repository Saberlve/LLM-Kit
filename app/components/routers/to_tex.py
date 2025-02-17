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

# 创建信号量来限制并发请求数
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
        # 使用信号量限制并发
        async with semaphore:
            try:
                filename = request.filename
                print(filename)
                PARSED_FILES_DIR1 = f"{filename}\\tex_files"
                raw_filename = filename.split('.')[0]
                parsed_filename1 = f"{raw_filename}.json"
                # 读取文件内容
                file_path1 = os.path.join(PARSED_FILES_DIR1, parsed_filename1)
                if os.path.isfile(file_path1):
                    return APIResponse(
                        status="success",
                        message="内容已成功转换为LaTeX格式",
                        data={"a": "aaa"}
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

                try:
                    with open(file_path, 'r', encoding='utf-8') as file:
                        content = file.read()
                except Exception as e:
                    logger.error(f"读取文件失败: {str(e)}")
                    raise HTTPException(status_code=500, detail=f"读取文件失败: {str(e)}")

                service = ToTexService(db)
                try:
                    # 设置超时时间为10分钟
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
                        timeout=600  # 10分钟超时
                    )
                except TimeoutError:
                    logger.error("处理超时")
                    # 更新记录状态为超时
                    await db.llm_kit.tex_records.update_one(
                        {"input_file": request.filename},
                        {"$set": {"status": "timeout"}}
                    )
                    raise HTTPException(status_code=504, detail="处理超时，请稍后重试")
                except Exception as e:
                    logger.error(f"转换失败: {str(e)}")
                    raise HTTPException(status_code=500, detail=f"转换失败: {str(e)}")

                return APIResponse(
                    status="success",
                    message="内容已成功转换为LaTeX格式",
                    data=result
                )

            except HTTPException:
                raise
            except Exception as e:
                error_message = f"LaTeX转换失败: {str(e)}"
                logger.error(error_message, exc_info=True)
                raise HTTPException(status_code=500, detail=error_message)
    finally:
        # 确保在任何情况下都释放信号量
        pass  # semaphore会在async with结束时自动释放

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
        request: FileNameRequest,
        db: AsyncIOMotorClient = Depends(get_database)
):
    """获取LaTeX转换进度"""
    try:
        # 使用更精确的查询条件
        record = await db.llm_kit.tex_records.find_one(
            {
                "input_file": request.filename,
                "status": {"$in": ["processing", "completed", "failed", "timeout"]}
            },
            sort=[("created_at", -1)]  # 获取最新的记录
        )
        
        if not record:
            return APIResponse(
                status="not_found",
                message=f"文件 {request.filename} 的进度记录未找到",
                data={
                    "progress": 0,
                    "status": "not_found"
                }
            )
        
        # 标准化状态
        status = record.get("status", "processing")
        progress = record.get("progress", 0)
        
        # 如果状态是completed，确保进度是100%
        if status == "completed":
            progress = 100
        # 如果状态是failed或timeout，保持当前进度
        elif status in ["failed", "timeout"]:
            progress = progress
        
        return APIResponse(
            status="success",
            message="进度获取成功",
            data={
                "progress": progress,
                "status": status,
                "error_message": record.get("error_message", ""),  # 添加错误信息
                "last_update": record.get("created_at", datetime.now(timezone.utc)).isoformat()  # 添加最后更新时间
            }
        )
    except Exception as e:
        logger.error(f"获取进度失败: {str(e)}", exc_info=True)
        return APIResponse(
            status="error",
            message=f"获取进度失败: {str(e)}",
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