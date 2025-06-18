<script lang="ts">
  import type EvalEntry from "../../class/EvalEntry";
  import ActionPageTitle from "../components/ActionPageTitle.svelte";
  import axios from "axios";
  import { PlusOutline, ArrowDownToBracketOutline } from "flowbite-svelte-icons";
  import { getContext } from "svelte";
  const t: any = getContext("t");
  let eval_entries: Array<EvalEntry> = [];
  import {
    Accordion,
    AccordionItem,
    Button,
    Checkbox,
    Table,
    TableHead,
    TableHeadCell,
    TableBody,
    TableBodyCell,
    TableBodyRow,
    Input,
    Spinner,
    Modal,
    Alert,
    Progressbar
  } from "flowbite-svelte";
  import { page } from "$app/stores";

  import { UPDATE_VIEW_INTERVAL } from "../store";
  import { onDestroy, onMount } from "svelte";

  interface APIResponse<T = Record<string, unknown>> {
    status: string;
    message: string;
    data?: T | null;
  }

  // 自定义QAFile类型,与API返回匹配
  interface QAFile {
    id: string;
    filename: string;
    created_at: string;
  }

  interface QualityHistoryRecord {
    generation_id: string;
    input_file: string;
    dataset_id: string;
    output_file: string;
    model_name: string;
    status: string;
    qa_count: number;
    created_at: string;
  }

  let description = ""; // Domain description
let quality_eval_processing: boolean = false;
let errorMessage: string | null = null;
let successMessage: string | null = null;
let upQAFiles: QAFile[] = [];
let qualityHistory: QualityHistoryRecord[] = [];
let historyLoaded = false;
let lastHistoryRefresh: Date | null = null;

let parallel_num: number = 2;
let similarity_rate: number = 0.5;
let coverage_rate: number = 0.5;
let max_attempts: number = 1;
let modelOptions = [
    { value: 'Qwen' , label: 'Qwen'  },
    { value: 'erine', label: 'erine' },
    { value: 'flash', label: 'flash' },
    { value: 'lite' , label: 'lite'  }
];
let selectedFileId: string = '';

let modelname: String = 'erine';
  // Default AK/SK values from config
  let api_keys = ["nNgmVkQ22wuaVu4h2OimBvYM", "NDodQ4HrnTA0pV9nCf5cipaU"];
  let secret_keys = ["AzMeGq4B89wjCkTQSHSXhOFu4MoB1P3x", "cFLtpSn773bVJLx0JTA8P0aSLIYoFMQr"];

  // 进度追踪 - 改为文件级别的进度跟踪
  let progressIntervals: { [filename: string]: number } = {};
  let fileProgress: { [filename: string]: {
    progress: number,
    status: string,
    elapsedTime: string,
    remainingTime: string,
    estimatedCompletionTime: string,
    processedItems: number,
    totalItems: number,
    isComplete: boolean,
    errorMessage: string
  }} = {};

  // 显示控制
  let abortConfirmModal = false;
  let previewModal = false;
  let previewData = [];
  let currentPage = 1;
  let pageSize = 10;
  let totalPages = 1;
  let totalPreviewItems = 0;
  let currentDatasetId = "";
  let showDeleteHistoryModal = false;
  let historyIdToDelete = '';


  $: selectedFile = upQAFiles.find(f => f.id === selectedFileId);
  $: selectedFilename = selectedFile ? selectedFile.filename : '';
  
  $: {
    if (parallel_num < 1) parallel_num = 1;
    if (parallel_num > 10) parallel_num = 10; // Allow up to 10 parallel processes
    // Initialize with default values from config, then fill remaining slots if needed
    const defaultAKs = ["nNgmVkQ22wuaVu4h2OimBvYM", "NDodQ4HrnTA0pV9nCf5cipaU"];
    const defaultSKs = ["AzMeGq4B89wjCkTQSHSXhOFu4MoB1P3x", "cFLtpSn773bVJLx0JTA8P0aSLIYoFMQr"];

    api_keys = Array(parallel_num).fill("").map((_, i) => defaultAKs[i] || "");
    secret_keys = Array(parallel_num).fill("").map((_, i) => defaultSKs[i] || "");
  }
  
  $: validForQualityEval = selectedFileId !== '' && api_keys.every(key => key.trim() !== '');

  async function fetchFileContent(fileId: string): Promise<any[] | null> {
    try {
      const response = await axios.post<APIResponse<any>>(
        `http://127.0.0.1:8000/quality/qa_content`,
        {
          record_id: fileId,
        }
      );

      if (response.data.status === "success" && response.data.data) {
        return response.data.data.qa_pairs || response.data.data.content || [];
      } else {
        console.error("Error fetching file content:", response.data.message);
        errorMessage = "Failed to fetch file content: " + response.data.message;
        return null;
      }
    } catch (error) {
      console.error("Error fetching file content:", error);
      errorMessage = "Failed to fetch file content, please check network or server status";
      return null;
    }
  }

  async function startQualityEval() {
    quality_eval_processing = true;
    errorMessage = null;

    const contentData = await fetchFileContent(selectedFileId);
    if (!contentData || contentData.length === 0) {
        errorMessage = "Unable to fetch or parse source file content, please check the file.";
        quality_eval_processing = false;
        return;
    }

    // 初始化文件进度跟踪
    fileProgress[selectedFilename] = {
      progress: 0,
      status: 'processing',
      elapsedTime: '0s',
      remainingTime: 'Calculating...',
      estimatedCompletionTime: 'Calculating...',
      processedItems: 0,
      totalItems: contentData.length,
      isComplete: false,
      errorMessage: ''
    };

    try {
      const response = await axios.post(`http://127.0.0.1:8000/quality/quality`, {
        content: JSON.stringify(contentData), // Convert to string for current server schema
        filename: selectedFilename,
        model_name: modelname,
        SK: secret_keys,
        AK: api_keys,
        parallel_num: parallel_num,
        similarity_rate: parseFloat(similarity_rate.toString()),
        coverage_rate: parseFloat(coverage_rate.toString()),
        max_attempts: parseInt(max_attempts.toString()),
        domain: description,
      });

      if (response.data && response.data.status === "success") {
        startProgressPolling(selectedFilename);
      } else {
        throw new Error(response.data.message || "Request failed, server returned non-success status");
      }
    } catch (error) {
      console.error("Error during quality evaluation:", error);
      errorMessage = `Quality evaluation startup failed: ${error.message || "Unknown error"}`;
      quality_eval_processing = false;
      if (fileProgress[selectedFilename]) {
        fileProgress[selectedFilename].status = 'failed';
        fileProgress[selectedFilename].errorMessage = errorMessage;
      }
    }
  }

  function startProgressPolling(filename: string) {
    if (progressIntervals[filename]) {
      clearInterval(progressIntervals[filename]);
    }

    progressIntervals[filename] = setInterval(async () => {
      try {
        const response = await axios.post(`http://127.0.0.1:8000/quality/progress`, { filename });

        if (response.data && response.data.status === "success") {
          const data = response.data.data;

          if (fileProgress[filename]) {
            fileProgress[filename] = {
              progress: data.progress,
              status: data.status,
              elapsedTime: data.formatted_elapsed_time || "-",
              remainingTime: data.formatted_remaining_time || "-",
              estimatedCompletionTime: data.formatted_completion_time || "-",
              processedItems: data.processed_items || 0,
              totalItems: data.total_items || 0,
              isComplete: data.status === 'completed',
              errorMessage: data.status === 'failed' ? (data.error_message || "Processing failed") : ''
            };

            // 强制更新UI
            fileProgress = {...fileProgress};
          }

          if (["completed", "failed", "aborted"].includes(data.status)) {
            clearInterval(progressIntervals[filename]);
            delete progressIntervals[filename];
            quality_eval_processing = false;
            await fetchQAFiles();
            await fetchQualityHistory();

            if (data.status === "aborted") {
              if (fileProgress[filename]) {
                fileProgress[filename].errorMessage = "Task was aborted by user";
              }
            }
            if (data.status === "completed") {
              successMessage = "Quality evaluation completed!";
              setTimeout(() => successMessage = null, 3000);

              // 5秒后移除进度条
              setTimeout(() => {
                delete fileProgress[filename];
                fileProgress = {...fileProgress};
              }, 5000);
            }
          }
        } else if(response.data.status !== 'not_found') {
          console.warn("Progress API returned non-success status:", response.data);
        }
      } catch (error) {
        console.error("Error fetching progress:", error);
      }
    }, 1000);
  }
  
  async function abortQualityTask() {
    try {
      const response = await axios.post(`http://127.0.0.1:8000/quality/abort_quality_task`, {
        filename: selectedFilename
      });
      if (response.data && response.data.status === "success") {
        console.log("Task aborted successfully");
        successMessage = "Task aborted successfully";
        setTimeout(() => successMessage = null, 3000);

        // 停止进度跟踪
        if (progressIntervals[selectedFilename]) {
          clearInterval(progressIntervals[selectedFilename]);
          delete progressIntervals[selectedFilename];
        }

        // 更新文件进度状态
        if (fileProgress[selectedFilename]) {
          fileProgress[selectedFilename].status = 'aborted';
          fileProgress[selectedFilename].errorMessage = 'Task was aborted by user';
          fileProgress = {...fileProgress};
        }

        quality_eval_processing = false;
      } else {
        errorMessage = response.data.message || "Failed to abort task";
      }
      abortConfirmModal = false;
    } catch (error) {
      errorMessage = error.message || "Network error occurred while aborting task";
      console.error("Error aborting task:", error);
    }
  }

  async function fetchQAFiles(): Promise<void> {
    try {
      const response = await axios.get<APIResponse<{ files: QAFile[] }>>(
        `http://127.0.0.1:8000/quality/qa_files`
      );

      if (response.data.status === "success") {
        upQAFiles = response.data.data.files || [];
      } else {
        errorMessage = t("data.uploader.fetch_fail");
      }
    } catch (error) {
      console.error("Error fetching QA files:", error);
      errorMessage = t("data.uploader.fetch_fail");
    }
  }

  async function fetchQualityHistory(): Promise<void> {
      try {
          historyLoaded = false;
          const response = await axios.get<APIResponse<{ records: QualityHistoryRecord[] }>>(
              `http://127.0.0.1:8000/quality/history`
          );
          if (response.data.status === "success") {
              qualityHistory = response.data.data.records || [];
              lastHistoryRefresh = new Date();
          } else {
              errorMessage = "Failed to load quality evaluation history: " + response.data.message;
          }
      } catch (error) {
          console.error("Error fetching quality history:", error);
          errorMessage = "Failed to load quality evaluation history, please check network or server";
      } finally {
          historyLoaded = true;
      }
  }

  async function deleteHistoryRecord() {
    if (!historyIdToDelete) return;
    try {
        const response = await axios.delete(`http://127.0.0.1:8000/quality/quality_records`, {
            data: { record_id: historyIdToDelete }
        });

        if (response.data && response.data.status === "success") {
            successMessage = "History record deleted successfully";
            setTimeout(() => successMessage = null, 3000);
            await fetchQualityHistory(); // Refresh list
        } else {
            errorMessage = response.data.message || "Failed to delete history record";
        }
    } catch (err) {
        errorMessage = "Failed to delete history record";
        console.error(err);
    } finally {
        showDeleteHistoryModal = false;
        historyIdToDelete = '';
    }
  }
  
  async function previewDataset(id: string, page: number = 1) {
    try {
      currentDatasetId = id;
      previewModal = true;
      const response = await axios.get(`http://127.0.0.1:8000/quality/preview/${id}?page=${page}&page_size=${pageSize}`);
      
      if (response.data) {
        previewData = response.data.items || [];
        totalPages = response.data.total_pages || 1;
        totalPreviewItems = response.data.total_items || 0;
        currentPage = response.data.page || 1;
      } else {
        errorMessage = "Unable to get preview data";
      }
    } catch (error) {
      errorMessage = `Failed to get preview: ${error.message || "Unknown error"}`;
    }
  }
  
  async function downloadDataset(id: string) {
    window.location.href = `http://127.0.0.1:8000/quality/download/${id}`;
  }

  function changePage(delta: number) {
    const newPage = currentPage + delta;
    if (newPage >= 1 && newPage <= totalPages) {
      previewDataset(currentDatasetId, newPage);
    }
  }

  let fetchEntriesUpdater: any;
  onMount(async () => {
    await fetchQAFiles();
    await fetchQualityHistory();
    // 只定期刷新QA文件列表，不刷新历史记录
    fetchEntriesUpdater = setInterval(() => {
        fetchQAFiles();
        // fetchQualityHistory(); // 移除频繁刷新历史记录
    }, UPDATE_VIEW_INTERVAL);
  });

  onDestroy(() => {
    clearInterval(fetchEntriesUpdater);
    // 清理所有进度跟踪间隔
    Object.values(progressIntervals).forEach(intervalId => {
      clearInterval(intervalId);
    });
  });

</script>

<ActionPageTitle returnTo="/" title="Quality Control" />

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

    <!-- Success Message Section -->
    {#if successMessage}
        <div class="p-4 bg-green-100 border-l-4 border-green-500 text-green-700 rounded shadow-md">
            <div class="flex items-center">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 mr-2" viewBox="0 0 20 20" fill="currentColor">
                    <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd" />
                </svg>
                <span><strong class="font-bold">Success!</strong> {successMessage}</span>
            </div>
        </div>
    {/if}

    <!-- Statistics Overview -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <div class="bg-white rounded-lg shadow-md p-4 flex items-center">
            <div class="p-3 rounded-full bg-blue-100 text-blue-500 mr-4">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
            </div>
            <div>
                <p class="text-gray-500 text-sm">Total QA Datasets</p>
                <p class="text-2xl font-semibold">{upQAFiles.length}</p>
            </div>
        </div>

        <div class="bg-white rounded-lg shadow-md p-4 flex items-center">
            <div class="p-3 rounded-full bg-yellow-100 text-yellow-500 mr-4">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                </svg>
            </div>
            <div>
                <p class="text-gray-500 text-sm">Quality Evaluations Run</p>
                <p class="text-2xl font-semibold">{qualityHistory.length}</p>
            </div>
        </div>

        <div class="bg-white rounded-lg shadow-md p-4 flex items-center">
            <div class="p-3 rounded-full bg-green-100 text-green-500 mr-4">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z" />
                </svg>
            </div>
            <div>
                <p class="text-gray-500 text-sm">Successful Evaluations</p>
                <p class="text-2xl font-semibold">{qualityHistory.filter(r => r.status === 'completed').length}</p>
            </div>
        </div>
    </div>

    <!-- Main Content - Left/Right Layout -->
    <div class="flex flex-col md:flex-row gap-6">
        <!-- Left Side - File List -->
        <div class="w-full md:w-1/2">
            <div class="bg-white rounded-lg shadow-md overflow-hidden">
                <div class="px-6 py-4 bg-gray-50 border-b border-gray-200">
                    <h2 class="text-lg font-semibold text-gray-700">{t("quality_eval.qa_files")}</h2>
                </div>

                <div class="flex justify-between items-center px-4 py-3 border-b border-gray-200 bg-gray-50">
                    <div>
                        <span class="text-sm text-gray-500">{upQAFiles.length} files, {selectedFileId ? 1 : 0} selected</span>
                    </div>
                </div>
                <div class="overflow-x-auto" style="max-height: 600px;">
                    <Table striped={true} hoverable={true}>
                        <TableHead class="bg-gray-50 sticky top-0 z-10">
                            <TableHeadCell class="w-10">
                                <input type="checkbox" class="rounded border-gray-300 text-blue-600 shadow-sm focus:border-blue-300 focus:ring focus:ring-blue-200 focus:ring-opacity-50" checked={selectedFileId !== ''} on:change={() => selectedFileId = selectedFileId ? '' : (upQAFiles[0]?.id || '')} />
                            </TableHeadCell>
                            <TableHeadCell>{t("quality_eval.files.filename")}</TableHeadCell>
                            <TableHeadCell>{t("quality_eval.files.create_at")}</TableHeadCell>
                            <TableHeadCell>Operations</TableHeadCell>
                        </TableHead>
                        <TableBody>
                            {#each upQAFiles as file}
                                <tr class="hover:bg-gray-50 transition-colors">
                                    <TableBodyCell>
                                        <input
                                            type="checkbox"
                                            class="rounded border-gray-300 text-blue-600 shadow-sm focus:border-blue-300 focus:ring focus:ring-blue-200 focus:ring-opacity-50"
                                            checked={selectedFileId === file.id}
                                            on:change={() => selectedFileId = selectedFileId === file.id ? '' : file.id}
                                        />
                                    </TableBodyCell>
                                    <TableBodyCell>
                                        <div class="flex items-center">
                                            <!-- File type icon -->
                                            <span class="mr-2">
                                                <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-blue-500" viewBox="0 0 20 20" fill="currentColor">
                                                    <path fill-rule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4zm2 6a1 1 0 011-1h6a1 1 0 110 2H7a1 1 0 01-1-1zm1 3a1 1 0 100 2h6a1 1 0 100-2H7z" clip-rule="evenodd" />
                                                </svg>
                                            </span>
                                            <span class="text-blue-600 hover:text-blue-800">{file.filename}</span>
                                        </div>
                                    </TableBodyCell>
                                    <TableBodyCell>{new Date(file.created_at).toLocaleString()}</TableBodyCell>
                                    <TableBodyCell>
                                        <Button size="xs" color="light" on:click={(e) => { e.stopPropagation(); previewDataset(file.id); }}>Preview</Button>
                                    </TableBodyCell>
                                </tr>

                                <!-- Inline Progress Bar Row -->
                                {#if fileProgress[file.filename] && fileProgress[file.filename].status === 'processing'}
                                    <tr class="bg-blue-50">
                                        <td colspan="4" class="px-6 py-4">
                                            <div class="w-full space-y-3">
                                                <div class="flex justify-between text-sm text-gray-600 mb-2">
                                                    <div class="font-medium">Quality Evaluation Progress</div>
                                                    <div class="text-blue-600">Processing...</div>
                                                </div>
                                                <Progressbar
                                                    progress={fileProgress[file.filename].progress}
                                                    size="h-2"
                                                    color="blue"
                                                />
                                                <div class="flex justify-between text-xs text-gray-500">
                                                    <span>{fileProgress[file.filename].progress}% Complete</span>
                                                    <span>{fileProgress[file.filename].processedItems} / {fileProgress[file.filename].totalItems} items</span>
                                                </div>
                                                <div class="grid grid-cols-2 gap-4 text-xs text-gray-600">
                                                    <div>
                                                        <span class="font-medium">Elapsed:</span> {fileProgress[file.filename].elapsedTime}
                                                    </div>
                                                    <div>
                                                        <span class="font-medium">Remaining:</span> {fileProgress[file.filename].remainingTime}
                                                    </div>
                                                </div>
                                                <div class="flex justify-between items-center">
                                                    <div class="text-xs text-gray-500 animate-pulse">
                                                        Refreshing progress every second...
                                                    </div>
                                                    <Button size="xs" color="red" on:click={() => abortConfirmModal = true}>
                                                        Abort Task
                                                    </Button>
                                                </div>
                                            </div>
                                        </td>
                                    </tr>
                                {/if}

                                <!-- Error/Completed Status Row -->
                                {#if fileProgress[file.filename] && (fileProgress[file.filename].status === 'failed' || fileProgress[file.filename].status === 'aborted' || fileProgress[file.filename].status === 'completed')}
                                    <tr class="bg-gray-50">
                                        <td colspan="4" class="px-6 py-3">
                                            <div class="flex items-center justify-between">
                                                <div class="flex items-center">
                                                    {#if fileProgress[file.filename].status === 'completed'}
                                                        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-green-500 mr-2" viewBox="0 0 20 20" fill="currentColor">
                                                            <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd" />
                                                        </svg>
                                                        <span class="text-green-700 font-medium">Quality evaluation completed successfully!</span>
                                                    {:else}
                                                        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-red-500 mr-2" viewBox="0 0 20 20" fill="currentColor">
                                                            <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
                                                        </svg>
                                                        <span class="text-red-700 font-medium">{fileProgress[file.filename].errorMessage || 'Task failed'}</span>
                                                    {/if}
                                                </div>
                                                {#if fileProgress[file.filename].status === 'completed'}
                                                    <div class="text-xs text-gray-500">
                                                        Progress will be hidden in a few seconds...
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

        <!-- Right Side - Parameter Settings -->
        <div class="w-full md:w-1/2">
            <div class="bg-white rounded-lg shadow-md overflow-hidden">
                <div class="px-6 py-4 bg-gray-50 border-b border-gray-200">
                    <h2 class="text-lg font-semibold text-gray-700">{t("quality_eval.params")}</h2>
                </div>
                <div class="p-6 space-y-4">
                    <div class="flex gap-4 mb-4">

            <div class="w-1/2">
                <label class="block text-sm font-medium text-gray-700 mb-2">{t("quality_eval.parallel_num")}</label>
                <input
                    type="number"
                    min="1"
                    max="10"
                    bind:value={parallel_num}
                    class="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
                />
                <p class="text-xs text-gray-500 mt-1">Maximum 10 parallel processes supported</p>
            </div>

            <div class="w-1/2">
                <label class="block text-sm font-medium text-gray-700 mb-2">Domain Description</label>
                <input
                    type="text"
                    placeholder="Enter domain description"
                    bind:value={description}
                    class="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
                />
                <p class="text-xs text-gray-500 mt-1">Optional domain context for quality evaluation</p>
            </div>

        </div>

                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-2">{t("quality_eval.model_name")}</label>
                        <select
                            bind:value={modelname}
                            class="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                        >
                            {#each modelOptions as option}
                                <option value={option.value}>{option.label}</option>
                            {/each}
                        </select>
                    </div>

                    <div class="border-t border-gray-200 pt-4">
                        <h3 class="text-md font-medium text-gray-700 mb-3">API Keys</h3>
                        <div class="space-y-3">
                            {#each Array(parallel_num) as _, index}
                                <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
                                    <div>
                                        <label class="block text-sm font-medium text-gray-700 mb-1">{t("quality_eval.AK")} {index + 1}</label>
                                        <input
                                            type="password"
                                            placeholder="Access Key"
                                            bind:value={api_keys[index]}
                                            class="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                                        />
                                    </div>
                                    <div>
                                        <label class="block text-sm font-medium text-gray-700 mb-1">{t("quality_eval.SK")} {index + 1}</label>
                                        <input
                                            type="password"
                                            placeholder="Secret Key"
                                            bind:value={secret_keys[index]}
                                            class="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                                        />
                                    </div>
                                </div>
                            {/each}
                        </div>
                    </div>

                    <div class="border-t border-gray-200 pt-4">
                        <h3 class="text-md font-medium text-gray-700 mb-3">Quality Parameters</h3>
                        <div class="space-y-4">
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-2">{t("quality_eval.similarity_rate")} ({similarity_rate})</label>
                                <input type="range" bind:value={similarity_rate} min={0} max={1} step={0.01} class="w-full" />
                            </div>
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-2">{t("quality_eval.coverage_rate")} ({coverage_rate})</label>
                                <input type="range" bind:value={coverage_rate} min={0} max={1} step={0.01} class="w-full" />
                            </div>
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-2">{t("quality_eval.max_attempts")}</label>
                                <input
                                    type="number"
                                    min="1"
                                    max="10"
                                    bind:value={max_attempts}
                                    class="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
                                />
                            </div>
                        </div>
                    </div>

                    <div class="flex justify-center pt-4">
                        <Button
                            type="button"
                            color="green"
                            class="px-6 py-2 flex items-center w-full"
                            disabled={!validForQualityEval || quality_eval_processing}
                            on:click={startQualityEval}
                        >
                            {#if quality_eval_processing}
                                <div class="mr-2 animate-spin h-4 w-4 border-2 border-white rounded-full border-t-transparent"></div>
                                {t("quality_eval.processing")}
                            {:else}
                                <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 mr-2" viewBox="0 0 20 20" fill="currentColor">
                                    <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-11a1 1 0 10-2 0v2H7a1 1 0 100 2h2v2a1 1 0 102 0v-2h2a1 1 0 100-2h-2V7z" clip-rule="evenodd" />
                                </svg>
                                {t("quality_eval.start")}
                            {/if}
                        </Button>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Quality Evaluation History -->
    <div class="bg-white rounded-lg shadow-md overflow-hidden mt-6">
        <div class="px-6 py-4 bg-gray-50 border-b border-gray-200 flex justify-between items-center">
            <h2 class="text-lg font-semibold text-gray-700">Quality Evaluation History</h2>
            <div class="flex items-center space-x-3">
                <div class="text-sm text-gray-500">
                    <div>{qualityHistory.length} evaluations completed</div>
                    {#if lastHistoryRefresh}
                        <div class="text-xs text-gray-400">
                            Last updated: {lastHistoryRefresh.toLocaleTimeString()}
                        </div>
                    {/if}
                </div>
                <Button size="xs" color="light" on:click={fetchQualityHistory} disabled={!historyLoaded}>
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 mr-1" viewBox="0 0 20 20" fill="currentColor">
                        <path fill-rule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" clip-rule="evenodd" />
                    </svg>
                    Refresh
                </Button>
            </div>
        </div>
        <div class="p-4">
            {#if historyLoaded}
                {#if qualityHistory.length > 0}
                    <Table striped={true} hoverable={true}>
                        <TableHead class="bg-gray-50">
                            <TableHeadCell>Input File</TableHeadCell>
                            <TableHeadCell>Status</TableHeadCell>
                            <TableHeadCell>QA Count</TableHeadCell>
                            <TableHeadCell>Created</TableHeadCell>
                            <TableHeadCell>Operations</TableHeadCell>
                        </TableHead>
                        <TableBody>
                            {#each qualityHistory as record}
                                <tr class="hover:bg-gray-50 transition-colors">
                                    <TableBodyCell>
                                        <div class="flex items-center">
                                            <span class="mr-2">
                                                <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-blue-500" viewBox="0 0 20 20" fill="currentColor">
                                                    <path fill-rule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4zm2 6a1 1 0 011-1h6a1 1 0 110 2H7a1 1 0 01-1-1zm1 3a1 1 0 100 2h6a1 1 0 100-2H7z" clip-rule="evenodd" />
                                                </svg>
                                            </span>
                                            <span class="font-medium">{record.input_file}</span>
                                        </div>
                                    </TableBodyCell>
                                    <TableBodyCell>
                                        <span class="px-2 py-1 text-xs font-semibold rounded-full"
                                              class:bg-green-100={record.status === 'completed'}
                                              class:text-green-800={record.status === 'completed'}
                                              class:bg-red-100={record.status === 'failed'}
                                              class:text-red-800={record.status === 'failed'}
                                              class:bg-yellow-100={record.status === 'aborted'}
                                              class:text-yellow-800={record.status === 'aborted'}
                                              class:bg-gray-100={record.status !== 'completed' && record.status !== 'failed' && record.status !== 'aborted'}
                                              class:text-gray-800={record.status !== 'completed' && record.status !== 'failed' && record.status !== 'aborted'}>
                                            {record.status}
                                        </span>
                                    </TableBodyCell>
                                    <TableBodyCell>
                                        <span class="font-semibold text-blue-600">{record.qa_count}</span>
                                    </TableBodyCell>
                                    <TableBodyCell>{new Date(record.created_at).toLocaleString()}</TableBodyCell>
                                    <TableBodyCell>
                                        <div class="flex items-center space-x-3">
                                            <!-- Preview button -->
                                            <button
                                                class="px-3 py-1 text-xs font-medium text-center text-white bg-blue-600 rounded-lg hover:bg-blue-700 focus:ring-4 focus:outline-none focus:ring-blue-300"
                                                on:click={() => previewDataset(record.dataset_id || record.generation_id)}
                                            >
                                                Preview
                                            </button>

                                            <!-- Download button -->
                                            <button
                                                class="px-3 py-1 text-xs font-medium text-center text-white bg-green-600 rounded-lg hover:bg-green-700 focus:ring-4 focus:outline-none focus:ring-green-300"
                                                on:click={() => downloadDataset(record.dataset_id || record.generation_id)}
                                            >
                                                Download
                                            </button>

                                            <!-- Delete button -->
                                            <button
                                                class="px-3 py-1 text-xs font-medium text-center text-white bg-red-600 rounded-lg hover:bg-red-700 focus:ring-4 focus:outline-none focus:ring-red-300"
                                                on:click={() => { historyIdToDelete = record.generation_id; showDeleteHistoryModal = true; }}
                                            >
                                                Delete
                                            </button>
                                        </div>
                                    </TableBodyCell>
                                </tr>
                            {/each}
                        </TableBody>
                    </Table>
                {:else}
                    <div class="py-6 text-center text-gray-500">
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-12 w-12 mx-auto text-gray-400 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
                        </svg>
                        <p>No quality evaluation history available. Run quality evaluations first.</p>
                    </div>
                {/if}
            {:else}
                <div class="py-6 text-center">
                    <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto"></div>
                    <p class="mt-2 text-gray-500">Loading evaluation history...</p>
                </div>
            {/if}
        </div>
    </div>
</div>

<!-- Delete History Modal -->
<Modal title="Delete History Record" bind:open={showDeleteHistoryModal} size="md" autoclose={false} class="rounded-lg">
    <h3 slot="header" class="text-xl font-bold text-gray-900">
        Delete History Record
    </h3>
    <div class="my-6 text-gray-600">
        <div class="flex items-center mb-4">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-12 w-12 text-red-500 mr-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
            </svg>
            <p>Are you sure you want to delete this history record? This action cannot be undone!</p>
        </div>
    </div>
    <div slot="footer" class="flex justify-end gap-2">
        <Button color="light" on:click={() => showDeleteHistoryModal = false}>Cancel</Button>
        <Button color="red" on:click={deleteHistoryRecord}>
            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 mr-1" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clip-rule="evenodd" />
            </svg>
            Confirm Delete
        </Button>
    </div>
</Modal>



<!-- Abort Confirmation Modal -->
<Modal
  title="Abort Quality Evaluation"
  bind:open={abortConfirmModal}
  autoclose={false}
  size="sm"
  class="rounded-lg"
>
  <h3 slot="header" class="text-xl font-bold text-gray-900">
    Abort Quality Evaluation
  </h3>

  <div class="my-6 text-gray-600">
    <div class="flex items-center mb-4">
      <svg xmlns="http://www.w3.org/2000/svg" class="h-12 w-12 text-yellow-500 mr-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
      </svg>
      <p>Are you sure you want to abort the current quality evaluation task? This action cannot be undone.</p>
    </div>
  </div>

  <svelte:fragment slot="footer">
    <div class="flex justify-end gap-2">
      <Button color="light" on:click={() => abortConfirmModal = false}>
        Cancel
      </Button>
      <Button color="red" on:click={abortQualityTask}>
        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
        Confirm Abort
      </Button>
    </div>
  </svelte:fragment>
</Modal>

<!-- Preview Modal -->
<Modal bind:open={previewModal} size="xl" autoclose={false} class="w-full max-w-5xl">
  <h3 slot="header" class="flex justify-between items-center text-xl font-semibold text-gray-900 dark:text-white">
    <span>Preview Quality Evaluation Results</span>
    <Button color="blue" size="sm" on:click={() => downloadDataset(currentDatasetId)} class="flex items-center">
      <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 mr-1" viewBox="0 0 20 20" fill="currentColor">
        <path fill-rule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm3.293-7.707a1 1 0 011.414 0L9 10.586V3a1 1 0 112 0v7.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z" clip-rule="evenodd" />
      </svg>
      Download
    </Button>
  </h3>

  <div class="space-y-4">
    {#if previewData.length > 0}
      <div class="bg-white rounded-lg overflow-hidden mb-4">
        <Table striped={true}>
          <TableHead>
            <TableHeadCell class="table-cell-border">Question</TableHeadCell>
            <TableHeadCell class="table-cell-border">Answer</TableHeadCell>
            <TableHeadCell class="table-cell-border">Quality Scores</TableHeadCell>
          </TableHead>
          <TableBody class="divide-y">
            {#each previewData as item, i}
              <tr>
                <TableBodyCell class="whitespace-normal break-words max-w-xs">
                  <div class="font-medium text-blue-700">Q{i + 1 + (currentPage - 1) * pageSize}:</div>
                  <div class="mt-1">{item.question}</div>
                  {#if item.original_question}
                    <div class="mt-2 pt-2 border-t border-gray-100">
                      <div class="text-xs text-gray-500 font-medium">Original:</div>
                      <div class="text-sm text-gray-600">{item.original_question}</div>
                    </div>
                  {/if}
                </TableBodyCell>
                <TableBodyCell class="whitespace-normal break-words max-w-xs">
                  <div class="prose prose-sm">{item.answer}</div>
                  {#if item.original_answer}
                    <div class="mt-2 pt-2 border-t border-gray-100">
                      <div class="text-xs text-gray-500 font-medium">Original:</div>
                      <div class="text-sm text-gray-600">{item.original_answer}</div>
                    </div>
                  {/if}
                </TableBodyCell>
                <TableBodyCell class="whitespace-normal break-words max-w-xs">
                  {#if item.similarity_score !== undefined || item.coverage_score !== undefined}
                    <div class="flex flex-col gap-2">
                      {#if item.similarity_score !== undefined}
                        <span class="px-2 py-1 bg-blue-100 text-blue-800 text-xs font-semibold rounded-full text-center">
                          Similarity: {(item.similarity_score * 100).toFixed(1)}%
                        </span>
                      {/if}
                      {#if item.coverage_score !== undefined}
                        <span class="px-2 py-1 bg-green-100 text-green-800 text-xs font-semibold rounded-full text-center">
                          Coverage: {(item.coverage_score * 100).toFixed(1)}%
                        </span>
                      {/if}
                    </div>
                  {:else}
                    <span class="text-gray-400 text-sm">No scores available</span>
                  {/if}
                </TableBodyCell>
              </tr>
            {/each}
          </TableBody>
        </Table>
      </div>

      {#if totalPages > 1}
        <div class="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-gray-200">
          <div class="flex items-center gap-2">
            <Button color="blue" disabled={currentPage === 1} on:click={() => changePage(-1)}>
              <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 mr-1" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M12.707 5.293a1 1 0 010 1.414L9.414 10l3.293 3.293a1 1 0 01-1.414 1.414l-4-4a1 1 0 010-1.414l4-4a1 1 0 011.414 0z" clip-rule="evenodd" />
              </svg>
              Previous
            </Button>
            <Button color="blue" disabled={currentPage === totalPages} on:click={() => changePage(1)}>
              Next
              <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 ml-1" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clip-rule="evenodd" />
              </svg>
            </Button>
          </div>

          <span class="text-gray-700 bg-gray-100 px-3 py-1 rounded-md">
            Showing {(currentPage - 1) * pageSize + 1}-{Math.min(currentPage * pageSize, totalPreviewItems)} of {totalPreviewItems} items
          </span>

          <span class="text-gray-700 bg-gray-100 px-3 py-1 rounded-md">
            Page {currentPage} / {totalPages}
          </span>
        </div>
      {/if}
    {:else}
      <div class="bg-gray-50 rounded-lg p-8 text-center">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-12 w-12 mx-auto text-gray-400 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
        </svg>
        <p class="text-gray-600">No preview data available</p>
      </div>
    {/if}
  </div>

  <svelte:fragment slot="footer">
    <Button color="light" on:click={() => previewModal = false}>Close</Button>
  </svelte:fragment>
</Modal>