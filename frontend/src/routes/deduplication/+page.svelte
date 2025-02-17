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
    entries = (await axios.get("http://127.0.0.1:8000/parse/parse/history")).data;
  }
  onMount(async () => {
    await fetch_dataset_entries();
  })

  let selectedDatasetId: number | null = null;
  let name = `deduplicationed-${Date.now().toString().substring(5, 10)}`;
  let description = `deduplicationed-${Date.now().toString().substring(5, 10)}`;
  let deduplicationing: boolean = false;
  let dedupByAnswer: boolean = true;
  let minAnswerLength: number = 10;
  let deduplicatedEntries: Array<DatasetEntry> = [];
  let deletedPairs: Array<any> = [];

  $: validFordeduplication = selectedDatasetId !== null;

  function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  async function deduplication() {
    deduplicationing = true;
    try {
      const response = await axios.post(`http://127.0.0.1:8000/dedup/deduplicate_qa`, {
        input_file: selectedDatasetId,
        output_file: name,
        dedup_by_answer: dedupByAnswer,
        min_answer_length: minAnswerLength,
        deleted_pairs_file: `${name}-deleted.json`,
      });

      if (response.data) {
        deduplicatedEntries = response.data[0]; // Assuming the first element is deduplicated entries
        deletedPairs = response.data[1];  // Assuming the second element is deleted pairs
        goto('/deduplication/dedup_process', {
          state: {
            deduplicatedEntries: deduplicatedEntries,
            deletedPairs: deletedPairs
          }
        });

      } else {
        console.error("Deduplication failed, no data received")
      }
    } catch (error) {
      console.error("Error during deduplication:", error);
    } finally {
      await sleep(500);
      deduplicationing = false;
    }
  }

  let fetch_entries_updater: any;
  onMount(async () => {
    fetch_entries_updater = setInterval(
            fetch_dataset_entries,
            UPDATE_VIEW_INTERVAL,
    );
  });
  onDestroy(async () => {
    clearInterval(fetch_entries_updater);
  });

  let progress = { "progress": 1, "time": 0 };

  function updateProgress(current, total) {
    progress.progress = current;
    progress.time = total;
  }
  let response;
  async function fetchProgress() {
    try {
      response = (await axios.get('/api/deduplication/progress')).data;
      console.log('Progress:', response);
      updateProgress(response.progress, response.time);
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
</script>


<ActionPageTitle returnTo={"/data"} title={t("deduplication.title")}/>

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
  <div>
    <div>{t("deduplication.progress")}{response.progress}%</div>
    {#if response.time !== 0}
      <div>{t("deduplication.remain_time")}{response.time}s</div>
    {:else}
      <div>{t("deduplication.wait")}{response.time}s</div>
    {/if}
  </div>
  <div class="relative pt-1">
    <div class="flex overflow-hidden bg-black rounded-lg shadow-sm" style="height: 23px;">
      <div
              class="flex-grow bg-white rounded-lg"
              style="width: {100 - response.progress}%"
      >
        <div
                class="flex-grow bg-blue-700 rounded-lg"
                style="width: {response.progress}%"
        >
          {#if response.progress !== 100}
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