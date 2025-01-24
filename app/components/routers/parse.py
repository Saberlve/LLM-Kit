import logging
import os
from fastapi import APIRouter, HTTPException, Depends
from motor.motor_asyncio import AsyncIOMotorClient
from app.components.core.database import get_database
from app.components.models.schemas import ParseRequest, APIResponse, OCRRequest
from app.components.services.parse_service import ParseService
from text_parse.parse import single_ocr

router = APIRouter()
logger = logging.getLogger(__name__)

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
        logger.error(f"解析文件失败: {str(e)}", exc_info=True)
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

@router.post("/ocr")
async def ocr_file(
    request: OCRRequest,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """对文件进行OCR识别"""
    try:
        # 确保文件存在
        if not os.path.exists(request.file_path):
            raise HTTPException(status_code=400, detail="File not found")
            
        # 确保保存路径存在
        os.makedirs(os.path.dirname(request.save_path), exist_ok=True)
        
        result = single_ocr(request.file_path)
        
        # 保存OCR记录到数据库
        parse_record = {
            "input_file": request.file_path,
            "content": result,
            "status": "completed",
            "file_type": "ocr",
            "save_path": request.save_path,
            "parsed_file_path": request.save_path  # 添加解析后的文件路径
        }
        
        await db.llm_kit.parse_records.insert_one(parse_record)
        
        # 将结果保存到文件
        save_path = os.path.join(request.save_path, os.path.basename(request.file_path) + '.txt')
        with open(save_path, 'w', encoding='utf-8') as f:
            f.write(result)
            
        return APIResponse(
            status="success",
            message="OCR completed successfully",
            data={
                "result": result,
                "save_path": save_path
            }
        )
    except Exception as e:
        logger.error(f"OCR处理失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))