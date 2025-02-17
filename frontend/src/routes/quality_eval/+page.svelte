<script lang="ts">
    import type EvalEntry from "../../class/EvalEntry";
    import ActionPageTitle from "../components/ActionPageTitle.svelte";
    import axios from "axios";
    import { PlusOutline } from "flowbite-svelte-icons";
    import { getContext } from "svelte";
    const t: any = getContext("t");
    let eval_entries: Array<EvalEntry> = [];
    onMount(async () => {
      eval_entries = (await axios.get("/api/eval")).data;
    });
    import type PoolEntry from "../../class/PoolEntry";
    import type DatasetEntry from "../../class/DatasetEntry";
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
    import { page } from "$app/stores";
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

    import { UPDATE_VIEW_INTERVAL } from "../store";
    import DatasetTable from "./DatasetTable.svelte";
    import { onDestroy, onMount } from "svelte";

    let selectedDatasetId: number | null = null;
    let name = `quality_control-${Date.now().toString().substring(5, 10)}`;
    let description = `quality_control-${Date.now().toString().substring(5, 10)}`;
    let quality_eval_processing: boolean | null = false;
    let minAnswerLength: number | null = null;
    let quality_controling: boolean = false;
    let loading = false;
    let errorMessage: string | null = null;
    let uploadedFiles: UnifiedFile[] = [];
    let parallel_num: number | null = 1;
    let similarity_rate: number = 0.8;
    let coverage_rate: number = 0.8;
    let max_attempts: number = 1;
    let progress_response;
    let progress = { "progress": 1, "time": 0 };
    let modelOptions = [
      { value: 'Qwen' , label: 'Qwen'  },
      { value: 'erine', label: 'erine' },
      { value: 'flash', label: 'flash' },
      { value: 'lite' , label: 'lite'  }
    ];
    let modelname: String = 'Qwen';
    let api_keys = []; // 用于存储API-KEY的列表
    let secret_keys = []; // 用于存储SECRET KEY的列表
    let parsingProgressIntervals: { [fileId: string]: any } = {};

    const uploaded_file_heads = [
    t("data.uploader.filename"),
    t("data.uploader.file_type"),
    t("data.uploader.size"),
    t("data.uploader.created_at"),
    t("data.uploader.upload_status"),
    ]

    // 当parallel_num改变时，更新api_keys和secret_keys的长度
    $: {
        api_keys = Array(parallel_num).fill(null);
        secret_keys = Array(parallel_num).fill(null);
    }
    $: validFordeduplication = selectedDatasetId !== null;
    
    function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
    } 


    async function quality_eval() {
      quality_eval_processing = true;
      try {
        const response = await axios.post(`http://127.0.0.1:8000/quality`, {
          content: selectedDatasetId,
          filename: name,
          save_path: 'result/',
          SK: secret_keys,
          AK: api_keys,
          parallel_num: parallel_num,
          model_name: modelname,
          similarity_rate: similarity_rate,
          coverage_rate: coverage_rate,
          max_attempts: 5,
          domain: description,
        });

        if (!response.data) {
          console.error("Quality Control failed, no data received")
        }
      } catch (error) {
        console.error("Error during quality control:", error);
      } finally {
        await sleep(500);
        quality_eval_processing = false;
      }
    }

    function updateProgress(current, total) {
      progress.progress = current;
      progress.time = total;
    }

    async function fetchProgress() {
      try {
        progress_response = (await axios.get('/api/quality/progress')).data;
        console.log('Progress:', progress_response);
        updateProgress(progress_response.progress, progress_response.time);
      } catch (error) {
        console.error('Error fetching progress:', error);
      }
    }

    onMount(async () => {
      await fetchProgress();
    })

    let progressInterval: any;
    onMount(async() => {
      progressInterval = setInterval(
              fetchProgress,
              UPDATE_VIEW_INTERVAL
      );
    });
    onDestroy(async() => {
      clearInterval(progressInterval);
    });

  async function checkParseHistory(filename: string): Promise<number> {
    try {
      const response = await axios.post(
              "http://127.0.0.1:8000/parse/phistory",
              { filename },
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

</script>

<ActionPageTitle
  title={t("quality_eval.title")}
  subtitle={t("quality_eval.subtitle")}
>
</ActionPageTitle>

{#if !quality_eval_processing}
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
          <span slot="header">{t("quality_eval.params")}</span>
          <div class="justify-end items-center text-black">
            <div class="m-2 p-2">
              <span>{t("quality_eval.parallel_num")}</span>
              <input
                  type="number"
                  id="parallel_num"
                  aria-describedby="helper-text-explanation"
                  class="bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white dark:focus:ring-blue-500 dark:focus:border-blue-500"
                  style="width: 100px;"
                  bind:value={parallel_num}
                  min="1"
              />
            </div>
            
            {#each api_keys as api_key, index}
                <div class="m-2 p-2">
                    <span>{t("quality_eval.AK") + " " + (index + 1)}</span>
                    <input
                        type="text"
                        id="API KEY"
                        aria-describedby="helper-text-explanation"
                        class="bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white dark:focus:ring-blue-500 dark:focus:border-blue-500"
                        style="width: 300px;"
                        bind:value={api_keys[index]}
                    />
                </div>
            {/each}
            
            {#each secret_keys as secret_key, index}
                <div class="m-2 p-2">
                    <span>{t("quality_eval.SK") + " " + (index + 1)}</span>
                    <input
                        id="SCERET KEY"
                        type="text"
                        aria-describedby="helper-text-explanation"
                        class="bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white dark:focus:ring-blue-500 dark:focus:border-blue-500"
                        style="width: 300px;"
                        bind:value={secret_keys[index]}
                        placeholder={t("quality_eval.optional")}
                    />
                </div>
            {/each}
            <div class="m-2 p-2">
              <span>{t("quality_eval.model_name")}</span>
              <select
                  id="model-name-select"
                  class={`bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white dark:focus:ring-blue-500 dark:focus:border-blue-500`}
                  bind:value={modelname}
              >
                  {#each modelOptions as option}
                      <option value={option.value}>{option.label}</option>
                  {/each}
              </select>
            </div>
            <div class="m-2 p-2">
              <span>{t("quality_eval.name")}</span>
              <input
                  type="text"
                  aria-describedby="helper-text-explanation"
                  class={`bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white dark:focus:ring-blue-500 dark:focus:border-blue-500`}
                  bind:value={name}
              />
            </div>
            
            <div class="m-2 p-2">
              <span>{t("quality_eval.des")}</span>
              <input
                  type="text"
                  aria-describedby="helper-text-explanation"
                  class={`bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white dark:focus:ring-blue-500 dark:focus:border-blue-500`}
                  bind:value={description}
              />                 
            </div>

            <div class="w-full flex flex-row">
              <div class="m-2 p-2">
                <span>{t("quality_eval.similarity_rate")}</span>                
              </div>
              <div class="w-7/12 flex-row">
                  <div class="relative w-full mx-2">
                      <input
                          type="range"
                          bind:value={similarity_rate}
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
                    bind:value={similarity_rate}
                    min={0}
                    max={1}
                    step={0.001}
                  />
              </div>
            </div>

            <div class="w-full flex flex-row">
              <div class="m-2 p-2">
                <span>{t("quality_eval.coverage_rate")}</span>                
              </div>
              <div class="w-7/12 flex-row">
                  <div class="relative w-full mx-2">
                      <input
                          type="range"
                          bind:value={coverage_rate}
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
                    bind:value={coverage_rate}
                    min={0}
                    max={1}
                    step={0.001}
                  />
              </div>
            </div>

            <div class="m-2 p-2">
              <span>{t("quality_eval.max_attempts")}</span>
              <input
                  type="number"
                  id="max_attempts_number"
                  aria-describedby="helper-text-explanation"
                  class="bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white dark:focus:ring-blue-500 dark:focus:border-blue-500"
                  style="width: 100px;"
                  bind:value={max_attempts}
                  min="1"
                  max="10"
              />
            </div>
          </div>
        </AccordionItem>
      </Accordion>
    </div>
  </div>

  <div class="flex flex-row justify-end gap-2 mt-4">
    <Button
            on:click={quality_eval}
            disabled={!validFordeduplication}
    >
      {t("quality_eval.start")}
    </Button>
  </div>
</div>
{:else}
  <div>
    <div>{t("deduplication.progress")}{progress_response.progress}%</div>
    {#if progress_response.time !== 0}
      <div>{t("deduplication.remain_time")}{progress_response.time}s</div>
    {:else}
      <div>{t("deduplication.wait")}{progress_response.time}s</div>
    {/if}
  </div>
  <div class="relative pt-1">
    <div class="flex overflow-hidden bg-black rounded-lg shadow-sm" style="height: 23px;">
      <div
              class="flex-grow bg-white rounded-lg"
              style="width: {100 - progress_response.progress}%"
      >
        <div
                class="flex-grow bg-blue-700 rounded-lg"
                style="width: {progress_response.progress}%"
        >
          {#if progress_response.progress !== 100}
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
{/if}