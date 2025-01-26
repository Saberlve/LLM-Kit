import logging
from fastapi import APIRouter, HTTPException, Depends
from motor.motor_asyncio import AsyncIOMotorClient
from app.components.core.database import get_database
from app.components.models.schemas import QAGenerateRequest, APIResponse
from app.components.services.qa_generate_service import QAGenerateService

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/tex_files")
async def get_tex_files(
    db: AsyncIOMotorClient = Depends(get_database)
):
    """获取所有已转换的tex文件列表"""
    try:
        service = QAGenerateService(db)
        files = await service.get_all_tex_files()
        return APIResponse(
            status="success",
            message="获取文件列表成功",
            data={"files": files}
        )
    except Exception as e:
        logger.error(f"获取tex文件列表失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tex_content/{filename}")
async def get_tex_content(
    filename: str,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """获取指定tex文件的内容"""
    try:
        service = QAGenerateService(db)
        content = await service.get_tex_content(filename)
        return APIResponse(
            status="success",
            message="获取文件内容成功",
            data=content
        )
    except Exception as e:
        logger.error(f"获取tex文件内容失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

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
            content=request.content,
            filename=request.filename,  # 添加文件名参数
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

@router.get("/generate_qa/progress/{record_id}")
async def get_qa_progress(
    record_id: str,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """获取问答对生成进度"""
    try:
        from bson import ObjectId
        record = await db.llm_kit.qa_generations.find_one({"_id": ObjectId(record_id)})
        
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