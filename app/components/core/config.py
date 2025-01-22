from pydantic_settings import BaseSettings
from typing import Dict, Any


class Settings(BaseSettings):
    PROJECT_NAME: str = "LLM-Kit API"
    MONGODB_URL: str = "mongodb://localhost:27017"
    DATABASE_NAME: str = "llm_kit"

    # 添加集合名称配置
    COLLECTIONS: Dict[str, str] = {
        "parse_records": "parse_records",
        "tex_records": "tex_records",
        "qa_generations": "qa_generations",
        "qa_pairs": "qa_pairs",
        "quality_generations": "quality_generations",
        "quality_records": "quality_records",
        "dedup_records": "dedup_records",
        "deleted_pairs": "deleted_pairs",
        "kept_pairs": "kept_pairs"
    }

    # 添加索引配置
    INDEXES: Dict[str, list] = {
        "parse_records": [("created_at", -1), ("status", 1)],
        "tex_records": [("created_at", -1), ("status", 1)],
        "qa_generations": [("start_time", -1), ("status", 1)],
        "qa_pairs": [("generation_id", 1)],
        "quality_generations": [("start_time", -1), ("status", 1)],
        "quality_records": [("generation_id", 1), ("status", 1)],
        "dedup_records": [("start_time", -1), ("status", 1)],
        "deleted_pairs": [("dedup_id", 1)],
        "kept_pairs": [("dedup_id", 1)]
    }

    class Config:
        env_file = ".env"


settings = Settings()