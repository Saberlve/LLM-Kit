from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from routers import parse, to_tex, qa_generate, quality, qa_dedup
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="LLM-Kit API")

# 添加基本的CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global error occurred: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "message": str(exc)}
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
    logger.info("Health check endpoint called")
    return {"status": "ok", "message": "LLM-Kit API is running"}

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting LLM-Kit API server")
    uvicorn.run(app, host="0.0.0.0", port=8000)
