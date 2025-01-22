from fastapi import APIRouter, HTTPException, Depends
from motor.motor_asyncio import AsyncIOMotorClient
from app.components.core.database import get_database
from app.components.models.schemas import QualityControlRequest, APIResponse
from app.components.services.quality_service import QualityService

router = APIRouter()

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
            max_attempts=request.max_attempts
        )
        return APIResponse(
            status="success",
            message="QA pairs optimized successfully",
            data=result
        )
    except Exception as e:
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