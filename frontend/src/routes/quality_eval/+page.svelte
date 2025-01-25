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
    import SimplePoolCard from "./QltEvlPoolCard.svelte";
    import type DatasetEntry from "../../class/DatasetEntry";
    import {
      Accordion,
      AccordionItem,
      Button,
    } from "flowbite-svelte";
    import { page } from "$app/stores";

    import { UPDATE_VIEW_INTERVAL } from "../store";
    import { goto } from "$app/navigation";
    import DatasetTable from "./DatasetTable.svelte";
    import { onDestroy, onMount } from "svelte";
    
    const col_names = ["ID", "名称", "创建时间", "条目数", "描述", ""];
    let pools = [] as Array<PoolEntry>;
    onMount(async () => {
      pools = (await axios.get(`/api/pool/`)).data as Array<PoolEntry>;
    });
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
    let quality_eval_processing: boolean | null = false;

    $: validFordeduplication = selectedDatasetId !== null;
    
    function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
    } 

    async function quality_eval() {
      quality_eval_processing = true;
      await axios.post(`http://127.0.0.1:8000/`, {
        name: name,
        domain: description,
        source_entry_id: selectedDatasetId,
      });
      await sleep(500);
      quality_eval_processing = false;
    }
  </script>

<ActionPageTitle
  title={t("eval.title")}
  subtitle={t("eval.subtitle")}
>
  <svelte:fragment slot="right">
    <div class="flex gap-2">
      <Button color="blue" href="/eval/tasks">
        <PlusOutline class="sm" />
        {t("eval.create_task")}
      </Button>
    </div>
  </svelte:fragment>
</ActionPageTitle>

<!-- <div class="w-full grid grid-cols-3">
  {#each pools as pool}
    <div class="m-2">
      <SimplePoolCard {pool} />
    </div>
  {/each}
</div> -->

<!-- <div class="m-2 p-2">
  <span>{t("deduplication.p1")}</span>
  <DatasetTable datasetEntries={entries} noOperation={true} on:modified={async (_) => {
          await fetch_dataset_entries();
      }} selectable={true} bind:selectedDatasetId={selectedDatasetId}/>
</div>


<div class="flex flex-row justify-end gap-2 mt-4">
  <Button
          on:click={quality_eval}
          disabled={!validFordeduplication}
  >
    {t("deduplication.begin")}
  </Button>
</div> -->