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
  } from "flowbite-svelte";
  import { Dropzone } from "flowbite-svelte";
  import { UPDATE_VIEW_INTERVAL } from "../store";
  import DatasetTable from "./DatasetTable.svelte";
  import type DatasetEntry from "../../class/DatasetEntry";
  import { onDestroy, onMount } from "svelte";
  import { getContext } from "svelte";
  import { goto } from "$app/navigation";
  const t: any = getContext("t");
  import ActionPageTitle from "../components/ActionPageTitle.svelte";

  // --- 类型定义 ---
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
    content: string;
    file_type: string;
    size: number;
    status: string;
    created_at: string;
  }
  interface UploadedBinaryFile {
    filename: string;
    file_type: string;
    mime_type: string;
    size: number;
    status: string;
    created_at: string;
  }

  type UnifiedFile = UploadedFile | UploadedBinaryFile;
  interface UnifiedFileListResponse {
    status: string;
    message: string;
    data: UnifiedFile[];
  }

  // --- 组件状态 ---
  let submissions: SubmissionEntry[] = [];
  let loading = false;
  let errorMessage: string | null = null;
  let uploadedFiles: UnifiedFile[] = [];
  let entries: DatasetEntry[] = [];
  export let stageEmpty = submissions.length == 0;
  $: stageEmpty = submissions.length == 0;


  // --- 辅助函数 ---
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


  function file_to_default_entry(file: File): SubmissionEntry {
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

  function file_to_default_binary_entry(file: File): SubmissionEntry {
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

  function files_to_default_entries(files: File[]): SubmissionEntry[] {
    return files.map((file) => {
      const fileType = file.name.split(".").pop()?.toLowerCase();
      if (["pdf", "jpg", "jpeg", "png"].includes(fileType)) {
        return file_to_default_binary_entry(file);
      } else {
        return file_to_default_entry(file);
      }
    });
  }

  // --- 事件处理 ---
  function drop_handle(event: DragEvent) {
    event.preventDefault();
    const files_in_items = Array.from(event.dataTransfer.items)
            .filter((item) => {
              return item.kind === "file";
            })
            .map((item) => {
              return item.getAsFile();
            });
    const files_in_files = Array.from(event.dataTransfer.files);
    const files = Array.from(new Set([...files_in_items, ...files_in_files]));
    submissions = [...submissions, ...files_to_default_entries(files)];
  }


  function change_handle(event: any) {
    event.preventDefault();
    const files: File[] = Array.from(event.target.files);
    submissions = [...submissions, ...files_to_default_entries(files)];
  }

  function updateSubmissionProgress(id: string, progress: number) {
    submissions = submissions.map((submission) =>
            submission.id === id ? { ...submission, uploadProgress: progress } : submission
    );
  }

  // --- API 函数 ---
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
            const fileContent = e.target.result;
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

  async function fetchDatasetEntries(): Promise<void> {
    try {
      entries = (
              await axios.get<DatasetEntry[]>(
                      `http://127.0.0.1:8000/parse/parse/history`
              )
      ).data;
    } catch (error) {
      console.error("Error fetching entries:", error);
      errorMessage = t("data.uploader.fetch_fail");
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

  // --- 上传逻辑 ---
  async function submit_handle() {
    loading = true;
    errorMessage = null;
    try {
      for (const entry of submissions) {
        const response = await uploadFile(entry);

        if (response.status !== "success") {
          errorMessage = t("data.uploader.upload_fail") + ":" + entry.file.name;
          console.error(`Error uploading file ${entry.file.name}:`, response);
        } else {
          console.log("File uploaded successfully, id is", response.data.file_id);
        }
      }
      await fetchDatasetEntries();
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

  let fetch_entries_updater: any;
  onMount(async () => {
    fetch_entries_updater = setInterval(
            fetchDatasetEntries,
            UPDATE_VIEW_INTERVAL
    );
    await fetchUploadedFiles();
    await fetchDatasetEntries();
  });

  onDestroy(() => {
    clearInterval(fetch_entries_updater);
  });

  function remove_from_stage_handle(id: string) {
    submissions = submissions.filter((entry) => entry.id !== id);
  }
</script>

<ActionPageTitle returnTo={"/data"} title={t("data.uploader.title")} />

<style>
  .file-list {
    display: flex;
    flex-direction: column;
  }

  .file-item {
    display: flex;
    flex-direction: column; /* Changed to column to stack items */
    margin-bottom: 5px;
    padding: 5px; /* Add some padding for better spacing */
    border: 1px solid #e0e0e0; /* Add border for each file item */
    border-radius: 4px; /* Rounded corners */
    background-color: #f9f9f9; /* Light background color */
    box-shadow: 0 1px 3px rgba(0,0,0,0.05); /* Subtle box shadow */
    gap: 4px;
  }
  .file-item div {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    align-items: center;
  }

  .file-size {
    max-width: 100px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .file-item button {
    padding: 3px 6px;
    border: 1px solid #ccc;
    border-radius: 3px;
    background-color: #fff;
    cursor: pointer;
    font-size: 0.8rem;
    color: #007bff;
  }
</style>

{#if !loading}
  <div class="w-full max-w-full overflow-x-auto">
    <div class="m-2">
      <Accordion>
        <AccordionItem open={true}>
          <span slot="header">{t("data.uploader.datapool_detail")}</span>
          {#if uploadedFiles.length > 0}
            <div class="mb-2">
              <div class="font-bold">{t("data.uploader.uploaded_files_title")}</div>
            </div>
            <ul class="space-y-2">
              <div class="file-list">
                {#each uploadedFiles as file}
                  <li class="file-item">
                    <div>
                      <div class="text-gray-800 font-medium">{file.filename}</div>
                      <div class="text-gray-500 text-sm">
                                <span >
                                    ({file.file_type || file.mime_type}, <span class="file-size">{formatFileSize(file.size)}</span>, {new Date(file.created_at).toLocaleString()})
                                </span>
                      </div>
                    </div>
                  </li>
                {/each}
              </div>
            </ul>
          {:else}
            <div class="text-center">
              {t("data.uploader.no_file_uploaded")}
            </div>
          {/if}
          <div class="m-2">
            <div class="font-bold">{t("data.uploader.data_list_title")}</div>
            <div class="text-gray-500 text-sm">
              ID - {t("data.uploader.col_filename")} - {t("data.uploader.col_creation_time")} - {t("data.uploader.col_filesize")} - {t("data.uploader.col_filetype")} - {t("data.uploader.col_des")}
            </div>
          </div>
          <div class="overflow-y-auto max-h-96 m-2">
            <DatasetTable
                    datasetEntries={entries}
                    on:modified={async (_) => {
                    await fetchDatasetEntries();
                  }}
            />
          </div>

        </AccordionItem>
      </Accordion>
    </div>
    {#if errorMessage}
      <div class="m-4 p-4 bg-red-100 border border-red-400 text-red-700 rounded">
        {errorMessage}
      </div>
    {/if}
    <div>
      <div class="m-2">
        <Accordion>
          <AccordionItem open={true}>
            <span slot="header">{t("data.uploader.zone")}</span>
            <div class="flex flex-row justify-end items-center text-black">
              <div>
                <Button class="m-2 text-center" on:click={submit_handle}>
                  {t("data.uploader.submit")}
                </Button>
              </div>
            </div>
            <div class="border border-gray-200 text-gray-800 rounded p-2 m-2">
              {#if submissions.length === 0}
                <div class="w-full text-center">
                  <span>{t("data.uploader.no_file")}</span>
                </div>
              {:else}
                <div class="mb-2">
                  <div class="font-bold">{t("data.uploader.stage_list_title")}</div>
                  <div class="text-gray-500 text-sm">
                    ID - {t("data.uploader.col_filename")} - {t("data.uploader.col_uploadtime")} - {t("data.uploader.col_filesize")} - {t("data.uploader.col_filetype")} - {t("data.uploader.col_des")}
                  </div>
                </div>
                <div class="file-list">
                  {#each submissions as entry (entry.id)}
                    <li class="file-item">
                      <div>
                        <div class="text-gray-800 font-medium">
                          {entry.id} - {entry.name} - <span class="file-size">{entry.size}</span> - {entry.isBinary? "Binary" : "Text"}
                        </div>

                        <input
                                placeholder={t("data.uploader.enter_des")}
                                bind:value={entry.domain}
                                class="border-2 border-gray-300 rounded-md p-1 mt-1 w-full"
                        />
                      </div>

                      <button
                              on:click={() => remove_from_stage_handle(entry.id)}
                      >
                        {t("data.uploader.remove_stage")}
                      </button>
                    </li>
                  {/each}
                </div>
              {/if}
            </div>
          </AccordionItem>
        </Accordion>
      </div>

      <div class="m-4">
        <Dropzone
                id="dropzone"
                on:drop={drop_handle}
                on:dragover={(event) => event.preventDefault()}
                on:change={change_handle}
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
          >{t("data.uploader.p1")}</span>{t("data.uploader.p2")}
          </p>
          <p class="text-xs text-gray-500 dark:text-gray-400">JSON, PDF, JPG, PNG</p>
        </Dropzone>
      </div>
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
                  class="flex overflow-hidden bg-black rounded-lg shadow-sm"
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