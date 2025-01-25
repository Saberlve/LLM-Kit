import logging
from fastapi import APIRouter, HTTPException, Depends
from motor.motor_asyncio import AsyncIOMotorClient
from app.components.core.database import get_database
from app.components.models.schemas import QualityControlRequest, APIResponse
from app.components.services.quality_service import QualityService

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/quality")
async def evaluate_and_optimize_qa(
    request: QualityControlRequest,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """评估和优化问答对"""
    try:
        service = QualityService(db)
        result = await service.evaluate_and_optimize_qa(
            qa_path=request.qa_path,
            filename=request.filename,
            save_path=request.save_path,
            SK=request.SK,
            AK=request.AK,
            parallel_num=request.parallel_num,
            model_name=request.model_name,
            similarity_rate=request.similarity_rate,
            coverage_rate=request.coverage_rate,
            max_attempts=request.max_attempts,
            domain=request.domain
        )
        return APIResponse(
            status="success",
            message="QA pairs optimized successfully",
            data=result
        )
    except Exception as e:
        logger.error(f"问答对质量评估优化失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/quality/history")
async def get_quality_history(
    db: AsyncIOMotorClient = Depends(get_database)
):
    """获取质量控制历史记录"""
    try:
        service = QualityService(db)
        records = await service.get_quality_records()
        return APIResponse(
            status="success",
            message="Records retrieved successfully",
            data={"records": records}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/qa_files")
async def get_qa_files(
    db: AsyncIOMotorClient = Depends(get_database)
):
    """获取所有已生成的问答对文件列表"""
    try:
        service = QualityService(db)
        files = await service.get_all_qa_files()
        return APIResponse(
            status="success",
            message="获取文件列表成功",
            data={"files": files}
        )
    except Exception as e:
        logger.error(f"获取问答对文件列表失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/qa_content/{filename}")
async def get_qa_content(
    filename: str,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """获取指定问答对文件的内容"""
    try:
        service = QualityService(db)
        content = await service.get_qa_content(filename)
        return APIResponse(
            status="success",
            message="获取文件内容成功",
            data=content
        )
    except Exception as e:
        logger.error(f"获取问答对文件内容失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))