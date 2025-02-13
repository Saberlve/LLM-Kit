import logging
from fastapi import APIRouter, HTTPException, Depends
from motor.motor_asyncio import AsyncIOMotorClient
from app.components.core.database import get_database
from app.components.models.schemas import APIResponse
from app.components.services.cot_generate_service import COTGenerateService
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)

PROMPT_TEMPLATE = """
{text}
# 你是一位经验丰富的{domain}专家，同时一个专业的用户问题分析师，同时也擅长markdown的专业使用；你也擅长专业的{domain}文章写作，拥有极高的文学素养。擅长针对用户提出的{domain}相关问题进行深入分析和专业解答。你的目标受众可能是{domain}专业人士、患者或普通用户，因此回答既要专业又易于理解。
# ##任务背景 
# - 我们团队要完成一个复杂的{domain}推理任务 
# - 我们现在已经有了一个具体的用户问题，我们要针对用户问题给一个完善的回答，整篇文章围绕用户问题来展开，这篇文章是对用户问题的作答。 
# - 首先你需要根据用户的问题，并充分结合你广博又扎实的{domain}知识，从更全面、更多样的角度来分析用户的问题（尽可能多的给出用户可能患的病情或尽可能多的给出解决方案），之后根据你认为最有可能的情况为用户撰写一篇分析深入、逻辑严谨、论述完整、关怀到位的{domain}建议！并给出你的分析过程。
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
    request: GenerateCOTRequest,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """生成COT推理"""
    try:
        # 替换提示词中的domain
        begin_prompt = PROMPT_TEMPLATE.format(
            text=request.content,
            domain=request.domain
        )
        service = COTGenerateService(db)
        result = await service.generate_cot(
            content=request.content,
            filename=request.filename,
            model_name=request.model_name,
            ak=request.ak,
            sk=request.sk,
            begin_prompt=begin_prompt
        )

        return APIResponse(
            status="success",
            message="COT generated successfully",
            data=result
        )
    except Exception as e:
        logger.error(f"生成COT失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/content/{filename}")
async def get_cot_content(
    filename: str,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """获取COT文件内容"""
    try:
        service = COTGenerateService(db)
        content = await service.get_cot_content(filename)
        return APIResponse(
            status="success",
            message="Content retrieved successfully",
            data=content
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="COT file not found")
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
