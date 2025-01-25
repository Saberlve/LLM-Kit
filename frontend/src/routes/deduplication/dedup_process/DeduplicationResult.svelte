<script lang="ts">
    import { onMount, onDestroy } from 'svelte';
    import { goto } from "$app/navigation";
    import { page } from "$app/stores";
    import axios from 'axios';
    import { getContext } from "svelte";

    const t: any = getContext("t");
    import type DatasetEntry from "../../../class/DatasetEntry";
    import ActionPageTitle from "../../components/ActionPageTitle.svelte";
    import { Button } from "flowbite-svelte";
    export let deduplicatedEntries: Array<DatasetEntry> = [];
    export let deletedPairs: Array<any> = [];

    async function handlePreview(datasetId: number) {
        goto(`/data/preview?id=${datasetId}`)
    }
    function returnToData(){
        goto(`/deduplication`);
    }

</script>
<ActionPageTitle returnTo={"/data"} title={t("deduplication.result_title")}/>

<div class="m-2 p-2">
    <h2>{t("deduplication.deduplicated_entries")}</h2>
    {#if deduplicatedEntries && deduplicatedEntries.length > 0}
        <table class="w-full text-sm text-left text-gray-500 dark:text-gray-400">
            <thead class="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-400">
            <tr>
                <th scope="col" class="px-6 py-3">
                    {t("data.table.name")}
                </th>
                <th scope="col" class="px-6 py-3">
                    {t("data.table.des")}
                </th>
                <th scope="col" class="px-6 py-3">
                    {t("data.table.operate")}
                </th>
            </tr>
            </thead>
            <tbody>
            {#each deduplicatedEntries as entry}
                <tr class="bg-white border-b dark:bg-gray-800 dark:border-gray-700">
                    <th scope="row" class="px-6 py-4 font-medium text-gray-900 whitespace-nowrap dark:text-white">
                        {entry.name}
                    </th>
                    <td class="px-6 py-4">
                        {entry.description}
                    </td>
                    <td class="px-6 py-4">
                        <Button on:click={() => handlePreview(entry.id)}>{t("data.table.preview")}</Button>
                    </td>
                </tr>
            {/each}
            </tbody>
        </table>
    {:else}
        <p>{t("deduplication.no_deduplicated_data")}</p>
    {/if}
</div>

<div class="m-2 p-2">
    <h2>{t("deduplication.deleted_pairs")}</h2>
    {#if deletedPairs && deletedPairs.length > 0}
        <table class="w-full text-sm text-left text-gray-500 dark:text-gray-400">
            <thead class="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-400">
            <tr>
                <th scope="col" class="px-6 py-3">
                    {t("deduplication.original_question")}
                </th>
                <th scope="col" class="px-6 py-3">
                    {t("deduplication.deleted_question")}
                </th>
            </tr>
            </thead>
            <tbody>
            {#each deletedPairs as pair}
                <tr class="bg-white border-b dark:bg-gray-800 dark:border-gray-700">
                    <td class="px-6 py-4">
                        {#if pair && pair[0] && pair[0].question}{pair[0].question}{/if}
                    </td>
                    <td class="px-6 py-4">
                        {#if pair && pair[1] && pair[1].question}{pair[1].question}{/if}
                    </td>
                </tr>
            {/each}
            </tbody>
        </table>
    {:else}
        <p>{t("deduplication.no_deleted_data")}</p>
    {/if}
</div>
<div class="flex flex-row justify-end gap-2 mt-4">
    <Button
            on:click={returnToData}
    >
        {t("deduplication.return")}
    </Button>
</div>