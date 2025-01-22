from typing import Dict, List, ClassVar
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # MongoDB配置
    MONGODB_URL: str = "mongodb://localhost:27017"
    DATABASE_NAME: str = "llm_kit"

    # 使用 ClassVar 标注静态配置
    COLLECTIONS: ClassVar[Dict[str, str]] = {
        # 1. 解析模块
        "parse_records": "parse_records",

        # 2. LaTeX转换模块
        "tex_records": "tex_records",

        # 3. 问答生成模块
        "qa_generations": "qa_generations",
        "qa_pairs": "qa_pairs",

        # 4. 质量控制模块
        "quality_generations": "quality_generations",
        "quality_records": "quality_records",

        # 5. 去重模块
        "dedup_records": "dedup_records",
        "kept_pairs": "kept_pairs"
    }

    INDEXES: ClassVar[Dict[str, List[tuple]]] = {
        "parse_records": [("created_at", -1)],
        "tex_records": [("created_at", -1)],
        "qa_generations": [("created_at", -1)],
        "qa_pairs": [("generation_id", 1)],
        "quality_generations": [("created_at", -1)],
        "quality_records": [("generation_id", 1)],
        "dedup_records": [("created_at", -1)],
        "kept_pairs": [("dedup_id", 1)]
    }

    class Config:
        env_file = ".env"


settings = Settings()