from pydantic import BaseModel
from typing import List, Optional, Literal
from datetime import datetime
from fastapi import UploadFile

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
    dedup_by_answer: bool = False
    min_answer_length: int = 10
    dedup_threshold: float = 0.8

class QualityControlRequest(BaseRequest):
    qa_path: str
    model_name: str
    similarity_rate: float = 0.8
    coverage_rate: float = 0.8
    max_attempts: int = 3
    domain: str

class ParseRequest(BaseRequest):
    # file_path: str
    convert_to_tex: Optional[bool] = False

class ToTexRequest(BaseRequest):
    content: str  # 改为直接接收内容
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

class FileUploadRequest(BaseModel):
    filename: str  # 不包含扩展名的文件名
    content: str
    file_type: Literal['tex', 'txt', 'json', 'pdf']  # 文件扩展名

    @property
    def full_filename(self) -> str:
        """获取完整文件名（包含扩展名）"""
        return f"{self.filename}.{self.file_type}"

class BinaryFileResponse(BaseModel):
    """二进制文件响应模型"""
    file_id: str
    filename: str
    file_type: str
    mime_type: str
    size: int
    status: str
    created_at: datetime

class ParsedFileListResponse(BaseModel):
    """已解析文件列表的响应模型"""
    filename: str
    created_at: datetime
    file_type: str

class ParsedContentResponse(BaseModel):
    """解析内容的响应模型"""
    content: str
    filename: str
    created_at: datetime
    file_type: str