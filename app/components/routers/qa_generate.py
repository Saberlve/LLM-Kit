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
from datetime import datetime, timezone, timedelta
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
    """
    生成QA对，已修改为完全使用数据库存储和获取数据，不再使用文件系统
    """
    print("Raw request body:",request_body)

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
           
            # 检查文件是否已经进行过LaTeX转换并且有有效内容
            tex_record = await db.llm_kit.tex_records.find_one(
                {"input_file": filename, "status": "completed"},
                sort=[("created_at", -1)]
            )
            
            # 验证tex_record是否包含有效内容
            has_valid_content = False
            if tex_record and "content" in tex_record:
                try:
                    # 检查内容是否有效
                    content_data = tex_record["content"]
                    if isinstance(content_data, list) and len(content_data) > 0:
                        # 列表类型的内容直接判断
                        has_valid_content = True
                        logger.info(f"文件 {filename} 已有有效的LaTeX转换内容")
                    elif isinstance(content_data, str):
                        # 字符串类型需要解析
                        json_content = json.loads(content_data)
                        if json_content and len(json_content) > 0:
                            has_valid_content = True
                            logger.info(f"文件 {filename} 已有有效的LaTeX转换内容(字符串格式)")
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"LaTeX记录内容解析失败: {str(e)}")
                    has_valid_content = False
            
            if not has_valid_content:
                # 如果未进行LaTeX转换或内容无效，先执行转换
                from app.components.services.to_tex_service import ToTexService
                tex_service = ToTexService(db)
                
                try:
                    logger.info(f"开始对文件 {filename} 进行LaTeX转换")
                    result = await tex_service.convert_to_latex(
                        content=file_record["content"],
                        filename=filename,
                        save_path="result/",  # 此参数将被忽略，但为了向后兼容保留
                        SK=request_body.SK,
                        AK=request_body.AK,
                        parallel_num=request_body.parallel_num,
                        model_name=request_body.model_name
                    )
                    logger.info(f"文件 {filename} LaTeX转换完成，结果：{result}")
                    
                    # 获取转换后的内容
                    if "content" in result and result["content"]:
                        content = json.dumps(result["content"])
                        logger.info(f"获取到LaTeX转换内容，长度: {len(content)}")
                    else:
                        raise HTTPException(
                            status_code=500,
                            detail=f"LaTeX转换完成但无法获取结果内容"
                        )
                except Exception as e:
                    logger.error(f"LaTeX转换失败: {str(e)}", exc_info=True)
                    raise HTTPException(
                        status_code=500,
                        detail=f"LaTeX转换失败: {str(e)}"
                    )
            else:
                # 已经进行过LaTeX转换且内容有效，直接获取内容
                if isinstance(tex_record["content"], list):
                    content = json.dumps(tex_record["content"])
                else:
                    content = tex_record["content"]
                logger.info(f"使用已有的LaTeX转换内容，长度: {len(content) if content else 0}")
        else:
            # 如果在uploaded_files中找不到，尝试从tex_records直接获取
            tex_record = await db.llm_kit.tex_records.find_one(
                {"input_file": filename, "status": "completed"},
                sort=[("created_at", -1)]
            )
            
            # 验证tex_record是否包含有效内容
            has_valid_content = False
            if tex_record and "content" in tex_record:
                try:
                    # 检查内容是否有效
                    content_data = tex_record["content"]
                    if isinstance(content_data, list) and len(content_data) > 0:
                        has_valid_content = True
                        content = json.dumps(content_data)
                        logger.info(f"从tex_records获取到有效内容，长度: {len(content)}")
                    elif isinstance(content_data, str):
                        json_content = json.loads(content_data)
                        if json_content and len(json_content) > 0:
                            has_valid_content = True
                            content = content_data
                            logger.info(f"从tex_records获取到有效内容(字符串格式)，长度: {len(content)}")
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"从tex_records获取的内容解析失败: {str(e)}")
                    has_valid_content = False
            
            if not has_valid_content:
                # 找不到有效内容，无法继续
                raise HTTPException(
                    status_code=404,
                    detail=f"文件 {filename} 未找到或未完成LaTeX转换，请先上传文件"
                )

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

        # 将QA结果直接存储到数据库
        try:
            # 假设result中有qa_data字段包含QA对
            if "qa_data" in result and result["qa_data"]:
                qa_data = result["qa_data"]
                
                # 创建新的数据集条目并保存到数据库
                raw_filename = request_body.filename.split('.')[0]
                dataset_entry = {
                    "name": f"QA-{raw_filename}",
                    "description": f"Generated QA from {request_body.filename} using {request_body.model_name}",
                    "pool_id": 2,  # 假设这是QA构建的池ID
                    "kind": 2,     # 表示这是构建的数据集
                    "file_data": json.dumps(qa_data) if not isinstance(qa_data, str) else qa_data,
                    "created_at": datetime.now(),
                    "model_name": request_body.model_name,
                    "domain": request_body.domain,
                    "is_qa": True
                }
                
                result_id = await db.llm_kit.dataset_entries.insert_one(dataset_entry)
                
                # 将数据库ID添加到返回结果中
                result["dataset_id"] = str(result_id.inserted_id)
            else:
                logger.warning(f"生成的QA结果中没有qa_data字段或为空")
        except Exception as e:
            logger.error(f"存储QA结果到数据库失败: {str(e)}", exc_info=True)
            # 继续执行，不阻止返回结果

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
    """获取QA生成进度信息，包括进度百分比、预估完成时间和已用时间"""
    try:
        logger.info(f"获取QA生成进度: filename={request.filename}")
        
        # 查找最新的记录
        record = await db.llm_kit.qa_generations.find_one(
            {
                "input_file": request.filename,
                "status": {"$in": ["processing", "completed", "failed", "timeout"]}
            },
            sort=[("created_at", -1)]  # 按创建时间降序排序
        )

        if not record:
            logger.warning(f"未找到文件 {request.filename} 的QA生成进度记录")
            return APIResponse(
                status="not_found",
                message=f"Progress record for file {request.filename} not found",
                data={
                    "progress": 0,
                    "status": "not_found",
                    "elapsed_time": 0,
                    "estimated_remaining_time": 0,
                    "estimated_completion_time": None,
                    "processed_chunks": 0,
                    "total_chunks": 0,
                    "step": "qa_generation"
                }
            )

        # 获取状态和进度
        status = record.get("status", "processing")
        progress = record.get("progress", 0)
        
        # 获取块处理信息
        chunk_info = record.get("chunk_info", {"total_chunks": 0, "processed_chunks": 0})
        total_chunks = chunk_info.get("total_chunks", 0)
        processed_chunks = chunk_info.get("processed_chunks", 0)
        
        logger.info(f"QA生成进度: status={status}, progress={progress}%, processed_chunks={processed_chunks}/{total_chunks}")
        
        # 计算已经花费的时间（秒）
        # 确保时间对象都是带时区的
        current_time = datetime.now(timezone.utc)
        
        # 如果start_time存在，使用它，否则使用created_at
        start_time = record.get("start_time")
        if start_time and not isinstance(start_time, datetime):
            # 如果start_time不是datetime对象，尝试转换
            try:
                start_time = datetime.fromisoformat(str(start_time))
            except:
                start_time = None
                
        # 如果start_time为空或转换失败，使用created_at
        if not start_time:
            start_time = record.get("created_at")
            
        # 确保start_time有时区信息
        if start_time and start_time.tzinfo is None:
            # 如果start_time没有时区信息，添加UTC时区
            start_time = start_time.replace(tzinfo=timezone.utc)
            
        if not start_time:
            # 如果仍然没有有效的start_time，使用当前时间
            start_time = current_time
        
        # 现在两个时间都有时区信息，可以安全计算差值
        elapsed_seconds = int((current_time - start_time).total_seconds())
        
        # 计算预估剩余时间
        estimated_remaining_seconds = 0
        estimated_completion_time = None
        
        if status == "processing" and progress > 0:
            # 如果记录中已有预估完成时间，直接使用
            if "estimated_completion_time" in record and record["estimated_completion_time"]:
                estimated_completion_time = record["estimated_completion_time"]
                # 确保estimated_completion_time有时区信息
                if estimated_completion_time and estimated_completion_time.tzinfo is None:
                    estimated_completion_time = estimated_completion_time.replace(tzinfo=timezone.utc)
                if estimated_completion_time:
                    estimated_remaining_seconds = max(0, int((estimated_completion_time - current_time).total_seconds()))
            # 否则基于当前进度估算
            elif progress < 100 and progress > 10 and elapsed_seconds > 0:
                # 基于已完成的百分比和已用时间来估计
                total_estimated_seconds = (elapsed_seconds / progress) * 100
                estimated_remaining_seconds = max(0, int(total_estimated_seconds - elapsed_seconds))
                estimated_completion_time = current_time + timedelta(seconds=estimated_remaining_seconds)
        
        # 如果状态是已完成，设置进度为100%
        if status == "completed":
            progress = 100
            estimated_remaining_seconds = 0
            processed_chunks = total_chunks
        
        # 格式化时间显示
        formatted_elapsed_time = format_time_duration(elapsed_seconds)
        formatted_remaining_time = format_time_duration(estimated_remaining_seconds)
        formatted_completion_time = estimated_completion_time.strftime("%H:%M:%S") if estimated_completion_time else None

        response_data = {
            "progress": progress,
            "status": status,
            "error_message": record.get("error_message", ""),
            "last_update": record.get("created_at", datetime.now(timezone.utc)).isoformat(),
            "elapsed_time": elapsed_seconds,
            "formatted_elapsed_time": formatted_elapsed_time,
            "estimated_remaining_time": estimated_remaining_seconds,
            "formatted_remaining_time": formatted_remaining_time,
            "estimated_completion_time": estimated_completion_time.isoformat() if estimated_completion_time else None,
            "formatted_completion_time": formatted_completion_time,
            "processed_chunks": processed_chunks,
            "total_chunks": total_chunks,
            "step": "qa_generation"
        }
        
        logger.info(f"返回QA生成进度数据: progress={progress}%, status={status}")
        return APIResponse(
            status="success",
            message="Progress retrieved successfully",
            data=response_data
        )
    except Exception as e:
        logger.error(f"获取QA生成进度失败: {str(e)}", exc_info=True)
        return APIResponse(
            status="error",
            message=f"Failed to get progress: {str(e)}",
            data={
                "progress": 0,
                "status": "error",
                "elapsed_time": 0,
                "estimated_remaining_time": 0,
                "estimated_completion_time": None,
                "processed_chunks": 0,
                "total_chunks": 0,
                "step": "qa_generation"
            }
        )

def format_time_duration(seconds: int) -> str:
    """将秒数格式化为人类可读的时间格式（小时:分钟:秒）"""
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"

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
    """
    预览QA数据集内容，已修改为仅从数据库读取数据，不再使用文件系统
    """
    try:
        # 尝试从数据库获取内容
        dataset = None
        
        # 先尝试将dataset_id当作ObjectId
        try:
            obj_id = ObjectId(dataset_id)
            dataset = await db.llm_kit.dataset_entries.find_one({"_id": obj_id})
        except:
            # 如果不是有效的ObjectId，尝试用名称查找
            dataset = await db.llm_kit.dataset_entries.find_one({"name": dataset_id})
        
        if not dataset:
            raise HTTPException(status_code=404, detail="QA数据集未找到")
        
        # 获取QA内容
        try:
            qa_data = []
            if "file_data" in dataset:
                if isinstance(dataset["file_data"], str):
                    qa_data = json.loads(dataset["file_data"])
                else:
                    qa_data = dataset["file_data"]
        except json.JSONDecodeError:
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

@router.get("/download/{dataset_id}")
async def download_qa_dataset(
    dataset_id: str,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """
    Download QA dataset content from database
    """
    try:
        # Try to get content from database
        dataset = None
        
        # First try to use dataset_id as ObjectId
        try:
            obj_id = ObjectId(dataset_id)
            dataset = await db.llm_kit.dataset_entries.find_one({"_id": obj_id})
        except:
            # If not a valid ObjectId, try to find by name
            dataset = await db.llm_kit.dataset_entries.find_one({"name": dataset_id})
        
        if not dataset:
            raise HTTPException(status_code=404, detail="QA dataset not found")
        
        # Get QA content
        file_data = dataset.get("file_data", "[]")
        
        # Ensure file_data is proper JSON string with UTF-8 encoding
        if isinstance(file_data, str):
            try:
                # Parse string to object to ensure it's valid JSON
                json_obj = json.loads(file_data)
                # Re-encode with proper formatting for Chinese characters
                file_data = json.dumps(json_obj, ensure_ascii=False, indent=2)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON data in dataset: {str(e)}")
                file_data = "[]"
        else:
            # If it's already a Python object (not a string), convert to proper JSON
            file_data = json.dumps(file_data, ensure_ascii=False, indent=2)
        
        # Create a safe ASCII filename by using only alphanumeric characters
        safe_name = "".join(c for c in dataset.get('name', 'qa_dataset') if c.isalnum() or c in '-_.')
        if not safe_name:
            safe_name = "qa_dataset"
        file_name = f"{safe_name}.json"
        
        # URL encode the filename to handle non-ASCII characters
        encoded_filename = urllib.parse.quote(file_name)
        
        # Return file for download with correct encoding
        return StreamingResponse(
            io.StringIO(file_data),
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"}
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Failed to download QA dataset: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.post("/tex_processing_progress")
async def get_tex_processing_progress(
        request: FilenameRequest,
        db: AsyncIOMotorClient = Depends(get_database)
):
    """获取LaTeX处理的实时进度信息，从临时进度记录表中读取"""
    try:
        from app.components.services.to_tex_service import ToTexService
        
        logger.info(f"获取LaTeX处理进度: filename={request.filename}")
        
        # 创建服务实例
        service = ToTexService(db)
        
        # 调用服务函数获取进度信息
        progress_data = await service.get_tex_processing_progress(request.filename)
        
        logger.info(f"返回LaTeX处理进度数据: progress={progress_data['progress']}%, status={progress_data['status']}")
        
        return APIResponse(
            status="success",
            message="Progress retrieved successfully",
            data=progress_data
        )
    except Exception as e:
        logger.error(f"获取LaTeX处理进度失败: {str(e)}", exc_info=True)
        return APIResponse(
            status="error",
            message=f"Failed to get progress: {str(e)}",
            data={
                "progress": 0,
                "status": "error",
                "elapsed_time": 0,
                "estimated_remaining_time": 0,
                "estimated_completion_time": None,
                "processed_chunks": 0,
                "total_chunks": 0,
                "step": "latex_conversion"
            }
        )