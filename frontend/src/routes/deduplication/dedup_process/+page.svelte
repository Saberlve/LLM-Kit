<script lang="ts">
    import type DatasetEntry from "../../../class/DatasetEntry";
    import {
        Accordion,
        AccordionItem,
        Button,
    } from "flowbite-svelte";
    import axios from "axios";
    import { page } from "$app/stores";
    import { getContext, onDestroy, onMount } from "svelte";
    const t: any = getContext("t");
    import { UPDATE_VIEW_INTERVAL } from "../../store";
    import { goto } from "$app/navigation";
    import ActionPageTitle from "../../components/ActionPageTitle.svelte";
    import DatasetTable from "../DatasetTable.svelte";
    const poolId = $page.url.searchParams.get("pool_id");
    let availableModels: string[] = [];
    let selectedModels: string[] = [];
    let selectedFiles: FileList | null = null;
    let isDeduplicating = false;
    let progress = { "progress": 0, "time": 0 };
    let response: any = null;
    let poolEntries: Array<DatasetEntry> = [];
    let selectedPoolEntryIds: number[] = [];
    async function fetchAvailableModels() {
        try {
            const response = await axios.get('/api/available_llms');
            availableModels = response.deduplication;
        } catch (error) {
            console.error("Error fetching available models:", error);
        }
    }
    async function fetchPoolEntries() {
        try {
            poolEntries = (await axios.get(`/api/dataset_entry/by_pool/${poolId}`)).deduplication;
        } catch (error) {
            console.error("Error fetching pool entries:", error);
        }
    }
    async function qucong() {
        if (!selectedModels.length && selectedPoolEntryIds.length === 0 && (!selectedFiles || selectedFiles.length === 0)) {
            alert(t("deduplication.select_models_or_files"));
            return;
        }
        isDeduplicating = true;
        const formData = new FormData();
        if (selectedModels.length > 0) {
            formData.append('models', JSON.stringify(selectedModels));
        }
        if (selectedFiles && selectedFiles.length > 0) {
            for (let i = 0; i < selectedFiles.length; i++) {
                formData.append('files', selectedFiles[i]);
            }
        }
        if (selectedPoolEntryIds.length > 0) {
            formData.append('pool_entry_ids', JSON.stringify(selectedPoolEntryIds));
        }
        try {
            const response = await axios.post('/api/qucong', formData, {
                headers: {
                    'Content-Type': 'multipart/form-deduplication',
                },
            });
            console.log("Deduplication started:", response.deduplication);
            await fetchProgress();
        } catch (error) {
            console.error("Error during deduplication:", error);
            isDeduplicating = false;
        }
    }
    function updateProgress(current: number, total: number) {
        progress.progress = current;
        progress.time = total;
    }
    async function fetchProgress() {
        try {
            const progressResponse = await axios.get('/api/qucong/progress');
            response = progressResponse.deduplication;
            console.log('Deduplication Progress:', response);
            updateProgress(response.progress || 0, response.time || 0);
            if (response.progress === 100) {
                isDeduplicating = false;
                clearInterval(progressInterval);
            }
        } catch (error) {
            console.error('Error fetching deduplication progress:', error);
            // Optionally handle error, but might be okay to just log it
        }
    }
    let progressInterval: any;
    onMount(async () => {
        await fetchAvailableModels();
        await fetchPoolEntries();
    });
    $: validForDeduplicate = (selectedModels.length > 0 || selectedPoolEntryIds.length > 0 || (selectedFiles !== null && selectedFiles.length > 0));
    onMount(() => {
        progressInterval = setInterval(
            fetchProgress,
            UPDATE_VIEW_INTERVAL
        );
    });
    onDestroy(() => {
        clearInterval(progressInterval);
    });
</script>
<ActionPageTitle returnTo={"/deduplication"} title={t("deduplication.title")} />
{#if !isDeduplicating}
    <div class="m-2 p-2">
        <span>{t("deduplication.select_data_pool")}</span>
        <DatasetTable
                datasetEntries={poolEntries}
                noOperation={true}
                selectable={true}
                bind:selectedDatasetIds={selectedPoolEntryIds}
                on:modified={fetchPoolEntries}
        />
    </div>
    <div class="m-2 p-2">
        <span>{t("deduplication.dedup_process.upload_files")}</span>
        <input
                type="file"
                multiple
                class="block w-full text-sm text-gray-900 border border-gray-300 rounded-lg cursor-pointer bg-gray-50 dark:text-gray-400 focus:outline-none dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400"
                bind:files={selectedFiles}
        />
    </div>
    <div class="m-2 p-2">
        <span>{t("deduplication.dedup_process.select_models")}</span>
        <div class="flex flex-wrap gap-2 mt-2">
            {#each availableModels as model}
                <label class="inline-flex items-center">
                    <input
                            type="checkbox"
                            class="form-checkbox h-5 w-5 text-blue-600"
                            value={model}
                            bind:group={selectedModels}
                    />
                    <span class="ml-2">{model}</span>
                </label>
            {/each}
        </div>
    </div>
    <div class="flex flex-row justify-end gap-2 mt-4 m-2 p-2">
        <Button
                color="primary"
                on:click={qucong}
                disabled={!validForDeduplicate}
        >
            {t("deduplication.dedup_process.start")}
        </Button>
    </div>
{:else}
    <div class="m-2 p-2">
        <div>{t("deduplication.dedup_process.progress")}{progress.progress}%</div>
        {#if progress.time !== 0}
            <div>{t("deduplication.dedup_process.remain_time")}{progress.time}s</div>
        {:else}
            <div>{t("deduplication.dedup_process.wait")}</div>
        {/if}
    </div>
    <div class="relative pt-1 m-2 p-2">
        <div class="flex overflow-hidden bg-gray-200 rounded-lg shadow-sm dark:bg-gray-700" style="height: 23px;">
            <div
                    class="flex flex-col justify-center overflow-hidden bg-blue-600 text-xs font-medium text-white text-center rounded-lg dark:bg-blue-500"
                    style="width: {progress.progress}%"
            >
                {progress.progress}%
            </div>
        </div>
    </div>
{/if}
