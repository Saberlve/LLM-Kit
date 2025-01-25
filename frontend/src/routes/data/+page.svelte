<script lang="ts">
  export let poolId: number;
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
    Hr,
  } from "flowbite-svelte";
  import { Label } from "flowbite-svelte";
  import { Dropzone } from "flowbite-svelte";
  import { UPDATE_VIEW_INTERVAL } from "../store";
  import DatasetTable from "./DatasetTable.svelte";
  import type DatasetEntry from "../../class/DatasetEntry";
  import { onDestroy, onMount } from "svelte";
  import { getContext } from "svelte";
  const t: any = getContext("t");

  interface SubmissionEntry {
    name: string;
    domain: string;
    file: File;
    size:string;
  }

  let submissions: Array<SubmissionEntry> = [];
  let loadingProgress = 1;
  let loadingTotal = 0;

  function file_to_default_entry(file: File): SubmissionEntry {
    const sizeInBytes = file.size;
    const sizeInKilobytes = sizeInBytes / 1024;
    const sizeInMegabytes = sizeInKilobytes / 1024;

    let displaySize;
    if(sizeInMegabytes > 1){
      displaySize = `${sizeInMegabytes.toFixed(2)} MB`;
    }else if(sizeInKilobytes>1){
      displaySize = `${sizeInKilobytes.toFixed(2)} KB`;
    }else{
      displaySize = `${sizeInBytes} B`;
    }
    return {
      name: file.name.split(".")[0],
      domain: `Uploaded file ${file.name}`,
      file: file,
      size:displaySize
    };
  }

  function files_to_default_entries(files: Array<File>) {
    return files.map((file) => {
      return file_to_default_entry(file);
    });
  }

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
    const files: Array<File> = Array.from(event.target.files);
    submissions = [...submissions, ...files_to_default_entries(files)];
  }

  const stage_table_heads = [
    t("data.uploader.col_filename"),
    t("data.uploader.col_filesize"),
    t("data.uploader.col_des"),
    t("data.uploader.col_option")];

  let loading = false;

  async function submit_handle() {
    loadingTotal = submissions.length;
    loadingProgress = 0;
    loading = true;
    for (var i = 0; i < submissions.length; i++) {
      const form = new FormData();
      const entry = submissions[i];
      form.append("file", entry.file);
      await axios.post(`http://127.0.0.1:8000/parse/parse/parse_content`, form, {
        params: {
          name: entry.name,
          domain: entry.domain,
        },
      });
      loadingProgress += 1;
    }
    await fetch_dataset_entries();
    submissions = [];
    loading = false;
  }
  let fetch_entries_updater: any;
  onMount(async () => {
    fetch_entries_updater = setInterval(
            fetch_dataset_entries,
            UPDATE_VIEW_INTERVAL,
    );
  });
  onDestroy(async () => {
    clearInterval(fetch_entries_updater);
  });
  let entries: Array<DatasetEntry> = [];
  export let stageEmpty = submissions.length == 0;
  $: stageEmpty = submissions.length == 0;

  async function fetch_dataset_entries() {
    entries = (await axios.get(`http://127.0.0.1:8000/`)).data;
  }

  onMount(async () => {
    await fetch_dataset_entries();
  });

  async function remove_from_stage_handle(i: number) {
    submissions = submissions.filter((_, index) => {
      return index != i;
    });
  }
</script>

{#if !loading}
  <div class="w-full">
    <div class="m-2">
      <Accordion>
        <AccordionItem open={true}>
          <span slot="header">{t("data.uploader.datapool_detail")}</span>
          <DatasetTable
                  datasetEntries={entries}
                  on:modified={async (_) => {
              await fetch_dataset_entries();
            }}
          />
        </AccordionItem>
      </Accordion>
    </div>
    <div>
      <div class="m-2">
        <Accordion>
          <AccordionItem open={true}>
            <span slot="header">{t("data.uploader.zone")}</span>
            <div class="flex flex-row justify-end items-center text-black">
              <div>
                <Button
                        class="m-2 text-center"
                        on:click={(_) => submit_handle()}>{t("data.uploader.submit")}</Button
                >
              </div>
            </div>
            <div class="border border-gray-200 text-gray-800 rounded p-2 m-2">
              {#if submissions.length == 0}
                <div class="w-full text-center">
                  <span>{t("data.uploader.no_file")}</span>
                </div>
              {:else}
                <Table striped={true}>
                  <TableHead>
                    {#each stage_table_heads as head}
                      <TableHeadCell>{head}</TableHeadCell>
                    {/each}
                  </TableHead>
                  {#each submissions as entry, index (index)}
                    <TableBody>
                      <TableBodyCell>
                        {entry.file.name}
                      </TableBodyCell>
                      <TableBodyCell>
                        {entry.size}
                      </TableBodyCell>
                      <TableBodyCell>
                        <input
                                placeholder={t("data.uploader.enter_des")}
                                bind:value={entry.domain}
                                class="border-2 border-gray-300 rounded-md p-1"
                        />
                      </TableBodyCell>
                      <TableBodyCell>
                        <button
                                on:click={(_) => remove_from_stage_handle(index)}
                                class="text-blue-500 hover:text-blue-800 hover:underline"
                        >移出暂存区</button
                        >
                      </TableBodyCell>
                    </TableBody>
                  {/each}
                </Table>
              {/if}
            </div>
          </AccordionItem>
        </Accordion>
      </div>

      <div class="m-4">
        <Dropzone
                id="dropzone"
                on:drop={drop_handle}
                on:dragover={(event) => {
            event.preventDefault();
          }}
                on:change={change_handle}
        >
          <svg
                  aria-hidden="true"
                  class="mb-3 w-10 h-10 text-gray-400"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                  xmlns="http://www.w3.org/2000/svg"
          ><path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
          /></svg
          >
          <p class="mb-2 text-sm text-gray-500 dark:text-gray-400">
            <span class="font-semibold">{t("data.uploader.click")}</span>{t("data.uploader.or")}<span class="font-semibold"
          >{t("data.uploader.p1")}</span
          >{t("data.uploader.p2")}
          </p>
          <p class="text-xs text-gray-500 dark:text-gray-400">JSON</p>
        </Dropzone>
      </div>
    </div>
  </div>
{:else}
  <div>
    {loadingProgress} out of {loadingTotal}
  </div>
{/if}