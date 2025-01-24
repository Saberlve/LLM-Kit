import logging
from fastapi import APIRouter, HTTPException, Depends
from motor.motor_asyncio import AsyncIOMotorClient
from app.components.core.database import get_database
from app.components.models.schemas import QAGenerateRequest, APIResponse
from app.components.services.qa_generate_service import QAGenerateService

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/generate_qa")
async def generate_qa_pairs(
    request: QAGenerateRequest,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """生成问答对"""
    try:
        # 验证 AK 和 SK 数量是否匹配
        if len(request.AK) != len(request.SK):
            raise HTTPException(
                status_code=400,
                detail="AK 和 SK 的数量必须相同"
            )
            
        # 验证并行数量是否合理
        if request.parallel_num > len(request.AK):
            raise HTTPException(
                status_code=400,
                detail="并行数量不能大于 API 密钥对数量"
            )
            
        service = QAGenerateService(db)
        result = await service.generate_qa_pairs(
            chunks_path=request.chunks_path,
            save_path=request.save_path,
            SK=request.SK,
            AK=request.AK,
            parallel_num=request.parallel_num,
            model_name=request.model_name,
            domain=request.domain
        )
        
        return APIResponse(
            status="success",
            message="QA pairs generated successfully",
            data=result
        )
    except Exception as e:
        logger.error(f"生成问答对失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/generate_qa/history")
async def get_qa_history(
    db: AsyncIOMotorClient = Depends(get_database)
):
    """获取问答对生成历史记录"""
    try:
        service = QAGenerateService(db)
        records = await service.get_qa_records()
        return APIResponse(
            status="success",
            message="Records retrieved successfully",
            data={"records": records}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))