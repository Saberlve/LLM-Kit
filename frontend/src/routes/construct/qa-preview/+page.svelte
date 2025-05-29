<script lang="ts">
    import { onMount } from 'svelte';
    import axios from 'axios';
    import { page } from '$app/stores';
    import ActionPageTitle from '../../components/ActionPageTitle.svelte';
    import { Button, Table, TableHead, TableHeadCell, TableBody, TableBodyCell } from 'flowbite-svelte';
    import { getContext } from "svelte";

    const t: any = getContext("t");
    let filename: string = '';
    let qaContent = [];
    let errorMessage = null;
    let currentPage = 1;
    let totalPages = 1;
    let itemsPerPage = 10;
    let pageInput = '1';

    onMount(async () => {
        filename = $page.url.searchParams.get('filename') || '';
        if (filename) {
            await fetchQaContent();
        }
    });

    const fetchQaContent = async () => {
        try {
            const response = await axios.get(`http://127.0.0.1:8000/qa/preview/${filename}?page=${currentPage}&page_size=${itemsPerPage}`);
            if (response.status === 200) {
                qaContent = response.data.items || [];
                totalPages = response.data.total_pages || 1;
            } else {
                errorMessage = t("construct.preview_failed") + (response.data?.detail ? `: ${response.data.detail}` : '');
            }
        } catch (error) {
            console.error('Error fetching QA content:', error);
            errorMessage = t("construct.network_error");
        }
    };

    const goToPage = (page) => {
        if (page >= 1 && page <= totalPages) {
            currentPage = page;
            fetchQaContent();
        }
    };

    const handlePageInputChange = () => {
        const newPage = parseInt(pageInput);
        if (!isNaN(newPage) && newPage >= 1 && newPage <= totalPages) {
            goToPage(newPage);
        }
    };
</script>

<ActionPageTitle returnTo="/construct" title={t("construct.qa_preview")} />

<div class="container mx-auto px-4 py-6">
    {#if errorMessage}
        <div class="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4">{errorMessage}</div>
    {/if}

    <h2 class="text-2xl font-bold mb-4">{t("construct.file_preview")} {filename}</h2>

    {#if qaContent && qaContent.length > 0}
        <div class="bg-white shadow-md rounded-lg overflow-hidden mb-4">
            <Table striped={true}>
                <TableHead>
                    <TableHeadCell class="table-cell-border">{t("construct.question")}</TableHeadCell>
                    <TableHeadCell class="table-cell-border">{t("construct.answer")}</TableHeadCell>
                    <TableHeadCell class="table-cell-border">{t("construct.context")}</TableHeadCell>
                </TableHead>
                <TableBody>
                    {#each qaContent as item}
                        <tr>
                            <TableBodyCell class="whitespace-normal break-words">{item.question}</TableBodyCell>
                            <TableBodyCell class="whitespace-normal break-words">{item.answer}</TableBodyCell>
                            <TableBodyCell class="whitespace-normal break-words">{item.context}</TableBodyCell>
                        </tr>
                    {/each}
                </TableBody>
            </Table>
        </div>

        <div class="flex items-center justify-between">
            <Button color="blue" disabled={currentPage === 1} on:click={() => goToPage(currentPage - 1)}>
                {t("construct.previous")}
            </Button>
            <span class="text-gray-700">
                {t("construct.page")} {currentPage} / {totalPages}
            </span>
            <Button color="blue" disabled={currentPage === totalPages} on:click={() => goToPage(currentPage + 1)}>
                {t("construct.next")}
            </Button>
            <div class="flex items-center ml-4">
                <label for="pageInput" class="mr-2">{t("construct.go_to")}</label>
                <input
                    id="pageInput"
                    type="number"
                    class="w-16 px-2 py-1 border border-gray-300 rounded"
                    min="1"
                    max={totalPages}
                    bind:value={pageInput}
                    on:change={handlePageInputChange}
                />
            </div>
        </div>
    {:else}
        <p>{t("construct.no_content")}</p>
    {/if}
</div>

<style>
    :global(.multiline-cell) {
        word-wrap: break-word; 
        overflow-y: auto;      
        max-height: 10em;      
        /* display: block;   <-- Removed display: block; */
        white-space: pre-line; 
        max-width: 300px;     
    }
    :global(.table-cell-border) {
        border: 1px solid #ddd;
    }
</style>