<!-- frontend/src/routes/data/raw-preview/+page.svelte -->
<script lang="ts">
    import { onMount } from 'svelte';
    import axios from 'axios';
    import { page } from '$app/stores';
    import ActionPageTitle from '../../components/ActionPageTitle.svelte';
    import { Button } from 'flowbite-svelte';
    import { getContext } from "svelte";

    const t: any = getContext("t");
    let filename: string = '';
    let rawContent = '';
    let errorMessage = null;

    onMount(async () => {
        filename = $page.url.searchParams.get('filename') || '';
        if (filename) {
            await fetchRawContent();
        }
    });

    const fetchRawContent = async () => {
        try {
            const response = await axios.get(`http://127.0.0.1:8000/qa/get_raw_content?filename=${filename}`);
            if (response.status === 200) {
                rawContent = response.data;
            } else {
                errorMessage = t("data.construct.preview_raw_fetch_failed") + (response.data?.detail ? `: ${response.data.detail}` : '');
            }
        } catch (error) {
            errorMessage = t("data.construct.preview_raw_network_error");
            console.error("Error fetching raw content:", error);
        }
    };

</script>

<ActionPageTitle returnTo=" /construct" title={t("data.construct.raw_file_preview_title")} />

<div class="container mx-auto p-4">
    {#if errorMessage}
        <div class="m-4 p-4 bg-red-100 border border-red-400 text-red-700 rounded">
            {errorMessage}
        </div>
    {/if}

    {#if !errorMessage}
        <h2 class="text-2xl font-bold mb-4">{t("data.construct.raw_file_preview_for_file")} {filename}</h2>
        <pre class="whitespace-pre-wrap break-words p-4 border rounded shadow-sm" style="max-height: 70vh; overflow-y: auto;">
            {rawContent}
        </pre>
    {:else}
        <p>{t("data.construct.no_raw_content_available")}</p>
    {/if}
</div>