from fastapi import APIRouter, HTTPException, Depends
from motor.motor_asyncio import AsyncIOMotorClient
from app.components.core.database import get_database
from app.components.models.schemas import ParseRequest, APIResponse
from app.components.services.parse_service import ParseService

router = APIRouter()

@router.post("/parse")
async def parse_file(
    request: ParseRequest,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """解析文件并保存记录"""
    try:
        service = ParseService(db)
        result = await service.parse_file(
            file_path=request.file_path,
            save_path=request.save_path,
            SK=request.SK,
            AK=request.AK,
            parallel_num=request.parallel_num
        )
        return APIResponse(
            status="success",
            message="File parsed successfully",
            data=result
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/parse/history")
async def get_parse_history(
    db: AsyncIOMotorClient = Depends(get_database)
):
    """获取解析历史记录"""
    try:
        service = ParseService(db)
        records = await service.get_parse_records()
        return APIResponse(
            status="success",
            message="Records retrieved successfully",
            data={"records": records}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))