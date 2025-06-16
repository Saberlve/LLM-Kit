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

  let description = `quality_control-${Date.now().toString().substring(5, 10)}`;
  let quality_eval_processing: boolean = false;
  let errorMessage: string | null = null;
  let successMessage: string | null = null;
  let upQAFiles: QAFile[] = [];
  let qualityHistory: QualityHistoryRecord[] = [];
  let historyLoaded = false;
  
  let parallel_num: number = 1;
  let similarity_rate: number = 0.8;
  let coverage_rate: number = 0.8;
  let max_attempts: number = 1;
  let modelOptions = [
    { value: 'Qwen' , label: 'Qwen'  },
    { value: 'erine', label: 'erine' },
    { value: 'flash', label: 'flash' },
    { value: 'lite' , label: 'lite'  }
  ];
  let selectedFileId: string = '';
  
  let modelname: String = 'Qwen';
  let api_keys = [""];
  let secret_keys = [""];

  // 进度追踪
  let progress = 0;
  let progressStatus = "idle"; // idle, processing, completed, failed, aborted
  let progressIntervalId: number | null = null;
  let elapsedTime = "0s";
  let estimatedRemainingTime = "0s";
  let estimatedCompletionTime = "";
  let processedItems = 0;
  let totalItems = 0;
  let errorMsg = "";
  
  // 显示控制
  let showProgressModal = false;
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
    api_keys = Array(parallel_num).fill("");
    secret_keys = Array(parallel_num).fill("");
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
        errorMessage = "获取文件内容失败: " + response.data.message;
        return null;
      }
    } catch (error) {
      console.error("Error fetching file content:", error);
      errorMessage = "获取文件内容失败，请检查网络或服务器状态";
      return null;
    }
  }

  async function startQualityEval() {
    quality_eval_processing = true;
    showProgressModal = true;
    errorMessage = null;
    progress = 0;
    progressStatus = "processing";
    processedItems = 0;
    
    const contentData = await fetchFileContent(selectedFileId);
    if (!contentData || contentData.length === 0) {
        errorMessage = "无法获取或解析源文件内容，请检查文件。";
        quality_eval_processing = false;
        progressStatus = "failed";
        errorMsg = errorMessage;
        return;
    }
    totalItems = contentData.length;
    
    try {
      const response = await axios.post(`http://127.0.0.1:8000/quality/quality`, {
        content: contentData,
        filename: selectedFilename,
        model_name: modelname,
        save_path: "/result",
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
        throw new Error(response.data.message || "请求失败，服务器返回非成功状态");
      }
    } catch (error) {
      console.error("Error during quality evaluation:", error);
      errorMessage = `质量评估启动失败: ${error.message || "未知错误"}`;
      quality_eval_processing = false;
      progressStatus = "failed";
      errorMsg = errorMessage;
    }
  }

  function startProgressPolling(filename: string) {
    if (progressIntervalId !== null) clearInterval(progressIntervalId);
    
    progressIntervalId = setInterval(async () => {
      try {
        const response = await axios.post(`http://127.0.0.1:8000/quality/progress`, { filename });
        
        if (response.data && response.data.status === "success") {
          const data = response.data.data;
          progress = data.progress;
          progressStatus = data.status;
          elapsedTime = data.formatted_elapsed_time || "-";
          estimatedRemainingTime = data.formatted_remaining_time || "-";
          estimatedCompletionTime = data.formatted_completion_time || "-";
          processedItems = data.processed_items || 0;
          totalItems = data.total_items || 0;
          
          if (["completed", "failed", "aborted"].includes(data.status)) {
            clearInterval(progressIntervalId);
            progressIntervalId = null;
            quality_eval_processing = false;
            await fetchQAFiles();
            await fetchQualityHistory();
            
            if (data.status === "failed") errorMsg = data.error_message || "处理失败";
            if (data.status === "aborted") errorMsg = "任务已被用户中止";
            if (data.status === "completed") {
                successMessage = "质量评估完成！";
                setTimeout(() => successMessage = null, 3000);
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
        successMessage = "任务已成功中止";
        setTimeout(() => successMessage = null, 3000);
      } else {
        errorMessage = response.data.message || "中止任务失败";
      }
      abortConfirmModal = false;
    } catch (error) {
      errorMessage = error.message || "中止任务时发生网络错误";
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
          } else {
              errorMessage = "加载优化历史失败: " + response.data.message;
          }
      } catch (error) {
          console.error("Error fetching quality history:", error);
          errorMessage = "加载优化历史失败，请检查网络或服务器";
      } finally {
          historyLoaded = true;
      }
  }

  async function deleteHistoryRecord() {
    if (!historyIdToDelete) return;
    try {
        await axios.post(`http://127.0.0.1:8000/quality/quality_records/delete`, { 
            record_id: historyIdToDelete 
        });
        successMessage = "历史记录删除成功";
        setTimeout(() => successMessage = null, 3000);
        await fetchQualityHistory(); // Refresh list
    } catch (err) {
        errorMessage = "删除历史记录失败";
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
        errorMessage = "无法获取预览数据";
      }
    } catch (error) {
      errorMessage = `获取预览失败: ${error.message || "未知错误"}`;
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
    fetchEntriesUpdater = setInterval(() => {
        fetchQAFiles();
        fetchQualityHistory();
    }, UPDATE_VIEW_INTERVAL);
  });

  onDestroy(() => {
    clearInterval(fetchEntriesUpdater);
    if (progressIntervalId !== null) clearInterval(progressIntervalId);
  });

</script>

<ActionPageTitle
  title={t("quality_eval.title")}
  subtitle={t("quality_eval.subtitle")}
/>

<div class="w-full flex flex-col space-y-6 p-4">
    {#if errorMessage}
        <Alert color="red" on:dismiss={() => errorMessage = null}>
            <span class="font-medium">错误!</span> {errorMessage}
        </Alert>
    {/if}
    {#if successMessage}
        <Alert color="green" on:dismiss={() => successMessage = null}>
            <span class="font-medium">成功!</span> {successMessage}
        </Alert>
    {/if}

    <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <div class="bg-white rounded-lg shadow-md p-4 flex items-center">
            <div class="p-3 rounded-full bg-blue-100 text-blue-500 mr-4">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
            </div>
            <div>
                <p class="text-gray-500 text-sm">总QA数据集</p>
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
                <p class="text-gray-500 text-sm">已运行优化</p>
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
                <p class="text-gray-500 text-sm">成功优化</p>
                <p class="text-2xl font-semibold">{qualityHistory.filter(r => r.status === 'completed').length}</p>
            </div>
        </div>
    </div>


    <div class="flex flex-col md:flex-row gap-6">
        <div class="w-full md:w-1/2">
            <div class="bg-white rounded-lg shadow-md overflow-hidden">
                <div class="px-6 py-4 bg-gray-50 border-b border-gray-200">
                    <h2 class="text-lg font-semibold text-gray-700">{t("quality_eval.qa_files")}</h2>
                </div>
                <div class="overflow-x-auto" style="max-height: 600px;">
                    <Table hoverable={true}>
                        <TableHead>
                            <TableHeadCell class="p-4">{t("quality_eval.files.select")}</TableHeadCell>
                            <TableHeadCell>{t("quality_eval.files.filename")}</TableHeadCell>
                            <TableHeadCell>{t("quality_eval.files.create_at")}</TableHeadCell>
                            <TableHeadCell>操作</TableHeadCell>
                        </TableHead>
                        <TableBody>
                            {#each upQAFiles as file}
                                <TableBodyRow class="cursor-pointer" on:click={() => selectedFileId = file.id}>
                                    <TableBodyCell class="p-4">
                                        <Checkbox checked={selectedFileId === file.id} />
                                    </TableBodyCell>
                                    <TableBodyCell>{file.filename}</TableBodyCell>
                                    <TableBodyCell>{new Date(file.created_at).toLocaleString()}</TableBodyCell>
                                     <TableBodyCell>
                                        <Button size="xs" color="light" on:click={(e) => { e.stopPropagation(); previewDataset(file.id); }}>预览</Button>
                                    </TableBodyCell>
                                </TableBodyRow>
                            {/each}
                        </TableBody>
                    </Table>
                </div>
            </div>
        </div>

        <div class="w-full md:w-1/2">
            <div class="bg-white rounded-lg shadow-md overflow-hidden">
                <div class="px-6 py-4 bg-gray-50 border-b border-gray-200">
                    <h2 class="text-lg font-semibold text-gray-700">{t("quality_eval.params")}</h2>
                </div>
                <div class="p-6 space-y-4">
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-2">{t("quality_eval.parallel_num")}</label>
                        <Input type="number" bind:value={parallel_num} min="1" />
                    </div>
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-2">{t("quality_eval.model_name")}</label>
                        <select bind:value={modelname} class="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500">
                            {#each modelOptions as option}
                                <option value={option.value}>{option.label}</option>
                            {/each}
                        </select>
                    </div>
                    {#each Array(parallel_num) as _, index}
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-2">{t("quality_eval.AK")} {index + 1}</label>
                            <Input type="text" placeholder="Access Key" bind:value={api_keys[index]} />
                        </div>
                         <div>
                            <label class="block text-sm font-medium text-gray-700 mb-2">{t("quality_eval.SK")} {index + 1}</label>
                            <Input type="password" placeholder="Secret Key" bind:value={secret_keys[index]} />
                        </div>
                    {/each}
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-2">{t("quality_eval.domain")}</label>
                        <Input type="text" bind:value={description} />
                    </div>
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
                        <Input type="number" bind:value={max_attempts} min="1" max="10" />
                    </div>
                    <div class="flex justify-center pt-4">
                         <Button on:click={startQualityEval} disabled={!validForQualityEval || quality_eval_processing} color="green" class="w-full">
                            {#if quality_eval_processing}
                                <Spinner class="mr-2" /> {t("quality_eval.processing")}
                            {:else}
                                {t("quality_eval.start")}
                            {/if}
                        </Button>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <div class="bg-white rounded-lg shadow-md overflow-hidden mt-6">
        <div class="px-6 py-4 bg-gray-50 border-b border-gray-200">
            <h2 class="text-lg font-semibold text-gray-700">优化历史</h2>
        </div>
        <div class="p-4">
            {#if historyLoaded}
                {#if qualityHistory.length > 0}
                    <Table>
                        <TableHead>
                            <TableHeadCell>输入文件</TableHeadCell>
                            <TableHeadCell>状态</TableHeadCell>
                            <TableHeadCell>QA数量</TableHeadCell>
                            <TableHeadCell>创建时间</TableHeadCell>
                            <TableHeadCell>操作</TableHeadCell>
                        </TableHead>
                        <TableBody>
                            {#each qualityHistory as record}
                                <TableBodyRow>
                                    <TableBodyCell>{record.input_file}</TableBodyCell>
                                    <TableBodyCell>
                                        <span class:text-green-500={record.status === 'completed'}
                                              class:text-red-500={record.status === 'failed'}
                                              class:text-yellow-500={record.status === 'aborted'}>
                                            {record.status}
                                        </span>
                                    </TableBodyCell>
                                    <TableBodyCell>{record.qa_count}</TableBodyCell>
                                    <TableBodyCell>{new Date(record.created_at).toLocaleString()}</TableBodyCell>
                                    <TableBodyCell>
                                        <div class="flex space-x-2">
                                            <Button size="xs" color="light" on:click={() => previewDataset(record.dataset_id || record.generation_id)}>预览</Button>
                                            <Button size="xs" color="light" on:click={() => downloadDataset(record.dataset_id || record.generation_id)}>下载</Button>
                                            <Button size="xs" color="red" on:click={() => { historyIdToDelete = record.generation_id; showDeleteHistoryModal = true; }}>删除</Button>
                                        </div>
                                    </TableBodyCell>
                                </TableBodyRow>
                            {/each}
                        </TableBody>
                    </Table>
                {:else}
                    <p class="text-center text-gray-500 py-6">没有优化历史记录。</p>
                {/if}
            {:else}
                <div class="flex justify-center py-6"><Spinner /></div>
            {/if}
        </div>
    </div>
</div>

<!-- Modals -->
<Modal title="删除历史记录" bind:open={showDeleteHistoryModal} size="md" autoclose>
    <p class="text-center">您确定要删除这条历史记录吗？此操作无法撤销。</p>
    <svelte:fragment slot="footer">
        <Button color="red" on:click={deleteHistoryRecord}>确认删除</Button>
        <Button color="alternative" on:click={() => showDeleteHistoryModal = false}>取消</Button>
    </svelte:fragment>
</Modal>

<!-- 进度模态框 -->
<Modal
  title={t("quality_eval.progress_title")}
  bind:open={showProgressModal}
  autoclose={false}
  size="lg"
>
  <div class="space-y-6">
    {#if progressStatus === 'failed' || progressStatus === 'aborted'}
      <Alert color="red">
        <span class="font-medium">{t("quality_eval.error")}</span>
        {errorMsg}
      </Alert>
    {/if}

    <div>
      <div class="flex justify-between mb-1">
        <span class="text-base font-medium text-blue-700 dark:text-white">{t("quality_eval.progress")}</span>
        <span class="text-sm font-medium text-blue-700 dark:text-white">{progress}%</span>
      </div>
      <Progressbar 
        progress={progress} 
        size="h-4"
        color={
          progressStatus === 'failed' || progressStatus === 'aborted'
            ? 'red'
            : progressStatus === 'completed'
            ? 'green'
            : 'blue'
        }
      />
    </div>

    <div class="grid grid-cols-2 gap-4 mt-4">
      <div>
        <span class="block text-sm font-medium text-gray-700">
          {t("quality_eval.status")}:
        </span>
        <span class="block font-semibold">
          {progressStatus === 'processing' ? t("quality_eval.processing_status") :
           progressStatus === 'completed' ? t("quality_eval.completed_status") :
           progressStatus === 'failed' ? t("quality_eval.failed_status") :
           progressStatus === 'aborted' ? t("quality_eval.aborted_status") :
           t("quality_eval.idle_status")}
        </span>
      </div>
      
      <div>
        <span class="block text-sm font-medium text-gray-700">
          {t("quality_eval.progress_items")}:
        </span>
        <span class="block font-semibold">
          {processedItems} / {totalItems}
        </span>
      </div>
      
      <div>
        <span class="block text-sm font-medium text-gray-700">
          {t("quality_eval.elapsed_time")}:
        </span>
        <span class="block font-semibold">
          {elapsedTime}
        </span>
      </div>
      
      <div>
        <span class="block text-sm font-medium text-gray-700">
          {t("quality_eval.remaining_time")}:
        </span>
        <span class="block font-semibold">
          {progressStatus === 'completed' ? '0s' : estimatedRemainingTime}
        </span>
      </div>
    </div>
  </div>

  <svelte:fragment slot="footer">
    <div class="flex justify-between w-full">
      {#if progressStatus === 'processing'}
        <Button color="red" on:click={() => abortConfirmModal = true}>
          {t("quality_eval.abort")}
        </Button>
      {:else}
        <div></div> <!-- 空元素保持布局 -->
      {/if}
      
      <Button color="alternative" on:click={() => showProgressModal = false}>
        {t("quality_eval.close")}
      </Button>
    </div>
  </svelte:fragment>
</Modal>

<!-- 中止确认对话框 -->
<Modal
  title={t("quality_eval.abort_confirm_title")}
  bind:open={abortConfirmModal}
  autoclose={false}
  size="sm"
>
  <p class="text-base leading-relaxed text-gray-600 dark:text-gray-400">
    {t("quality_eval.abort_confirm_message")}
  </p>
  
  <svelte:fragment slot="footer">
    <Button color="red" on:click={abortQualityTask}>
      {t("quality_eval.confirm_abort")}
    </Button>
    <Button color="alternative" on:click={() => abortConfirmModal = false}>
      {t("quality_eval.cancel")}
    </Button>
  </svelte:fragment>
</Modal>

<!-- 预览模态框 -->
<Modal
  title={t("quality_eval.preview_title")}
  bind:open={previewModal}
  size="xl"
>
  <div class="overflow-y-auto max-h-96">
    {#if previewData.length > 0}
      <div class="space-y-6">
        {#each previewData as item, i}
          <div class="border border-gray-200 rounded-lg p-4">
            <h3 class="font-bold text-lg text-blue-700">Q{i + 1 + (currentPage - 1) * pageSize}:</h3>
            <p class="mb-4">{item.question}</p>
            <h3 class="font-bold text-lg text-green-700">A:</h3>
            <p class="whitespace-pre-wrap">{item.answer}</p>
            
            {#if item.original_question || item.original_answer}
              <div class="mt-4 pt-4 border-t border-gray-200">
                <h4 class="font-bold text-gray-700">{t("quality_eval.original_qa")}:</h4>
                {#if item.original_question}
                  <p class="text-sm mb-2"><span class="font-medium">Q:</span> {item.original_question}</p>
                {/if}
                {#if item.original_answer}
                  <p class="text-sm"><span class="font-medium">A:</span> {item.original_answer}</p>
                {/if}
              </div>
            {/if}
            
            {#if item.similarity_score !== undefined || item.coverage_score !== undefined}
              <div class="mt-4 flex flex-wrap gap-2">
                {#if item.similarity_score !== undefined}
                  <span class="px-2 py-1 bg-blue-100 text-blue-800 text-xs font-semibold rounded-full">
                    {t("quality_eval.similarity")}: {(item.similarity_score * 100).toFixed(1)}%
                  </span>
                {/if}
                {#if item.coverage_score !== undefined}
                  <span class="px-2 py-1 bg-green-100 text-green-800 text-xs font-semibold rounded-full">
                    {t("quality_eval.coverage")}: {(item.coverage_score * 100).toFixed(1)}%
                  </span>
                {/if}
              </div>
            {/if}
          </div>
        {/each}
      </div>
    {:else}
      <p class="text-center text-gray-500">
        {t("quality_eval.no_preview_data")}
      </p>
    {/if}
  </div>
  
  {#if totalPages > 1}
    <div class="flex justify-between items-center mt-4">
      <div>
        {t("quality_eval.showing")} {(currentPage - 1) * pageSize + 1}-{Math.min(currentPage * pageSize, totalPreviewItems)} {t("quality_eval.of")} {totalPreviewItems} {t("quality_eval.items")}
      </div>
      <div class="flex space-x-2">
        <Button size="sm" disabled={currentPage === 1} on:click={() => changePage(-1)}>
          {t("quality_eval.prev")}
        </Button>
        <Button size="sm" disabled={currentPage === totalPages} on:click={() => changePage(1)}>
          {t("quality_eval.next")}
        </Button>
      </div>
    </div>
  {/if}

  <svelte:fragment slot="footer">
    <Button on:click={() => downloadDataset(currentDatasetId)}>
      <ArrowDownToBracketOutline class="mr-2 h-5 w-5" />
      {t("quality_eval.download")}
    </Button>
    <Button color="alternative" on:click={() => previewModal = false}>
      {t("quality_eval.close")}
    </Button>
  </svelte:fragment>
</Modal>