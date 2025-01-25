<script lang="ts">
  import type DatasetEntry from "../../class/DatasetEntry";
  import {
    Accordion,
    AccordionItem,
    Button,
  } from "flowbite-svelte";
  import axios from "axios";
  import { page } from "$app/stores";
  import { getContext } from "svelte";
  const t: any = getContext("t");

  import { UPDATE_VIEW_INTERVAL } from "../store";
  import { goto } from "$app/navigation";
  import DatasetTable from "../../DatasetTable.svelte";
  import { onDestroy, onMount } from "svelte";
  import ActionPageTitle from "../components/ActionPageTitle.svelte";

  const poolId = $page.url.searchParams.get("pool_id");
  let entries: Array<DatasetEntry> = [];
  async function fetch_dataset_entries() {
    entries = (await axios.get(`/api/dataset_entry/by_pool/${poolId}?operation=${2}`)).data;
  }
  onMount(async () => {
    await fetch_dataset_entries();
  })

  let selectedDatasetId: number | null = null;
  let name = `Constructed-${Date.now().toString().substring(5, 10)}`;
  let description = `Constructed-${Date.now().toString().substring(5, 10)}`;
  let constructing: boolean = false;
  let apiurl: String | null = null;
  let apikey: String | null = null;
  let modelname: String | null = null;
  let prompt: String | null = null;
  $: validForConstruct = selectedDatasetId !== null && apiurl != null && apikey != null && modelname != null;

  function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  async function construct() {
    constructing = true;
    await axios.post(`/api/construct/`, {}, {
      params: {
        pool_id: poolId,
        name: name,
        description: description,
        source_entry_id: selectedDatasetId,
        api_key: apikey,
        api_url: apiurl,
        model_name: modelname,
        Prompt: prompt,
      }
    })
    await sleep(500);
    constructing = false;
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
      response = (await axios.get('/api/construct/progress')).data;
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

<ActionPageTitle returnTo={"/data"} title={t("data.construct.title")}/>

{#if !constructing}
  <div class="m-2 p-2">
    <span>{t("data.construct.p1")}</span>
    <DatasetTable datasetEntries={entries} noOperation={true} on:modified={async (_) => {
            await fetch_dataset_entries();
        }} selectable={true} bind:selectedDatasetId={selectedDatasetId}/>
  </div>

  <div>
    <div class="m-2">
      <Accordion>
        <AccordionItem open={true}>
          <span slot="header">{t("data.construct.zone")}</span>
          <div class="justify-end items-center text-black">
            <div class="m-2 p-2">
              <span>{t("data.construct.AU")}</span>
              <input
                      type="text"
                      id="API URL"
                      aria-describedby="helper-text-explanation"
                      class={`bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white dark:focus:ring-blue-500 dark:focus:border-blue-500 border-width-2`}
                      style="width: 300px;"
                      bind:value={apiurl}
              />
            </div>
            <div class="m-2 p-2">
              <span>{t("data.construct.AK")}</span>
              <input
                      id="API KEY"
                      type="text"
                      aria-describedby="helper-text-explanation"
                      class="bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white dark:focus:ring-blue-500 dark:focus:border-blue-500"
                      style="width: 300px;"
                      bind:value={apikey}
              />
            </div>
            <div class="m-2 p-2">
              <span>{t("data.construct.prompt")}</span>
              <input
                      type="text"
                      id="prompt"
                      aria-describedby="helper-text-explanation"
                      class="bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white dark:focus:ring-blue-500 dark:focus:border-blue-500"
                      bind:value={prompt}
                      placeholder={t("data.construct.optional")}
              />
            </div>
            <div class="m-2 p-2">
              <span>{t("data.construct.model_name")}</span>
              <input
                      id="Token Length"
                      type="text"
                      aria-describedby="helper-text-explanation"
                      class={`bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white dark:focus:ring-blue-500 dark:focus:border-blue-500`}
                      bind:value={modelname}
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
            on:click={construct}
            disabled={!validForConstruct}
    >
      {t("data.construct.begin")}
    </Button>
  </div>
{:else}
  <div>
    <div>{t("data.construct.progress")}{response.progress}%</div>
    {#if response.time !== 0}
      <div>{t("data.construct.remain_time")}{response.time}s</div>
    {:else}
      <div>{t("data.construct.wait")}{response.time}s</div>
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
              {t("data.construct.constructing")}
            </div>
          {:else}
            <div class="flex items-center justify-center text-xs font-medium text-center text-white p-1">
              {t("data.construct.construct_finish")}
            </div>
          {/if}
        </div>
      </div>
    </div>
  </div>
{/if}