import type { UploadedFile, UploadedBinaryFile, UnifiedFile } from "./FileTypes";

// Define common API response structure
export interface APIResponse {
    status: "success" | "fail";
    message: string;
    data: any;
}

// Define upload response type
export interface UploadResponse extends APIResponse {
    data: { file_id: string };
}

// Define parse response type
export interface ParseResponse extends APIResponse {
    data: { 
        record_id: string;
        parsed_file_path?: string;
        content?: string;
    };
}

// Define task progress response type
export interface TaskProgressResponse extends APIResponse {
    data: { 
        progress: number; 
        status: string; 
        task_type: string;
        ocr_info?: {
            total_pages: number;
            processed_pages: number;
            elapsed_seconds: number;
            estimated_remaining_seconds: number;
        };
    };
}

// Define parse history response type
export interface ParseHistoryResponse extends APIResponse {
    data: { exists: number };
}

// Define unified file list response type
export interface UnifiedFileListResponse extends APIResponse {
    data: UnifiedFile[]; // Using unified file type definition
}

// Request interfaces
export interface FileIDRequest {
    file_id: string;
}

export interface RecordIDRequest {
    record_id: string;
}

export interface FilenameRequest {
    filename: string;
}