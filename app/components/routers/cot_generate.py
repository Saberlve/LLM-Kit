import logging
from fastapi import APIRouter, HTTPException, Depends,Query
from motor.motor_asyncio import AsyncIOMotorClient
from app.components.core.database import get_database
from app.components.models.schemas import APIResponse, COTGenerateRequest
from app.components.services.cot_generate_service import COTGenerateService
from pydantic import BaseModel
import os
import json

router = APIRouter()
logger = logging.getLogger(__name__)

PROMPT_TEMPLATE = """
以下是用户的问题或描述：
{text}

你是一位经验丰富的{domain}专家，同时一个专业的用户问题分析师，同时也擅长markdown的专业使用；你也擅长专业的{domain}文章写作，拥有极高的文学素养。擅长针对用户提出的{domain}相关问题进行深入分析和专业解答。你的目标受众可能是{domain}专业人士、患者或普通用户，因此回答既要专业又易于理解。

##任务背景 
- 我们团队要完成一个复杂的{domain}推理任务 
- 我们现在已经有了一个具体的用户问题，我们要针对这段内容给一个完善的回答，整篇文章围绕这个内容来展开。
- 首先你需要根据上述内容，并充分结合你广博又扎实的{domain}知识，从更全面、更多样的角度来分析问题（尽可能多的给出可能的情况或解决方案），之后根据你认为最有可能的情况撰写一篇分析深入、逻辑严谨、论述完整、关怀到位的{domain}建议！并给出你的分析过程。

输出格式必须严格遵循以下 JSON 结构：
'''json
{{
"推理": [
    {{"action": "分析", "title": "...", "content": "..."}},
    ...,
    {{"action": "最终总结", "content": "..."}},
    {{"action": "验证", "content": "..." }}
]
}}
'''
"""

class GenerateCOTRequest(BaseModel):
    """生成COT请求"""
    content: str
    filename: str
    model_name: str
    ak: str
    sk: str
    domain: str = "医学"

@router.post("/generate")
async def generate_cot(
    request: COTGenerateRequest,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """生成COT推理"""
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

        # 替换提示词中的domain，保留text占位符供后续替换
        begin_prompt = PROMPT_TEMPLATE.format(
            text="{text}",  # 保留text占位符
            domain=request.domain
        )
        filename=request.filename
        PARSED_FILES_DIR = f"{filename}\\tex_files"
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
            #content=request.content,
            content=content,
            filename=request.filename,
            model_name=request.model_name,
            ak_list=request.AK,
            sk_list=request.SK,
            parallel_num=request.parallel_num,
            begin_prompt=begin_prompt,
            domain=request.domain
        )

        return APIResponse(
            status="success",
            message="COT generated successfully",
            data=result
        )
    except Exception as e:
        logger.error(f"生成COT失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

class FilenameRequest(BaseModel):
    filename: str
@router.post("/content")
async def get_cot_content( request: FilenameRequest):
   # filename: str,
    #db: AsyncIOMotorClient = Depends(get_database)

   """获取COT文件内容"""
   try:
       parsed_dir = os.path.join("result", "cot")
       raw_filename = request.filename.split('.')[0]
       parsed_filename = f"{raw_filename}_cot.json"
       target_path = os.path.join(parsed_dir, parsed_filename)
       if not os.path.isfile(target_path):
           raise HTTPException(status_code=404, detail="COT file not found")
       with open(target_path, 'r', encoding='utf-8') as f:
           content = json.load(f)
       return content
   except FileNotFoundError:
       raise HTTPException(status_code=404, detail="QA file not found")
   except json.JSONDecodeError:
       raise HTTPException(status_code=500, detail="Failed to decode QA file content")
   except Exception as e:
       raise HTTPException(status_code=500, detail=str(e))

@router.delete("/file/{filename}")
async def delete_cot_file(
    filename: str,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """删除COT文件"""
    try:
        service = COTGenerateService(db)
        result = await service.delete_cot_file(filename)

        if result:
            return APIResponse(
                status="success",
                message="File deleted successfully"
            )
        else:
            return APIResponse(
                status="success",
                message="File not found"
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class FilenameRequest(BaseModel):
    filename: str
def check_parsed_file_exist(raw_filename: str) -> int:
    """检查解析结果文件是否存在"""
    filename=raw_filename
    PARSED_FILES_DIR = "result\cot"
    raw_filename = filename.split('.')[0]
    parsed_filename = f"{raw_filename}_cot.json"
    file_path = os.path.join(PARSED_FILES_DIR, parsed_filename)
    return 1 if os.path.isfile(file_path) else 0


@router.post("/cothistory")
async def get_parse_history(request: FilenameRequest):
    try:

        filename = request.filename

        exists = check_parsed_file_exist(filename)
        print(exists)
        return {"status": "OK", "exists": exists}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))