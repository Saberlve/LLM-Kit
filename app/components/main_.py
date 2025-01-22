from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import parse, to_tex, qa_generate, quality, qa_dedup

app = FastAPI(title="LLM-Kit API")

# 添加基本的CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
