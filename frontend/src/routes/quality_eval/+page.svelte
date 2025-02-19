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
    import { page } from "$app/stores";
    import type {
      UnifiedFile
    } from '../../class/Filetypes';

    import { UPDATE_VIEW_INTERVAL } from "../store";
    import { onDestroy, onMount } from "svelte";

    interface APIResponse<T = Record<string, unknown>> {
      status: string;
      message: string;
      data?: T | null;
    }

    let description = `quality_control-${Date.now().toString().substring(5, 10)}`;
    let quality_eval_processing: boolean | null = false;
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
    let selectedFileId: number;
    let selectedFilename: string = ''; // 用于存储选中的文件名
    let contentData: Array<Record<string, any>> = []; // 存储从API获取的内容

    let modelname: String = 'Qwen';
    let api_keys = []; // 用于存储API-KEY的列表
    let secret_keys = []; // 用于存储SECRET KEY的列表
    let parsingProgressIntervals: { [fileId: string]: any } = {};

    const uploaded_file_heads = [
    t("quality_eval.files.record_id"),
    t("quality_eval.files.filename"),
    t("quality_eval.files.create_at"),
    ]

    // 当parallel_num改变时，更新api_keys和secret_keys的长度
    $: {
        api_keys = Array(parallel_num).fill(null);
        secret_keys = Array(parallel_num).fill(null);
    }
    
    // 移除selectedDatasetId相关代码，改用selectedFilename
    $: validFordeduplication = selectedFilename !== '';

    async function fetchFileContent(fileId: number): Promise<void> {
      try {
        const response = await axios.post<APIResponse<{ content: any }>>(
          `http://127.0.0.1:8000/quality/qa_content`,
          {
            record_id: fileId,
          }
        );

        if (response.data.status === "success") {
          contentData = response.data.data.content;
        } else {
          console.error("Error fetching file content:", response.data.message);
          contentData = [];
        }
      } catch (error) {
        console.error("Error fetching file content:", error);
        contentData = [];
      }
    }

    function sleep(ms) {
      return new Promise(resolve => setTimeout(resolve, ms));
    } 

    async function quality_eval() {
        quality_eval_processing = true;
        try {
            // 获取选中文件的内容
            await fetchFileContent(selectedFileId);
            
            const response = await axios.post(`http://127.0.0.1:8000/quality/quality`, {
                content: contentData,
                filename: selectedFilename,
                model_name: modelname,
                save_path: "/result",
                SK: secret_keys,
                AK: api_keys,
                parallel_num: parallel_num,
                similarity_rate: similarity_rate,
                coverage_rate: coverage_rate,
                max_attempts: max_attempts,
                domain: description, // 确保description对应domain字段
            });

            if (!response.data) {
                console.error("Quality Control failed, no data received");
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
        progress_response = (await axios.get('http://127.0.0.1:8000/quality/progress')).data;
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

  async function fetchUploadedFiles(): Promise<void> {
    try {
      const response = await axios.get<APIResponse<{ files: Array<{ id: string; filename: string; create_at: string }> }>>(
        `http://127.0.0.1:8000/quality/qa_files`
      );

      if (response.data.status === "success") {
        const files = response.data.data.files.map((file: { id: string; filename: string; create_at: string }) => ({
          id: file.id,
          filename: file.filename,
          create_at: file.create_at,
        }));

        uploadedFiles = files;
      } else {
        console.error("Error fetching uploaded files:", response.data.message);
        errorMessage = t("data.uploader.fetch_fail");
      }
    } catch (error) {
      console.error("Error fetching uploaded files:", error);
      errorMessage = t("data.uploader.fetch_fail");
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
                    <TableHeadCell>{t("quality_eval.files.record_id")}</TableHeadCell>
                    <TableHeadCell>{t("quality_eval.files.filename")}</TableHeadCell>
                    <TableHeadCell>{t("quality_eval.files.create_at")}</TableHeadCell>
                    <TableHeadCell>{t("quality_eval.files.select")}</TableHeadCell>

                  </TableHead>
                  <TableBody>
                    {#each uploadedFiles as file}
                      <tr>
                        <TableBodyCell>{file.id}</TableBodyCell>
                        <TableBodyCell>{file.filename}</TableBodyCell>
                        <TableBodyCell>{file.create_at}</TableBodyCell>
                        <TableBodyCell>
                          <Checkbox
                            checked={selectedFilename === file.filename && selectedFileId === file.id}
                            on:change={(event) => {
                              const target = event.target as HTMLInputElement; 
                              if (target.checked) {
                                selectedFilename = file.filename;
                                selectedFileId = file.id; 
                              } else if (selectedFilename === file.filename && selectedFileId === file.id) {
                                selectedFilename = null;
                                selectedFileId = null;
                              }
                            }}
                          />
                        </TableBodyCell>
                      </tr>
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
          
          <!-- 修改max_attempts绑定 -->
          <div class="m-2 p-2">
              <span>{t("quality_eval.max_attempts")}</span>
              <input
                  type="number"
                  id="max_attempts_number"
                  class="bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white dark:focus:ring-blue-500 dark:focus:border-blue-500"
                  style="width: 100px;"
                  bind:value={max_attempts}
                  min="1"
                  max="10"
              />
          </div>

          <div class="m-2 p-2">
              <span>{t("quality_eval.domain")}</span>
              <input
                  type="text"
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