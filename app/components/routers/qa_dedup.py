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
            file_ids=request.quality_file_ids,
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

@router.get("/dedup/progress/{record_id}")
async def get_dedup_progress(
    record_id: str,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """获取去重进度"""
    try:
        from bson import ObjectId
        record = await db.llm_kit.dedup_records.find_one(
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

@router.get("/quality_content/{file_id}")
async def get_quality_content(
    file_id: str,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """获取指定quality文件的内容"""
    try:
        service = QADedupService(db)
        content = await service.get_quality_content(file_id)
        return APIResponse(
            status="success",
            message="获取文件内容成功",
            data=content
        )
    except Exception as e:
        logger.error(f"获取quality文件内容失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/dedup_content/{file_id}")
async def get_dedup_content(
    file_id: str,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """获取指定去重文件的内容"""
    try:
        service = QADedupService(db)
        content = await service.get_dedup_content(file_id)
        return APIResponse(
            status="success",
            message="获取文件内容成功",
            data=content
        )
    except Exception as e:
        logger.error(f"获取去重文件内容失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))