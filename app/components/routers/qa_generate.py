import logging
from fastapi import APIRouter, HTTPException, Depends,Request,Query
from fastapi.responses import JSONResponse, StreamingResponse
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
from datetime import datetime, timezone
import io
from bson import ObjectId
import base64
import urllib.parse

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
    """Get all converted tex files list"""
    try:
        service = QAGenerateService(db)
        files = await service.get_all_tex_files()
        return APIResponse(
            status="success",
            message="File list retrieved successfully",
            data={"files": [TexFile(**file) for file in files]}
        )
    except Exception as e:
        logger.error(f"Failed to get tex file list: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/tex_content", response_model=APIResponse)
async def get_tex_content(
        request: TexContentRequest,
        db: AsyncIOMotorClient = Depends(get_database)
):
    """Get content of specified tex file"""
    try:
        service = QAGenerateService(db)
        content = await service.get_tex_content(request.file_id)
        return APIResponse(
            status="success",
            message="File content retrieved successfully",
            data=content
        )
    except Exception as e:
        logger.error(f"Failed to get tex file content: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/generate_qa")
async def generate_qa_pairs(
        request_body: QAGenerateRequest,
        raw_request: Request,
        db: AsyncIOMotorClient = Depends(get_database)
):

    print("Raw request body:",request_body)

    """Generate QA pairs"""
    try:
        # Verify that AK and SK counts match
        if len(request_body.AK) != len(request_body.SK):
            raise HTTPException(
                status_code=400,
                detail="The number of AK and SK must be the same"
            )

        # Verify that parallel count is reasonable
        if request_body.parallel_num > len(request_body.AK):
            raise HTTPException(
                status_code=400,
                detail="Parallel count cannot be greater than the number of API key pairs"
            )
        
        filename = request_body.filename
        content = None
        # 首先尝试从数据库中获取文件内容
        
        file_record = await db.llm_kit.uploaded_files.find_one({"filename": filename})
        
        if file_record and "content" in file_record:
            # 检查文件是否已经进行过LaTeX转换
            tex_record = await db.llm_kit.tex_records.find_one(
                {"input_file": filename, "status": "completed"},
                sort=[("created_at", -1)]
            )
            
           
            if not tex_record:
                # 如果未进行LaTeX转换，先执行转换
                from app.components.services.to_tex_service import ToTexService
                tex_service = ToTexService(db)
                
                try:
                    logger.info(f"开始对文件 {filename} 进行LaTeX转换")
                    result = await tex_service.convert_to_latex(
                        content=file_record["content"],
                        filename=filename,
                        save_path="result/",
                        SK=request_body.SK,
                        AK=request_body.AK,
                        parallel_num=request_body.parallel_num,
                        model_name=request_body.model_name
                    )
                    logger.info(f"文件 {filename} LaTeX转换完成，结果：{result}")
                    
                    # 获取转换后的内容
                    if "content" in result:
                        content = json.dumps(result["content"])
                    else:
                        # 从文件中读取
                        save_path = result.get("save_path")
                        if save_path and os.path.isfile(save_path):
                            with open(save_path, 'r', encoding='utf-8') as f:
                                content = f.read()
                        else:
                            raise HTTPException(
                                status_code=500,
                                detail=f"LaTeX转换完成但无法读取结果文件"
                            )
                except Exception as e:
                    logger.error(f"LaTeX转换失败: {str(e)}", exc_info=True)
                    raise HTTPException(
                        status_code=500,
                        detail=f"LaTeX转换失败: {str(e)}"
                    )
            else:
                # 已经进行过LaTeX转换，直接获取内容
                if "content" in tex_record:
                    content = json.dumps(tex_record["content"])
                else:
                    # 从文件中读取
                    save_path = tex_record.get("save_path")
                    if save_path and os.path.isfile(save_path):
                        with open(save_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                    else:
                        raise HTTPException(
                            status_code=500,
                            detail=f"无法读取LaTeX转换结果文件"
                        )
        else:
            # 如果数据库中没有找到，尝试从文件系统读取
            # 首先检查是否有LaTeX转换记录
            tex_record = await db.llm_kit.tex_records.find_one(
                {"input_file": filename, "status": "completed"},
                sort=[("created_at", -1)]
            )
            
            if tex_record:
                # 已经进行过LaTeX转换，直接获取内容
                if "content" in tex_record:
                    content = json.dumps(tex_record["content"])
                else:
                    # 从文件中读取
                    save_path = tex_record.get("save_path")
                    if save_path and os.path.isfile(save_path):
                        with open(save_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                    else:
                        raise HTTPException(
                            status_code=500,
                            detail=f"无法读取LaTeX转换结果文件"
                        )
            else:
                # 尝试在文件系统中寻找
                PARSED_FILES_DIR = os.path.join("result", "tex_files")
                raw_filename = filename.split('.')[0]
                parsed_filename = f"{raw_filename}.json"
                file_path = os.path.join(PARSED_FILES_DIR, parsed_filename)
                
                if not os.path.isfile(file_path):
                    # 找不到文件，无法继续
                    raise HTTPException(
                        status_code=404,
                        detail=f"文件 {filename} 未找到，请先上传文件"
                    )
                
                with open(file_path, 'r', encoding='utf-8') as file:
                    content = file.read()

        # 确保content不为空
        if not content:
            raise HTTPException(
                status_code=500,
                detail=f"无法获取 {filename} 的LaTeX转换内容"
            )

        service = QAGenerateService(db)
        result = await service.generate_qa_pairs(
            content=content,
            filename=request_body.filename,  
            SK=request_body.SK,
            AK=request_body.AK,
            parallel_num=request_body.parallel_num,
            model_name=request_body.model_name,
            domain=request_body.domain
        )

        # 将生成的结果存储到数据库
        qa_data = None
        PARSED_FILES_DIR = os.path.join("result", "qas")
        raw_filename = request_body.filename.split('.')[0]
        parsed_filename = f"{raw_filename}_qa.json"
        file_path = os.path.join(PARSED_FILES_DIR, parsed_filename)
        
        if os.path.isfile(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                qa_data = f.read()
        
        if qa_data:
            # 创建新的数据集条目并保存到数据库
            dataset_entry = {
                "name": f"QA-{raw_filename}",
                "description": f"Generated QA from {request_body.filename} using {request_body.model_name}",
                "pool_id": 2,  # 假设这是QA构建的池ID
                "kind": 2,     # 表示这是构建的数据集
                "file_data": qa_data,
                "created_at": datetime.now(),
                "model_name": request_body.model_name,
                "domain": request_body.domain,
                "is_qa": True
            }
            
            result_id = await db.llm_kit.dataset_entries.insert_one(dataset_entry)
            
            # 将数据库ID添加到返回结果中
            result["dataset_id"] = str(result_id.inserted_id)

        return APIResponse(
            status="success",
            message="QA pairs generated successfully",
            data=result
        )
    except Exception as e:
        logger.error(f"Failed to generate QA pairs: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/generate_qa/history")
async def get_qa_history(
        db: AsyncIOMotorClient = Depends(get_database)
):
    """Get QA generation history records"""
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
    """Get QA generation progress"""
    try:
        # 
        record = await db.llm_kit.qa_generations.find_one(
            {
                "input_file": request.filename,
                "status": {"$in": ["processing", "completed", "failed", "timeout"]}
            },
            sort=[("created_at", -1)]  # 
        )

        if not record:
            return APIResponse(
                status="not_found",
                message=f"Progress record for file {request.filename} not found",
                data={
                    "progress": 0,
                    "status": "not_found"
                }
            )

        # 
        status = record.get("status", "processing")
        progress = record.get("progress", 0)

        # completed，100%
        if status == "completed":
            progress = 100
        # failedtimeout，
        elif status in ["failed", "timeout"]:
            progress = progress

        return APIResponse(
            status="success",
            message="Progress retrieved successfully",
            data={
                "progress": progress,
                "status": status,
                "error_message": record.get("error_message", ""),  # 
                "last_update": record.get("created_at", datetime.now(timezone.utc)).isoformat()  # 
            }
        )
    except Exception as e:
        logger.error(f"Failed to get progress: {str(e)}", exc_info=True)
        return APIResponse(
            status="error",
            message=f"Failed to get progress: {str(e)}",
            data={
                "progress": 0,
                "status": "error"
            }
        )

@router.delete("/qa_records")
async def delete_qa_record(
        request: RecordIDRequest,
        db: AsyncIOMotorClient = Depends(get_database)
):
    """Delete QA generation record and related QA pairs by ID"""
    try:
        from bson import ObjectId

        # 
        result = await db.llm_kit.qa_generations.delete_one({"_id": ObjectId(request.record_id)})

        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Record not found")

        # 
        await db.llm_kit.qa_pairs.delete_many({"generation_id": ObjectId(request.record_id)})

        return APIResponse(
            status="success",
            message="QA record and related pairs deleted successfully",
            data={"record_id": request.record_id}
        )

    except Exception as e:
        logger.error(f"Failed to delete QA record, record_id: {request.record_id}, error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

class FilenameRequest(BaseModel):
    filename: str

async def check_parsed_file_exist(raw_filename: str, db: AsyncIOMotorClient) -> int:
    """Check if parsed result file exists in database"""
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


@router.post("/qashistory")
async def get_parse_history(
    request: FilenameRequest,
    db: AsyncIOMotorClient = Depends(get_database)
):
    try:
        # 获取文件名并进行URL解码
        filename = request.filename
        decoded_filename = urllib.parse.unquote(filename)
        logger.info(f"检查QA历史: 原始文件名={filename}, 解码后文件名={decoded_filename}")

        exists = await check_parsed_file_exist(decoded_filename, db)
        logger.info(f"文件 {decoded_filename} QA历史存在状态: {exists}")
        return {"status": "OK", "exists": exists}
    except Exception as e:
        logger.error(f"获取QA历史失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/delete_file")
async def delete_files(
    request: FilenameRequest,
    db: AsyncIOMotorClient = Depends(get_database)
):
    '''Delete construction file from database'''
    try:
        # URL解码文件名
        decoded_filename = urllib.parse.unquote(request.filename)
        logger.info(f"删除QA文件: 原始文件名={request.filename}, 解码后文件名={decoded_filename}")
        
        # 尝试按文件名删除
        result = await db.llm_kit.dataset_entries.delete_one({"name": decoded_filename})
        if result.deleted_count > 0:
            logger.info(f"成功从数据库删除QA文件: {decoded_filename}")
            return {"status": "success"}
        
        # 尝试使用ID删除
        try:
            if len(decoded_filename) == 24:
                try:
                    obj_id = ObjectId(decoded_filename)
                    result = await db.llm_kit.dataset_entries.delete_one({"_id": obj_id})
                    if result.deleted_count > 0:
                        logger.info(f"成功通过ID从数据库删除QA文件: {decoded_filename}")
                        return {"status": "success"}
                except:
                    pass
        except Exception as e:
            logger.warning(f"尝试通过ID删除QA文件时出错: {str(e)}")
        
        logger.warning(f"QA文件在数据库中不存在: {decoded_filename}")
        return {"status": "failed", "message": "File not found in database"}
    except Exception as e:
        logger.error(f"删除QA文件失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get_qa_content")
async def get_qa_content(
    filename: str = Query(..., title="Filename"),
    db: AsyncIOMotorClient = Depends(get_database)
):
    """Get QA file content"""
    try:
        # URL解码文件名
        decoded_filename = urllib.parse.unquote(filename)
        logger.info(f"获取QA内容: 原始文件名={filename}, 解码后文件名={decoded_filename}")
        
        # 尝试从数据库中获取QA数据集
        # 先查询文件名对应的dataset_entries
        dataset = await db.llm_kit.dataset_entries.find_one({"name": decoded_filename})
        if dataset:
            logger.info(f"在数据库dataset_entries中找到QA内容: {decoded_filename}")
            try:
                return json.loads(dataset.get("file_data", "[]"))
            except json.JSONDecodeError:
                logger.error(f"解析数据库中QA数据格式失败: {decoded_filename}")
                raise HTTPException(status_code=500, detail="Invalid QA data format in database")
        
        # 尝试使用文件ID查找
        try:
            if len(decoded_filename) == 24:
                try:
                    obj_id = ObjectId(decoded_filename)
                    # 尝试用ObjectId查找
                    dataset = await db.llm_kit.dataset_entries.find_one({"_id": obj_id})
                    if dataset:
                        logger.info(f"通过ID在数据库中找到QA内容: {decoded_filename}")
                        try:
                            return json.loads(dataset.get("file_data", "[]"))
                        except json.JSONDecodeError:
                            logger.error(f"解析数据库中QA数据格式失败: {decoded_filename}")
                            raise HTTPException(status_code=500, detail="Invalid QA data format in database")
                except:
                    pass
        except Exception as e:
            logger.warning(f"尝试通过ID查找QA内容时出错: {str(e)}")
        
        logger.error(f"QA内容未在数据库中找到: {decoded_filename}")
        raise HTTPException(status_code=404, detail="QA content not found in database")
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"获取QA内容失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/get_raw_content")
async def get_raw_content(
    filename: str = Query(..., title="Filename"),
    db: AsyncIOMotorClient = Depends(get_database)
):
    """Get raw file content"""
    try:
        # URL解码文件名
        decoded_filename = urllib.parse.unquote(filename)
        logger.info(f"获取原始内容: 原始文件名={filename}, 解码后文件名={decoded_filename}")
        
        # 从数据库中查找文件
        file_record = await db.llm_kit.uploaded_files.find_one({"filename": decoded_filename})
        logger.info(f"数据库查询结果: {'找到文件' if file_record else '未找到文件'}")
        
        if file_record and "content" in file_record:
            # 从文本文件集合中找到
            logger.info(f"在数据库中找到文件: {decoded_filename}")
            return file_record["content"]
        
        # 尝试使用文件ID查找
        try:
            if len(decoded_filename) == 24:
                try:
                    obj_id = ObjectId(decoded_filename)
                    # 尝试用ObjectId查找
                    file_record = await db.llm_kit.uploaded_files.find_one({"_id": obj_id})
                    if file_record and "content" in file_record:
                        logger.info(f"通过ID在数据库中找到文件: {decoded_filename}")
                        return file_record["content"]
                except:
                    pass
        except Exception as e:
            logger.warning(f"尝试通过ID查找文件时出错: {str(e)}")
        
        # 如果在数据库中没有找到
        logger.error(f"原始文件未找到: {decoded_filename}")
        raise HTTPException(status_code=404, detail="Raw file not found in database")
    except Exception as e:
        logger.error(f"获取原始内容失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/preview/{dataset_id}")
async def preview_qa_dataset(
    dataset_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: AsyncIOMotorClient = Depends(get_database)
):
    """预览QA数据集内容"""
    try:
        try:
            obj_id = ObjectId(dataset_id)
        except:
            # 如果不是有效的ObjectId，尝试从文件读取
            return await preview_qa_file(dataset_id, page, page_size)
            
        # 从数据库获取内容
        dataset = await db.llm_kit.dataset_entries.find_one({"_id": obj_id})
        if not dataset:
            # 如果数据库中找不到，尝试从文件读取
            return await preview_qa_file(dataset_id, page, page_size)
        
        # 获取QA内容
        try:
            qa_data = json.loads(dataset.get("file_data", "[]"))
        except:
            raise HTTPException(status_code=500, detail="无效的QA数据格式")
        
        # 分页处理
        total_items = len(qa_data)
        total_pages = (total_items + page_size - 1) // page_size
        
        start_idx = (page - 1) * page_size
        end_idx = min(start_idx + page_size, total_items)
        
        items = qa_data[start_idx:end_idx]
        
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
        logger.error(f"预览QA数据集失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"服务器错误: {str(e)}")

async def preview_qa_file(filename: str, page: int, page_size: int):
    """从文件预览QA内容"""
    try:
        parsed_dir = os.path.join("result", "qas")
        raw_filename = filename.split('.')[0]
        parsed_filename = f"{raw_filename}_qa.json"
        target_path = os.path.join(parsed_dir, parsed_filename)
        
        if not os.path.isfile(target_path):
            raise HTTPException(status_code=404, detail="QA文件未找到")
            
        with open(target_path, 'r', encoding='utf-8') as f:
            qa_data = json.load(f)
        
        # 分页处理
        total_items = len(qa_data)
        total_pages = (total_items + page_size - 1) // page_size
        
        start_idx = (page - 1) * page_size
        end_idx = min(start_idx + page_size, total_items)
        
        items = qa_data[start_idx:end_idx]
        
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
        logger.error(f"预览QA文件失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"服务器错误: {str(e)}")

@router.get("/download/{dataset_id}")
async def download_qa_dataset(
    dataset_id: str,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """下载QA数据集内容"""
    try:
        try:
            obj_id = ObjectId(dataset_id)
        except:
            # 如果不是有效的ObjectId，尝试从文件下载
            return await download_qa_file(dataset_id)
            
        # 从数据库获取内容
        dataset = await db.llm_kit.dataset_entries.find_one({"_id": obj_id})
        if not dataset:
            # 如果数据库中找不到，尝试从文件下载
            return await download_qa_file(dataset_id)
        
        # 获取QA内容
        file_data = dataset.get("file_data", "[]")
        file_name = f"{dataset.get('name', 'qa_dataset')}.json"
        
        # 返回文件下载
        return StreamingResponse(
            io.StringIO(file_data),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename={file_name}"}
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"下载QA数据集失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"服务器错误: {str(e)}")

async def download_qa_file(filename: str):
    """从文件下载QA内容"""
    try:
        parsed_dir = os.path.join("result", "qas")
        raw_filename = filename.split('.')[0]
        parsed_filename = f"{raw_filename}_qa.json"
        target_path = os.path.join(parsed_dir, parsed_filename)
        
        if not os.path.isfile(target_path):
            raise HTTPException(status_code=404, detail="QA文件未找到")
            
        with open(target_path, 'r', encoding='utf-8') as f:
            qa_data = f.read()
        
        # 返回文件下载
        return StreamingResponse(
            io.StringIO(qa_data),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename={parsed_filename}"}
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"下载QA文件失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"服务器错误: {str(e)}")