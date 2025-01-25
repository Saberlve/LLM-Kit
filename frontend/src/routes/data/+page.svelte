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
  interface SubmissionEntry {
    id: string;
    name: string;
    domain: string;
    file: File;
    size: string;
    uploadProgress: number;
    isBinary: boolean;
  }

  interface UploadResponse {
    status: "success" | "fail";
    message: string;
    data: { file_id: string };
  }

  interface UploadedFile {
    filename: string;
    file_type: string;
    size: number;
    status: string;
    created_at: string;
    type: string;
  }
  interface UploadedBinaryFile {
    filename: string;
    file_type: string;
    mime_type: string;
    size: number;
    status: string;
    created_at: string;
    type: string;
  }

  type UnifiedFile = UploadedFile | UploadedBinaryFile;
  interface UnifiedFileListResponse {
    status: string;
    message: string;
    data: UnifiedFile[];
  }

  // --- Component State ---
  let submissions: SubmissionEntry[] = [];
  let loading = false;
  let errorMessage: string | null = null;
  let uploadedFiles: UnifiedFile[] = [];
  let entries: DatasetEntry[] = [];
  export let stageEmpty = submissions.length == 0;
  $: stageEmpty = submissions.length == 0;

  const uploaded_file_heads = [
    t("data.uploader.filename"),
    t("data.uploader.file_type"),
    t("data.uploader.size"),
    t("data.uploader.created_at"),
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

  function fileToDefaultEntry(file: File): SubmissionEntry {
    return {
      id: generateUniqueId(),
      name: file.name.split(".")[0],
      domain: `Uploaded file ${file.name}`,
      file: file,
      size: formatFileSize(file.size),
      uploadProgress: 0,
      isBinary: false,
    };
  }

  function fileToDefaultBinaryEntry(file: File): SubmissionEntry {
    return {
      id: generateUniqueId(),
      name: file.name.split(".")[0],
      domain: `Uploaded file ${file.name}`,
      file: file,
      size: formatFileSize(file.size),
      uploadProgress: 0,
      isBinary: true,
    };
  }

  function filesToDefaultEntries(files: File[]): SubmissionEntry[] {
    return files.map((file) => {
      const fileType = file.name.split(".").pop()?.toLowerCase();
      if (["pdf", "jpg", "jpeg", "png"].includes(fileType)) {
        return fileToDefaultBinaryEntry(file);
      } else {
        return fileToDefaultEntry(file);
      }
    });
  }

  // --- Event Handlers ---
  function dropHandle(event: DragEvent) {
    event.preventDefault();
    const filesInItems = Array.from(event.dataTransfer.items)
            .filter((item) => item.kind === "file")
            .map((item) => item.getAsFile());
    const filesInFiles = Array.from(event.dataTransfer.files);
    const files = Array.from(new Set([...filesInItems, ...filesInFiles]));
    submissions = [...submissions, ...filesToDefaultEntries(files)];
  }

  function changeHandle(event: any) {
    event.preventDefault();
    const files: File[] = Array.from(event.target.files);
    submissions = [...submissions, ...filesToDefaultEntries(files)];
  }

  function updateSubmissionProgress(id: string, progress: number) {
    submissions = submissions.map((submission) =>
            submission.id === id ? { ...submission, uploadProgress: progress } : submission
    );
  }

  // --- API Functions ---
  async function uploadFile(entry: SubmissionEntry): Promise<UploadResponse> {
    const file = entry.file;
    try {
      if (entry.isBinary) {
        const formData = new FormData();
        formData.append("file", file);
        const response = await axios.post<UploadResponse>(
                `http://127.0.0.1:8000/parse/upload/binary`,
                formData,
                {
                  onUploadProgress: (progressEvent) => {
                    const percentage = Math.round(
                            (progressEvent.loaded * 100) / progressEvent.total
                    );
                    updateSubmissionProgress(entry.id, percentage);
                  },
                }
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
                      },
                      {
                        onUploadProgress: (progressEvent) => {
                          const percentage = Math.round(
                                  (progressEvent.loaded * 100) / progressEvent.total
                          );
                          updateSubmissionProgress(entry.id, percentage);
                        },
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
        uploadedFiles = response.data.data;
      } else {
        console.error("Error fetching uploaded files:", response);
        errorMessage = t("data.uploader.fetch_fail");
      }
    } catch (error) {
      console.error("Error fetching uploaded files:", error);
      errorMessage = t("data.uploader.fetch_fail");
    }
  }


  // --- Upload Logic ---
  async function submitHandle() {
    loading = true;
    errorMessage = null;
    try {
      for (const entry of submissions) {
        const response = await uploadFile(entry);

        if (response.status !== "success") {
          errorMessage = t("data.uploader.upload_fail") + ": " + entry.file.name;
          console.error(`Error uploading file ${entry.file.name}:`, response);
        } else {
          console.log("File uploaded successfully, id is", response.data.file_id);
        }
      }
      await fetchUploadedFiles();
      submissions = []; // Clear submissions after successful upload
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
  });

  function removeFromStageHandle(id: string) {
    submissions = submissions.filter((entry) => entry.id !== id);
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
    {#if uploadedFiles && uploadedFiles.length > 0}
      <div class="m-2">
        <Accordion>
          <AccordionItem open={true}>
            <span slot="header">{t("data.uploader.uploaded_files")}</span>
            <div class="overflow-x-auto" style="max-height: 300px;">
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
                      <TableBodyCell>{file.file_type}</TableBodyCell>
                      <TableBodyCell>{formatFileSize(file.size)}</TableBodyCell>
                      <TableBodyCell>{file.created_at}</TableBodyCell>
                    </tr>
                  {/each}
                </TableBody>
              </Table>
            </div>
          </AccordionItem>
        </Accordion>
      </div>
    {/if}
    <div class="m-2">
      <Accordion>
        <AccordionItem open={true}>
          <span slot="header">{t("data.uploader.zone")}</span>
          <div class="flex flex-row justify-end items-center text-black">
            <div>
              <Button class="m-2 text-center" on:click={submitHandle}
              >{t("data.uploader.submit")}</Button
              >
            </div>
          </div>
          <div class="border border-gray-200 text-gray-800 rounded p-2 m-2">
            {#if submissions.length === 0}
              <div class="w-full text-center">
                <span>{t("data.uploader.no_file")}</span>
              </div>
            {:else}
              <ul class="flex flex-col gap-2">
                {#each submissions as entry}
                  <li class="flex flex-col gap-2">
                    <div class="font-semibold">{entry.file.name}</div>
                    <div class="flex flex-row gap-2">
                      <Input
                              placeholder={t("data.uploader.enter_name")}
                              bind:value={entry.name}
                      />
                      <Input
                              placeholder={t("data.uploader.enter_des")}
                              bind:value={entry.domain}
                      />
                      <div class="flex justify-center items-center">
                        <button
                                on:click={() => removeFromStageHandle(entry.id)}
                                class="text-blue-500 hover:text-blue-800 hover:underline"
                        >{t("data.uploader.remove_stage")}</button
                        >
                      </div>
                    </div>
                  </li>
                {/each}
              </ul>
            {/if}
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
    <div class="flex flex-col gap-2">
      {#each submissions as entry}
        <div class="relative pt-1">
          <div
                  class="flex overflow-hidden bg-gray-200 rounded-lg shadow-sm"
                  style="height: 23px;"
          >
            <div
                    class="flex-grow bg-white rounded-lg"
                    style="width: {100 - entry.uploadProgress}%"
            >
              <div
                      class="flex-grow bg-blue-700 rounded-lg"
                      style="width: {entry.uploadProgress}%"
              />
            </div>
          </div>
          <span>{entry.file.name} : {entry.uploadProgress.toFixed(2)}%</span>
        </div>
      {/each}
    </div>
  </div>
{/if}