from fastapi import APIRouter, HTTPException, Depends
from app.components.core.database import get_database
from app.components.models.schemas import QAGenerateRequest, APIResponse
from app.components.services.qa_generate_service import QAGenerateService
from motor.motor_asyncio import AsyncIOMotorClient

router = APIRouter()

@router.post("/generate_qa")
async def generate_qa_pairs(
    request: QAGenerateRequest,
    db: AsyncIOMotorClient = Depends(get_database)
):
    try:
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
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))