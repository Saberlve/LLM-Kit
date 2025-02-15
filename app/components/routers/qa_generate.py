import logging
from fastapi import APIRouter, HTTPException, Depends,Request,Query
from motor.motor_asyncio import AsyncIOMotorClient
from app.components.core.database import get_database
from app.components.models.schemas import (
    QAGenerateRequest, APIResponse, TexFile,
    TexContentRequest
)
import os
from app.components.services.qa_generate_service import QAGenerateService
from pydantic import BaseModel
import json
router = APIRouter()
logger = logging.getLogger(__name__)

class FileIDRequest(BaseModel):
    file_id: str

class FilenameRequest(BaseModel):
    filename: str

class RecordIDRequest(BaseModel):
    record_id: str

class FilenameRequest(BaseModel):
    filename: str

@router.get("/tex_files", response_model=APIResponse)
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
            data={"files": [TexFile(**file) for file in files]}
        )
    except Exception as e:
        logger.error(f"获取tex文件列表失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/tex_content", response_model=APIResponse)
async def get_tex_content(
        request: TexContentRequest,
        db: AsyncIOMotorClient = Depends(get_database)
):
    """获取指定tex文件的内容"""
    try:
        service = QAGenerateService(db)
        content = await service.get_tex_content(request.file_id)
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
        request_body: QAGenerateRequest,
        raw_request: Request,
        db: AsyncIOMotorClient = Depends(get_database)
):

    print("Raw request body:",request_body)

    """生成问答对"""
    try:
        # 验证 AK 和 SK 数量是否匹配
        if len(request_body.AK) != len(request_body.SK):
            raise HTTPException(
                status_code=400,
                detail="AK 和 SK 的数量必须相同"
            )

        # 验证并行数量是否合理
        if request_body.parallel_num > len(request_body.AK):
            raise HTTPException(
                status_code=400,
                detail="并行数量不能大于 API 密钥对数量"
            )
        filename=request_body.filename
        PARSED_FILES_DIR = f"{filename}\\tex_files"
        raw_filename = filename.split('.')[0]
        parsed_filename = f"{raw_filename}.json"
        # 读取文件内容
        file_path = os.path.join(PARSED_FILES_DIR, parsed_filename)
        if not os.path.isfile(file_path):
            raise HTTPException(
                status_code=404,
                detail=f"文件 {request_body.filename} 未找到"
            )

        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()

        # 调用生成问答对的服务
        service = QAGenerateService(db)
        result = await service.generate_qa_pairs(
            content=content,
            filename=request_body.filename,  # 保留文件名参数
            save_path=request_body.save_path,
            SK=request_body.SK,
            AK=request_body.AK,
            parallel_num=request_body.parallel_num,
            model_name=request_body.model_name,
            domain=request_body.domain
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


@router.post("/generate_qa/progress")
async def get_qa_progress(
        request: FilenameRequest,
        db: AsyncIOMotorClient = Depends(get_database)
):
    """获取问答对生成进度"""
    try:
        # 查询进度记录
        record = await db.llm_kit.qa_generations.find_one({"input_file": request.filename})

        if not record:
            raise HTTPException(status_code=404, detail=f"文件 {request.filename} 的进度记录未找到")

        # 如果文件状态为已完成，重置进度为 0 并更新数据库
        if record.get("status") == "completed":
            await db.llm_kit.qa_generations.update_one(
                {"input_file": request.filename},
                {"$set": {"status": "processing", "progress": 0}}
            )
            progress = 0
        else:
            progress = record.get("progress", 0)

        return APIResponse(
            status="success",
            message="Progress retrieved successfully",
            data={
                "progress": progress,
                "status": record.get("status", "processing")
            }
        )
    except Exception as e:
        logger.error(f"获取进度失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/qa_records")
async def delete_qa_record(
        request: RecordIDRequest,
        db: AsyncIOMotorClient = Depends(get_database)
):
    """根据ID删除问答生成记录及相关问答对"""
    try:
        from bson import ObjectId

        # 删除生成记录
        result = await db.llm_kit.qa_generations.delete_one({"_id": ObjectId(request.record_id)})

        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Record not found")

        # 删除相关的问答对
        await db.llm_kit.qa_pairs.delete_many({"generation_id": ObjectId(request.record_id)})

        return APIResponse(
            status="success",
            message="QA record and related pairs deleted successfully",
            data={"record_id": request.record_id}
        )

    except Exception as e:
        logger.error(f"删除问答记录失败 record_id: {request.record_id}, 错误: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

class FilenameRequest(BaseModel):
    filename: str
def check_parsed_file_exist(raw_filename: str) -> int:
    """检查解析结果文件是否存在"""
    parsed_dir = os.path.join("result", "qas")
    raw_filename = raw_filename.split('.')[0]
    parsed_filename = f"{raw_filename}_qa.json"
    target_path = os.path.join(parsed_dir, parsed_filename)
    return 1 if os.path.isfile(target_path) else 0


@router.post("/qashistory")
async def get_parse_history(request: FilenameRequest):
    try:

        filename = request.filename

        exists = check_parsed_file_exist(filename)
        print(exists)
        return {"status": "OK", "exists": exists}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/delete_file")
async def delete_files(request: FilenameRequest):
    '''删除构造文件'''
    PARSED_FILES_DIR = "result\qas"
    filename = request.filename
    PARSED_FILES_DIR1 = f"{filename}\\tex_files"

    filename = filename.split('.')[0]
    parsed_filename = f"{filename}_qa.json"
    file_path = os.path.join(PARSED_FILES_DIR, parsed_filename)

    parsed_filename1 = f"{filename}.json"
    file_path1 = os.path.join(PARSED_FILES_DIR1, parsed_filename1)

    if os.path.exists(file_path):
        os.remove(file_path)
        if os.path.exists(file_path1):
            os.remove(file_path1)
        return {"status": "success"}
    return {"status": "failed"}


@router.get("/get_qa_content")
async def get_qa_content(filename: str = Query(..., title="Filename")):
    """获取QA文件内容"""
    try:
        parsed_dir = os.path.join("result", "qas")
        raw_filename = filename.split('.')[0]
        parsed_filename = f"{raw_filename}_qa.json"
        target_path = os.path.join(parsed_dir, parsed_filename)
        if not os.path.isfile(target_path):
            raise HTTPException(status_code=404, detail="QA file not found")
        with open(target_path, 'r', encoding='utf-8') as f:
            content = json.load(f)
        return content
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="QA file not found")
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Failed to decode QA file content")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/get_raw_content")
async def get_raw_content(filename: str = Query(..., title="Filename")):
    """获取原始文件内容"""
    try:
        PARSED_FILES_DIR = "parsed_files/parsed_file"
        target_filename = f"{filename}_parsed.txt"
        target_path = os.path.join(PARSED_FILES_DIR, target_filename)
        if not os.path.isfile(target_path):
            raise HTTPException(status_code=404, detail="Raw file not found")
        with open(target_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return content
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Raw file not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))