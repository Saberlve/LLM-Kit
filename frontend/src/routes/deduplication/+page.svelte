<script lang="ts">
  import type DatasetEntry from "../../class/DatasetEntry";
  import axios from "axios";
  import { page } from "$app/stores";
  import { getContext } from "svelte";
  const t: any = getContext("t");

  import { UPDATE_VIEW_INTERVAL } from "../store";
  import { onDestroy, onMount } from "svelte";
  import ActionPageTitle from "../components/ActionPageTitle.svelte";
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
    UnifiedFile
  } from '../../class/Filetypes';
  
  interface APIResponse<T = Record<string, unknown>> {
      status: string;
      message: string;
      data?: T | null;
  }

  let errorMessage: string | null = null;
  let upQAFiles: UnifiedFile[] = [];
  let parsingProgressIntervals: { [fileId: string]: any } = {};
  let deduplicationing: boolean = false;
  let min_answer_length: number = 10;
  let deduplicatedEntries: Array<DatasetEntry> = [];
  let deletedPairs: Array<any> = [];
  let dedup_by_answer: boolean = true;
  let dedup_threshold: number = 0.8;
  let selected_file_ids: Array<string> = [];
  let selectedFilename: string = ''; // 用于存储选中的文件名

  // 验证条件为选中文件数量
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
      const response = await axios.post(
        "http://127.0.0.1:8000/dedup/deduplicate_qa",
        {
          quality_file_ids: selected_file_ids,
          dedup_by_answer: dedup_by_answer,
          min_answer_length: min_answer_length,
          dedup_threshold: dedup_threshold,
        }
      );

      // 检查后端返回的数据
      if (response.status !== 200) {
        console.error("Network Error:", response.statusText);
        return;
      }

      const responseData = response.data;
      if (responseData.status === "success") {
        const result = responseData.data;
        const { dedup_id, input_file, output_file, deleted_pairs_file, status, source_text, original_count, kept_count, kept_pairs, deleted_pairs, create_at } = result;

        console.log("Deduplication successful:", {
          dedupId: dedup_id,
          outputFile: output_file,
          deletedPairsFile: deleted_pairs_file,
          keptPairs: kept_pairs,
          originalCount: original_count,
          keptCount: kept_count,
          deletedPairs: deleted_pairs,
        });

        // 根据需求处理结果，例如更新页面显示
        errorMessage = null;

      } else {
        console.error("Deduplication failed:", responseData.message);
        errorMessage = responseData.message;
      }
    } catch (error) {
      console.error("Error during deduplication:", error);
      errorMessage = "An error occurred while processing the request.";
    } finally {
      await sleep(500);
      deduplicationing = false;
    }
  }


  async function fetchQAFiles(): Promise<void> {
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

        upQAFiles = files;
      } else {
        console.error("Error fetching QA files:", response.data.message);
        errorMessage = t("data.uploader.fetch_fail");
      }
    } catch (error) {
      console.error("Error fetching QA files:", error);
      errorMessage = t("data.uploader.fetch_fail");
    }
  }

  let fetchEntriesUpdater: any;
  onMount(async () => {
    fetchEntriesUpdater = setInterval(fetchQAFiles, UPDATE_VIEW_INTERVAL);
    await fetchQAFiles();
  });

  onDestroy(() => {
    clearInterval(fetchEntriesUpdater);
    for (const intervalId in parsingProgressIntervals) {
      clearInterval(parsingProgressIntervals[intervalId]);
    }
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
              <span slot="header">{t("quality_eval.qa_files")}</span>
                <div class="overflow-x-auto" style="max-height: 600px;">
                  <Table striped={true}>
                    <TableHead>
                      <TableHeadCell>{t("quality_eval.files.record_id")}</TableHeadCell>
                      <TableHeadCell>{t("quality_eval.files.filename")}</TableHeadCell>
                      <TableHeadCell>{t("quality_eval.files.create_at")}</TableHeadCell>
                      <TableHeadCell>{t("quality_eval.files.select")}</TableHeadCell>
                    </TableHead>
                    <TableBody>
                      {#each upQAFiles as file}
                        <tr>
                          <TableBodyCell>{file.id}</TableBodyCell>
                          <TableBodyCell>{file.filename}</TableBodyCell>
                          <TableBodyCell>{file.create_at}</TableBodyCell>
                          <TableBodyCell>
                            <Checkbox
                              checked={selected_file_ids.includes(String(file.id))}
                              on:change={(event) => {
                                handleCheckboxChange(String(file.id));
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
{/if}