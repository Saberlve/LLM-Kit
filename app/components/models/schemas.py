from pydantic import BaseModel
from typing import List, Optional

# API 请求/响应基础模型
class BaseRequest(BaseModel):
    save_path: str = "result/"
    SK: List[str]
    AK: List[str]
    parallel_num: int = 1

class QAGenerateRequest(BaseRequest):
    chunks_path: str
    model_name: str
    domain: str

class DedupRequest(BaseRequest):
    input_file: str
    output_file: str
    dedup_by_answer: bool = False
    min_answer_length: int = 15
    deleted_pairs_file: Optional[str] = None
    dedup_threshold: float = 0.8
    dedup_num_perm: int = 128

class QualityControlRequest(BaseRequest):
    qa_path: str
    model_name: str
    similarity_rate: float = 0.8
    coverage_rate: float = 0.8
    max_attempts: int = 3

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