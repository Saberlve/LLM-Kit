from fastapi import APIRouter, HTTPException, Depends
from motor.motor_asyncio import AsyncIOMotorClient
from app.components.core.database import get_database
from app.components.models.schemas import ToTexRequest, APIResponse
from app.components.services.to_tex_service import ToTexService

router = APIRouter()

@router.post("/to_tex")
async def convert_to_latex(
    request: ToTexRequest,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """将解析后的文本转换为LaTeX格式"""
    try:
        service = ToTexService(db)
        result = await service.convert_to_latex(
            parsed_file_path=request.parsed_file_path,
            save_path=request.save_path,
            SK=request.SK,
            AK=request.AK,
            parallel_num=request.parallel_num,
            model_name=request.model_name
        )
        return APIResponse(
            status="success",
            message="File converted to LaTeX successfully",
            data=result
        )
    except Exception as e:
        error_message = f"LaTeX conversion failed: {str(e)}"
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