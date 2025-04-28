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
        filename=request.filename
        PARSED_FILES_DIR = f"{filename}\\tex_files"
        raw_filename = filename.split('.')[0]
        parsed_filename = f"{raw_filename}.json"
        file_path = os.path.join(PARSED_FILES_DIR, parsed_filename)

        if not os.path.isfile(file_path):
            raise HTTPException(
                status_code=404,
                detail=f"File {request.filename} not found"
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
        logger.error(f"Failed to generate COT: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

class FilenameRequest(BaseModel):
    filename: str
@router.post("/content")
async def get_cot_content( request: FilenameRequest):
   # filename: str,
    #db: AsyncIOMotorClient = Depends(get_database)

   """Get COT file content"""
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
    """Delete COT file"""
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
    """Check if the parsed result file exists"""
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