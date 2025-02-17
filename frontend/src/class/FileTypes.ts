import type { APIResponse } from './APIResponse';

// 定义上传文件的结构
export interface UploadedFile {
    file_id: string;
    filename: string;
    file_type: string;
    size: number;
    status: string;
    created_at: string;
    type: string;
    parseStatus?: string;
    parseProgress?: number;
    recordId?: string | null;
}

// 定义上传二进制文件的结构
export interface UploadedBinaryFile {
    file_id: string;
    filename: string;
    file_type: string;
    mime_type: string;
    size: number;
    status: string;
    created_at: string;
    type: string;
    parseStatus?: string;
    parseProgress?: number;
    recordId?: string | null;
}

// 定义统一文件类型
export type UnifiedFile = UploadedFile | UploadedBinaryFile;

export interface UnifiedFileListResponse extends APIResponse {
    data: UnifiedFile[];
}