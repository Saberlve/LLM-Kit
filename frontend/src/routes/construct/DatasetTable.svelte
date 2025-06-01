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
  import { goto } from "$app/navigation";
  
  // Use English column names
  const col_names = ["Name", "Operations"];

  export let datasetEntries: Array<FinetuneDatasetEntry>;
  export let noOperation = false;
  export let selectedDatasetId: number | null = null;
  export let selectable = false;
  let delete_modal = false;
  let id_to_delete: null | number = null;

  // Preview modal variables
  let previewModalOpen = false;
  let previewDatasetName = '';
  let previewContent = [];
  let previewLoading = false;
  let previewError = null;
  let previewCurrentPage = 1;
  let previewTotalPages = 1;
  let previewItemsPerPage = 10;

  import { createEventDispatcher } from "svelte";
  import VisbilityButton from "../components/VisbilityButton.svelte";

  const dispatch = createEventDispatcher();

  async function delete_handle() {
    if (id_to_delete == null) {
      throw "Attempting to delete without an id";
    }
    
    try {
      console.log(`Deleting dataset ID: ${id_to_delete}`);
      const response = await axios.delete(`http://127.0.0.1:8000/api/dataset/${id_to_delete}`);
      console.log("Dataset deleted successfully:", response.data);
      dispatch("modified");
      delete_modal = false;
    } catch (err) {
      console.error(`Failed to delete dataset ID ${id_to_delete}:`, err);
      alert(`Delete failed: ${err.message || "Unknown error"}`);
    }
  }

  // Preview dataset with modal
  async function previewDataset(dataset) {
    previewModalOpen = true;
    previewDatasetName = dataset.name;
    previewLoading = true;
    previewError = null;
    previewCurrentPage = 1;
    
    try {
      // Check if it's a QA dataset
      if (dataset.is_qa) {
        const response = await axios.get(`http://127.0.0.1:8000/qa/preview/${dataset.id}?page=${previewCurrentPage}&page_size=${previewItemsPerPage}`);
        if (response.status === 200) {
          previewContent = response.data.items || [];
          previewTotalPages = response.data.total_pages || 1;
        } else {
          previewError = "Failed to load preview data";
        }
      } else {
        // Regular dataset
        const response = await axios.get(`http://127.0.0.1:8000/api/dataset/preview/${dataset.id}?page=${previewCurrentPage}&page_size=${previewItemsPerPage}`);
        if (response.status === 200) {
          previewContent = response.data.items || [];
          previewTotalPages = response.data.total_pages || 1;
        } else {
          previewError = "Failed to load preview data";
        }
      }
    } catch (error) {
      console.error("Error loading preview data:", error);
      previewError = "Error loading preview data: " + (error.message || "Unknown error");
    } finally {
      previewLoading = false;
    }
  }

  // Pagination functionality
  async function goToPage(page) {
    if (page >= 1 && page <= previewTotalPages) {
      previewCurrentPage = page;
      previewLoading = true;
      previewError = null;
      
      try {
        const dataset = datasetEntries.find(d => d.name === previewDatasetName);
        if (!dataset) {
          previewError = "Dataset not found";
          previewLoading = false;
          return;
        }
        
        if (dataset.is_qa) {
          const response = await axios.get(`http://127.0.0.1:8000/qa/preview/${dataset.id}?page=${page}&page_size=${previewItemsPerPage}`);
          if (response.status === 200) {
            previewContent = response.data.items || [];
            previewTotalPages = response.data.total_pages || 1;
          } else {
            previewError = "Failed to load preview data";
          }
        } else {
          const response = await axios.get(`http://127.0.0.1:8000/api/dataset/preview/${dataset.id}?page=${page}&page_size=${previewItemsPerPage}`);
          if (response.status === 200) {
            previewContent = response.data.items || [];
            previewTotalPages = response.data.total_pages || 1;
          } else {
            previewError = "Failed to load preview data";
          }
        }
      } catch (error) {
        console.error("Error loading preview data:", error);
        previewError = "Error loading preview data: " + (error.message || "Unknown error");
      } finally {
        previewLoading = false;
      }
    }
  }

  // Download dataset
  function downloadDataset(dataset) {
    // Check if it's a QA dataset
    if (dataset.is_qa) {
      window.open(`http://127.0.0.1:8000/qa/download/${dataset.id}`, '_blank');
    } else {
      // Regular dataset
      window.open(`http://127.0.0.1:8000/api/dataset/download/${dataset.id}`, '_blank');
    }
  }
</script>

<Modal title="Delete Dataset" bind:open={delete_modal} autoclose>
  <p class="text-base leading-relaxed text-gray-500 dark:text-gray-400">
    Are you sure you want to delete this dataset?
  </p>
  <p class="text-base leading-relaxed text-red-600 dark:text-gray-400">
    This action cannot be undone!
  </p>
  <svelte:fragment slot="footer">
    <div class="w-full flex justify-end gap-2">
      <Button color="red" on:click={() => delete_handle()}>Yes, Delete</Button>
      <Button color="alternative">Cancel</Button>
    </div>
  </svelte:fragment>
</Modal>

<!-- Preview Modal -->
<Modal bind:open={previewModalOpen} size="xl" title={`Preview: ${previewDatasetName}`}>
  <div class="space-y-4">
    {#if previewError}
      <div class="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
        {previewError}
      </div>
    {/if}

    {#if previewLoading}
      <div class="flex justify-center items-center py-8">
        <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
        <span class="ml-3 text-gray-700">Loading preview...</span>
      </div>
    {:else if previewContent && previewContent.length > 0}
      <div class="bg-white rounded-lg overflow-hidden mb-4">
        <Table striped={true}>
          <TableHead>
            <TableHeadCell>Question</TableHeadCell>
            <TableHeadCell>Answer</TableHeadCell>
          </TableHead>
          <TableBody>
            {#each previewContent as item}
              <tr>
                <TableBodyCell class="whitespace-normal break-words max-w-xs">
                  <div class="font-medium text-blue-700">{item.question}</div>
                </TableBodyCell>
                <TableBodyCell class="whitespace-normal break-words max-w-xs">
                  <div class="prose prose-sm">{item.answer}</div>
                </TableBodyCell>
              </tr>
            {/each}
          </TableBody>
        </Table>
      </div>

      <!-- Pagination Controls -->
      {#if previewTotalPages > 1}
        <div class="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-gray-200">
          <div class="flex items-center gap-2">
            <Button color="blue" size="sm" disabled={previewCurrentPage === 1} on:click={() => goToPage(previewCurrentPage - 1)}>
              <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 mr-1" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M12.707 5.293a1 1 0 010 1.414L9.414 10l3.293 3.293a1 1 0 01-1.414 1.414l-4-4a1 1 0 010-1.414l4-4a1 1 0 011.414 0z" clip-rule="evenodd" />
              </svg>
              Previous
            </Button>
            <Button color="blue" size="sm" disabled={previewCurrentPage === previewTotalPages} on:click={() => goToPage(previewCurrentPage + 1)}>
              Next
              <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 ml-1" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clip-rule="evenodd" />
              </svg>
            </Button>
          </div>
          
          <span class="text-gray-700 bg-gray-100 px-3 py-1 rounded-md">
            Page {previewCurrentPage} of {previewTotalPages}
          </span>
        </div>
      {/if}
    {:else}
      <div class="bg-gray-50 rounded-lg p-8 text-center">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-12 w-12 mx-auto text-gray-400 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
        </svg>
        <p class="text-gray-600">No content available</p>
      </div>
    {/if}
  </div>

  <svelte:fragment slot="footer">
    <Button color="light" on:click={() => previewModalOpen = false}>Close</Button>
  </svelte:fragment>
</Modal>

<div class="overflow-x-auto">
  <table class="w-full text-sm text-left text-gray-500">
    <thead class="text-xs text-gray-700 uppercase bg-gray-50">
      {#each col_names as name}
        <th scope="col" class="px-6 py-3">{name}</th>
      {/each}
    </thead>
    <tbody>
      {#each datasetEntries as row}
        <tr class="bg-white border-b hover:bg-gray-50">
          <td class="px-6 py-4 font-medium text-gray-900">{row.name}</td>
          <td class="px-6 py-4">
            <div class="flex items-center space-x-3">
              <!-- Preview button -->
              <button
                class="px-3 py-1 text-xs font-medium text-center text-white bg-blue-600 rounded-lg hover:bg-blue-700 focus:ring-4 focus:outline-none focus:ring-blue-300"
                on:click|stopPropagation={() => previewDataset(row)}
              >
                Preview
              </button>
              
              <!-- Download button -->
              <button
                class="px-3 py-1 text-xs font-medium text-center text-white bg-green-600 rounded-lg hover:bg-green-700 focus:ring-4 focus:outline-none focus:ring-green-300"
                on:click|stopPropagation={() => downloadDataset(row)}
              >
                Download
              </button>
              
              <!-- Delete button -->
              <button
                class="px-3 py-1 text-xs font-medium text-center text-white bg-red-600 rounded-lg hover:bg-red-700 focus:ring-4 focus:outline-none focus:ring-red-300"
                on:click|stopPropagation={() => {
                  id_to_delete = row.id;
                  delete_modal = true;
                }}
              >
                Delete
              </button>
            </div>
          </td>
        </tr>
      {/each}
    </tbody>
  </table>
</div>

{#if datasetEntries.length == 0}
  <div class="w-full text-center py-4">
    <span>No datasets available</span>
  </div>
{/if}