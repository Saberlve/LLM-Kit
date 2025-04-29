<script lang="ts">
  import {
    Modal,
    Button,
    Table,
    TableBody,
    TableBodyCell,
    TableBodyRow,
    TableHead,
    TableHeadCell,
  } from "flowbite-svelte";
  import type FinetuneDatasetEntry from "../../class/DatasetEntry";
  import axios from "axios";
  import { getContext } from "svelte";
  const t: any = getContext("t");
  const col_names = ["id", t("data.table.col_name"), t("data.table.col_time"), t("data.table.col_size"), t("data.table.col_format"), t("data.table.col_des")];

  export let datasetEntries: Array<FinetuneDatasetEntry>;
  export let noOperation = false;
  export let selectedDatasetId: number | null = null;
  export let selectable = false;
  let delete_modal = false;
  let id_to_delete: null | number = null;
  
  import VisbilityButton from "../components/VisbilityButton.svelte";
</script>

<table class="table-auto w-full divide-y divide-gray-200">
  <thead class="bg-gray-50">
    {#each col_names as name}
      <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">{name}</th>
    {/each}
  </thead>
  <tbody class="bg-white divide-y divide-gray-200">
    {#each datasetEntries as row}
      <tr class={`
        ${selectable ? "cursor-pointer" : ""} ${selectedDatasetId == row.id ? "text-white bg-blue-500 border-blue-600" : ""}
      `} on:click={(_) => {
        if (!selectable) return;
        if(selectedDatasetId == row.id) {
          selectedDatasetId = null;
        } else {
          selectedDatasetId = row.id;
        }
      }}>
        <td class="px-6 py-4 whitespace-nowrap">{row.id}</td>
        <td class="px-6 py-4 whitespace-nowrap">{row.name}</td>
        <td class="px-6 py-4 whitespace-nowrap">{row.created_on}</td>
        <td class="px-6 py-4 whitespace-nowrap">{row.size}</td>
        <td class="px-6 py-4 whitespace-nowrap">{row.type}</td>
        <td class="px-6 py-4 whitespace-nowrap">{row.description}</td>
        {#if !noOperation}
        <td class="px-6 py-4 whitespace-nowrap">
          <button
            class="text-blue-500 hover:underline hover:text-blue-700"
            on:click={(_) => {
              id_to_delete = row.id;
              delete_modal = true;
            }}>{t("data.delete.data")}</button
          >
          <VisbilityButton
            id={row.id.toString()}
            asset="dataset"
            interactStyle="link"
          />
        </td>
        {/if}
      </tr>
    {/each}
  </tbody>
</table>

{#if datasetEntries.length == 0}
  <div class="w-full text-center">
    <span>{t("data.no_dataset")}</span>
  </div>
{/if}