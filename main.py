from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.components.routers import parse, to_tex, qa_generate, quality, qa_dedup
from app.components.core.database import init_db, get_database
app = FastAPI(title="LLM-Kit API")

# 添加基本的CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def clear_all_collections():
    """清空所有集合的数据"""
    db = await get_database()
    collections = [
        "parse_records",
        "tex_records",
        "qa_generations",
        "qa_pairs",
        "quality_generations",
        "quality_records",
        "dedup_records",
        "kept_pairs"
    ]
    for collection_name in collections:
        collection = db.llm_kit[collection_name]  # 获取正确的集合引用
        try:
            await collection.delete_many({})  # 使用异步删除方法
            print(f"Cleared collection: {collection_name}")
        except Exception as e:
            print(f"Error clearing collection {collection_name}: {str(e)}")

# 注册路由
app.include_router(parse.router, prefix="/parse", tags=["parse"])
app.include_router(to_tex.router, prefix="/to_tex", tags=["to_tex"])
app.include_router(qa_generate.router, prefix="/qa", tags=["qa_generate"])
app.include_router(quality.router, prefix="/quality", tags=["quality"])
app.include_router(qa_dedup.router, prefix="/dedup", tags=["qa_dedup"])

# 健康检查接口
@app.get("/")
async def root():
    return {"status": "ok", "message": "LLM-Kit API is running"}

@app.post("/clear-data")
async def clear_data():
    """手动清空所有数据的API端点"""
    await clear_all_collections()
    return {"message": "All collections cleared successfully"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
