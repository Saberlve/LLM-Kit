from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

# API 请求/响应基础模型
class BaseRequest(BaseModel):
    save_path: str = "result/"
    SK: Optional[List[str]] = None
    AK: Optional[List[str]] = None
    parallel_num: int = 1

class QAGenerateRequest(BaseRequest):
    chunks_path: str
    model_name: str
    domain: str

class DedupRequest(BaseModel):
    input_file: List[str]
    output_file: str
    dedup_by_answer: bool = False
    min_answer_length: int = 10
    deleted_pairs_file: Optional[str] = "deleted.json"
    dedup_threshold: float = 0.8

class QualityControlRequest(BaseRequest):
    qa_path: str
    model_name: str
    similarity_rate: float = 0.8
    coverage_rate: float = 0.8
    max_attempts: int = 3
    domain: str

class ParseRequest(BaseRequest):
    file_path: str
    convert_to_tex: Optional[bool] = True

class ToTexRequest(BaseRequest):
    parsed_file_path: str
    model_name: str

class APIResponse(BaseModel):
    status: str
    message: str
    data: Optional[dict] = None

class OCRRequest(BaseRequest):
    file_path: str

class ErrorLogResponse(BaseModel):
    """错误日志响应模型"""
    id: str
    timestamp: datetime
    error_message: str
    source: str
    stack_trace: Optional[str] = None
    request_path: Optional[str] = None
    request_method: Optional[str] = None
    status_code: int = 500
    request_headers: Optional[dict] = None
    request_query_params: Optional[dict] = None
    request_body: Optional[str] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }

class ErrorLogsListResponse(BaseModel):
    """错误日志列表响应"""
    total: int
    logs: List[ErrorLogResponse]