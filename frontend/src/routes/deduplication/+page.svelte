<script lang="ts">
  import type DatasetEntry from "../../class/DatasetEntry";
  import {
    Accordion,
    AccordionItem,
    Button,
    Input,
    Checkbox
  } from "flowbite-svelte";
  import axios from "axios";
  import { page } from "$app/stores";
  import { getContext } from "svelte";
  const t: any = getContext("t");

  import { UPDATE_VIEW_INTERVAL } from "../store";
  import { goto } from "$app/navigation";
  import DatasetTable from "./DatasetTable.svelte";
  import { onDestroy, onMount } from "svelte";
  import ActionPageTitle from "../components/ActionPageTitle.svelte";

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

  <div class="m-2 p-2">
    <span>{t("deduplication.p1")}</span>
    <DatasetTable datasetEntries={entries} noOperation={true} on:modified={async (_) => {
      await fetch_dataset_entries();
    }} selectable={true} bind:selectedDatasetId={selectedDatasetId}/>
  </div>

  <div>
    <div class="m-2">
      <Accordion>
        <AccordionItem open={true}>
          <span slot="header">{t("deduplication.zone")}</span>
          <div class="justify-end items-center text-black">
            <div class="m-2 p-2 flex flex-row items-center gap-2">
              <Checkbox bind:checked={dedupByAnswer}>{t('deduplication.dedup_by_answer')}</Checkbox>
            </div>
            <div class="m-2 p-2">
              <span>{t("deduplication.min_answer_length")}</span>
              <Input
                      type="number"
                      aria-describedby="helper-text-explanation"
                      class={`bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white dark:focus:ring-blue-500 dark:focus:border-blue-500`}
                      bind:value={minAnswerLength}
              />
            </div>
            <div class="m-2 p-2">
              <span>{t("data.filter.name")}</span>
              <input
                      type="text"
                      aria-describedby="helper-text-explanation"
                      class={`bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white dark:focus:ring-blue-500 dark:focus:border-blue-500`}
                      bind:value={name}
              />
            </div>

            <div class="m-2 p-2">
              <span>{t("data.filter.des")}</span>
              <input
                      type="text"
                      aria-describedby="helper-text-explanation"
                      class={`bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white dark:focus:ring-blue-500 dark:focus:border-blue-500`}
                      bind:value={description}
              />
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