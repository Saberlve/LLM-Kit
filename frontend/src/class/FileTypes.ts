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
}

// Define unified file type
export type UnifiedFile = UploadedFile | UploadedBinaryFile;

export interface UnifiedFileListResponse extends APIResponse {
    data: UnifiedFile[];
}