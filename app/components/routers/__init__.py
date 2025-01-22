from fastapi import APIRouter
from app.components.routers import parse, to_tex, qa_generate, quality, qa_dedup

# 创建主路由
api_router = APIRouter(prefix="/routers/v1")

# 按照处理流程顺序添加子路由
routers = [
    (parse.router, "parse", "文档解析模块"),
    (to_tex.router, "to_tex", "LaTeX转换模块"),
    (qa_generate.router, "qa_generate", "问答生成模块"),
    (quality.router, "quality", "质量控制模块"),
    (qa_dedup.router, "qa_dedup", "问答去重模块")
]

# 注册所有路由
for router, tag, description in routers:
    api_router.include_router(
        router,
        prefix=f"/{tag}",
        tags=[tag],
        responses={404: {"description": "Not found"}},
    )