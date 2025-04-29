from pydantic import BaseModel
from typing import List, Optional, Literal
from datetime import datetime
from fastapi import UploadFile

class TexFile(BaseModel):
    file_id: str
    filename: str
    created_at: datetime

class TexContentRequest(BaseModel):
    file_id: str

# API Request/Response Base Model
class BaseRequest(BaseModel):
    save_path: str = "result/"
    SK: Optional[List[str]] = None
    AK: Optional[List[str]] = None
    parallel_num: int = 1

class QAGenerateRequest(BaseRequest):
    content: str = None
    filename: str  # Filename parameter for tracking files
    model_name: str
    domain: str

class COTGenerateRequest(BaseRequest):
    #content: str
    filename: str
    model_name: str
    domain: str = "Medicine"

class DedupRequest(BaseModel):
    quality_filenames: List[str]
    dedup_by_answer: bool = False
    min_answer_length: int = 10
    dedup_threshold: float = 0.8

class QualityControlRequest(BaseModel):
    content: str  # QA pair content, a list of dictionaries
    filename: str  # Filename
    save_path: str = "result/"
    SK: Optional[List[str]] = None
    AK: Optional[List[str]] = None
    parallel_num: int = 1
    model_name: str
    similarity_rate: float = 0.8
    coverage_rate: float = 0.8
    max_attempts: int = 3
    domain: str

class ParseRequest(BaseRequest):
    # file_path: str
    convert_to_tex: Optional[bool] = False

class ToTexRequest(BaseRequest):
    content: str  # Text content
    filename: str  # Filename
    model_name: str

class APIResponse(BaseModel):
    status: str
    message: str
    data: Optional[dict] = None

class OCRRequest(BaseRequest):
    file_path: str

class ErrorLogResponse(BaseModel):
    """Error log response model"""
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
    """Error log list response"""
    total: int
    logs: List[ErrorLogResponse]

class FileUploadRequest(BaseModel):
    filename: str  # Filename without extension
    content: str
    file_type: Literal['tex', 'txt', 'json', 'pdf']  # File extension

    @property
    def full_filename(self) -> str:
        """Get full filename (including extension)"""
        return f"{self.filename}.{self.file_type}"

class BinaryFileResponse(BaseModel):
    """Binary file response model"""
    file_id: str
    filename: str
    file_type: str
    mime_type: str
    size: int
    status: str
    created_at: datetime

class ParsedFileListResponse(BaseModel):
    """Response model for parsed file list"""
    filename: str
    created_at: datetime
    file_type: str

class ParsedContentResponse(BaseModel):
    """Response model for parsed content"""
    content: str
    filename: str
    created_at: datetime
    file_type: str