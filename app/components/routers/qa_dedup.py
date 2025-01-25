import logging
from fastapi import APIRouter, HTTPException, Depends
from motor.motor_asyncio import AsyncIOMotorClient
from app.components.core.database import get_database
from app.components.models.schemas import DedupRequest, APIResponse
from app.components.services.qa_dedup_service import QADedupService

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/deduplicate_qa")
async def deduplicate_qa(
    request: DedupRequest,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """执行问答对去重"""
    try:
        service = QADedupService(db)
        result = await service.deduplicate_qa(
            input_file=request.input_file,
            dedup_by_answer=request.dedup_by_answer,
            dedup_threshold=request.dedup_threshold,
            min_answer_length=request.min_answer_length,
        )
        return APIResponse(
            status="success",
            message="QA pairs deduplicated successfully",
            data=result
        )
    except Exception as e:
        logger.error(f"问答对去重失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/deduplicate_qa/history")
async def get_dedup_history(
    db: AsyncIOMotorClient = Depends(get_database)
):
    """获取去重历史记录"""
    try:
        service = QADedupService(db)
        records = await service.get_dedup_records()
        return APIResponse(
            status="success",
            message="Records retrieved successfully",
            data={"records": records}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))