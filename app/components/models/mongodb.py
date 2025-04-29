from datetime import datetime, timezone
from typing import Optional, Literal, List
from pydantic import BaseModel, Field
from bson import ObjectId

# Base ID and model definitions
class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v, info=None):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)

class MongoBaseModel(BaseModel):
    """Base class for all MongoDB models"""
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        allow_population_by_alias = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

# 1. Parse Module
class ParseRecord(MongoBaseModel):
    """Parse record"""
    input_file: str
    content: Optional[str] = None
    parsed_file_path: Optional[str] = None
    status: str = "processing"  # processing, completed, failed
    file_type: str
    save_path: str
    progress: int = 0  # Progress field
    task_type: str = "parse"  # parse or ocr, used to distinguish task types

# 2. LaTeX Conversion Module
class TexConversionRecord(MongoBaseModel):
    """LaTeX conversion record"""
    input_file: str  # Input file path
    content: Optional[str] = None  # Converted content
    save_path: Optional[str] = None  # Save path
    status: str = "processing"  # processing, completed, failed
    file_type: str = "tex"  # Fixed as tex
    model_name: str  # Model name used
    progress: int = 0  # Progress field

# 3. Q&A Generation Module
class QAGeneration(MongoBaseModel):
    """Q&A generation record"""
    input_file: str
    save_path: str
    model_name: str
    domain: str
    status: str = "processing"  # processing, completed, failed
    source_text: str
    progress: int = 0  # Progress field

class QAPairDB(MongoBaseModel):
    """Q&A pair database record"""
    generation_id: PyObjectId
    question: str
    answer: str

# 4. Quality Control Module
class QualityControlGeneration(MongoBaseModel):
    """Quality control record"""
    input_file: str
    save_path: str
    model_name: str
    status: str = "processing"  # processing, completed, failed
    source_text: str
    progress: int = 0  # Progress field

class QAQualityRecord(MongoBaseModel):
    """Q&A quality record"""
    generation_id: PyObjectId
    question: str
    answer: str
    similarity_score: float = Field(ge=0.0, le=1.0)
    is_explicit: bool
    is_domain_relative: bool
    coverage_rate: float = Field(ge=0.0, le=1.0)
    status: Literal["passed", "failed"]

# 5. Deduplication Module
class DedupRecord(MongoBaseModel):
    """Deduplication record"""
    input_file: list[str]
    output_file: str
    deleted_pairs_file: str
    dedup_by_answer: bool
    threshold: float = Field(ge=0.0, le=1.0)
    min_answer_length: int = Field(default=10)
    status: str = "processing"  # processing, completed, failed
    source_text: str
    original_count: Optional[int] = Field(ge=0)
    kept_count: Optional[int] = Field(ge=0)
    progress: int = 0  # Progress field

class KeptQAPair(MongoBaseModel):
    """Kept Q&A pair"""
    dedup_id: PyObjectId
    qa_id: str
    question: str
    answer: str

class ErrorLog(MongoBaseModel):
    """Error log model"""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    error_message: str
    source: str
    stack_trace: Optional[str] = None
    request_path: Optional[str] = None
    request_method: Optional[str] = None
    status_code: int = Field(default=500)
    request_headers: Optional[dict] = None
    request_query_params: Optional[dict] = None
    request_body: Optional[str] = None

    class Config:
        schema_extra = {
            "example": {
                "error_message": "Division by zero",
                "source": "/api/calculate",
                "stack_trace": "Traceback (most recent call last)...",
                "request_path": "/api/calculate",
                "request_method": "POST",
                "status_code": 500,
                "request_headers": {"content-type": "application/json"},
                "request_query_params": {"param1": "value1"},
                "request_body": '{"value": 42}'
            }
        }

class DeletedQAPair(MongoBaseModel):
    """Deleted Q&A pair"""
    dedup_id: PyObjectId
    qa_id: str
    question: str
    answer: str
    similar_pairs: List[dict]  # Store similar Q&A pair information

class UploadedFile(MongoBaseModel):
    """Uploaded file record"""
    filename: str
    content: str  # File content
    file_type: str  # File type
    size: int  # File size (bytes)
    status: str = "to_parse"  # to_parse(waiting to be parsed), pending(parsing), finish(parsing completed)

class UploadedBinaryFile(MongoBaseModel):
    """Uploaded binary file record"""
    filename: str
    content: bytes  # Binary file content
    file_type: str  # File type (pdf, jpg, png, etc.)
    mime_type: str  # MIME type
    size: int  # File size (bytes)
    status: str = "to_parse"  # to_parse(waiting to be parsed), pending(parsing), finish(parsing completed)