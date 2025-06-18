<script lang="ts">
  import type DatasetEntry from "../../class/DatasetEntry";
  import axios from "axios";
  import { page } from "$app/stores";
  import { getContext } from "svelte";
  const t: any = getContext("t");

  import { UPDATE_VIEW_INTERVAL } from "../store";
  import { onDestroy, onMount } from "svelte";
  import ActionPageTitle from "../components/ActionPageTitle.svelte";
  import { PlusOutline, ArrowDownToBracketOutline } from "flowbite-svelte-icons";
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
    Card,
    Badge,
    Spinner,
    Alert,
  } from "flowbite-svelte";

  interface APIResponse<T = Record<string, unknown>> {
      status: string;
      message: string;
      data?: T | null;
  }

  let errorMessage: string | null = null;
  let upQAFiles= [];
  let parsingProgressIntervals: { [fileId: string]: any } = {};
  let deduplicationing: boolean = false;
  let min_answer_length: number = 10;
  let deduplicatedEntries: Array<DatasetEntry> = [];
  let deletedPairs: Array<any> = [];
  let dedup_by_answer: boolean = true;
  let dedup_threshold: number = 0.8;
  let selected_file_ids: Array<string> = [];
  let selectedFilename: string = ''; // Used to store the selected filename
  let showResultModal: boolean = false;
  let dedupResult: any = null;
  let isDownloading: boolean = false;

  // Validation condition is the number of selected files
  $: validFordeduplication = selected_file_ids.length > 0;

  // Add checkbox handling function
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
        "/dedup/deduplicate_qa",
        {
          quality_filenames: selected_file_ids,
          dedup_by_answer: dedup_by_answer,
          min_answer_length: min_answer_length,
          dedup_threshold: dedup_threshold,
        }
      );

      // Check backend response data
      if (response.status !== 200) {
        console.error("Network Error:", response.statusText);
        return;
      }

      const responseData = response.data;
      if (responseData.status === "success") {
        const result = responseData.data;
        dedupResult = result;
        showResultModal = true;
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

  async function downloadDedupFile(fileId: string, fileName: string) {
    if (!fileId) return;
    
    isDownloading = true;
    try {
      const response = await axios.get(`/dedup/download/${fileId}`, {
        responseType: 'blob'
      });
      
      // Create a blob URL and trigger download
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `${fileName || 'dedup_result'}.json`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error("Error downloading file:", error);
      errorMessage = "Failed to download file.";
    } finally {
      isDownloading = false;
    }
  }

  async function fetchQAFiles(): Promise<void> {
    try {
      const response = await axios.get<APIResponse<{ files: Array<{ id: string; filename: string; create_at: string }> }>>(
        `/quality/qa_files`
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

  async function fetchDedupHistory() {
    try {
      const response = await axios.get('/dedup/deduplicate_qa/history');
      if (response.data.status === "success" && response.data.data.records.length > 0) {
        dedupResult = response.data.data.records[0];
      }
    } catch (error) {
      console.error("Error fetching deduplication history:", error);
    }
  }

  let fetchEntriesUpdater: any;
  onMount(async () => {
    fetchEntriesUpdater = setInterval(fetchQAFiles, UPDATE_VIEW_INTERVAL);
    await fetchQAFiles();
    await fetchDedupHistory();
  });

  onDestroy(() => {
    clearInterval(fetchEntriesUpdater);
    for (const intervalId in parsingProgressIntervals) {
      clearInterval(parsingProgressIntervals[intervalId]);
    }
  });

</script>

<ActionPageTitle returnTo={"/"} title={t("deduplication.title")}/>

{#if errorMessage}
  <Alert color="red" class="my-4">
    <span class="font-medium">{t("common.error")}!</span> {errorMessage}
  </Alert>
{/if}

{#if deduplicationing}
  <div class="flex flex-col items-center justify-center p-8">
    <Spinner size="12" class="mb-4" />
    <p class="text-lg font-medium text-gray-700">{t("deduplication.processing")}</p>
    <p class="text-sm text-gray-500 mt-2">{t("deduplication.please_wait")}</p>
  </div>
{:else}
  <div class="w-full flex flex-col gap-4">
    <Card class="mb-4">
      <h3 class="text-lg font-medium mb-4">{t("quality_eval.qa_files")}</h3>
      <div class="overflow-x-auto" style="max-height: 400px;">
        <Table striped={true} hoverable={true}>
          <TableHead>
            <TableHeadCell>{t("quality_eval.files.record_id")}</TableHeadCell>
            <TableHeadCell>{t("quality_eval.files.filename")}</TableHeadCell>
            <TableHeadCell>{t("quality_eval.files.create_at")}</TableHeadCell>
            <TableHeadCell>{t("quality_eval.files.select")}</TableHeadCell>
          </TableHead>
          <TableBody>
            {#each upQAFiles as file}
              <tr class="hover:bg-gray-50 dark:hover:bg-gray-600">
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
        {#if upQAFiles.length === 0}
          <div class="text-center py-4 text-gray-500">
            {t("deduplication.no_qa_files")}
          </div>
        {/if}
      </div>
    </Card>

    <Card>
      <h3 class="text-lg font-medium mb-4">{t("deduplication.params")}</h3>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label for="min_answer_length" class="block mb-2 text-sm font-medium text-gray-700">
            {t("deduplication.min_answer_length")}
          </label>
          <Input
            id="min_answer_length"
            type="number"
            bind:value={min_answer_length}
            min="0"
            class="w-full md:w-1/2"
          />
        </div>
        
        <div>
          <label class="flex items-center space-x-2">
            <Checkbox bind:checked={dedup_by_answer} />
            <span class="text-sm font-medium text-gray-700">{t("deduplication.dedup_by_answer")}</span>
          </label>
        </div>
      </div>
      
      <div class="mt-6">
        <label class="block mb-2 text-sm font-medium text-gray-700">
          {t("deduplication.dedup_threshold")}: {dedup_threshold.toFixed(2)}
        </label>
        <div class="flex items-center space-x-4">
          <input
            type="range"
            bind:value={dedup_threshold}
            min={0}
            max={1}
            step={0.01}
            class="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer"
          />
          <Input
            type="number"
            bind:value={dedup_threshold}
            min={0}
            max={1}
            step={0.01}
            class="w-24"
          />
        </div>
      </div>
    </Card>

    {#if dedupResult}
      <Card>
        <h3 class="text-lg font-medium mb-4">{t("deduplication.previous_results")}</h3>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <p class="text-sm font-medium text-gray-700">{t("deduplication.original_count")}: 
              <Badge color="blue">{dedupResult.original_count}</Badge>
            </p>
            <p class="text-sm font-medium text-gray-700 mt-2">{t("deduplication.kept_count")}: 
              <Badge color="green">{dedupResult.kept_count}</Badge>
            </p>
            <p class="text-sm font-medium text-gray-700 mt-2">{t("deduplication.deleted_count")}: 
              <Badge color="red">{dedupResult.original_count - dedupResult.kept_count}</Badge>
            </p>
          </div>
          <div class="flex flex-col items-end justify-center">
            <Button color="blue" class="flex items-center gap-2" on:click={() => downloadDedupFile(dedupResult.dedup_id, 'dedup_result')} disabled={isDownloading}>
              <ArrowDownToBracketOutline size="sm" />
              {isDownloading ? t("common.downloading") : t("deduplication.download_results")}
            </Button>
          </div>
        </div>
      </Card>
    {/if}

    <div class="flex justify-end mt-4">
      <Button
        color="blue"
        on:click={deduplication}
        disabled={!validFordeduplication}
      >
        {t("deduplication.begin")}
      </Button>
    </div>
  </div>
{/if}

<Modal bind:open={showResultModal} size="lg" autoclose={false} title={t("deduplication.result_title")}>
  {#if dedupResult}
    <div class="p-4">
      <div class="mb-4">
        <h3 class="text-lg font-medium">{t("deduplication.summary")}</h3>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mt-2">
          <div class="bg-gray-50 p-3 rounded">
            <p class="text-sm text-gray-500">{t("deduplication.original_count")}</p>
            <p class="text-2xl font-bold">{dedupResult.original_count}</p>
          </div>
          <div class="bg-green-50 p-3 rounded">
            <p class="text-sm text-gray-500">{t("deduplication.kept_count")}</p>
            <p class="text-2xl font-bold text-green-600">{dedupResult.kept_count}</p>
          </div>
          <div class="bg-red-50 p-3 rounded">
            <p class="text-sm text-gray-500">{t("deduplication.deleted_count")}</p>
            <p class="text-2xl font-bold text-red-600">{dedupResult.original_count - dedupResult.kept_count}</p>
          </div>
        </div>
      </div>
      
      <div class="flex justify-end mt-4 space-x-2">
        <Button color="blue" class="flex items-center gap-2" on:click={() => downloadDedupFile(dedupResult.dedup_id, 'dedup_result')} disabled={isDownloading}>
          <ArrowDownToBracketOutline size="sm" />
          {isDownloading ? t("common.downloading") : t("deduplication.download_results")}
        </Button>
        <Button color="alternative" on:click={() => showResultModal = false}>
          {t("common.close")}
        </Button>
      </div>
    </div>
  {:else}
    <div class="p-4 text-center">
      <p>{t("deduplication.no_results")}</p>
    </div>
  {/if}
</Modal>