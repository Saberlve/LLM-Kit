<script lang="ts">
    import { onMount } from 'svelte';
    import axios from 'axios';
    import { page } from '$app/stores';
    import ActionPageTitle from '../../components/ActionPageTitle.svelte';
    import { Button } from 'flowbite-svelte';
    import { getContext } from "svelte";
    import { Table, TableHead, TableHeadCell, TableBody, TableBodyCell } from 'flowbite-svelte'; // Import Table components

    const t: any = getContext("t");
    let filename: string = '';
    let qaContent = [];
    let errorMessage = null;
    let currentPage = 1;
    const itemsPerPage = 3;
    let totalPages = 1;

    onMount(async () => {
        filename = $page.url.searchParams.get('filename') || '';
        if (filename) {
            await fetchQaContent();
        }
    });

    const fetchQaContent = async () => {
        try {
            const response = await axios.get(`http://127.0.0.1:8000/qa/get_qa_content?filename=${filename}`);
            if (response.status === 200) {
                qaContent = response.data;
                console.log("Fetched QA Content:", qaContent); // Debug: Log fetched data
                totalPages = Math.ceil(qaContent.length / itemsPerPage);
                if (totalPages === 0) totalPages = 1; // Ensure at least one page if no content
            } else {
                errorMessage = t("data.construct.preview_qa_fetch_failed") + (response.data?.detail ? `: ${response.data.detail}` : '');
            }
        } catch (error) {
            errorMessage = t("data.construct.preview_qa_network_error");
            console.error("Error fetching QA content:", error);
        }
    };

    $: displayedContent = qaContent.slice((currentPage - 1) * itemsPerPage, currentPage * itemsPerPage);

    const goToPage = (pageNumber: number) => {
        if (pageNumber >= 1 && pageNumber <= totalPages) {
            currentPage = pageNumber;
        }
    };

    const goToPreviousPage = () => goToPage(currentPage - 1);
    const goToNextPage = () => goToPage(currentPage + 1);
    const handlePageInput = (event: Event) => {
        const pageNumber = parseInt((event.target as HTMLInputElement).value, 10);
        goToPage(pageNumber);
    };
</script>

<ActionPageTitle returnTo="/construct" title={t("data.construct.qa_preview_title")} />

<div class="container mx-auto p-4">
    {#if errorMessage}
        <div class="m-4 p-4 bg-red-100 border border-red-400 text-red-700 rounded">
            {errorMessage}
        </div>
    {/if}

    {#if !errorMessage && qaContent.length > 0}
        <h2 class="text-2xl font-bold mb-4">{t("data.construct.qa_preview_for_file")} {filename}</h2>

        <div class="overflow-x-auto">
            <Table striped={false}>  <!-- striped=false to remove zebra striping if you don't want it -->
                <TableHead>
                    <TableHeadCell class="table-cell-border">{t("data.construct.question")}</TableHeadCell>
                    <TableHeadCell class="table-cell-border">{t("data.construct.answer")}</TableHeadCell>
                    <TableHeadCell class="table-cell-border">{t("data.construct.text_context")}</TableHeadCell>
                </TableHead>
                <TableBody>
                    {#each displayedContent as qaItem}
                        <tr>
                            <TableBodyCell class="multiline-cell table-cell-border">{qaItem.question}</TableBodyCell>
                            <TableBodyCell class="multiline-cell table-cell-border">{qaItem.answer}</TableBodyCell>
                            <TableBodyCell class="multiline-cell table-cell-border">{qaItem.text}</TableBodyCell>
                        </tr>
                    {/each}
                </TableBody>
            </Table>
        </div>

        <div class="flex justify-center items-center space-x-4 mt-4">
            <Button on:click={goToPreviousPage} disabled={currentPage === 1}>  <!-- Removed color="gray" -->
                {t("data.construct.previous_page")}
            </Button>
            <span>
                {t("data.construct.page")} {currentPage} / {totalPages}
            </span>
            <Button on:click={goToNextPage} disabled={currentPage === totalPages}>  <!-- Removed color="gray" -->
                {t("data.construct.next_page")}
            </Button>
            <div class="flex items-center">
                <label for="pageInput" class="mr-2">{t("data.construct.go_to_page")}</label>
                <input
                    type="number"
                    id="pageInput"
                    min="1"
                    max={totalPages}
                    value={currentPage}
                    class="w-16 border rounded px-2 py-1 text-center"
                    on:change={handlePageInput}
                />
            </div>
        </div>
    {:else if !errorMessage && qaContent.length === 0}
        <p>{t("data.construct.no_qa_content_available")}</p>
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