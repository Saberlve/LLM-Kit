from datetime import datetime, timezone
from typing import Optional, Literal, List
from pydantic import BaseModel, Field
from bson import ObjectId

# 基础ID和模型定义
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
    """所有MongoDB模型的基类"""
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        allow_population_by_alias = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

# 1. 解析模块
class ParseRecord(MongoBaseModel):
    """解析记录"""
    input_file: str
    content: Optional[str] = None
    parsed_file_path: Optional[str] = None
    status: str = "processing"
    file_type: str
    save_path: str

# 2. LaTeX转换模块
class TexConversionRecord(MongoBaseModel):
    """LaTeX转换记录"""
    input_file: str  # 输入文件路径
    content: Optional[str] = None  # 转换后的内容
    save_path: Optional[str] = None  # 保存路径
    status: str = "processing"
    file_type: str = "tex"  # 固定为tex
    model_name: str  # 使用的模型名称

# 3. 问答生成模块
class QAGeneration(MongoBaseModel):
    """问答生成记录"""
    input_file: str
    save_path: str
    model_name: str
    domain: str
    status: str = "processing"
    source_text: str

class QAPairDB(MongoBaseModel):
    """问答对数据库记录"""
    generation_id: PyObjectId
    question: str
    answer: str

# 4. 质量控制模块
class QualityControlGeneration(MongoBaseModel):
    """质量控制记录"""
    input_file: str
    save_path: str
    model_name: str
    status: str = "processing"
    source_text: str

class QAQualityRecord(MongoBaseModel):
    """问答质量记录"""
    generation_id: PyObjectId
    question: str
    answer: str
    similarity_score: float = Field(ge=0.0, le=1.0)
    is_explicit: bool
    is_domain_relative: bool
    coverage_rate: float = Field(ge=0.0, le=1.0)
    status: Literal["passed", "failed"]

# 5. 去重模块
class DedupRecord(MongoBaseModel):
    """去重记录"""
    input_file: list[str]
    output_file: str  # 将由系统自动生成
    deleted_pairs_file: str  # 将由系统自动生成
    dedup_by_answer: bool
    threshold: float = Field(ge=0.0, le=1.0)
    min_answer_length: int = Field(default=10)
    status: str = "processing"
    source_text: str
    original_count: Optional[int] = Field(ge=0)
    kept_count: Optional[int] = Field(ge=0)

class KeptQAPair(MongoBaseModel):
    """保留的问答对"""
    dedup_id: PyObjectId
    qa_id: str
    question: str
    answer: str

class ErrorLog(MongoBaseModel):
    """错误日志模型"""
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
    """被删除的问答对"""
    dedup_id: PyObjectId
    qa_id: str
    question: str
    answer: str
    similar_pairs: List[dict]  # 存储相似的问答对信息

class UploadedFile(MongoBaseModel):
    """上传的文件记录"""
    filename: str
    content: str  # 文件内容
    file_type: str  # 文件类型
    size: int  # 文件大小(字节)
    status: str = "pending"  # pending, processed

class UploadedBinaryFile(MongoBaseModel):
    """上传的二进制文件记录"""
    filename: str
    content: bytes  # 二进制文件内容
    file_type: str  # 文件类型 (pdf, jpg, png等)
    mime_type: str  # MIME类型
    size: int  # 文件大小(字节)
    status: str = "pending"  # pending, processed