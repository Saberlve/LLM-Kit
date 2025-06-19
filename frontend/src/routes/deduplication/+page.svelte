<script lang="ts">
  import axios from "axios";
  import { getContext } from "svelte";
  const t: any = getContext("t");

  import { UPDATE_VIEW_INTERVAL } from "../store";
  import { onDestroy, onMount } from "svelte";
  import ActionPageTitle from "../components/ActionPageTitle.svelte";
  import {
    ArrowDownToBracketOutline,
    EyeOutline,
    StarOutline,
    // DocumentOutline,
    CheckCircleOutline
  } from "flowbite-svelte-icons";
  import {
    Button,
    Checkbox,
    Table,
    TableHead,
    TableHeadCell,
    TableBody,
    TableBodyCell,
    Input,
    Modal,
    Card,
    Badge,
    Spinner,
    Alert,
    Tabs,
    TabItem,
  } from "flowbite-svelte";

  // Animation states
  let isAnimating = false;
  let showSuccessAnimation = false;

  interface APIResponse<T = Record<string, unknown>> {
      status: string;
      message: string;
      data?: T | null;
  }

  interface FileSelection {
    file_id: string;
    file_type: "optimized" | "unoptimized";
    priority: number;
    filename: string;
    qa_count: number;
    created_at: string;
  }

  interface AvailableFile {
    file_id: string;
    filename: string;
    file_type: "optimized" | "unoptimized";
    created_at: string;
    qa_count: number;
  }

  let errorMessage: string | null = null;
  let optimizedFiles: AvailableFile[] = [];
  let unoptimizedFiles: AvailableFile[] = [];
  let selectedFiles: FileSelection[] = [];
  let deduplicationing: boolean = false;
  let min_answer_length: number = 10;
  let dedup_by_answer: boolean = true;
  let dedup_threshold: number = 0.8;
  let showResultModal: boolean = false;
  let showPreviewModal: boolean = false;
  let dedupResult: any = null;
  let previewData: any = null;
  let isDownloading: boolean = false;
  let currentPage: number = 1;
  let pageSize: number = 10;

  // Validation condition is the number of selected files
  $: validFordeduplication = selectedFiles.length > 0;

  // File selection functions
  function addFileToSelection(file: AvailableFile) {
    const newSelection: FileSelection = {
      file_id: file.file_id,
      file_type: file.file_type,
      priority: selectedFiles.length + 1,
      filename: file.filename,
      qa_count: file.qa_count,
      created_at: file.created_at
    };
    selectedFiles = [...selectedFiles, newSelection];
  }

  function removeFileFromSelection(fileId: string) {
    selectedFiles = selectedFiles.filter(f => f.file_id !== fileId);
    // Reorder priorities
    selectedFiles = selectedFiles.map((f, index) => ({
      ...f,
      priority: index + 1
    }));
  }

  function movePriority(fileId: string, direction: 'up' | 'down') {
    const index = selectedFiles.findIndex(f => f.file_id === fileId);
    if (index === -1) return;

    const newIndex = direction === 'up' ? index - 1 : index + 1;
    if (newIndex < 0 || newIndex >= selectedFiles.length) return;

    const newSelectedFiles = [...selectedFiles];
    [newSelectedFiles[index], newSelectedFiles[newIndex]] = [newSelectedFiles[newIndex], newSelectedFiles[index]];

    // Update priorities
    selectedFiles = newSelectedFiles.map((f, idx) => ({
      ...f,
      priority: idx + 1
    }));
  }

  function sleep(ms: number) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  async function deduplication() {
    deduplicationing = true;
    isAnimating = true;
    try {
      const response = await axios.post(
        "http://127.0.0.1:8000/dedup/deduplicate_qa",
        {
          selected_files: selectedFiles,
          dedup_by_answer: dedup_by_answer,
          min_answer_length: min_answer_length,
          dedup_threshold: dedup_threshold,
        }
      );

      // Check backend response data
      if (response.status !== 200) {
        console.error("Network Error:", response.statusText);
        return;
      }

      const responseData = response.data;
      if (responseData.status === "success") {
        const result = responseData.data;
        dedupResult = result;
        showSuccessAnimation = true;
        showResultModal = true;
        errorMessage = null;

        // Hide success animation after 3 seconds
        setTimeout(() => {
          showSuccessAnimation = false;
        }, 3000);
      } else {
        console.error("Deduplication failed:", responseData.message);
        errorMessage = responseData.message;
      }
    } catch (error) {
      console.error("Error during deduplication:", error);
      errorMessage = "An error occurred while processing the request.";
    } finally {
      await sleep(500);
      deduplicationing = false;
      isAnimating = false;
    }
  }

  async function downloadDedupFile(fileId: string, fileName: string) {
    if (!fileId) return;

    isDownloading = true;
    try {
      const response = await axios.get(`http://127.0.0.1:8000/dedup/download/${fileId}`, {
        responseType: 'blob'
      });

      // Create a blob URL and trigger download
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `${fileName || 'dedup_result'}.json`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error("Error downloading file:", error);
      errorMessage = "Failed to download file.";
    } finally {
      isDownloading = false;
    }
  }

  async function previewDedupResult(dedupId: string) {
    try {
      const response = await axios.get(`http://127.0.0.1:8000/dedup/preview/${dedupId}?page=${currentPage}&page_size=${pageSize}`);
      if (response.data.status === "success") {
        previewData = response.data.data;
        showPreviewModal = true;
      } else {
        errorMessage = response.data.message;
      }
    } catch (error) {
      console.error("Error fetching preview:", error);
      errorMessage = "Failed to fetch preview data.";
    }
  }

  async function fetchAvailableFiles(): Promise<void> {
    try {
      const response = await axios.get<APIResponse<{ optimized_files: AvailableFile[]; unoptimized_files: AvailableFile[] }>>(
        `http://127.0.0.1:8000/dedup/available_files`
      );

      if (response.data.status === "success") {
        optimizedFiles = response.data.data.optimized_files || [];
        unoptimizedFiles = response.data.data.unoptimized_files || [];
      } else {
        console.error("Error fetching available files:", response.data.message);
        errorMessage = "Failed to fetch available files";
      }
    } catch (error) {
      console.error("Error fetching available files:", error);
      errorMessage = "Failed to fetch available files";
    }
  }

  async function fetchDedupHistory() {
    try {
      const response = await axios.get('http://127.0.0.1:8000/dedup/deduplicate_qa/history');
      if (response.data.status === "success" && response.data.data.records.length > 0) {
        dedupResult = response.data.data.records[0];
      }
    } catch (error) {
      console.error("Error fetching deduplication history:", error);
    }
  }

  let fetchEntriesUpdater: any;
  onMount(async () => {
    fetchEntriesUpdater = setInterval(fetchAvailableFiles, UPDATE_VIEW_INTERVAL);
    await fetchAvailableFiles();
    await fetchDedupHistory();
  });

  onDestroy(() => {
    clearInterval(fetchEntriesUpdater);
  });

</script>

<!-- Custom CSS for animations and styling -->
<style>
  :global(body) {
    background: #f8fafc;
    min-height: 100vh;
  }

  .dedup-container {
    min-height: 100vh;
    background: #f8fafc;
    position: relative;
    overflow: hidden;
  }

  .floating-shapes {
    position: absolute;
    width: 100%;
    height: 100%;
    overflow: hidden;
    z-index: 0;
  }

  .shape {
    position: absolute;
    opacity: 0.1;
    animation: float 6s ease-in-out infinite;
  }

  .shape:nth-child(1) {
    top: 10%;
    left: 10%;
    animation-delay: 0s;
  }

  .shape:nth-child(2) {
    top: 20%;
    right: 10%;
    animation-delay: 2s;
  }

  .shape:nth-child(3) {
    bottom: 10%;
    left: 20%;
    animation-delay: 4s;
  }

  .shape:nth-child(4) {
    bottom: 20%;
    right: 20%;
    animation-delay: 1s;
  }

  @keyframes float {
    0%, 100% { transform: translateY(0px) rotate(0deg); }
    50% { transform: translateY(-20px) rotate(180deg); }
  }

  .card-hover {
    transition: all 0.3s ease;
  }

  .card-hover:hover {
    transform: translateY(-5px);
    box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
  }

  .pulse-animation {
    animation: pulse 2s infinite;
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }

  .bounce-in {
    animation: bounceIn 0.6s ease-out;
  }

  @keyframes bounceIn {
    0% { transform: scale(0.3); opacity: 0; }
    50% { transform: scale(1.05); }
    70% { transform: scale(0.9); }
    100% { transform: scale(1); opacity: 1; }
  }

  .slide-in-left {
    animation: slideInLeft 0.5s ease-out;
  }

  @keyframes slideInLeft {
    0% { transform: translateX(-100%); opacity: 0; }
    100% { transform: translateX(0); opacity: 1; }
  }

  .slide-in-right {
    animation: slideInRight 0.5s ease-out;
  }

  @keyframes slideInRight {
    0% { transform: translateX(100%); opacity: 0; }
    100% { transform: translateX(0); opacity: 1; }
  }

  .success-animation {
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    z-index: 1000;
    animation: successPop 3s ease-out;
  }

  @keyframes successPop {
    0% { transform: translate(-50%, -50%) scale(0); opacity: 0; }
    20% { transform: translate(-50%, -50%) scale(1.2); opacity: 1; }
    100% { transform: translate(-50%, -50%) scale(1); opacity: 0; }
  }

  .processing-overlay {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: rgba(0, 0, 0, 0.8);
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    z-index: 999;
  }

  .robot-icon {
    font-size: 4rem;
    animation: robotWork 2s ease-in-out infinite;
  }

  @keyframes robotWork {
    0%, 100% { transform: rotate(-5deg); }
    50% { transform: rotate(5deg); }
  }
</style>

<div class="dedup-container">
  <!-- Floating background shapes -->
  <div class="floating-shapes">
    <div class="shape">🔄</div>
    <div class="shape">📊</div>
    <div class="shape">✨</div>
    <div class="shape">🎯</div>
  </div>

  <!-- Success Animation -->
  {#if showSuccessAnimation}
    <div class="success-animation">
      <div class="text-6xl">🎉</div>
      <div class="text-white text-xl font-bold mt-2">Deduplication Complete!</div>
    </div>
  {/if}

  <!-- Processing Overlay -->
  {#if deduplicationing}
    <div class="processing-overlay">
      <div class="robot-icon">🤖</div>
      <div class="text-white text-2xl font-bold mb-4">Working Hard!</div>
      <div class="text-white text-lg mb-6">Removing duplicate QA pairs...</div>
      <Spinner size="12" class="mb-4" color="white" />
      <div class="text-white text-sm">Please wait while we process your files</div>
    </div>
  {/if}

  <div class="relative z-10 min-h-screen">
    <ActionPageTitle returnTo={"/"} title="🔄 Smart QA Deduplication"/>

    {#if errorMessage}
      <Alert color="red" class="mx-4 my-4 bounce-in">
        <span class="font-medium">❌ Error!</span> {errorMessage}
      </Alert>
    {/if}

    <div class="w-full h-full">
      <div class="grid grid-cols-1 lg:grid-cols-3 h-full">

      <!-- Left Column: File Selection -->
      <div class="lg:col-span-2 slide-in-left h-full">
        <Card class="!w-full h-full card-hover bg-white border shadow-lg !m-0 !max-w-none">
          <div class="flex items-center gap-3 mb-6">
            <div class="text-3xl">📁</div>
            <h3 class="text-2xl font-bold text-gray-800">Select QA Files for Deduplication</h3>
            <div class="text-2xl">✨</div>
          </div>

          <Tabs>
            <TabItem open title="🌟 Optimized Files">
              <div class="overflow-x-auto rounded-lg" style="max-height: 70vh;">
                {#if optimizedFiles.length === 0}
                  <div class="text-center py-16">
                    <div class="text-6xl mb-4">🤖</div>
                    <div class="text-xl text-gray-600 mb-2">No optimized files available</div>
                    <div class="text-sm text-gray-500">Upload and optimize some QA files first!</div>
                  </div>
                {:else}
                  <Table striped={true} hoverable={true} class="rounded-lg overflow-hidden">
                    <TableHead class="bg-gradient-to-r from-green-400 to-blue-500 text-white">
                      <TableHeadCell class="text-base font-bold">📄 Filename</TableHeadCell>
                      <TableHeadCell class="text-base font-bold">📊 QA Count</TableHeadCell>
                      <TableHeadCell class="text-base font-bold">📅 Created At</TableHeadCell>
                      <TableHeadCell class="text-base font-bold">⚡ Action</TableHeadCell>
                    </TableHead>
                    <TableBody>
                      {#each optimizedFiles as file, index}
                        <tr class="hover:bg-gradient-to-r hover:from-green-50 hover:to-blue-50 transition-all duration-300" style="animation-delay: {index * 0.1}s">
                          <TableBodyCell class="max-w-md truncate text-sm font-medium">
                            <div class="flex items-center gap-2">
                              <span class="text-lg">🌟</span>
                              {file.filename}
                            </div>
                          </TableBodyCell>
                          <TableBodyCell>
                            <Badge color="green" class="text-sm font-bold animate-pulse">
                              {file.qa_count} pairs
                            </Badge>
                          </TableBodyCell>
                          <TableBodyCell class="text-sm">{new Date(file.created_at).toLocaleDateString()}</TableBodyCell>
                          <TableBodyCell>
                            {#if selectedFiles.find(f => f.file_id === file.file_id)}
                              <Badge color="blue" class="text-sm bounce-in">
                                <CheckCircleOutline size="sm" class="mr-1" />
                                Selected
                              </Badge>
                            {:else}
                              <Button size="sm" color="blue" on:click={() => addFileToSelection(file)} class="hover:scale-105 transition-transform">
                                <StarOutline size="sm" class="mr-1" />
                                Add
                              </Button>
                            {/if}
                          </TableBodyCell>
                        </tr>
                      {/each}
                    </TableBody>
                  </Table>
                {/if}
              </div>
            </TabItem>

            <TabItem title="📝 Unoptimized Files">
              <div class="overflow-x-auto rounded-lg" style="max-height: 70vh;">
                {#if unoptimizedFiles.length === 0}
                  <div class="text-center py-16">
                    <div class="text-6xl mb-4">📝</div>
                    <div class="text-xl text-gray-600 mb-2">No unoptimized files available</div>
                    <div class="text-sm text-gray-500">Generate some QA pairs first!</div>
                  </div>
                {:else}
                  <Table striped={true} hoverable={true} class="rounded-lg overflow-hidden">
                    <TableHead class="bg-gradient-to-r from-yellow-400 to-orange-500 text-white">
                      <TableHeadCell class="text-base font-bold">📄 Filename</TableHeadCell>
                      <TableHeadCell class="text-base font-bold">📊 QA Count</TableHeadCell>
                      <TableHeadCell class="text-base font-bold">📅 Created At</TableHeadCell>
                      <TableHeadCell class="text-base font-bold">⚡ Action</TableHeadCell>
                    </TableHead>
                    <TableBody>
                      {#each unoptimizedFiles as file, index}
                        <tr class="hover:bg-gradient-to-r hover:from-yellow-50 hover:to-orange-50 transition-all duration-300" style="animation-delay: {index * 0.1}s">
                          <TableBodyCell class="max-w-md truncate text-sm font-medium">
                            <div class="flex items-center gap-2">
                              <span class="text-lg">📝</span>
                              {file.filename}
                            </div>
                          </TableBodyCell>
                          <TableBodyCell>
                            <Badge color="yellow" class="text-sm font-bold animate-pulse">
                              {file.qa_count} pairs
                            </Badge>
                          </TableBodyCell>
                          <TableBodyCell class="text-sm">{new Date(file.created_at).toLocaleDateString()}</TableBodyCell>
                          <TableBodyCell>
                            {#if selectedFiles.find(f => f.file_id === file.file_id)}
                              <Badge color="blue" class="text-sm bounce-in">
                                <CheckCircleOutline size="sm" class="mr-1" />
                                Selected
                              </Badge>
                            {:else}
                              <Button size="sm" color="blue" on:click={() => addFileToSelection(file)} class="hover:scale-105 transition-transform">
                                <StarOutline size="sm" class="mr-1" />
                                Add
                              </Button>
                            {/if}
                          </TableBodyCell>
                        </tr>
                      {/each}
                    </TableBody>
                  </Table>
                {/if}
              </div>
            </TabItem>
          </Tabs>
        </Card>
      </div>

      <!-- Right Column: Selected Files and Parameters -->
      <div class="lg:col-span-1 slide-in-right h-full">
        <!-- Selected Files with Priority Management -->
        {#if selectedFiles.length > 0}
          <Card class="!w-full mb-6 card-hover bg-white border shadow-lg !m-0 !max-w-none">
            <div class="flex items-center gap-2 mb-4">
              <div class="text-2xl">🎯</div>
              <h3 class="text-xl font-bold text-gray-800">Selected Files</h3>
            </div>
            <p class="text-sm text-gray-600 mb-4 flex items-center gap-2">
              <span class="text-lg">📋</span>
              Priority Order (1 = Highest)
            </p>
            <div class="space-y-3 max-h-80 overflow-y-auto">
              {#each selectedFiles as file, index}
                <div class="flex items-center justify-between p-4 bg-gradient-to-r from-blue-50 to-purple-50 rounded-lg border-2 border-blue-200 hover:border-blue-400 transition-all duration-300 bounce-in" style="animation-delay: {index * 0.1}s">
                  <div class="flex-1 min-w-0">
                    <div class="flex items-center gap-2 mb-2">
                      <Badge color="blue" class="text-sm font-bold animate-pulse">
                        #{file.priority}
                      </Badge>
                      <Badge color={file.file_type === 'optimized' ? 'green' : 'yellow'} class="text-sm">
                        {file.file_type === 'optimized' ? '🌟' : '📝'} {file.file_type}
                      </Badge>
                    </div>
                    <p class="text-sm font-medium truncate flex items-center gap-1" title={file.filename}>
                      <span class="text-lg">📄</span>
                      {file.filename}
                    </p>
                    <p class="text-xs text-gray-500 flex items-center gap-1">
                      <span>📊</span>
                      {file.qa_count} QA pairs
                    </p>
                  </div>
                  <div class="flex flex-col gap-1 ml-3">
                    <Button
                      size="xs"
                      color="light"
                      disabled={index === 0}
                      on:click={() => movePriority(file.file_id, 'up')}
                      title="Move up"
                      class="hover:scale-110 transition-transform"
                    >
                      ⬆️
                    </Button>
                    <Button
                      size="xs"
                      color="light"
                      disabled={index === selectedFiles.length - 1}
                      on:click={() => movePriority(file.file_id, 'down')}
                      title="Move down"
                      class="hover:scale-110 transition-transform"
                    >
                      ⬇️
                    </Button>
                    <Button
                      size="xs"
                      color="red"
                      on:click={() => removeFileFromSelection(file.file_id)}
                      title="Remove"
                      class="hover:scale-110 transition-transform"
                    >
                      🗑️
                    </Button>
                  </div>
                </div>
              {/each}
            </div>
          </Card>
        {:else}
          <Card class="!w-full mb-6 card-hover bg-white border shadow-lg !m-0 !max-w-none">
            <div class="text-center py-8">
              <div class="text-6xl mb-4">🎯</div>
              <div class="text-lg text-gray-600 mb-2">No files selected</div>
              <div class="text-sm text-gray-500">Choose files from the left panel to get started!</div>
            </div>
          </Card>
        {/if}

        <!-- Deduplication Parameters -->
        <Card class="!w-full mb-6 card-hover bg-white border shadow-lg !m-0 !max-w-none">
          <div class="flex items-center gap-2 mb-4">
            <div class="text-2xl">⚙️</div>
            <h3 class="text-xl font-bold text-gray-800">Parameters</h3>
          </div>
          <div class="space-y-6">
            <div>
              <label for="min_answer_length" class="block mb-2 text-base font-medium text-gray-700 flex items-center gap-2">
                <span class="text-lg">📏</span>
                Minimum Answer Length
              </label>
              <Input
                id="min_answer_length"
                type="number"
                bind:value={min_answer_length}
                min="0"
                class="w-full text-base border-2 border-blue-200 focus:border-blue-500 transition-colors"
                placeholder="10"
              />
            </div>

            <div class="bg-gradient-to-r from-purple-50 to-pink-50 p-4 rounded-lg border-2 border-purple-200">
              <label class="flex items-center space-x-3">
                <Checkbox bind:checked={dedup_by_answer} class="text-purple-600" />
                <span class="text-base font-medium text-gray-700 flex items-center gap-2">
                  <span class="text-lg">🎯</span>
                  Deduplicate by Answer
                </span>
              </label>
              <p class="text-sm text-gray-500 mt-2 ml-8">If unchecked, will deduplicate by question</p>
            </div>

            <div>
              <label for="threshold_range" class="block mb-2 text-base font-medium text-gray-700 flex items-center gap-2">
                <span class="text-lg">🎚️</span>
                Similarity Threshold: <span class="text-blue-600 font-bold">{dedup_threshold.toFixed(2)}</span>
              </label>
              <div class="relative">
                <input
                  id="threshold_range"
                  type="range"
                  bind:value={dedup_threshold}
                  min={0}
                  max={1}
                  step={0.01}
                  class="w-full h-4 bg-gradient-to-r from-green-200 to-red-200 rounded-lg appearance-none cursor-pointer slider"
                />
                <div class="flex justify-between text-xs text-gray-500 mt-2">
                  <span class="flex items-center gap-1">
                    <span>🟢</span>
                    Less strict
                  </span>
                  <span class="flex items-center gap-1">
                    More strict
                    <span>🔴</span>
                  </span>
                </div>
              </div>
            </div>
          </div>
        </Card>

        <!-- Action Button -->
        <Card class="!w-full mb-6 card-hover bg-gradient-to-r from-blue-500 to-purple-600 border-0 shadow-2xl !m-0 !max-w-none">
          <Button
            color="none"
            class="w-full text-lg py-4 text-white font-bold hover:scale-105 transition-transform bg-transparent"
            on:click={deduplication}
            disabled={!validFordeduplication}
          >
            {#if selectedFiles.length === 0}
              <span class="flex items-center justify-center gap-2">
                <span class="text-2xl">🚀</span>
                Select Files to Start
              </span>
            {:else}
              <span class="flex items-center justify-center gap-2">
                <span class="text-2xl">🚀</span>
                Start Deduplication ({selectedFiles.length} files)
                <span class="text-2xl">✨</span>
              </span>
            {/if}
          </Button>
        </Card>

        <!-- Previous Results -->
        {#if dedupResult}
          <Card class="!w-full card-hover bg-white border shadow-lg !m-0 !max-w-none">
            <div class="flex items-center gap-2 mb-4">
              <div class="text-2xl">📊</div>
              <h3 class="text-xl font-bold text-gray-800">Latest Results</h3>
              <div class="text-2xl">🎉</div>
            </div>
            <div class="space-y-4">
              <div class="grid grid-cols-3 gap-3 text-center">
                <div class="bg-gradient-to-br from-blue-400 to-blue-600 p-4 rounded-xl text-white shadow-lg hover:scale-105 transition-transform">
                  <div class="text-2xl mb-1">📝</div>
                  <div class="text-2xl font-bold">{dedupResult.original_count}</div>
                  <div class="text-xs opacity-90">Original</div>
                </div>
                <div class="bg-gradient-to-br from-green-400 to-green-600 p-4 rounded-xl text-white shadow-lg hover:scale-105 transition-transform">
                  <div class="text-2xl mb-1">✅</div>
                  <div class="text-2xl font-bold">{dedupResult.kept_count}</div>
                  <div class="text-xs opacity-90">Kept</div>
                </div>
                <div class="bg-gradient-to-br from-red-400 to-red-600 p-4 rounded-xl text-white shadow-lg hover:scale-105 transition-transform">
                  <div class="text-2xl mb-1">🗑️</div>
                  <div class="text-2xl font-bold">{dedupResult.original_count - dedupResult.kept_count}</div>
                  <div class="text-xs opacity-90">Deleted</div>
                </div>
              </div>
              <div class="flex flex-col gap-3 mt-6">
                <Button color="light" class="w-full hover:scale-105 transition-transform" on:click={() => previewDedupResult(dedupResult.dedup_id)}>
                  <EyeOutline size="sm" class="mr-2" />
                  👀 Preview Results
                </Button>
                <Button color="blue" class="w-full hover:scale-105 transition-transform" on:click={() => downloadDedupFile(dedupResult.dedup_id, 'dedup_result')} disabled={isDownloading}>
                  <ArrowDownToBracketOutline size="sm" class="mr-2" />
                  {isDownloading ? "⏳ Downloading..." : "💾 Download Results"}
                </Button>
              </div>
            </div>
          </Card>
        {/if}
      </div>
    </div>
  </div>
</div>

<!-- Result Modal -->
<Modal bind:open={showResultModal} size="lg" autoclose={false} title="🎉 Deduplication Complete!">
  {#if dedupResult}
    <div class="p-6 bg-gradient-to-br from-blue-50 to-purple-50">
      <div class="text-center mb-6">
        <div class="text-6xl mb-4">🎊</div>
        <h3 class="text-2xl font-bold text-gray-800 mb-2">Mission Accomplished!</h3>
        <p class="text-gray-600">Your QA pairs have been successfully deduplicated</p>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
        <div class="bg-gradient-to-br from-blue-400 to-blue-600 p-6 rounded-xl text-white text-center shadow-lg bounce-in">
          <div class="text-3xl mb-2">📝</div>
          <p class="text-sm opacity-90 mb-1">Original Count</p>
          <p class="text-3xl font-bold">{dedupResult.original_count}</p>
        </div>
        <div class="bg-gradient-to-br from-green-400 to-green-600 p-6 rounded-xl text-white text-center shadow-lg bounce-in" style="animation-delay: 0.1s">
          <div class="text-3xl mb-2">✅</div>
          <p class="text-sm opacity-90 mb-1">Kept Count</p>
          <p class="text-3xl font-bold">{dedupResult.kept_count}</p>
        </div>
        <div class="bg-gradient-to-br from-red-400 to-red-600 p-6 rounded-xl text-white text-center shadow-lg bounce-in" style="animation-delay: 0.2s">
          <div class="text-3xl mb-2">🗑️</div>
          <p class="text-sm opacity-90 mb-1">Deleted Count</p>
          <p class="text-3xl font-bold">{dedupResult.original_count - dedupResult.kept_count}</p>
        </div>
      </div>

      <div class="flex justify-center gap-4 mt-8">
        <Button color="light" class="flex items-center gap-2 hover:scale-105 transition-transform" on:click={() => previewDedupResult(dedupResult.dedup_id)}>
          <EyeOutline size="sm" />
          👀 Preview Results
        </Button>
        <Button color="blue" class="flex items-center gap-2 hover:scale-105 transition-transform" on:click={() => downloadDedupFile(dedupResult.dedup_id, 'dedup_result')} disabled={isDownloading}>
          <ArrowDownToBracketOutline size="sm" />
          {isDownloading ? "⏳ Downloading..." : "💾 Download Results"}
        </Button>
        <Button color="alternative" on:click={() => showResultModal = false} class="hover:scale-105 transition-transform">
          ❌ Close
        </Button>
      </div>
    </div>
  {:else}
    <div class="p-8 text-center">
      <div class="text-6xl mb-4">🤔</div>
      <p class="text-xl text-gray-600">No results available</p>
    </div>
  {/if}
</Modal>

<!-- Preview Modal -->
<Modal bind:open={showPreviewModal} size="xl" autoclose={false} title="👀 Deduplication Preview">
  {#if previewData}
    <div class="p-6 bg-gradient-to-br from-purple-50 to-pink-50 max-h-[80vh] overflow-y-auto">
      <div class="mb-6">
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div class="bg-gradient-to-br from-blue-400 to-blue-600 p-4 rounded-xl text-white text-center shadow-lg">
            <div class="text-2xl mb-1">📝</div>
            <p class="text-sm opacity-90">Original Count</p>
            <p class="text-2xl font-bold">{previewData.original_count}</p>
          </div>
          <div class="bg-gradient-to-br from-green-400 to-green-600 p-4 rounded-xl text-white text-center shadow-lg">
            <div class="text-2xl mb-1">✅</div>
            <p class="text-sm opacity-90">Kept Count</p>
            <p class="text-2xl font-bold">{previewData.kept_count}</p>
          </div>
          <div class="bg-gradient-to-br from-red-400 to-red-600 p-4 rounded-xl text-white text-center shadow-lg">
            <div class="text-2xl mb-1">🗑️</div>
            <p class="text-sm opacity-90">Deleted Count</p>
            <p class="text-2xl font-bold">{previewData.deleted_count}</p>
          </div>
        </div>
      </div>

      <Tabs>
        <TabItem open title="✅ Kept QA Pairs">
          <div class="overflow-y-auto max-h-96 space-y-3">
            {#each previewData.kept_pairs as qa, index}
              <Card class="card-hover bg-white/80 backdrop-blur-sm border-2 border-green-200">
                <div class="p-4">
                  <div class="flex items-center gap-2 mb-3">
                    <Badge color="green" class="text-sm">#{index + 1}</Badge>
                    <span class="text-lg">💬</span>
                  </div>
                  <div class="mb-3">
                    <p class="font-medium text-sm text-green-600 flex items-center gap-1 mb-1">
                      <span>❓</span> Question:
                    </p>
                    <p class="text-gray-800 bg-green-50 p-2 rounded">{qa.question}</p>
                  </div>
                  <div>
                    <p class="font-medium text-sm text-blue-600 flex items-center gap-1 mb-1">
                      <span>💡</span> Answer:
                    </p>
                    <p class="text-gray-800 bg-blue-50 p-2 rounded">{qa.answer}</p>
                  </div>
                </div>
              </Card>
            {/each}
          </div>
        </TabItem>

        <TabItem title="🗑️ Deleted Groups">
          <div class="overflow-y-auto max-h-96 space-y-3">
            {#if previewData.deleted_groups && previewData.deleted_groups.length > 0}
              {#each previewData.deleted_groups as group, index}
                <Card class="card-hover bg-white/80 backdrop-blur-sm border-2 border-red-200">
                  <div class="p-4">
                    <div class="flex items-center gap-2 mb-3">
                      <Badge color="red" class="text-sm">Group #{index + 1}</Badge>
                      <span class="text-lg">🗑️</span>
                      {#if group.group_size}
                        <Badge color="dark" class="text-xs">{group.group_size} pairs</Badge>
                      {/if}
                    </div>

                    <div class="mb-4 bg-red-50 p-3 rounded-lg border-l-4 border-red-400">
                      <p class="font-medium text-sm text-red-600 mb-2">🎯 Main Pair (Kept):</p>
                      <div class="ml-2">
                        <p class="text-sm mb-1"><strong>❓ Q:</strong> {group.main_pair?.question || 'N/A'}</p>
                        <p class="text-sm"><strong>💡 A:</strong> {group.main_pair?.answer || 'N/A'}</p>
                      </div>
                    </div>

                    {#if group.similar_pairs && group.similar_pairs.length > 0}
                      <div class="bg-gray-50 p-3 rounded-lg">
                        <p class="font-medium text-sm text-gray-600 mb-2">🔄 Similar Pairs (Deleted):</p>
                        {#each group.similar_pairs as similar, simIndex}
                          <div class="ml-2 mt-2 p-2 bg-white rounded border-l-2 border-gray-300">
                            <Badge color="dark" class="text-xs mb-1">#{simIndex + 1}</Badge>
                            <p class="text-xs text-gray-600"><strong>❓ Q:</strong> {similar.question || 'N/A'}</p>
                            <p class="text-xs text-gray-600"><strong>💡 A:</strong> {similar.answer || 'N/A'}</p>
                          </div>
                        {/each}
                      </div>
                    {:else}
                      <div class="bg-gray-50 p-3 rounded-lg text-center">
                        <p class="text-sm text-gray-500">No similar pairs found for this group</p>
                      </div>
                    {/if}
                  </div>
                </Card>
              {/each}
            {:else}
              <div class="text-center py-16">
                <div class="text-6xl mb-4">🤔</div>
                <div class="text-xl text-gray-600 mb-2">No deleted groups found</div>
                <div class="text-sm text-gray-500">All QA pairs were kept during deduplication</div>
              </div>
            {/if}
          </div>
        </TabItem>
      </Tabs>

      <div class="flex justify-center gap-4 mt-6 pt-4 border-t border-gray-200">
        <Button color="blue" class="flex items-center gap-2 hover:scale-105 transition-transform" on:click={() => downloadDedupFile(previewData.dedup_id, 'dedup_result')} disabled={isDownloading}>
          <ArrowDownToBracketOutline size="sm" />
          {isDownloading ? "⏳ Downloading..." : "💾 Download Full Results"}
        </Button>
        <Button color="alternative" on:click={() => showPreviewModal = false} class="hover:scale-105 transition-transform">
          ❌ Close
        </Button>
      </div>
    </div>
  {:else}
    <div class="p-8 text-center">
      <div class="text-6xl mb-4">🔄</div>
      <Spinner size="8" class="mb-4" />
      <p class="text-xl text-gray-600">Loading preview...</p>
      <p class="text-sm text-gray-500 mt-2">Please wait while we prepare your data</p>
    </div>
  {/if}
</Modal>

</div>