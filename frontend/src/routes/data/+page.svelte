<script lang="ts">
  import axios from "axios";
  import {
    Accordion,
    AccordionItem,
    Button,
    Table,
    TableHead,
    TableHeadCell,
    TableBody,
    TableBodyCell,
    Input,
    Progressbar,
    Modal,
  } from "flowbite-svelte";

  import { Dropzone } from "flowbite-svelte";
  import { UPDATE_VIEW_INTERVAL } from "../store";
  import type DatasetEntry from "../../class/DatasetEntry";
  import { onDestroy, onMount } from "svelte";
  import { getContext } from "svelte";
  import { goto } from "$app/navigation";
  const t: any = getContext("t");
  import ActionPageTitle from "../components/ActionPageTitle.svelte";
  import type { UploadedFile, UploadedBinaryFile, UnifiedFileListResponse } from "../../class/FileTypes";

// 扩展UnifiedFile类型以添加新的属性
interface UnifiedFile {
  file_id?: string;
  filename: string;
  file_type?: string;
  content?: string;
  size: number;
  status: string | { [key: number]: number };
  created_at: Date | string;
  type: string;
  mime_type?: string;
  parseStatus?: string;
  parseProgress?: number;
  recordId?: string;
  taskType?: string;
  ocr_info?: any;
  qa_status_message?: string;
  // 新增进度显示相关属性
  inProgress?: boolean;
  hasError?: boolean;
};
  import type { APIResponse, UploadResponse, ParseResponse, TaskProgressResponse, FileIDRequest, FilenameRequest } from "../../class/APIResponse";

  // 添加额外的翻译文本
  if (!t("data.uploader.ocr_processing")) {
    t.add({
      "data.uploader.ocr_processing": "OCR processing is in progress. This might take a few moments.",
      "data.uploader.title": "File Manager",
      "data.uploader.uploaded_files": "Uploaded Files",
      "data.uploader.filename": "Filename",
      "data.uploader.file_type": "File Type",
      "data.uploader.size": "Size",
      "data.uploader.created_at": "Upload Date",
      "data.uploader.upload_status": "Status",
      "data.uploader.action": "Action",
      "data.uploader.delete_action": "Delete",
      "data.uploader.parse_button": "Parse",
      "data.uploader.delete_button": "Delete",
      "data.uploader.parsed": "Parsed",
      "data.uploader.processed": "Processed",
      "data.uploader.pending": "Pending",
      "data.uploader.parse_status": "Parse Status",
      "data.uploader.completed": "Completed",
      "data.uploader.failed": "Failed",
      "data.uploader.click": "Click to upload",
      "data.uploader.or": " or drag and drop ",
      "data.uploader.p1": "files here",
      "data.uploader.p2": " to upload",
      "data.uploader.uploading": "Uploading...",
      "data.uploader.delete_confirmation_title": "Confirm Deletion",
      "data.uploader.delete_confirmation_message": "Are you sure you want to delete this file? This action cannot be undone.",
      "data.uploader.delete_confirm_button": "Delete",
      "data.uploader.delete_cancel_button": "Cancel",
      "data.uploader.fetch_fail": "Failed to fetch file list",
      "data.uploader.upload_fail": "Failed to upload file",
      "data.uploader.upload_fail_all": "Upload process failed",
      "data.uploader.delete_fail": "Failed to delete file",
      "data.uploader.delete_fail_all": "Delete process failed"
    });
  }

  // --- Component State ---
  let loading = false;
  let errorMessage: string | null = null;
  let uploadedFiles: UnifiedFile[] = [];
  let entries: DatasetEntry[] = [];
  export let stageEmpty = uploadedFiles.length == 0;
  $: stageEmpty = uploadedFiles.length == 0;
  let parsingProgressIntervals: { [fileId: string]: any } = {};

  let showDeleteConfirmation = false;
  let fileToDelete: UnifiedFile | null = null; // Store the file object to be deleted
  
  // 添加文件预览相关变量
  let previewModalOpen = false;
  let previewModalTitle = '';
  let previewContent = [];
  let previewContentType = ''; // 'raw'
  let previewErrorMessage = null;
  let previewLoading = false;
  let previewCurrentPage = 1;
  let previewTotalPages = 1;
  let previewItemsPerPage = 10;
  let previewPageInput = '1';
  let previewDatasetId = '';
  let rawContent = '';

  const uploaded_file_heads = [
    t("data.uploader.filename"),
    t("data.uploader.file_type"),
    t("data.uploader.size"),
    t("data.uploader.created_at"),
    t("data.uploader.upload_status"),
    t("data.uploader.action"),
    t("data.uploader.delete_action") // "Delete File" column header
  ]

  // --- Helper Functions ---
  function generateUniqueId(): string {
    return Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15);
  }

  function formatFileSize(sizeInBytes: number): string {
    const sizeInKilobytes = sizeInBytes / 1024;
    const sizeInMegabytes = sizeInKilobytes / 1024;

    if (sizeInMegabytes > 1) {
      return `${sizeInMegabytes.toFixed(2)} MB`;
    } else if (sizeInKilobytes > 1) {
      return `${sizeInKilobytes.toFixed(2)} KB`;
    } else {
      return `${sizeInBytes} B`;
    }
  }


  async function dropHandle(event: DragEvent) {
    event.preventDefault();
    const filesInItems = Array.from(event.dataTransfer.items)
            .filter((item) => item.kind === "file")
            .map((item) => item.getAsFile());
    const filesInFiles = Array.from(event.dataTransfer.files);
    const files = Array.from(new Set([...filesInItems, ...filesInFiles]));

    for (const file of files) {
      await uploadAndProcessFile(file);
    }
  }

  async function changeHandle(event: any) {
    event.preventDefault();
    const files: File[] = Array.from(event.target.files);
    for (const file of files) {
      await uploadAndProcessFile(file);
    }
  }

  function handleParseButtonClick(file: UnifiedFile) {
    parseFileForEntry(file);
  }

  function handleDeleteButtonClick(file: UnifiedFile) { // Modified: Takes file object
    fileToDelete = file; // Store the file object
    showDeleteConfirmation = true;
  }

  async function confirmDelete() {
    if (fileToDelete && fileToDelete.file_id) {
      await deleteFile(fileToDelete.file_id);
    }
    showDeleteConfirmation = false;
    fileToDelete = null;
  }

  function cancelDelete() {
    showDeleteConfirmation = false;
    fileToDelete = null;
  }

  // 文件预览功能
  const previewRawFile = async (file: UnifiedFile) => {
    previewModalTitle = `${file.filename}`;
    previewContentType = 'raw';
    previewLoading = true;
    previewErrorMessage = null;
    previewModalOpen = true;
    
    await fetchRawContent(file.filename);
  };
  
  // 添加查看解析后内容的方法
  const previewParsedContent = async (file: UnifiedFile) => {
    if (!file.recordId) {
      console.error('No record ID available for parsed content');
      return;
    }
    
    previewModalTitle = `${file.filename} (解析结果)`;
    previewContentType = 'parsed';
    previewLoading = true;
    previewErrorMessage = null;
    previewModalOpen = true;
    
    await fetchParsedContent(file.recordId);
  };

  const fetchRawContent = async (filename: string) => {
    try {
      const response = await axios.get(`http://127.0.0.1:8000/parse/preview_raw/${filename}`);
      if (response.status === 200 && response.data.status === "success") {
        rawContent = response.data.data.content || '';
        
        // 检查是否是OCR结果
        if (response.data.data.is_ocr_result) {
          previewContentType = 'ocr';
        }
      } else {
        previewErrorMessage = "Failed to preview file" + (response.data?.detail ? `: ${response.data.detail}` : '');
      }
    } catch (error) {
      console.error('Error fetching raw content:', error);
      previewErrorMessage = "Network error previewing file";
    } finally {
      previewLoading = false;
    }
  };
  
  const fetchParsedContent = async (recordId: string) => {
    try {
      const response = await axios.get(`http://127.0.0.1:8000/parse/preview_parsed/${recordId}`);
      if (response.status === 200) {
        if (response.data.status === "success") {
          rawContent = response.data.data.content || '';
          
          // 根据任务类型设置预览内容类型
          if (response.data.data.is_ocr_result) {
            previewContentType = 'ocr';
          } else if (response.data.data.task_type === 'pdf_text') {
            previewContentType = 'pdf_text';
          } else {
            previewContentType = 'parsed';
          }
        } else if (response.data.status === "pending") {
          previewErrorMessage = "解析尚未完成，请稍后再试";
        } else {
          previewErrorMessage = "Failed to preview parsed content" + (response.data?.message ? `: ${response.data.message}` : '');
        }
      } else {
        previewErrorMessage = "Failed to preview parsed content" + (response.data?.detail ? `: ${response.data.detail}` : '');
      }
    } catch (error) {
      console.error('Error fetching parsed content:', error);
      previewErrorMessage = "Network error previewing parsed content";
    } finally {
      previewLoading = false;
    }
  };

  const downloadContent = async () => {
    try {
      if (previewContentType === 'raw') {
        // 支持原始内容下载
        if (!rawContent) {
          previewErrorMessage = "Download failed";
          return;
        }
        const blob = new Blob([rawContent], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${previewModalTitle.replace(/\s+/g, '_')}.txt`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        return;
      }
    } catch (error) {
      console.error('Error downloading content:', error);
      previewErrorMessage = "Download failed";
    }
  };

  // --- API Functions ---
  async function uploadFile(file: File): Promise<UploadResponse> {
    try {
      const fileType = file.name.split(".").pop()?.toLowerCase();
      
      if (["pdf", "jpg", "jpeg", "png"].includes(fileType)) {
        // 使用FormData上传二进制文件
        const formData = new FormData();
        formData.append("file", file);
        
        try {
          const response = await axios.post<UploadResponse>(
            `http://127.0.0.1:8000/parse/upload_binary`,
            formData,
            {
              headers: {
                'Content-Type': 'multipart/form-data'
              }
            }
          );
          return response.data;
        } catch (error) {
          console.error(`Error uploading binary file ${file.name}:`, error);
          throw error;
        }
      } else {
        // 处理文本文件
        const reader = new FileReader();
        reader.readAsText(file);

        return await new Promise((resolve, reject) => {
          reader.onload = async (e) => {
            const fileContent = e.target?.result;
            if (typeof fileContent !== "string") {
              reject("File content could not be read")
              return
            }
            try {
              const response = await axios.post<UploadResponse>(
                      `http://127.0.0.1:8000/parse/upload`,
                      {
                        filename: file.name,
                        content: fileContent,
                        file_type: file.name.split(".").pop(),
                      }
              );
              resolve(response.data);
            } catch (error) {
              console.error(`Error uploading file ${file.name}:`, error);
              reject(error);
            }
          };
        });
      }
    } catch (error) {
      console.error(`Error processing file ${file.name}:`, error);
      throw error;
    }
  }

  async function parseFileForEntry(file: UnifiedFile) {
    if (!file.file_id) {
      console.error("File ID is missing, cannot parse.");
      return;
    }

    // 将文件状态更新为pending，并设置初始进度
    uploadedFiles = uploadedFiles.map(f =>
      f.file_id === file.file_id ? { 
        ...f, 
        parseStatus: "pending", 
        parseProgress: 0, 
        recordId: null,
        // 确保这些属性被正确初始化
        status: f.status || "pending"
      } : f
    );
    
    console.log("设置文件初始状态:", uploadedFiles.find(f => f.file_id === file.file_id));

    try {
      // 所有文件类型统一使用/parse/file接口
      const fileRequest: FileIDRequest = { file_id: file.file_id };
      
      console.log(`开始解析文件: ${file.filename}, 类型: ${file.type}, ID: ${file.file_id}`);
      
      // 统一使用parse/file接口进行解析
      const parseResponse = await axios.post<ParseResponse>(
        `http://127.0.0.1:8000/parse/parse/file`, 
        fileRequest
      );
      
      console.log(`解析API响应:`, parseResponse.data);

      if (parseResponse.data.status === "success") {
        const recordId = parseResponse.data.data.record_id;
        console.log(`解析任务创建成功, record_id: ${recordId}`);
        
        uploadedFiles = uploadedFiles.map(f =>
          f.file_id === file.file_id ? { ...f, recordId: recordId, parseStatus: "processing" } : f
        );
        
        // 判断文件类型 - 对于PDF和图片类型始终进行轮询
        // 检查file.type === 'binary'或特定的文件扩展名
        const isPdfOrImage = file.type === 'binary' || 
                           file.file_type === 'pdf' || 
                           ['jpg', 'jpeg', 'png'].includes(file.file_type);
        console.log(`文件类型检测: ${file.filename}, type=${file.type}, file_type=${file.file_type}, isPdfOrImage=${isPdfOrImage}`);
        
        // 对于PDF和图片文件，即使有content也进行轮询
        // 对于文本文件，有content则直接完成
        if (parseResponse.data.data.content && !isPdfOrImage) {
          // 直接更新状态为已完成
          console.log(`解析直接完成，更新状态`);
          uploadedFiles = uploadedFiles.map(f =>
            f.file_id === file.file_id ? { 
              ...f, 
              status: "parsed", 
              parseStatus: "completed", 
              parseProgress: 100,
              recordId: recordId
            } : f
          );
        } else {
          // 否则开始轮询进度
          console.log(`开始轮询解析进度, record_id: ${recordId}`);
          startPollingParsingProgress(file.file_id, recordId);
        }
      } else {
        console.error(`解析失败:`, parseResponse);
        uploadedFiles = uploadedFiles.map(f =>
          f.file_id === file.file_id ? { ...f, parseStatus: "failed", parseProgress: 0 } : f
        );
      }
    } catch (error) {
      console.error("Error starting parsing:", error);
      uploadedFiles = uploadedFiles.map(f =>
        f.file_id === file.file_id ? { ...f, parseStatus: "failed", parseProgress: 0 } : f
      );
    }
  }

  async function checkParseHistory(filename: string): Promise<number> {
    try {
      const filenameRequest: FilenameRequest = { filename };
      const response = await axios.post(
              "http://127.0.0.1:8000/parse/phistory",
              filenameRequest,
              { headers: { "Content-Type": "application/json" } }
      );

      // Check response data
      if (response.data && typeof response.data.exists === "number") {
        return response.data.exists;
      } else {
        console.error("Unexpected response format:", response);
        return 0;
      }
    } catch (error) {
      console.error("Error checking parse history:", error);
      return 0;
    }
  }

  async function fetchUploadedFiles(): Promise<void> {
    try {
      // 保存当前处理中的文件状态，用于刷新后恢复
      const processingFiles = new Map();
      uploadedFiles.forEach(file => {
        if ((file.parseStatus === 'processing' || file.inProgress) && file.file_id) {
          processingFiles.set(file.file_id, {
            parseStatus: file.parseStatus,
            parseProgress: file.parseProgress,
            inProgress: file.inProgress,
            hasError: file.hasError,
            recordId: file.recordId
          });
        }
      });
      
      console.log('保存当前处理中的文件状态:', [...processingFiles.entries()]);
      
      const response = await axios.get<UnifiedFileListResponse>(
        `http://127.0.0.1:8000/parse/files/all`
      );
      
      if (response.data.status === "success") {
        // 处理返回的文件列表，为每个文件添加解析状态信息
        const filesWithStatus = await Promise.all(
          response.data.data.map(async file => {
            // 检查文件是否已解析
            let status = file.status;
            const exists = await checkParseHistory(file.filename);
            
            // 根据解析历史更新文件状态
            if (exists === 1) {
              status = "parsed";
            }
            
            // 创建基本文件对象
            const updatedFile = {
              ...file,
              status: status,
              parseStatus: file.parseStatus || "",
              parseProgress: file.parseProgress || 0,
              recordId: file.recordId || null
            };
            
            // 检查是否有活跃的任务
            if (file.file_id && processingFiles.has(file.file_id)) {
              // 从保存的状态中恢复处理状态
              const savedState = processingFiles.get(file.file_id);
              console.log(`恢复文件 ${file.filename} 的处理状态:`, savedState);
              
              // 合并保存的状态
              Object.assign(updatedFile, {
                parseStatus: savedState.parseStatus,
                parseProgress: savedState.parseProgress,
                inProgress: savedState.inProgress,
                hasError: savedState.hasError,
                recordId: savedState.recordId
              });
            } else if (file.recordId) {
              // 如果有recordId但没有保存的状态，查询后端获取当前任务状态
              try {
                const progressResponse = await fetchTaskProgress(file.recordId);
                if (progressResponse.status === "success") {
                  // 如果任务仍在处理中，恢复显示进度条
                  if (progressResponse.data.status === "processing") {
                    console.log(`文件 ${file.filename} 的任务仍在处理中，恢复进度条:`, progressResponse.data);
                    Object.assign(updatedFile, {
                      parseStatus: "processing",
                      parseProgress: progressResponse.data.progress || 0,
                      inProgress: true,
                      taskType: progressResponse.data.task_type
                    });
                  }
                }
              } catch (err) {
                console.warn(`获取文件 ${file.filename} 的任务状态失败:`, err);
              }
            }
            
            return updatedFile;
          })
        );
        
        // 更新上传文件列表
        uploadedFiles = filesWithStatus as UnifiedFile[];
        
        // 检查是否有进行中的任务，如果有，确保启动轮询
        for (const file of uploadedFiles) {
          if ((file.parseStatus === 'processing' || file.inProgress) && file.recordId && file.file_id) {
            // 检查是否已经有轮询
            if (!parsingProgressIntervals[file.file_id]) {
              console.log(`恢复文件 ${file.filename} 的进度轮询, record_id: ${file.recordId}`);
              startPollingParsingProgress(file.file_id, file.recordId);
            }
          }
        }
        
      } else {
        console.error("Error fetching uploaded files:", response);
        errorMessage = t("Failed to fetch uploaded files");
      }
    } catch (error) {
      console.error("Error fetching uploaded files:", error);
      errorMessage = t("Failed to fetch uploaded files");
    }
  }

  async function fetchTaskProgress(recordId: string): Promise<TaskProgressResponse> {
    try {
      console.log(`获取任务进度, record_id: ${recordId}`);
      // 先尝试通过标准API获取任务进度
      const response = await axios.get<TaskProgressResponse>(
        `http://127.0.0.1:8000/parse/task/progress`, 
        { params: { record_id: recordId } }
      );
      
      console.log(`标准进度API响应:`, response.data);
      
      // 转换响应格式以符合TaskProgressResponse类型
      let taskResponse: TaskProgressResponse = {
        status: response.data.status,
        message: response.data.message,
        data: {
          progress: response.data.data.progress,
          status: response.data.data.status,
          task_type: response.data.data.task_type || "parse"
        }
      };
      
      // 对于PDF或OCR任务，尝试获取更详细的OCR进度信息
      // 注意：即使是pdf_text任务类型(直接提取文本)也需要获取进度信息
      if (response.data.data.task_type === "ocr" || 
          response.data.data.task_type === "pdf_text" || 
          (response.data.data.status === "processing" && response.data.data.progress < 100)) {
        try {
          console.log(`检测到PDF处理任务，获取详细进度`);
          // 尝试调用OCR专用的进度API
          const ocrResponse = await axios.get(
            `http://127.0.0.1:8000/parse/ocr/progress/${recordId}`
          );
          
          console.log(`OCR详细进度API响应:`, ocrResponse.data);
          
          if (ocrResponse.data.status === "success") {
            // 使用OCR专用API返回的更详细进度信息
            const ocrProgress = ocrResponse.data.data;
            
            // 构建增强的响应
            taskResponse = {
              status: response.data.status,
              message: response.data.message,
              data: {
                progress: ocrProgress.progress,
                status: ocrProgress.status,
                task_type: response.data.data.task_type,
                ocr_info: {
                  total_pages: ocrProgress.total_pages,
                  processed_pages: ocrProgress.processed_pages,
                  elapsed_seconds: ocrProgress.elapsed_seconds || 0,
                  estimated_remaining_seconds: ocrProgress.estimated_remaining_seconds || 0
                }
              }
            };
            console.log(`合并OCR详细信息到响应`, taskResponse);
          }
        } catch (error) {
          // 如果OCR专用API调用失败，继续使用标准API的结果
          console.warn("Failed to get detailed OCR progress, using standard progress:", error);
        }
      }
      
      return taskResponse;
    } catch (error) {
      console.error("Error fetching task progress:", error);
      throw error;
    }
  }

  function startPollingParsingProgress(fileId: string, recordId: string) {
    if (parsingProgressIntervals[fileId]) {
      clearInterval(parsingProgressIntervals[fileId]);
    }

    console.log(`开始轮询任务进度, file_id: ${fileId}, record_id: ${recordId}`);
    
    // 立即设置文件为处理状态，并且强制显示进度条
    uploadedFiles = uploadedFiles.map(f =>
      f.file_id === fileId ? { 
        ...f, 
        parseStatus: "processing", // 确保状态为processing
        parseProgress: f.parseProgress || 1, // 保留现有进度或设置为1%
        inProgress: true,          // 添加一个标志，表示正在处理中
        recordId: recordId         // 确保recordId被设置
      } : f
    );
    
    // 保存任务状态到本地存储，以便在页面刷新后恢复
    try {
      // 获取现有的任务
      const savedTasks = localStorage.getItem('parsingTasks') || '{}';
      const tasks = JSON.parse(savedTasks);
      
      // 添加或更新当前任务
      tasks[fileId] = {
        fileId,
        recordId,
        timestamp: Date.now(),
        filename: uploadedFiles.find(f => f.file_id === fileId)?.filename || ''
      };
      
      // 保存回本地存储
      localStorage.setItem('parsingTasks', JSON.stringify(tasks));
      console.log(`任务状态已保存到本地存储:`, tasks);
    } catch (e) {
      console.warn('保存任务状态到本地存储失败:', e);
    }
    
    // 立即获取一次进度，而不是等待第一个间隔
    setTimeout(async () => {
      try {
        const progressResponse = await fetchTaskProgress(recordId);
        updateFileProgress(fileId, recordId, progressResponse);
      } catch (error) {
        console.error("Error on initial progress check:", error);
      }
    }, 100);
    
    parsingProgressIntervals[fileId] = setInterval(async () => {
      try {
        console.log(`轮询任务进度 (${new Date().toLocaleTimeString()}), file_id: ${fileId}, record_id: ${recordId}`);
        const progressResponse = await fetchTaskProgress(recordId);
        console.log(`获取到的进度响应:`, progressResponse);
        updateFileProgress(fileId, recordId, progressResponse);
        
        // 轮询后检查文件状态
        const updatedFile = uploadedFiles.find(f => f.file_id === fileId);
        console.log(`轮询后文件状态:`, {
          parseStatus: updatedFile?.parseStatus,
          parseProgress: updatedFile?.parseProgress,
          status: updatedFile?.status
        });
      } catch (error) {
        console.error("Error fetching task progress:", error);
        // 即使遇到错误也不立即停止轮询，改为每5次错误才停止
        progressErrorCounter[fileId] = (progressErrorCounter[fileId] || 0) + 1;
        
        console.log(`轮询错误计数: ${progressErrorCounter[fileId]}/5`);
        
        // 如果连续错误超过5次，才停止轮询
        if (progressErrorCounter[fileId] >= 5) {
          console.log(`连续错误超过5次，停止轮询`);
          clearInterval(parsingProgressIntervals[fileId]);
          delete parsingProgressIntervals[fileId];
          uploadedFiles = uploadedFiles.map(f =>
            f.file_id === fileId ? { ...f, parseStatus: "failed", parseProgress: 0 } : f
          );
          // 重置错误计数
          progressErrorCounter[fileId] = 0;
        }
      }
    }, 1000); // 每1秒轮询一次，更频繁刷新
  }
  
  function updateFileProgress(fileId: string, recordId: string, progressResponse: TaskProgressResponse) {
    if (progressResponse.status === "success") {
      const progress = progressResponse.data.progress;
      const status = progressResponse.data.status;
      const taskType = progressResponse.data.task_type || "parse";
      
      console.log(`进度更新: ${progress}%, 状态: ${status}, 任务类型: ${taskType}`);
      
      // 查找当前文件
      const currentFile = uploadedFiles.find(f => f.file_id === fileId);
      if (!currentFile) {
        console.error(`找不到文件 ID: ${fileId}`);
        return;
      }
      
      console.log(`更新前文件状态:`, {
        parseStatus: currentFile.parseStatus,
        parseProgress: currentFile.parseProgress,
        status: currentFile.status
      });
      
      // 更新文件处理状态
      uploadedFiles = uploadedFiles.map(f => {
        if (f.file_id === fileId) {
          // 基本状态更新 - 确保保留原有数据
          const updatedFile = { 
            ...f, 
            parseProgress: progress || 0, // 确保有值
            parseStatus: status || 'processing', // 确保有值
            taskType: taskType // 保存任务类型
          };
          
          // 如果有OCR详细信息，添加到文件对象
          if (progressResponse.data.ocr_info) {
            console.log(`添加OCR详细信息到文件对象:`, progressResponse.data.ocr_info);
            updatedFile.ocr_info = progressResponse.data.ocr_info;
          }
          
          console.log(`更新后文件状态:`, {
            parseStatus: updatedFile.parseStatus,
            parseProgress: updatedFile.parseProgress,
            status: updatedFile.status
          });
          
          return updatedFile;
        }
        return f;
      });
      
      // 检查处理是否完成或失败
      if (status === "completed" || status === "failed") {
        console.log(`任务状态: ${status}，但保持进度条显示`);
        
        // 如果完成，更新文件状态为"已解析"，但保持进度条显示
        if (status === "completed") {
          console.log(`任务完成，更新文件状态为"已解析"但保持进度条显示`);
          
          // 先保留处理状态，只更新进度为100%
          uploadedFiles = uploadedFiles.map(f =>
            f.file_id === fileId ? { 
              ...f, 
              status: "parsed",                // 文件状态为已解析
              parseProgress: 100,              // 确保进度为100%
              recordId: recordId,              // 确保记录ID被保存
              inProgress: true,                // 保持显示进度条
              parseStatus: "processing"        // 保持处理状态以显示进度条
            } : f
          );
          
          // 显示完成状态10秒后再更新为完成状态并清除定时器
          setTimeout(() => {
            console.log(`将任务 ${fileId} 标记为已完成`);
            uploadedFiles = uploadedFiles.map(f =>
              f.file_id === fileId ? { 
                ...f, 
                parseStatus: "completed",  // 更新为完成状态
                inProgress: false          // 不再显示进度条
              } : f
            );
            
                          // 再等5秒后清除定时器并从本地存储中移除任务
              setTimeout(() => {
                console.log(`清除任务 ${fileId} 的进度轮询`);
                clearInterval(parsingProgressIntervals[fileId]);
                delete parsingProgressIntervals[fileId];
                
                // 从本地存储中移除任务
                try {
                  const savedTasks = localStorage.getItem('parsingTasks') || '{}';
                  const tasks = JSON.parse(savedTasks);
                  if (tasks[fileId]) {
                    delete tasks[fileId];
                    localStorage.setItem('parsingTasks', JSON.stringify(tasks));
                    console.log(`已从本地存储中移除任务 ${fileId}`);
                  }
                } catch (e) {
                  console.warn('从本地存储移除任务失败:', e);
                }
              }, 5000);
          }, 10000);
          
        } else if (status === "failed") {
          // 如果失败，先保持进度条显示，但标记为失败
          console.log(`任务失败，更新文件状态为"失败"但保持进度条显示`);
          uploadedFiles = uploadedFiles.map(f =>
            f.file_id === fileId ? { 
              ...f,
              parseStatus: "processing",   // 保持处理状态以显示进度条
              parseProgress: progress || 0,  // 保持当前进度
              inProgress: true,            // 保持显示进度条
              hasError: true               // 标记有错误
            } : f
          );
          
          // 显示失败状态10秒后再更新为失败状态并清除定时器
          setTimeout(() => {
            uploadedFiles = uploadedFiles.map(f =>
              f.file_id === fileId ? { 
                ...f,
                parseStatus: "failed",    // 更新为失败状态
                parseProgress: 0,
                inProgress: false         // 不再显示进度条
              } : f
            );
            
                          // 再等5秒后清除定时器并从本地存储中移除任务
              setTimeout(() => {
                clearInterval(parsingProgressIntervals[fileId]);
                delete parsingProgressIntervals[fileId];
                
                // 从本地存储中移除任务
                try {
                  const savedTasks = localStorage.getItem('parsingTasks') || '{}';
                  const tasks = JSON.parse(savedTasks);
                  if (tasks[fileId]) {
                    delete tasks[fileId];
                    localStorage.setItem('parsingTasks', JSON.stringify(tasks));
                    console.log(`已从本地存储中移除任务 ${fileId}`);
                  }
                } catch (e) {
                  console.warn('从本地存储移除任务失败:', e);
                }
              }, 5000);
          }, 10000);
        }
      }
    } else {
      console.error("Error fetching task progress:", progressResponse);
      clearInterval(parsingProgressIntervals[fileId]);
      delete parsingProgressIntervals[fileId];
      uploadedFiles = uploadedFiles.map(f =>
        f.file_id === fileId ? { ...f, parseStatus: "failed", parseProgress: 0 } : f
      );
    }
  }

  // --- API Functions ---
  async function deleteFile(fileId: string) {
    loading = true;
    errorMessage = null;
    try {
      // 使用正确的请求格式
      const fileRequest: FileIDRequest = { file_id: fileId };
      const response = await axios.delete<APIResponse>(
        `http://127.0.0.1:8000/parse/deletefiles`,
        {
          data: fileRequest
        }
      );

      if (response.data.status === "success") {
        // 从列表中移除删除的文件
        uploadedFiles = uploadedFiles.filter(file => file.file_id !== fileId);
      } else {
        errorMessage = t("Failed to delete file") + ": " + response.data.message;
        console.error("Error deleting file:", response);
      }
    } catch (error) {
      errorMessage = t("Failed to delete file");
      console.error("Error deleting file:", error);
    } finally {
      loading = false;
    }
  }

  // --- Upload Logic ---
  async function uploadAndProcessFile(file: File) {
    loading = true;
    errorMessage = null;
    
    try {
      // 上传文件
      const response = await uploadFile(file);

      if (response.status !== "success") {
        errorMessage = t("Failed to upload file") + ": " + file.name;
        console.error(`Error uploading file ${file.name}:`, response);
        loading = false;
        return;
      }
      
      console.log("File uploaded successfully, id is", response.data.file_id);
      
      // 刷新文件列表
      await fetchUploadedFiles();



    } catch (error) {
      errorMessage = t("Failed to upload file");
      console.error("Upload failed:", error);
    } finally {
      loading = false;
    }
  }


  function returnToData() {
    goto(`/data`);
  }

  let fetchEntriesUpdater: any;
  // 创建错误计数器对象，用于跟踪每个文件的请求错误次数
  let progressErrorCounter: {[fileId: string]: number} = {};
  
  // 从本地存储中恢复进行中的任务
  async function restoreTasksFromLocalStorage() {
    try {
      const savedTasks = localStorage.getItem('parsingTasks');
      if (!savedTasks) return;
      
      const tasks = JSON.parse(savedTasks);
      console.log('从本地存储恢复任务:', tasks);
      
      // 获取当前时间
      const now = Date.now();
      const updatedTasks = {};
      let tasksChanged = false;
      
      // 遍历所有保存的任务
      for (const fileId in tasks) {
        const task = tasks[fileId];
        
        // 检查任务是否过期（超过30分钟）
        if (now - task.timestamp > 30 * 60 * 1000) {
          console.log(`任务 ${fileId} 已过期，将被移除`);
          tasksChanged = true;
          continue;
        }
        
        // 保留未过期的任务
        updatedTasks[fileId] = task;
        
        // 尝试获取任务状态
        try {
          const progressResponse = await fetchTaskProgress(task.recordId);
          
          if (progressResponse.status === "success") {
            // 检查任务是否仍在处理中
            if (progressResponse.data.status === "processing") {
              console.log(`恢复任务 ${fileId} 的进度轮询:`, progressResponse.data);
              
              // 找到对应的文件
              const file = uploadedFiles.find(f => f.file_id === fileId);
              if (file) {
                // 更新文件状态
                uploadedFiles = uploadedFiles.map(f =>
                  f.file_id === fileId ? { 
                    ...f, 
                    parseStatus: "processing",
                    parseProgress: progressResponse.data.progress || 0,
                    inProgress: true,
                    recordId: task.recordId
                  } : f
                );
                
                // 启动轮询
                if (!parsingProgressIntervals[fileId]) {
                  startPollingParsingProgress(fileId, task.recordId);
                }
              }
            } else if (progressResponse.data.status === "completed" || progressResponse.data.status === "failed") {
              // 任务已完成或失败，从保存的任务中移除
              console.log(`任务 ${fileId} 已${progressResponse.data.status === "completed" ? "完成" : "失败"}，将被移除`);
              delete updatedTasks[fileId];
              tasksChanged = true;
            }
          }
        } catch (error) {
          console.warn(`检查任务 ${fileId} 状态时出错:`, error);
        }
      }
      
      // 如果任务列表有变化，更新本地存储
      if (tasksChanged) {
        localStorage.setItem('parsingTasks', JSON.stringify(updatedTasks));
      }
    } catch (error) {
      console.error('恢复任务状态失败:', error);
    }
  }

  onMount(async () => {
    fetchEntriesUpdater = setInterval(fetchUploadedFiles, UPDATE_VIEW_INTERVAL);
    
    // 先获取文件列表
    await fetchUploadedFiles();
    
    // 然后尝试恢复任务状态
    await restoreTasksFromLocalStorage();
  });

  onDestroy(() => {
    clearInterval(fetchEntriesUpdater);
    for (const intervalId in parsingProgressIntervals) {
      clearInterval(parsingProgressIntervals[intervalId]);
    }
  });


</script>


<ActionPageTitle returnTo={"/data"} title={t("data.uploader.title")} />

{#if !loading}
  <div class="w-full flex flex-col space-y-6 p-4">
    <!-- Error Message Section -->
    {#if errorMessage}
      <div class="p-4 bg-red-100 border-l-4 border-red-500 text-red-700 rounded shadow-md">
        <div class="flex items-center">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 mr-2" viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
          </svg>
          <span>{errorMessage}</span>
        </div>
      </div>
    {/if}

    <!-- Statistics Overview -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
      <div class="bg-white rounded-lg shadow-md p-4 flex items-center">
        <div class="p-3 rounded-full bg-blue-100 text-blue-500 mr-4">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
        </div>
        <div>
          <p class="text-gray-500 text-sm">Total Files</p>
          <p class="text-2xl font-semibold">{uploadedFiles.length}</p>
        </div>
      </div>

      <div class="bg-white rounded-lg shadow-md p-4 flex items-center">
        <div class="p-3 rounded-full bg-green-100 text-green-500 mr-4">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
          </svg>
        </div>
        <div>
          <p class="text-gray-500 text-sm">Parsed Files</p>
          <p class="text-2xl font-semibold">{uploadedFiles.filter(f => f.status === 'parsed').length}</p>
        </div>
      </div>

      <div class="bg-white rounded-lg shadow-md p-4 flex items-center">
        <div class="p-3 rounded-full bg-yellow-100 text-yellow-500 mr-4">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
        <div>
          <p class="text-gray-500 text-sm">Pending Files</p>
          <p class="text-2xl font-semibold">{uploadedFiles.filter(f => f.status === 'pending').length}</p>
        </div>
      </div>
    </div>

    <!-- File Upload Section -->
    <div class="bg-white rounded-lg shadow-md p-6">
      <h2 class="text-lg font-semibold text-gray-700 mb-4">Upload New Files</h2>
      <Dropzone
        id="dropzone"
        class="border-2 border-dashed border-blue-300 hover:border-blue-500 transition-colors rounded-lg"
        on:drop={dropHandle}
        on:dragover={(event) => { event.preventDefault(); }}
        on:change={changeHandle}
      >
        <div class="text-center py-6">
          <svg
            aria-hidden="true"
            class="mb-3 w-12 h-12 mx-auto text-gray-400"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            xmlns="http://www.w3.org/2000/svg"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
            />
          </svg>
          <p class="mb-2 text-sm text-gray-700">
            <span class="font-semibold">{t("data.uploader.click")}</span>
            {t("data.uploader.or")}
            <span class="font-semibold">{t("data.uploader.p1")}</span>
            {t("data.uploader.p2")}
          </p>
          <p class="text-xs text-gray-500">Supported formats: TXT, TEX, JSON, PDF, PNG, JPG, JPEG</p>
        </div>
      </Dropzone>
    </div>

    <!-- File List Section -->
    <div class="bg-white rounded-lg shadow-md overflow-hidden">
      <div class="px-6 py-4 bg-gray-50 border-b border-gray-200">
        <h2 class="text-lg font-semibold text-gray-700">{t("data.uploader.uploaded_files")}</h2>
      </div>
      <div class="overflow-x-auto" style="max-height: 500px;">
        <Table striped={true} hoverable={true} class="min-w-full">
          <TableHead class="bg-gray-50">
            {#each uploaded_file_heads as head}
              <TableHeadCell class="py-3">{head}</TableHeadCell>
            {/each}
          </TableHead>
          <TableBody>
            {#each uploadedFiles as file}
              <tr class="hover:bg-gray-50 transition-colors">
                <TableBodyCell class="max-w-xs truncate">
                  <div class="flex items-center">
                    <!-- File type icon -->
                    <span class="mr-2">
                      {#if file.file_type === 'txt'}
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-gray-500" viewBox="0 0 20 20" fill="currentColor">
                          <path fill-rule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4zm2 6a1 1 0 011-1h6a1 1 0 110 2H7a1 1 0 01-1-1zm1 3a1 1 0 100 2h6a1 1 0 100-2H7z" clip-rule="evenodd" />
                        </svg>
                      {:else if file.file_type === 'json'}
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-yellow-500" viewBox="0 0 20 20" fill="currentColor">
                          <path fill-rule="evenodd" d="M2 5a2 2 0 012-2h12a2 2 0 012 2v10a2 2 0 01-2 2H4a2 2 0 01-2-2V5zm3.293 1.293a1 1 0 011.414 0l3 3a1 1 0 010 1.414l-3 3a1 1 0 01-1.414-1.414L7.586 10 5.293 7.707a1 1 0 010-1.414zM11 12a1 1 0 100 2h3a1 1 0 100-2h-3z" clip-rule="evenodd" />
                        </svg>
                      {:else if file.file_type === 'tex'}
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-blue-500" viewBox="0 0 20 20" fill="currentColor">
                          <path fill-rule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z" clip-rule="evenodd" />
                        </svg>
                      {:else if file.file_type === 'pdf'}
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-red-500" viewBox="0 0 20 20" fill="currentColor">
                          <path fill-rule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z" clip-rule="evenodd" />
                        </svg>
                      {:else if ['jpg', 'jpeg', 'png'].includes(file.file_type)}
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-green-500" viewBox="0 0 20 20" fill="currentColor">
                          <path fill-rule="evenodd" d="M4 3a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V5a2 2 0 00-2-2H4zm12 12H4l4-8 3 6 2-4 3 6z" clip-rule="evenodd" />
                        </svg>
                      {:else}
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-gray-400" viewBox="0 0 20 20" fill="currentColor">
                          <path fill-rule="evenodd" d="M4 4a2 2 0 012-2h8a2 2 0 012 2v12a2 2 0 01-2 2H6a2 2 0 01-2-2V4z" clip-rule="evenodd" />
                        </svg>
                      {/if}
                    </span>
                    <span class="truncate">{file.filename}</span>
                  </div>
                </TableBodyCell>
                <TableBodyCell>{file.type === 'binary' ? file['mime_type'] : file.file_type}</TableBodyCell>
                <TableBodyCell>{formatFileSize(file.size)}</TableBodyCell>
                <TableBodyCell>{new Date(file.created_at).toLocaleString()}</TableBodyCell>
                <TableBodyCell>
                  {#if file.status === 'parsed'}
                    <span class="px-2 py-1 text-xs font-semibold rounded-full bg-green-100 text-green-800">{t("data.uploader.parsed")}</span>
                  {:else if file.status === 'processed'}
                    <span class="px-2 py-1 text-xs font-semibold rounded-full bg-blue-100 text-blue-800">{t("data.uploader.processed")}</span>
                  {:else}
                    <span class="px-2 py-1 text-xs font-semibold rounded-full bg-yellow-100 text-yellow-800">{t("data.uploader.pending")}</span>
                  {/if}
                </TableBodyCell>
                <TableBodyCell>
                  <div class="flex space-x-2">
                    {#if file.parseStatus !== "completed"}
                      <Button size="xs" color="blue" on:click={() => handleParseButtonClick(file)}>
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 mr-1" viewBox="0 0 20 20" fill="currentColor">
                          <path d="M4 4a2 2 0 00-2 2v1h16V6a2 2 0 00-2-2H4z" />
                          <path fill-rule="evenodd" d="M18 9H2v5a2 2 0 002 2h12a2 2 0 002-2V9zM4 13a1 1 0 011-1h1a1 1 0 110 2H5a1 1 0 01-1-1zm5-1a1 1 0 100 2h1a1 1 0 100-2H9z" clip-rule="evenodd" />
                        </svg>
                        {t("data.uploader.parse_button")}
                      </Button>
                    {/if}
                    
                    <!-- 原始内容预览按钮 -->
                    <Button size="xs" color="green" on:click={() => previewRawFile(file)}>
                      <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 mr-1" viewBox="0 0 20 20" fill="currentColor">
                        <path d="M10 12a2 2 0 100-4 2 2 0 000 4z" />
                        <path fill-rule="evenodd" d="M.458 10C1.732 5.943 5.522 3 10 3s8.268 2.943 9.542 7c-1.274 4.057-5.064 7-9.542 7S1.732 14.057.458 10zM14 10a4 4 0 11-8 0 4 4 0 018 0z" clip-rule="evenodd" />
                      </svg>
                      Preview
                    </Button>
                    
                    <!-- 解析后内容预览按钮 - 只在完成解析后显示 -->
                    {#if file.parseStatus === "completed" && file.recordId}
                      <Button size="xs" color="purple" on:click={() => previewParsedContent(file)}>
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 mr-1" viewBox="0 0 20 20" fill="currentColor">
                          <path d="M10 12a2 2 0 100-4 2 2 0 000 4z" />
                          <path fill-rule="evenodd" d="M.458 10C1.732 5.943 5.522 3 10 3s8.268 2.943 9.542 7c-1.274 4.057-5.064 7-9.542 7S1.732 14.057.458 10zM14 10a4 4 0 11-8 0 4 4 0 018 0z" clip-rule="evenodd" />
                        </svg>
                        解析结果
                      </Button>
                    {/if}
                  </div>
                </TableBodyCell>
                <TableBodyCell>
                  <Button size="xs" color="red" on:click={() => handleDeleteButtonClick(file)}>
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 mr-1" viewBox="0 0 20 20" fill="currentColor">
                      <path fill-rule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clip-rule="evenodd" />
                    </svg>
                    {t("data.uploader.delete_button")}
                  </Button>
                </TableBodyCell>
              </tr>
              {#if file.parseStatus}
                <tr class="bg-gray-50">
                  <td colspan="7">
                    <div class="flex flex-col space-y-2 p-2">
                      <div class="flex items-center">
                        <span class="text-sm text-gray-600 mr-2">{t("data.uploader.parse_status")}: </span>
                        {#if file.parseStatus === 'processing' || file.parseStatus === 'pending' || file.inProgress}
                          <div class="flex-1 max-w-md">
                            <Progressbar 
                              progress={file.parseProgress || 0} 
                              size="sm" 
                              color={file.hasError ? "red" : (file.parseProgress >= 100 ? "green" : "blue")}
                            />
                          </div>
                          <span class="ml-2 text-sm" class:text-blue-600={!file.hasError && file.parseProgress < 100} class:text-green-600={!file.hasError && file.parseProgress >= 100} class:text-red-600={file.hasError}>
                            {file.parseProgress || 0}%
                            {#if file.parseProgress >= 100 && !file.hasError}
                              <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 inline ml-1" viewBox="0 0 20 20" fill="currentColor">
                                <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd" />
                              </svg>
                            {/if}
                          </span>
                        {:else if file.parseStatus === 'completed'}
                          <span class="text-sm font-medium text-green-600">
                            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 inline mr-1" viewBox="0 0 20 20" fill="currentColor">
                              <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd" />
                            </svg>
                            {t("Completed")}
                          </span>
                        {:else if file.parseStatus === 'failed'}
                          <span class="text-sm font-medium text-red-600">
                            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 inline mr-1" viewBox="0 0 20 20" fill="currentColor">
                              <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd" />
                            </svg>
                            {t("data.uploader.failed")}
                          </span>
                        {/if}
                      </div>
                      
                      {#if file.parseStatus === 'processing' || file.parseStatus === 'pending' || file.inProgress}
                        <div class="flex flex-wrap justify-between text-xs text-gray-600 gap-2 mt-2">
                          <div class="font-semibold">
                            <span class="px-2 py-1 rounded inline-block" 
                              class:bg-blue-50={!file.hasError && file.parseProgress < 100}
                              class:text-blue-700={!file.hasError && file.parseProgress < 100}
                              class:bg-green-50={!file.hasError && file.parseProgress >= 100}
                              class:text-green-700={!file.hasError && file.parseProgress >= 100}
                              class:bg-red-50={file.hasError}
                              class:text-red-700={file.hasError}
                            >
                              {#if file.hasError}
                                任务遇到错误
                              {:else if file.parseProgress >= 100}
                                {file.type === 'binary' ? 'OCR处理完成' : '解析完成'}: 
                              {:else}
                                {file.type === 'binary' ? '正在处理' : '正在解析'}: 
                              {/if}
                              {file.filename}
                            </span>
                          </div>
                          
                          <div class="mt-1 text-xs text-gray-500" class:animate-pulse={file.parseProgress < 100}>
                            {#if file.parseProgress < 100}
                              {t("Refreshing progress every second...")}
                            {:else}
                              处理完成，将在数秒后隐藏进度条
                            {/if}
                          </div>
                        </div>
                        
                        <!-- 添加中止任务按钮 -->
                        {#if file.file_id}
                          <div class="mt-2">
                            <button 
                              class="text-xs px-2 py-1 bg-red-500 hover:bg-red-600 text-white rounded flex items-center"
                              on:click={() => {
                                console.log(`用户点击中止任务: ${file.file_id}`);
                                // 未实现: 中止任务功能可以后续添加
                              }}
                            >
                              <svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                              </svg>
                              中止任务
                            </button>
                          </div>
                        {/if}
                      {/if}
                      
                      <!-- 显示OCR详细信息 -->
                      {#if file.ocr_info}
                        <div class="flex flex-wrap items-center text-sm text-gray-600 mt-2 bg-gray-100 p-2 rounded">
                          <span class="mr-4 mb-1 font-medium">
                            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 inline mr-1" viewBox="0 0 20 20" fill="currentColor">
                              <path d="M9 2a2 2 0 00-2 2v8a2 2 0 002 2h6a2 2 0 002-2V6.414A2 2 0 0016.414 5L14 2.586A2 2 0 0012.586 2H9z" />
                              <path d="M3 8a2 2 0 012-2v10h8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" />
                            </svg>
                            <span class="text-blue-700">OCR处理进度:</span> {file.ocr_info.processed_pages}/{file.ocr_info.total_pages} 页
                            {#if file.ocr_info.total_pages > 0}
                              ({Math.round((file.ocr_info.processed_pages / file.ocr_info.total_pages) * 100)}%)
                            {/if}
                          </span>
                          
                          {#if file.ocr_info.elapsed_seconds > 0}
                            <span class="mr-4 mb-1">
                              <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 inline mr-1" viewBox="0 0 20 20" fill="currentColor">
                                <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z" clip-rule="evenodd" />
                              </svg>
                              已用时间: {Math.floor(file.ocr_info.elapsed_seconds / 60)}分{file.ocr_info.elapsed_seconds % 60}秒
                            </span>
                          {/if}
                          
                          {#if file.ocr_info.estimated_remaining_seconds > 0}
                            <span class="mb-1">
                              <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 inline mr-1" viewBox="0 0 20 20" fill="currentColor">
                                <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z" clip-rule="evenodd" />
                              </svg>
                              预计剩余: {Math.floor(file.ocr_info.estimated_remaining_seconds / 60)}分{file.ocr_info.estimated_remaining_seconds % 60}秒
                            </span>
                          {/if}
                        </div>
                      {:else if (file.parseStatus === 'processing' || file.parseStatus === 'pending') && file.type === 'binary'}
                        <div class="flex items-center text-sm text-gray-600 mt-2 bg-purple-50 p-2 rounded">
                          <span class="mr-4">
                            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 inline mr-1" viewBox="0 0 20 20" fill="currentColor">
                              <path d="M9 2a2 2 0 00-2 2v8a2 2 0 002 2h6a2 2 0 002-2V6.414A2 2 0 0016.414 5L14 2.586A2 2 0 0012.586 2H9z" />
                              <path d="M3 8a2 2 0 012-2v10h8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" />
                            </svg>
                            <span class="font-medium text-purple-800">
                              {file.file_type === 'pdf' ? 'PDF处理中' : '图片OCR处理中'}
                            </span>: 正在提取文本内容，请耐心等待...
                          </span>
                        </div>
                      {/if}
                    </div>
                  </td>
                </tr>
              {/if}
            {/each}
          </TableBody>
        </Table>
      </div>
    </div>
  </div>
{:else}
  <div class="flex items-center justify-center h-64">
    <div class="p-6 rounded-lg text-center">
      <div class="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500 mx-auto mb-4"></div>
      <p class="text-gray-600">{t("data.uploader.uploading")}</p>
    </div>
  </div>
{/if}

<!-- Delete Confirmation Modal -->
<Modal bind:open={showDeleteConfirmation} size="sm" autoclose={false} class="rounded-lg">
  <h3 slot="header" class="text-xl font-bold text-gray-900">
    {t("Confirm the deletion")}
  </h3>
  <div class="my-6 text-gray-600">
    <div class="flex items-center mb-4">
      <svg xmlns="http://www.w3.org/2000/svg" class="h-12 w-12 text-red-500 mr-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
      </svg>
      <p>{t("Are you sure you want to delete this file?")}</p>
    </div>
    {#if fileToDelete}
      <div class="bg-gray-100 p-3 rounded-lg mb-4">
        <div class="flex items-center">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-gray-500 mr-2" viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z" clip-rule="evenodd" />
          </svg>
          <span class="font-medium">{fileToDelete.filename}</span>
        </div>
        <div class="text-sm text-gray-500 mt-1">
          Type: {fileToDelete.file_type} · Size: {formatFileSize(fileToDelete.size)}
        </div>
      </div>
    {/if}
  </div>
  <div slot="footer" class="flex justify-end gap-2">
    <Button color="light" on:click={cancelDelete}>{t("Cancel")}</Button>
    <Button color="red" on:click={confirmDelete}>
      <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 mr-1" viewBox="0 0 20 20" fill="currentColor">
        <path fill-rule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clip-rule="evenodd" />
      </svg>
      {t("Confirm")}
    </Button>
  </div>
</Modal>

<!-- 文件预览模态框 -->
<Modal bind:open={previewModalOpen} size="xl" autoclose={false} class="w-full max-w-5xl">
  <h3 slot="header" class="text-xl font-semibold text-gray-900 dark:text-white flex items-center">
    {previewModalTitle}
    {#if previewContentType === 'ocr'}
      <span class="ml-2 px-2 py-1 text-xs font-semibold rounded-full bg-purple-100 text-purple-800">OCR解析结果</span>
    {:else if previewContentType === 'pdf_text'}
      <span class="ml-2 px-2 py-1 text-xs font-semibold rounded-full bg-blue-100 text-blue-800">PDF直接提取结果</span>
    {:else if previewContentType === 'parsed'}
      <span class="ml-2 px-2 py-1 text-xs font-semibold rounded-full bg-green-100 text-green-800">解析结果</span>
    {/if}
  </h3>

  <div class="space-y-4">
    {#if previewErrorMessage}
      <div class="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4">{previewErrorMessage}</div>
    {/if}

    {#if previewLoading}
      <div class="flex justify-center items-center py-8">
        <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
        <span class="ml-3 text-gray-700">Loading...</span>
      </div>
    {:else if previewContentType === 'raw' || previewContentType === 'parsed' || previewContentType === 'ocr' || previewContentType === 'pdf_text'}
      {#if previewContentType === 'pdf_text'}
        <div class="bg-blue-50 rounded-lg p-2 mb-3 flex items-center">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-blue-500 mr-2" viewBox="0 0 20 20" fill="currentColor">
            <path d="M9 2a2 2 0 00-2 2v8a2 2 0 002 2h6a2 2 0 002-2V6.414A2 2 0 0016.414 5L14 2.586A2 2 0 0012.586 2H9z" />
            <path d="M3 8a2 2 0 012-2v10h8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" />
          </svg>
          <span class="text-blue-700 font-medium">直接从PDF提取的文本内容</span>
        </div>
      {:else if previewContentType === 'ocr'}
        <div class="bg-purple-50 rounded-lg p-2 mb-3 flex items-center">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-purple-500 mr-2" viewBox="0 0 20 20" fill="currentColor">
            <path d="M3 4a1 1 0 011-1h12a1 1 0 011 1v2a1 1 0 01-1 1H4a1 1 0 01-1-1V4zm0 6a1 1 0 011-1h12a1 1 0 011 1v2a1 1 0 01-1 1H4a1 1 0 01-1-1v-2zm0 6a1 1 0 011-1h12a1 1 0 011 1v2a1 1 0 01-1 1H4a1 1 0 01-1-1v-2z" />
          </svg>
          <span class="text-purple-700 font-medium">OCR识别结果</span>
        </div>
      {/if}
      <div class="bg-gray-50 rounded-lg p-4 h-[70vh] overflow-auto">
        <pre class="whitespace-pre-wrap text-sm font-mono">{rawContent}</pre>
      </div>
    {:else}
      <p class="text-center py-8 text-gray-500">No content available</p>
    {/if}
  </div>

  <svelte:fragment slot="footer">
    <div class="flex justify-between w-full">
      <Button color="blue" on:click={downloadContent} disabled={!rawContent}>
        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
        </svg>
        Download
      </Button>
      <Button color="alternative" on:click={() => previewModalOpen = false}>
        Close
      </Button>
    </div>
  </svelte:fragment>
</Modal>