from motor.motor_asyncio import AsyncIOMotorClient
from .config import settings

# 创建全局数据库连接
client = AsyncIOMotorClient(settings.MONGODB_URL)
db = client[settings.DATABASE_NAME]

async def init_indexes():
    """初始化所有集合的索引"""
    for collection_name, indexes in settings.INDEXES.items():
        collection = db[collection_name]
        for index in indexes:
            await collection.create_index([index])

async def get_database() -> AsyncIOMotorClient:
    """获取数据库连接"""
    return client

# 在应用启动时初始化索引
async def init_db():
    """初始化数据库"""
    try:
        await init_indexes()
    except Exception as e:
        print(f"Failed to initialize database: {str(e)}")