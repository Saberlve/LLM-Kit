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

@router.get("/quality/progress/{record_id}")
async def get_quality_progress(
    record_id: str,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """获取质量控制进度"""
    try:
        from bson import ObjectId
        record = await db.llm_kit.quality_control_generations.find_one(
            {"_id": ObjectId(record_id)}
        )
        
        if not record:
            raise HTTPException(status_code=404, detail="Record not found")
        
        return APIResponse(
            status="success",
            message="Progress retrieved successfully",
            data={
                "progress": record.get("progress", 0),
                "status": record.get("status", "processing")
            }
        )
    except Exception as e:
        logger.error(f"获取进度失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))