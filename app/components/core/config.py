from typing import Dict, List, ClassVar
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # MongoDB configuration
    MONGODB_URL: str = "mongodb://localhost:27017"
    DATABASE_NAME: str = "llm_kit"

    # Use ClassVar to annotate static configuration
    COLLECTIONS: ClassVar[Dict[str, str]] = {
        # 1. Parsing module
        "parse_records": "parse_records",

        # 2. LaTeX conversion module
        "tex_records": "tex_records",

        # 3. QA generation module
        "qa_generations": "qa_generations",
        "qa_pairs": "qa_pairs",

        # 4. Quality control module
        "quality_generations": "quality_generations",
        "quality_records": "quality_records",

        # 5. Deduplication module
        "dedup_records": "dedup_records",
        "kept_pairs": "kept_pairs",
        "error_logs": "error_logs"
    }

    INDEXES: ClassVar[Dict[str, List[tuple]]] = {
        "parse_records": [("created_at", -1)],
        "tex_records": [("created_at", -1)],
        "qa_generations": [("created_at", -1)],
        "qa_pairs": [("generation_id", 1)],
        "quality_generations": [("created_at", -1)],
        "quality_records": [("generation_id", 1)],
        "dedup_records": [("created_at", -1)],
        "kept_pairs": [("dedup_id", 1)],
        "error_logs": [("timestamp", -1)]
    }

    class Config:
        env_file = ".env"


settings = Settings()