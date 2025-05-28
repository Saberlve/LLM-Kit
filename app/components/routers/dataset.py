from fastapi import APIRouter, HTTPException, Depends, File, UploadFile, Form, Query
from fastapi.responses import JSONResponse
from typing import List, Optional
from motor.motor_asyncio import AsyncIOMotorClient
from app.components.core.database import get_database
from bson import ObjectId
from datetime import datetime
import os
import json
import logging

# 设置日志
logger = logging.getLogger(__name__)

router = APIRouter()

# 数据模型定义
class DatasetEntry:
    def __init__(self, file_data, name, description, pool_id, kind=0):
        self.name = name
        self.description = description
        self.pool_id = pool_id
        self.kind = kind
        self.file_data = file_data
        self.created_at = datetime.now()

    def to_dict(self):
        return {
            "name": self.name,
            "description": self.description,
            "pool_id": self.pool_id,
            "kind": self.kind,
            "file_data": self.file_data,
            "created_at": self.created_at
        }

# 数据集API
@router.post("/dataset")
async def create_dataset(
    file: UploadFile = File(...),
    name: str = Query(None),
    description: str = Query(None),
    pool_id: int = Query(None),
    kind: int = Query(0),
    db: AsyncIOMotorClient = Depends(get_database)
):
    """创建新的数据集"""
    try:
        logger.info(f"接收到文件上传请求: 文件名={file.filename}, name={name}, description={description}, pool_id={pool_id}, kind={kind}")
        
        # 读取上传的文件内容
        file_content = await file.read()
        logger.info(f"文件内容大小: {len(file_content)} 字节")
        
        # 如果是JSON文件，验证其格式
        if file.filename.endswith('.json'):
            try:
                # 解码并验证JSON格式
                json_content = json.loads(file_content.decode('utf-8'))
                # 这里可以添加额外的JSON验证逻辑
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="无效的JSON文件")
        
        # 创建数据集条目
        try:
            file_data = file_content.decode('utf-8')
        except UnicodeDecodeError:
            # 如果无法解码为UTF-8，则保存为二进制字符串的base64编码
            import base64
            file_data = base64.b64encode(file_content).decode('ascii')
            
        dataset_entry = DatasetEntry(
            file_data=file_data,
            name=name,
            description=description,
            pool_id=pool_id,
            kind=kind
        )
        
        # 保存到数据库
        entry_dict = dataset_entry.to_dict()
        logger.info(f"准备保存数据集条目: 名称={entry_dict['name']}, 池ID={entry_dict['pool_id']}")
        result = await db.llm_kit.dataset_entries.insert_one(entry_dict)
        logger.info(f"数据集条目已保存，ID: {result.inserted_id}")
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "数据集已创建",
                "data": {
                    "id": str(result.inserted_id),
                    "name": name,
                    "description": description,
                    "pool_id": pool_id,
                    "kind": kind,
                    "created_at": dataset_entry.created_at.isoformat()
                }
            }
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"创建数据集失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"服务器错误: {str(e)}")

@router.get("/dataset_entry/by_pool/{pool_id}")
async def get_dataset_entries_by_pool(
    pool_id: int,
    operation: Optional[int] = None,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """获取特定池中的所有数据集条目"""
    try:
        logger.info(f"获取池ID为 {pool_id} 的数据集条目，operation={operation}")
        
        # 将pool_id转换为整数
        try:
            pool_id = int(pool_id)
        except ValueError:
            logger.warning(f"无效的池ID格式: {pool_id}")
            # 如果无法转换为整数，仍然尝试使用原始值
        
        # 构建查询条件
        query = {"pool_id": pool_id}
        if operation is not None:
            query["operation"] = operation
        
        logger.info(f"查询条件: {query}")
            
        # 查询数据库
        cursor = db.llm_kit.dataset_entries.find(query)
        
        # 收集结果
        entries = []
        async for doc in cursor:
            # 调整文档格式以匹配前端期望的DatasetEntry结构
            entry = {
                "id": str(doc["_id"]),
                "pool_id": doc["pool_id"],
                "name": doc["name"],
                "description": doc["description"],
                "type": "json",  # 默认类型
                "created_on": doc["created_at"].isoformat() if isinstance(doc["created_at"], datetime) else str(doc["created_at"]),
                "size": len(doc.get("file_data", "")) if "file_data" in doc else 0,
                "owner": "system",
                "public": True
            }
            
            # 添加其他可能的字段
            for key, value in doc.items():
                if key not in ["_id", "file_data", "created_at"] and key not in entry:
                    entry[key] = value
                    
            entries.append(entry)
        
        logger.info(f"找到 {len(entries)} 个数据集条目")
        return entries
    except Exception as e:
        logger.error(f"获取数据集条目失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"服务器错误: {str(e)}")

@router.delete("/dataset/{dataset_id}")
async def delete_dataset(
    dataset_id: str,
    db: AsyncIOMotorClient = Depends(get_database)
):
    """删除数据集条目"""
    try:
        logger.info(f"删除数据集ID: {dataset_id}")
        
        # 尝试将dataset_id转换为ObjectId
        try:
            obj_id = ObjectId(dataset_id)
            logger.info(f"将 {dataset_id} 转换为ObjectId: {obj_id}")
        except Exception as e:
            # 如果无法转换为ObjectId，则尝试作为整数处理
            logger.warning(f"无法将 {dataset_id} 转换为ObjectId: {str(e)}，尝试作为整数处理")
            try:
                dataset_id = int(dataset_id)
                # 查找具有该ID的数据集（使用 "id" 字段而不是 "_id"）
                dataset = await db.llm_kit.dataset_entries.find_one({"id": dataset_id})
                if dataset:
                    obj_id = dataset["_id"]
                else:
                    raise HTTPException(status_code=404, detail=f"未找到ID为 {dataset_id} 的数据集")
            except ValueError:
                raise HTTPException(status_code=400, detail=f"无效的数据集ID格式: {dataset_id}")
        
        # 删除数据集
        result = await db.llm_kit.dataset_entries.delete_one({"_id": obj_id})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail=f"未找到ID为 {dataset_id} 的数据集")
            
        logger.info(f"成功删除数据集ID: {dataset_id}")
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "数据集已删除",
                "data": {"id": dataset_id}
            }
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"删除数据集失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"服务器错误: {str(e)}") 