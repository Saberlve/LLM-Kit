<script lang="ts">
  import axios from "axios";
  import {
    Accordion,
    AccordionItem,
    Button,
    Table,
    TableHead,
    TableHeadCell,
    TableBody,
    TableBodyCell,
    Input,
    Progressbar,
  } from "flowbite-svelte";

  import { Dropzone } from "flowbite-svelte";
  import { UPDATE_VIEW_INTERVAL } from "../store";
  import type DatasetEntry from "../../class/DatasetEntry";
  import { onDestroy, onMount } from "svelte";
  import { getContext } from "svelte";
  import { goto } from "$app/navigation";
  const t: any = getContext("t");
  import ActionPageTitle from "../components/ActionPageTitle.svelte";

  // --- Types ---

  interface UploadResponse {
    status: "success" | "fail";
    message: string;
    data: { file_id: string };
  }

  interface ParseResponse {
    status: "success" | "fail";
    message: string;
    data: { record_id: string };
  }

  interface TaskProgressResponse {
    status: "success" | "fail";
    message: string;
    data: { progress: number, status: string, task_type: string };
  }

  interface UploadedFile {
    file_id: string;
    filename: string;
    file_type: string;
    size: number;
    status: string; // Backend upload status: "pending", "processed"
    created_at: string;
    type: string;
    parseStatus?: string; // Frontend parse status: "pending", "processing", "completed", "failed", ""
    parseProgress?: number; // 0-100
    recordId?: string | null;
  }
  interface UploadedBinaryFile {
    file_id: string;
    filename: string;
    file_type: string;
    mime_type: string;
    size: number;
    status: string; // Backend upload status: "pending", "processed"
    created_at: string;
    type: string;
    parseStatus?: string; // Frontend parse status: "pending", "processing", "completed", "failed", ""
    parseProgress?: number; // 0-100
    recordId?: string | null;
  }

  type UnifiedFile = UploadedFile | UploadedBinaryFile;
  interface UnifiedFileListResponse {
    status: string;
    message: string;
    data: UnifiedFile[];
  }

  // --- Component State ---
  let loading = false;
  let errorMessage: string | null = null;
  let uploadedFiles: UnifiedFile[] = [];
  let entries: DatasetEntry[] = [];
  export let stageEmpty = uploadedFiles.length == 0;
  $: stageEmpty = uploadedFiles.length == 0;
  let parsingProgressIntervals: { [fileId: string]: any } = {};


  const uploaded_file_heads = [
    t("data.uploader.filename"),
    t("data.uploader.file_type"),
    t("data.uploader.size"),
    t("data.uploader.created_at"),
    t("data.uploader.upload_status"), // 添加 upload status 列头
    t("data.uploader.action")
  ]


  // --- Helper Functions ---
  function generateUniqueId(): string {
    return Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15);
  }

  function formatFileSize(sizeInBytes: number): string {
    const sizeInKilobytes = sizeInBytes / 1024;
    const sizeInMegabytes = sizeInKilobytes / 1024;

    if (sizeInMegabytes > 1) {
      return `${sizeInMegabytes.toFixed(2)} MB`;
    } else if (sizeInKilobytes > 1) {
      return `${sizeInKilobytes.toFixed(2)} KB`;
    } else {
      return `${sizeInBytes} B`;
    }
  }


  // --- Event Handlers ---
  async function dropHandle(event: DragEvent) {
    event.preventDefault();
    const filesInItems = Array.from(event.dataTransfer.items)
            .filter((item) => item.kind === "file")
            .map((item) => item.getAsFile());
    const filesInFiles = Array.from(event.dataTransfer.files);
    const files = Array.from(new Set([...filesInItems, ...filesInFiles]));

    for (const file of files) {
      await uploadAndProcessFile(file);
    }
  }

  async function changeHandle(event: any) {
    event.preventDefault();
    const files: File[] = Array.from(event.target.files);
    for (const file of files) {
      await uploadAndProcessFile(file);
    }
  }


  // --- API Functions ---
  async function uploadFile(file: File): Promise<UploadResponse> {
    try {
      const fileType = file.name.split(".").pop()?.toLowerCase();
      if (["pdf", "jpg", "jpeg", "png"].includes(fileType)) {
        const formData = new FormData();
        formData.append("file", file);
        const response = await axios.post<UploadResponse>(
                `http://127.0.0.1:8000/parse/upload/binary`,
                formData,
        );
        return response.data;
      } else {
        const reader = new FileReader();
        reader.readAsText(file);

        return await new Promise((resolve, reject) => {
          reader.onload = async (e) => {
            const fileContent = e.target?.result;
            if (typeof fileContent !== "string") {
              reject("File content could not be read")
              return
            }
            try {
              const response = await axios.post<UploadResponse>(
                      `http://127.0.0.1:8000/parse/upload`,
                      {
                        filename: file.name,
                        content: fileContent,
                        file_type: file.name.split(".").pop(),
                      }
              );
              resolve(response.data);
            } catch (error) {
              console.error(`Error uploading file ${file.name}:`, error);
              reject(error);
            }
          };
        });
      }
    } catch (error) {
      // Error reading the file
      console.error(`Error processing file ${file.name}:`, error);
      throw error;
    }
  }


  async function fetchUploadedFiles(): Promise<void> {
    try {
      const response = await axios.get<UnifiedFileListResponse>(
              `http://127.0.0.1:8000/parse/files/all`
      );
      if (response.data.status === "success") {
        // Reset parse status and progress when fetching new file list
        uploadedFiles = response.data.data.map(file => ({
          ...file,
          parseStatus: file.parseStatus || "",
          parseProgress: file.parseProgress || 0,
          recordId: file.recordId || null
        }));
      } else {
        console.error("Error fetching uploaded files:", response);
        errorMessage = t("data.uploader.fetch_fail");
      }
    } catch (error) {
      console.error("Error fetching uploaded files:", error);
      errorMessage = t("data.uploader.fetch_fail");
    }
  }

  async function parseFileForEntry(file: UnifiedFile) {
    if (!file.file_id) {
      console.error("File ID is missing, cannot parse.");
      return;
    }

    uploadedFiles = uploadedFiles.map(f =>
            f.file_id === file.file_id ? { ...f, parseStatus: "pending", parseProgress: 0, recordId: null } : f
    );

    try {
      let parseResponse: ParseResponse;
      if (file.type === 'binary') {
        parseResponse = await axios.post<ParseResponse>(`http://127.0.0.1:8000/parse/parse/ocr`, { file_id: file.file_id }); // Send file_id in body
      } else {
        parseResponse = await axios.post<ParseResponse>(`http://127.0.0.1:8000/parse/parse/file`, { file_id: file.file_id }); // Send file_id in body
      }

      if (parseResponse.data.status === "success") {
        const recordId = parseResponse.data.data.record_id;
        uploadedFiles = uploadedFiles.map(f =>
                f.file_id === file.file_id ? { ...f, recordId: recordId } : f
        );
        startPollingParsingProgress(file.file_id, recordId);
      } else {
        uploadedFiles = uploadedFiles.map(f =>
                f.file_id === file.file_id ? { ...f, parseStatus: "failed", parseProgress: 0 } : f
        );
        console.error("Parsing failed:", parseResponse);
      }
    } catch (error) {
      uploadedFiles = uploadedFiles.map(f =>
              f.file_id === file.file_id ? { ...f, parseStatus: "failed", parseProgress: 0 } : f
      );
      console.error("Error starting parsing:", error);
    }
  }

  async function fetchTaskProgress(recordId: string): Promise<TaskProgressResponse> {
    return await axios.get<TaskProgressResponse>(`http://127.0.0.1:8000/parse/task/progress`, { params: { record_id: recordId } }); // Send record_id as query parameter
  }

  function startPollingParsingProgress(fileId: string, recordId: string) {
    if (parsingProgressIntervals[fileId]) {
      clearInterval(parsingProgressIntervals[fileId]);
    }

    parsingProgressIntervals[fileId] = setInterval(async () => {
      try {
        const progressResponse = await fetchTaskProgress(recordId);
        if (progressResponse.data.status === "success") {
          const progress = progressResponse.data.data.progress;
          const status = progressResponse.data.data.status;
          uploadedFiles = uploadedFiles.map(f =>
                  f.file_id === fileId ? { ...f, parseProgress: progress, parseStatus: status } : f
          );
          if (status === "completed" || status === "failed") {
            clearInterval(parsingProgressIntervals[fileId]);
            delete parsingProgressIntervals[fileId];
            if (status === "completed") { // Update upload status to "processed" after successful parse
              uploadedFiles = uploadedFiles.map(f =>
                      f.file_id === fileId ? { ...f, status: "processed" } : f
              );
            }
          }
        } else {
          console.error("Error fetching task progress:", progressResponse);
          clearInterval(parsingProgressIntervals[fileId]);
          delete parsingProgressIntervals[fileId];
          uploadedFiles = uploadedFiles.map(f =>
                  f.file_id === fileId ? { ...f, parseStatus: "failed", parseProgress: 0 } : f
          );
        }
      } catch (error) {
        console.error("Error fetching task progress:", error);
        clearInterval(parsingProgressIntervals[fileId]);
        delete parsingProgressIntervals[fileId];
        uploadedFiles = uploadedFiles.map(f =>
                f.file_id === fileId ? { ...f, parseStatus: "failed", parseProgress: 0 } : f
        );
      }
    }, 2000); // Poll every 2 seconds
  }


  // --- Upload Logic ---
  async function uploadAndProcessFile(file: File) {
    loading = true;
    errorMessage = null;
    try {
      const response = await uploadFile(file);

      if (response.status !== "success") {
        errorMessage = t("data.uploader.upload_fail") + ": " + file.name;
        console.error(`Error uploading file ${file.name}:`, response);
      } else {
        console.log("File uploaded successfully, id is", response.data.file_id);
      }
      await fetchUploadedFiles(); // Refresh file list after each upload
    } catch (error) {
      errorMessage = t("data.uploader.upload_fail_all");
      console.error("Upload failed:", error);
    } finally {
      loading = false;
    }
  }


  function returnToData() {
    goto(`/data`);
  }

  let fetchEntriesUpdater: any;
  onMount(async () => {
    fetchEntriesUpdater = setInterval(fetchUploadedFiles, UPDATE_VIEW_INTERVAL);
    await fetchUploadedFiles();
  });

  onDestroy(() => {
    clearInterval(fetchEntriesUpdater);
    for (const intervalId in parsingProgressIntervals) {
      clearInterval(parsingProgressIntervals[intervalId]);
    }
  });


  function handleParseButtonClick(file: UnifiedFile) {
    parseFileForEntry(file);
  }
</script>


<ActionPageTitle returnTo={"/data"} title={t("data.uploader.title")} />

{#if !loading}

  <div class="w-full flex flex-col">
    {#if errorMessage}
      <div class="m-4 p-4 bg-red-100 border border-red-400 text-red-700 rounded">
        {errorMessage}
      </div>
    {/if}
    <div class="m-2">
      <Accordion>
        <AccordionItem open={true}>
          <span slot="header">{t("data.uploader.uploaded_files")}</span>
          <div class="overflow-x-auto" style="max-height: 600px;">
            <Table striped={true}>
              <TableHead>
                {#each uploaded_file_heads as head}
                  <TableHeadCell>{head}</TableHeadCell>
                {/each}
              </TableHead>
              <TableBody>
                {#each uploadedFiles as file}
                  <tr>
                    <TableBodyCell>{file.filename}</TableBodyCell>
                    <TableBodyCell>{file.file_type || file.mime_type}</TableBodyCell>
                    <TableBodyCell>{formatFileSize(file.size)}</TableBodyCell>
                    <TableBodyCell>{file.created_at}</TableBodyCell>
                    <TableBodyCell>{file.status === 'processed' ? t("data.uploader.processed") : t("data.uploader.pending")}</TableBodyCell>
                    <TableBodyCell>
                      <Button size="xs" on:click={() => handleParseButtonClick(file)} disabled={file.parseStatus === 'processing' || file.parseStatus === 'completed' || file.status === 'processed'}>{t("data.uploader.parse_button")}</Button>
                    </TableBodyCell>
                  </tr>
                  {#if file.parseStatus}
                    <tr>
                      <td colspan="6">
                        <div class="flex flex-row items-center gap-2">
                          <span>{t("data.uploader.parse_status")}: {file.parseStatus}</span>
                          {#if file.parseStatus === 'processing'}
                            <Progressbar progress={file.parseProgress} size="sm" />
                          {:else if file.parseStatus === 'completed'}
                            <span class="text-green-500">({t("data.uploader.completed")})</span>
                          {:else if file.parseStatus === 'failed'}
                            <span class="text-red-500">({t("data.uploader.failed")})</span>
                          {/if}
                        </div>
                      </td>
                    </tr>
                  {/if}
                {/each}
              </TableBody>
            </Table>
          </div>
        </AccordionItem>
      </Accordion>
    </div>

    <div class="m-4">
      <Dropzone
              id="dropzone"
              on:drop={dropHandle}
              on:dragover={(event) => {
          event.preventDefault();
        }}
              on:change={changeHandle}
      >
        <svg
                aria-hidden="true"
                class="mb-3 w-10 h-10 text-gray-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                xmlns="http://www.w3.org/2000/svg"
        >
          <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
          />
        </svg>
        <p class="mb-2 text-sm text-gray-500 dark:text-gray-400">
          <span class="font-semibold">{t("data.uploader.click")}</span>{t("data.uploader.or")}<span
                class="font-semibold"
        >{t("data.uploader.p1")}</span
        >{t("data.uploader.p2")}
        </p>
        <p class="text-xs text-gray-500 dark:text-gray-400">TEXT,IMG,PDF</p>
      </Dropzone>
    </div>
  </div>
{:else}
  <div class="m-4 p-4 border-2 border-gray-300 rounded text-center">
    <div>
      {t("data.uploader.uploading")}
    </div>
  </div>
{/if}
