import logging
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import JSONResponse, StreamingResponse
from motor.motor_asyncio import AsyncIOMotorClient
from app.components.core.database import get_database
from app.components.models.schemas import APIResponse, COTGenerateRequest
from app.components.services.cot_generate_service import COTGenerateService
from pydantic import BaseModel
import os
import json
import io
from bson import ObjectId
from datetime import datetime
import base64
import urllib.parse

router = APIRouter()
logger = logging.getLogger(__name__)

PROMPT_TEMPLATE = """
Below is the user's question or description:
{text}

You are an experienced {domain} expert, a professional user question analyst, and also skilled in professional markdown usage. You are also proficient in professional {domain} article writing, with high literary attainment. You excel at providing in-depth analysis and professional answers to {domain}-related questions raised by users. Your target audience may be {domain} professionals, patients, or general users, so your answers should be both professional and easy to understand.

## Task Background
- Our team needs to complete a complex {domain} reasoning task
- We now have a specific user question, and we need to provide a comprehensive answer to this content, with the entire article centered around this content.
- First, you need to analyze the problem from a more comprehensive and diverse perspective based on the above content, fully combining your extensive and solid {domain} knowledge (providing as many possible situations or solutions as possible). Then, based on what you consider the most likely situation, write a {domain} recommendation that is deeply analyzed, logically rigorous, completely argued, and properly caring! And provide your analysis process.

The output format must strictly follow the JSON structure below:
'''json
{{
"reasoning": [
    {{"action": "Analysis", "title": "...", "content": "..."}},
    ...,
    {{"action": "Final Summary", "content": "..."}},
    {{"action": "Verification", "content": "..." }}
]
}}
'''
"""

class GenerateCOTRequest(BaseModel):
    """Generate COT request"""
    content: str
    filename: str
    model_name: str
    ak: str
    sk: str
    domain: str = "Medicine"

class FilenameRequest(BaseModel):
    filename: str

@router.post("/generate")
async def generate_cot(
    request: COTGenerateRequest,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """Generate COT reasoning"""
    try:
        # Verify that AK and SK quantities match
        if len(request.AK) != len(request.SK):
            raise HTTPException(
                status_code=400,
                detail="The number of AK and SK must be the same"
            )

        # Verify that the parallel number is reasonable
        if request.parallel_num > len(request.AK):
            raise HTTPException(
                status_code=400,
                detail="Parallel number cannot be greater than the number of API key pairs"
            )

        # Replace domain in the prompt, keep text placeholder for subsequent replacement
        begin_prompt = PROMPT_TEMPLATE.format(
            text="{text}",  # Keep text placeholder
            domain=request.domain
        )
        
        filename = request.filename
        content = None
        
        # 首先尝试从数据库中获取文件内容
        file_record = await db.llm_kit.uploaded_files.find_one({"filename": filename})
        if file_record and "content" in file_record:
            # 如果数据库中有文件内容，则使用它
            # 我们需要将内容转换为tex格式的JSON
            PARSED_FILES_DIR = os.path.join(filename, "tex_files")
            os.makedirs(PARSED_FILES_DIR, exist_ok=True)
            raw_filename = filename.split('.')[0]
            parsed_filename = f"{raw_filename}.json"
            file_path = os.path.join(PARSED_FILES_DIR, parsed_filename)
            
            # 检查文件是否已经存在，如果不存在则需要先执行to_tex转换
            if not os.path.isfile(file_path):
                # 先保存内容到临时文件
                temp_file_path = os.path.join(PARSED_FILES_DIR, f"{raw_filename}_temp.txt")
                with open(temp_file_path, 'w', encoding='utf-8') as f:
                    f.write(file_record["content"])
                
                # 调用to_tex服务进行转换（这里假设已经通过前端调用了to_tex服务）
                # 我们仍然尝试读取转换后的结果
                if os.path.isfile(file_path):
                    with open(file_path, 'r', encoding='utf-8') as file:
                        content = file.read()
                else:
                    raise HTTPException(
                        status_code=404,
                        detail=f"文件 {filename} 需要先进行LaTeX转换"
                    )
            else:
                # 文件已经存在，直接读取
                with open(file_path, 'r', encoding='utf-8') as file:
                    content = file.read()
        else:
            # 如果数据库中没有找到，尝试从文件系统读取
            PARSED_FILES_DIR = os.path.join(filename, "tex_files")
            raw_filename = filename.split('.')[0]
            parsed_filename = f"{raw_filename}.json"
            file_path = os.path.join(PARSED_FILES_DIR, parsed_filename)

            if not os.path.isfile(file_path):
                raise HTTPException(
                    status_code=404,
                    detail=f"文件 {request.filename} 未找到"
                )

            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()

        service = COTGenerateService(db)
        result = await service.generate_cot(
            content=content,
            filename=request.filename,
            model_name=request.model_name,
            ak_list=request.AK,
            sk_list=request.SK,
            parallel_num=request.parallel_num,
            begin_prompt=begin_prompt,
            domain=request.domain
        )
        
        # 将生成的结果存储到数据库
        cot_data = None
        parsed_dir = os.path.join("result", "cot")
        raw_filename = request.filename.split('.')[0]
        parsed_filename = f"{raw_filename}_cot.json"
        file_path = os.path.join(parsed_dir, parsed_filename)
        
        if os.path.isfile(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                cot_data = f.read()
        
        if cot_data:
            # 创建新的数据集条目并保存到数据库
            dataset_entry = {
                "name": f"COT-{raw_filename}",
                "description": f"Generated COT from {request.filename} using {request.model_name}",
                "pool_id": 2,  # 假设这是COT构建的池ID
                "kind": 2,     # 表示这是构建的数据集
                "file_data": cot_data,
                "created_at": datetime.now(),
                "model_name": request.model_name,
                "domain": request.domain,
                "is_cot": True
            }
            
            result_id = await db.llm_kit.dataset_entries.insert_one(dataset_entry)
            
            # 将数据库ID添加到返回结果中
            if isinstance(result, dict):
                result["dataset_id"] = str(result_id.inserted_id)

        return APIResponse(
            status="success",
            message="COT generated successfully",
            data=result
        )
    except Exception as e:
        logger.error(f"Failed to generate COT: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/content")
async def get_cot_content(request: FilenameRequest):
   """Get COT file content"""
   try:
       # URL解码文件名
       decoded_filename = urllib.parse.unquote(request.filename)
       logger.info(f"获取COT内容: 原始文件名={request.filename}, 解码后文件名={decoded_filename}")
       
       parsed_dir = os.path.join("result", "cot")
       raw_filename = decoded_filename.split('.')[0]
       parsed_filename = f"{raw_filename}_cot.json"
       target_path = os.path.join(parsed_dir, parsed_filename)
       
       logger.info(f"尝试读取COT文件: {target_path}")
       if not os.path.isfile(target_path):
           logger.error(f"COT文件未找到: {target_path}")
           raise HTTPException(status_code=404, detail="COT file not found")
           
       with open(target_path, 'r', encoding='utf-8') as f:
           content = json.load(f)
       return content
   except FileNotFoundError:
       logger.error(f"COT文件未找到: {decoded_filename}")
       raise HTTPException(status_code=404, detail="COT file not found")
   except json.JSONDecodeError:
       logger.error(f"解析COT文件内容失败: {decoded_filename}")
       raise HTTPException(status_code=500, detail="Failed to decode COT file content")
   except Exception as e:
       logger.error(f"获取COT内容失败: {str(e)}", exc_info=True)
       raise HTTPException(status_code=500, detail=str(e))

@router.delete("/file/{filename}")
async def delete_cot_file(
    filename: str,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """Delete COT file"""
    try:
        # URL解码文件名
        decoded_filename = urllib.parse.unquote(filename)
        logger.info(f"删除COT文件: 原始文件名={filename}, 解码后文件名={decoded_filename}")
        
        service = COTGenerateService(db)
        result = await service.delete_cot_file(decoded_filename)

        if result:
            logger.info(f"成功删除COT文件: {decoded_filename}")
            return APIResponse(
                status="success",
                message="File deleted successfully"
            )
        else:
            logger.info(f"未找到要删除的COT文件: {decoded_filename}")
            return APIResponse(
                status="success",
                message="File not found"
            )
    except Exception as e:
        logger.error(f"删除COT文件失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

async def check_parsed_file_exist(raw_filename: str, db: AsyncIOMotorClient) -> int:
    """Check if the parsed result file exists in database"""
    # 尝试按文件名查找
    dataset = await db.llm_kit.dataset_entries.find_one({"name": raw_filename})
    if dataset:
        return 1
    
    # 尝试使用ID查找
    try:
        if len(raw_filename) == 24:
            try:
                obj_id = ObjectId(raw_filename)
                dataset = await db.llm_kit.dataset_entries.find_one({"_id": obj_id})
                if dataset:
                    return 1
            except:
                pass
    except:
        pass
    
    return 0

@router.post("/cothistory")
async def get_parse_history(
    request: FilenameRequest,
    db: AsyncIOMotorClient = Depends(get_database)
):
    try:
        # 获取文件名并进行URL解码
        filename = request.filename
        decoded_filename = urllib.parse.unquote(filename)
        logger.info(f"检查COT历史: 原始文件名={filename}, 解码后文件名={decoded_filename}")

        exists = await check_parsed_file_exist(decoded_filename, db)
        logger.info(f"文件 {decoded_filename} COT历史存在状态: {exists}")
        return {"status": "OK", "exists": exists}
    except Exception as e:
        logger.error(f"获取COT历史失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/preview/{dataset_id}")
async def preview_cot_dataset(
    dataset_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: AsyncIOMotorClient = Depends(get_database)
):
    """预览COT数据集内容"""
    try:
        try:
            obj_id = ObjectId(dataset_id)
        except:
            # 如果不是有效的ObjectId，尝试从文件读取
            return await preview_cot_file(dataset_id, page, page_size)
            
        # 从数据库获取内容
        dataset = await db.llm_kit.dataset_entries.find_one({"_id": obj_id})
        if not dataset:
            # 如果数据库中找不到，尝试从文件读取
            return await preview_cot_file(dataset_id, page, page_size)
        
        # 获取COT内容
        try:
            cot_data = json.loads(dataset.get("file_data", "[]"))
        except:
            raise HTTPException(status_code=500, detail="无效的COT数据格式")
        
        # 分页处理
        total_items = len(cot_data)
        total_pages = (total_items + page_size - 1) // page_size
        
        start_idx = (page - 1) * page_size
        end_idx = min(start_idx + page_size, total_items)
        
        items = cot_data[start_idx:end_idx]
        
        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total_items": total_items,
            "total_pages": total_pages
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"预览COT数据集失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"服务器错误: {str(e)}")

async def preview_cot_file(filename: str, page: int, page_size: int):
    """从文件预览COT内容 - 此功能已弃用，改为使用数据库"""
    # 现在我们完全使用数据库，此函数只作为后备函数
    logger.error(f"尝试从文件预览COT内容，但该功能已弃用: {filename}")
    raise HTTPException(status_code=404, detail="COT文件未找到，所有内容应该存储在数据库中")

@router.get("/download/{dataset_id}")
async def download_cot_dataset(
    dataset_id: str,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """下载COT数据集内容"""
    try:
        try:
            obj_id = ObjectId(dataset_id)
        except:
            # 如果不是有效的ObjectId，尝试从文件下载
            return await download_cot_file(dataset_id)
            
        # 从数据库获取内容
        dataset = await db.llm_kit.dataset_entries.find_one({"_id": obj_id})
        if not dataset:
            # 如果数据库中找不到，尝试从文件下载
            return await download_cot_file(dataset_id)
        
        # 获取COT内容
        file_data = dataset.get("file_data", "[]")
        file_name = f"{dataset.get('name', 'cot_dataset')}.json"
        
        # 返回文件下载
        return StreamingResponse(
            io.StringIO(file_data),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename={file_name}"}
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"下载COT数据集失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"服务器错误: {str(e)}")

async def download_cot_file(filename: str):
    """从文件下载COT内容 - 此功能已弃用，改为使用数据库"""
    # 现在我们完全使用数据库，此函数只作为后备函数
    logger.error(f"尝试从文件下载COT内容，但该功能已弃用: {filename}")
    raise HTTPException(status_code=404, detail="COT文件未找到，所有内容应该存储在数据库中")