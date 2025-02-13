from fastapi import FastAPI, Query, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from app.components.routers import parse, to_tex, qa_generate, quality, qa_dedup, cot_generate
from app.components.core.database import init_db, get_database
from datetime import datetime, timezone
import logging
from fastapi.responses import JSONResponse
from app.components.models.schemas import  ErrorLogsListResponse

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

app = FastAPI(title="LLM-Kit API")

# 添加一个中间件类来处理非200响应
class ErrorLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            
            # 记录非200状态码的响应
            if response.status_code >= 400:
                error_message = "HTTP {}: {}".format(
                    response.status_code,
                    getattr(response, 'body', b'').decode('utf-8', 'replace')
                )
                await log_error(
                    error_message=error_message,
                    source=request.url.path,
                    request=request,
                    status_code=response.status_code
                )
            
            return response
            
        except HTTPException as exc:
            # 处理HTTP异常
            await log_error(
                error_message=str(exc.detail),
                source=request.url.path,
                request=request,
                status_code=exc.status_code
            )
            raise exc
        except Exception as exc:
            # 让全局异常处理器处理其他未捕获的异常
            raise exc

# 添加中间件（注意顺序很重要）
app.add_middleware(ErrorLoggingMiddleware)  # 先添加错误日志中间件
app.add_middleware(                         # 再添加CORS中间件
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 修改错误日志函数以包含请求体
async def log_error(error_message: str, source: str, stack_trace: str = None, request=None, status_code: int = 500):
    """记录错误到数据库"""
    db = await get_database()
    error_log = {
        "timestamp": datetime.now(timezone.utc),
        "error_message": error_message,
        "source": source,
        "stack_trace": stack_trace,
        "request_path": str(request.url) if request else None,
        "request_method": request.method if request else None,
        "status_code": status_code,
        "request_headers": dict(request.headers) if request else None,
        "request_query_params": dict(request.query_params) if request else None,
    }
    
    # 尝试获取请求体
    if request:
        try:
            body = await request.body()
            if body:
                error_log["request_body"] = body.decode('utf-8', 'replace')
        except Exception:
            pass  # 如果无法获取请求体，就忽略它
            
    await db.llm_kit.error_logs.insert_one(error_log)

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
        "kept_pairs",
        "error_logs",
        "uploaded_files",           # 添加文本文件集合
        "uploaded_binary_files"     # 添加二进制文件集合
    ]
    
    for collection_name in collections:
        collection = db.llm_kit[collection_name]
        try:
            await collection.delete_many({})
            print(f"Cleared collection: {collection_name}")
            
            # 如果是文件相关的集合，同时清理文件系统中的文件
            if collection_name in ["uploaded_files", "uploaded_binary_files"]:
                import shutil
                import os
                
                # 清理 parsed_files 目录
                parsed_files_dir = os.path.join("parsed_files", "parsed_file")
                if os.path.exists(parsed_files_dir):
                    shutil.rmtree(parsed_files_dir)
                    os.makedirs(parsed_files_dir, exist_ok=True)
                    print(f"Cleared directory: {parsed_files_dir}")
                
        except Exception as e:
            await log_error(str(e), f"clear_collection_{collection_name}")
            print(f"Error clearing collection {collection_name}: {str(e)}")

# 注册路由
app.include_router(parse.router, prefix="/parse", tags=["parse"])
app.include_router(to_tex.router, prefix="/to_tex", tags=["to_tex"])
app.include_router(qa_generate.router, prefix="/qa", tags=["qa_generate"])
app.include_router(quality.router, prefix="/quality", tags=["quality"])
app.include_router(qa_dedup.router, prefix="/dedup", tags=["qa_dedup"])
app.include_router(cot_generate.router, prefix="/cot", tags=["cot_generate"])

# 健康检查接口
@app.get("/")
async def root():
    return {"status": "ok", "message": "LLM-Kit API is running"}

@app.post("/clear-data")
async def clear_data():
    """手动清空所有数据的API端点"""
    await clear_all_collections()
    return {"message": "All collections cleared successfully"}

# 修改全局异常处理器
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """全局异常处理器"""
    import traceback
    error_msg = str(exc)
    stack_trace = traceback.format_exc()
    await log_error(
        error_msg, 
        request.url.path, 
        stack_trace, 
        request,
        status_code=500
    )
    logging.error(f"Global exception: {error_msg}\n{stack_trace}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "message": error_msg,
            "path": str(request.url)
        }
    )

@app.get("/error-logs", response_model=ErrorLogsListResponse)
async def get_error_logs(
    limit: int = Query(default=100, ge=1, le=1000),
    skip: int = Query(default=0, ge=0)
):
    """获取最近的错误日志
    
    Args:
        limit: 返回的日志数量限制
        skip: 跳过的日志数量
    """
    db = await get_database()
    cursor = db.llm_kit.error_logs.find() \
        .sort("timestamp", -1) \
        .skip(skip) \
        .limit(limit)
    
    total = await db.llm_kit.error_logs.count_documents({})
    
    logs = []
    async for log in cursor:
        log['id'] = str(log['_id'])  # 转换ObjectId为字符串
        del log['_id']  # 删除原始的_id字段
        logs.append(log)
    
    return {
        "total": total,
        "logs": logs
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)

# import os

# from deduplication.qa_deduplication import QADeduplication
# from generate_qas.qa_generator import QAGenerator
# from quality_control.quality_control import QAQualityGenerator
# from text_parse.parse import parse
# from text_parse.to_tex import LatexConverter
# from utils.hparams import DedupParams, HyperParams

# def dedup():
#     hparams=DedupParams.from_dedup_yaml('hparams/dedup.yaml')
#     qa_dedup=QADeduplication(hparams)
#     qa_dedup.process_qa_file(hparams)

# def main():
#     try:
#         hparams = HyperParams.from_hparams('hyparams/config.yaml')
        
#         file_list = []
#         if os.path.isdir(hparams.file_path):
#             files = os.listdir(hparams.file_path)
#             for file in files:
#                 file_list.append(file)
#         elif os.path.isfile(hparams.file_path):
#             file_list.append(hparams.file_path)

#         for file in file_list:
#             try:
#                 print('Start iterative optimization of ' + os.path.basename(file))
#                 parsed_file_path = parse(hparams)
#                 latex_converter = LatexConverter(parsed_file_path, hparams)
                
#                 if file.split('.')[-1] != 'tex' and hparams.convert_to_tex:
#                     latex_converter.convert_to_latex()
                
#                 qa_generator = QAGenerator(latex_converter.save_path, hparams)
#                 qa_path = qa_generator.convert_tex_to_qas()

#                 quality_control = QAQualityGenerator(qa_path, hparams)
#                 it_path = quality_control.iterate_optim_qa()
                
#             except Exception as e:
#                 import traceback
#                 error_msg = f"Error processing file {file}: {str(e)}"
#                 stack_trace = traceback.format_exc()
#                 # 由于命令行模式可能没有运行异步事件循环，这里使用同步方式记录错误
#                 import asyncio
#                 loop = asyncio.get_event_loop()
#                 loop.run_until_complete(log_error(error_msg, "main_process", stack_trace))
#                 print(error_msg)
#                 continue
                
#     except Exception as e:
#         import traceback
#         error_msg = f"Main process error: {str(e)}"
#         stack_trace = traceback.format_exc()
#         loop = asyncio.get_event_loop()
#         loop.run_until_complete(log_error(error_msg, "main_process", stack_trace))
#         print(error_msg)

# if __name__=='__main__':
#     main()

        
        
        
    

            
                
    
 
        
    


