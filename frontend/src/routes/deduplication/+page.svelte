<script lang="ts">
  import type DatasetEntry from "../../class/DatasetEntry";
  import axios from "axios";
  import { page } from "$app/stores";
  import { getContext } from "svelte";
  const t: any = getContext("t");

  import { UPDATE_VIEW_INTERVAL } from "../store";
  import { goto } from "$app/navigation";
  import DatasetTable from "./DatasetTable.svelte";
  import { onDestroy, onMount } from "svelte";
  import ActionPageTitle from "../components/ActionPageTitle.svelte";
  import type EvalEntry from "../../class/EvalEntry";
  import { PlusOutline } from "flowbite-svelte-icons";
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
    Input,
    Progressbar,
    Modal,
  } from "flowbite-svelte";
  import type {
    APIResponse,
    UploadResponse,
    ParseResponse,
    TaskProgressResponse,
    ParseHistoryResponse,
    UnifiedFileListResponse
  } from '../../class/APIResponse';
  import type {
    UploadedFile,
    UploadedBinaryFile,
    UnifiedFile
  } from '../../class/Filetypes';

  let entries: Array<DatasetEntry> = [];
  async function fetch_dataset_entries() {
    entries = (await axios.get("http://127.0.0.1:8000/parse/history")).data;
  }
  onMount(async () => {
    await fetch_dataset_entries();
  })
  
  let errorMessage: string | null = null;
  let uploadedFiles: UnifiedFile[] = [];
  let parsingProgressIntervals: { [fileId: string]: any } = {};
  let deduplicationing: boolean = false;
  let min_answer_length: number = 10;
  let deduplicatedEntries: Array<DatasetEntry> = [];
  let deletedPairs: Array<any> = [];
  let deduplicationg_processing: boolean = false;
  let dedup_by_answer: boolean = true;
  let dedup_threshold: number = 0.8;
  let selected_file_ids: Array<string> = [];

  let progressUrl: string = "";
  let progress: number = 0;
  let timeRemaining: number = 0;
  let progressInterval: any;

  // 从路由状态中获取进度条 URL
  $: progressUrl = page.state?.progressUrl || "";

  const uploaded_file_heads = [
    t("deduplication.select"), // 添加翻译键
    t("data.uploader.filename"),
    t("data.uploader.file_type"),
    t("data.uploader.size"),
    t("data.uploader.created_at"),
    t("data.uploader.upload_status"),
  ]

  // 修改验证条件为选中文件数量
  $: validFordeduplication = selected_file_ids.length > 0;

    // 添加复选框处理函数
  function handleCheckboxChange(fileId: string) {
    if (selected_file_ids.includes(fileId)) {
      selected_file_ids = selected_file_ids.filter(id => id !== fileId);
    } else {
      selected_file_ids = [...selected_file_ids, fileId];
    }
  }

  function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  async function deduplication() {
    deduplicationing = true;
    try {
      const response = await axios.post(`http://127.0.0.1:8000/dedup/deduplicate_qa`, {
        quality_file_ids: selected_file_ids, 
        dedup_by_answer: dedup_by_answer,
        min_answer_length: min_answer_length,
        dedup_threshold: dedup_threshold
      });
      // 检查后端返回的状态
      if (response.data.status === "success") {
            const result = response.data.data; // 获取去重结果
            deduplicatedEntries = result.deduplicatedEntries;
            deletedPairs = result.deletedPairs; 
            errorMessage = null;
        } else {
            console.error("Deduplication failed:", response.data.message);
        }
    } catch (error) {
        console.error("Error during deduplication:", error);
    } finally {
        await sleep(500);
        deduplicationing = false;
    }
  }

  async function checkParseHistory(filename: string): Promise<number> {
    try {
      const response = await axios.post(
              "http://127.0.0.1:8000/deduplicate_qa/history",
              {},
              { headers: { "Content-Type": "application/json" } }
      );

      // 检查响应数据
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
      const response = await axios.get<UnifiedFileListResponse>(
            `http://127.0.0.1:8000/parse/files/all`
      );
      if (response.data.status === "success") {

        uploadedFiles = response.data.data.map(async file => {
          let status = file.status;
          const exists = await checkParseHistory(file.filename);
          status = exists === 1 ? "parsed" : file.status; // Update status based on parse history
          return {
            ...file,
            status: status,
            parseStatus: file.parseStatus || "",
            parseProgress: file.parseProgress || 0,
            recordId: file.recordId || null
          };
        });

        uploadedFiles = await Promise.all(uploadedFiles) as UnifiedFile[];

      } else {
        console.error("Error fetching uploaded files:", response);
        errorMessage = t("data.uploader.fetch_fail");
      }
    } catch (error) {
      console.error("Error fetching uploaded files:", error);
      errorMessage = t("data.uploader.fetch_fail");
    }
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

  let fetchEntriesUpdater: any;
  onMount(async () => {
    fetchEntriesUpdater = setInterval(fetchUploadedFiles, UPDATE_VIEW_INTERVAL);
    await fetchUploadedFiles();
  });

  onDestroy(() => {
    clearInterval(fetchEntriesUpdater);
    for (const intervalId in parsingProgressIntervals) {
      clearInterval(parsingProgressIntervals[intervalId]);
    }
  });

  let response;
  async function fetchProgress() {
        try {
            const response = await axios.get(progressUrl);
            if (response.data.status === "success") {
                progress = response.data.progress;
                timeRemaining = response.data.time;
            } else {
                console.error("Error fetching progress:", response.data.message);
            }
        } catch (error) {
            console.error("Error fetching progress:", error);
        }
    }

    onMount(() => {
        fetchProgress();
        progressInterval = setInterval(fetchProgress, 10); // 每秒更新一次进度
    });

    onDestroy(() => {
        clearInterval(progressInterval);
    });

</script>


<ActionPageTitle returnTo={"/"} title={t("deduplication.title")}/>

{#if !deduplicationing}
<div class="w-full flex flex-col">
  {#if errorMessage}
  <div class="m-4 p-4 bg-red-100 border border-red-400 text-red-700 rounded">
    {errorMessage}
  </div>
  {/if}
  <div class="m-2">
    <Accordion>
        <AccordionItem open={true}>
            <span slot="header">{t("data.uploader.uploaded_files")}</span>
            <div class="overflow-x-auto" style="max-height: 600px;">
                <Table striped={true}>
                    <TableHead>
                        {#each uploaded_file_heads as head}
                            <TableHeadCell>{head}</TableHeadCell>
                        {/each}
                    </TableHead>
                    <TableBody>
                        {#each uploadedFiles as file}
                            <tr>
                               <!-- 添加复选框列 -->
                                <TableBodyCell>
                                  <Checkbox 
                                    checked={selected_file_ids.includes(file.id)}
                                    on:change={() => handleCheckboxChange(file.id)}
                                  />
                                </TableBodyCell>
                                <TableBodyCell style="overflow-x: auto; white-space: nowrap; max-width: 300px;">
                                    <div style="overflow-x: auto; white-space: nowrap;">{file.filename}</div>
                                </TableBodyCell>
                                <TableBodyCell>{file.file_type || file.mime_type}</TableBodyCell>
                                <TableBodyCell>{formatFileSize(file.size)}</TableBodyCell>
                                <TableBodyCell>{file.created_at.substring(0, 19)}</TableBodyCell>
                                <TableBodyCell>
                                    {file.status === 'parsed' ? t("data.uploader.parsed") : (file.status === 'processed' ? t("data.uploader.processed") : t("data.uploader.pending"))}
                                </TableBodyCell>
                            </tr>
                            {#if file.parseStatus}
                                <tr>
                                    <td colspan="5">
                                        <div class="flex flex-row items-center gap-2">
                                            <span>{t("data.uploader.parse_status")}: {file.parseStatus}</span>
                                            {#if file.parseStatus === 'processing'}
                                                <Progressbar progress={file.parseProgress} size="sm" />
                                            {:else if file.parseStatus === 'completed'}
                                                <span class="text-green-500">({t("data.uploader.completed")})</span>
                                            {:else if file.parseStatus === 'failed'}
                                                <span class="text-red-500">({t("data.uploader.failed")})</span>
                                            {/if}
                                        </div>
                                    </td>
                                </tr>
                            {/if}
                        {/each}
                    </TableBody>
                </Table>
            </div>
        </AccordionItem>
    </Accordion>
  </div>

  <div>
    <div class="m-2">
      <Accordion>
        <AccordionItem open={true}>
          <span slot="header">{t("deduplication.params")}</span>
          <div class="justify-end items-center text-black">
            <div class="m-2 p-2">
              <span>{t("deduplication.min_answer_length")}</span>
              <input
                  type="number"
                  id="min_answer_length"
                  aria-describedby="helper-text-explanation"
                  class="bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white dark:focus:ring-blue-500 dark:focus:border-blue-500"
                  style="width: 100px;"
                  bind:value={min_answer_length}
              />
            </div>

            <div class="m-2 p-2 flex items-center">
              <span>{t("deduplication.dedup_by_answer")}</span>
              <Checkbox
                  bind:checked={dedup_by_answer}
                  class="ml-2"  
              />
            </div>
            
            <div class="w-full flex flex-row">
              <div class="m-2 p-2">
                <span>{t("deduplication.dedup_threshold")}</span>                
              </div>
              <div class="w-7/12 flex-row">
                  <div class="relative w-full mx-2">
                      <input
                          type="range"
                          bind:value={dedup_threshold}
                          min={0}
                          max={1}
                          step={0.01}
                          class="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer dark:bg-gray-700"
                      />
                      <span
                          class="text-sm text-gray-500 dark:text-gray-400 absolute start-0 -bottom-6"
                          >0</span
                      >
                      <span
                          class="text-sm text-gray-500 dark:text-gray-400 absolute end-0 -bottom-6"
                          >1</span
                      >
                  </div>
              </div>
              <div class="mx-8">
                <input
                  type="number"
                  aria-describedby="helper-text-explanation"
                  class={`bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white dark:focus:ring-blue-500 dark:focus:border-blue-500`}
                  bind:value={dedup_threshold}
                  min={0}
                  max={1}
                  step={0.001}
                />
            </div>
          </div>

          </div>
        </AccordionItem>
      </Accordion>
    </div>
  </div>

  <div class="flex flex-row justify-end gap-2 mt-4">
    <Button
            on:click={deduplication}
            disabled={!validFordeduplication}
    >
      {t("deduplication.begin")}
    </Button>
  </div>
</div>
{:else}
  <div class="w-full flex flex-col items-center">
    <div class="m-4 text-xl">{t("deduplication.progress")}</div>
    <div class="w-full">
        <div class="relative pt-1">
            <div class="flex overflow-hidden bg-black rounded-lg shadow-sm" style="height: 23px;">
                <div class="flex-grow bg-white rounded-lg" style="width: {100 - progress}%">
                    <div class="flex-grow bg-blue-700 rounded-lg" style="width: {progress}%">
                        {#if progress !== 100}
                            <div class="flex items-center justify-center text-xs font-medium text-center text-white p-1">
                                {t("deduplication.deduplicationing")}
                            </div>
                        {:else}
                            <div class="flex items-center justify-center text-xs font-medium text-center text-white p-1">
                                {t("deduplication.deduplication_finish")}
                            </div>
                        {/if}
                    </div>
                </div>
            </div>
        </div>
    </div>
    {#if timeRemaining !== 0}
        <div class="m-2">{t("deduplication.remain_time")}{timeRemaining}s</div>
    {:else}
        <div class="m-2">{t("deduplication.wait")}</div>
    {/if}
  </div>
{/if}