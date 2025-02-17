import type { UploadedFile, UploadedBinaryFile } from "./filetypes";

// 定义通用的 API 响应结构
export interface APIResponse {
    status: "success" | "fail";
    message: string;
    data: any;
}

// 定义上传响应类型
export interface UploadResponse extends APIResponse {
    data: { file_id: string };
}

// 定义解析响应类型
export interface ParseResponse extends APIResponse {
    data: { record_id: string };
}

// 定义任务进度响应类型
export interface TaskProgressResponse extends APIResponse {
    data: { progress: number; status: string; task_type: string };
}

// 定义解析历史响应类型
export interface ParseHistoryResponse extends APIResponse {
    data: { exists: number };
}

// 定义统一文件列表响应类型
export interface UnifiedFileListResponse extends APIResponse {
    data: Array<UploadedFile | UploadedBinaryFile>; // 使用文件类型定义
}