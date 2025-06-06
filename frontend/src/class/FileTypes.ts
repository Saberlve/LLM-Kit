import type { APIResponse } from './APIResponse';

// Define the structure of uploaded files
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
    ocr_info?: {
        total_pages: number;
        processed_pages: number;
        elapsed_seconds: number;
        estimated_remaining_seconds: number;
    };
}

// Define the structure of uploaded binary files
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
    ocr_info?: {
        total_pages: number;
        processed_pages: number;
        elapsed_seconds: number;
        estimated_remaining_seconds: number;
    };
}

// Define unified file type
export type UnifiedFile = UploadedFile | UploadedBinaryFile;

export interface UnifiedFileListResponse extends APIResponse {
    data: UnifiedFile[];
}