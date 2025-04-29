from motor.motor_asyncio import AsyncIOMotorClient
from .config import settings


client = AsyncIOMotorClient(settings.MONGODB_URL)
db = client[settings.DATABASE_NAME]

async def init_indexes():
    for collection_name, indexes in settings.INDEXES.items():
        collection = db[collection_name]
        for index in indexes:
            await collection.create_index([index])

async def get_database() -> AsyncIOMotorClient:
    
    return client

async def init_db():
    try:
        await init_indexes()
    except Exception as e:
        print(f"Failed to initialize database: {str(e)}")