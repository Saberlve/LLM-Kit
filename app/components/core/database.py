from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.components.core.config import settings
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class Database:
    client: Optional[AsyncIOMotorClient] = None
    db: Optional[AsyncIOMotorDatabase] = None

    @classmethod
    async def connect_to_mongo(cls):
        """连接到MongoDB数据库并初始化"""
        try:
            # 连接数据库
            cls.client = AsyncIOMotorClient(settings.MONGODB_URL)
            cls.db = cls.client[settings.DATABASE_NAME]

            # 测试连接
            await cls.client.admin.command('ping')
            logger.info("Successfully connected to MongoDB")

            # 确保所有集合存在
            await cls.ensure_collections()

            # 创建索引
            await cls.create_indexes()

        except Exception as e:
            logger.error(f"Failed to initialize MongoDB: {e}")
            raise e

    @classmethod
    async def ensure_collections(cls):
        """确保所有必需的集合都存在"""
        try:
            existing_collections = await cls.db.list_collection_names()
            for collection_name in settings.COLLECTIONS.values():
                if collection_name not in existing_collections:
                    await cls.db.create_collection(collection_name)
                    logger.info(f"Created collection: {collection_name}")
        except Exception as e:
            logger.error(f"Failed to create collections: {e}")
            raise e

    @classmethod
    async def create_indexes(cls):
        """创建所有必需的索引"""
        try:
            for collection_name, indexes in settings.INDEXES.items():
                collection = cls.db[collection_name]
                for index in indexes:
                    await collection.create_index([index])
                    logger.info(f"Created index for {collection_name}: {index}")
        except Exception as e:
            logger.error(f"Failed to create indexes: {e}")
            raise e

    @classmethod
    async def close_mongo_connection(cls):
        """关闭MongoDB连接"""
        if cls.client:
            cls.client.close()
            cls.client = None
            cls.db = None
            logger.info("MongoDB connection closed")

db = Database()

# FastAPI dependency
async def get_database() -> AsyncIOMotorClient:
    """FastAPI依赖注入函数"""
    if not db.client:
        await db.connect_to_mongo()
    return db.client