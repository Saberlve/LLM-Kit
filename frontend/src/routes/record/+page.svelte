<script lang="ts">
    import axios from "axios";
    import { onMount } from "svelte";
    import { getContext } from "svelte";
    import toFormatted from "../../../../utils/ConvertDatetimeString";
    import TaggedSearchbar from "./TaggedSearchbar.svelte";
    import { SearchOutline } from "flowbite-svelte-icons";
    import { Badge, Button, Modal } from "flowbite-svelte";
    const t: any = getContext("t");
    const TASK_URLS = {
        parse: "/parse/phistory",
        to_tex: "/to_tex/to_tex/history",
        generate_qa: "/qa/generate_qa/history",
        dedup: "/dedup/deduplicate_qa/history", 
        cothistory: "/cot/cothistory",
    };
 
  interface SearchParams {
     tags: string[];
     start_time: string;
     end_time: string;
     limit: number;
     filename?: string;
  }
 
  interface Record {
    id: number;
    time: string;
    source: string[];
    message: string;
    filename: string;
    status: boolean;
    data?: any;
  }
 
  let records = [] as Record[];
  let searchParams: SearchParams = {
     tags: [],
     start_time: "",
     end_time: "",
     limit: 99,
     filename: ""
  };
 
  let selectedTask = TASK_URLS.parse; //  
 
  const col_names = [
      t("record.message"),
      t("record.time"),
      t("record.source"),
      t("record.action")
  ];
 
  onMount(async () => {
      fetchData();
  });
 
  async function fetchData() {
      try {
          //  
          const res = await axios.post(selectedTask, searchParams);
          records = res.data;
      } catch (error) {
          console.error("Error fetching data:", error);
      }
  }
 
  let tags = [] as string[];
 
  async function handleSearch(event) {
      searchParams.tags = tags;
      console.log(searchParams);
      fetchData();
  }
 
  //  
  function switchTask(task: string) {
      selectedTask = TASK_URLS[task] || TASK_URLS.parse;
      fetchData();
  }
 
  //  ： 
    async function deleteRecord(recordId: string) {
        try {
            const res = await axios.delete(`/quality_records`, {
                params: {
                    record_id: recordId
                }
            });
            console.log("Record deleted:", res.data);
            //  
            records = records.filter(record => record.id !== recordId);
        } catch (error) {
            console.error("Error deleting record:", error);
        }
    }
  </script>
  
  <div class="pt-2 w-full">
    <span class="text-2xl pt-1 text-black-400 font-bold">&nbsp;&nbsp;{t("record.title")}</span>
    <span class="text-1xl pt-2 text-black-400 text-center"
        >&nbsp;&nbsp;{t("record.description")}</span
    >
  </div>
  <hr class="pt-1" />
  
  <div class="overflow-x-auto">
    <div class="flex flex-row justify-between">
        <div class="flex w-full">    
            <div class="flex py-2 w-1/2 m-1">
                <TaggedSearchbar bind:tags />
            </div>
            <div class="flex m-1">
                <Button class="my-2" on:click={handleSearch}>
                    <SearchOutline size="sm" />
                    {t("search")}
                </Button>
            </div>
        </div>
        <div class="flex m-1">
            <!--   -->
            <select class="my-2 bg-white border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full pl-3 pr-6 p-2 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white dark:focus:ring-blue-500 dark:focus:border-blue-50"
                on:change={(e) => switchTask(e.target.value)}>
                <option value="parse">{t("record.tasks.parse")}</option>
                <option value="to_tex">{t("record.tasks.to_tex")}</option>
                <option value="generate_qa">{t("record.tasks.generate_qa")}</option>
                <option value="dedup">{t("record.tasks.dedup")}</option> <!--   -->
                <option value="cothistory">{t("record.tasks.cothistory")}</option> <!--   -->
            </select>
        </div>
    </div>
    <table class="table-auto border-collapse w-full h-full">
        <thead>
            <tr
                class="rounded-lg text-sm font-medium text-gray-700 text-left"
                style="font-size: 0.9674rem">
                {#each col_names as name (name)}
                <th class="px-4 py-2 bg-gray-200" style="background-color:#f8f8f8">{name}</th>
                {/each}
            </tr>
        </thead>
        <tbody class="text-sm font-normal text-gray-700">
            {#each records as record (record.id)}
            <tr class="hover:bg-gray-100 rounded-lg">
                <td class="px-4 py-4 w-1/3">{record.message}</td>
                <td class="px-4 py-4 w-[10%]">{toFormatted(record.time)}</td>
                <td class="px-4 py-4 w-1/8">
                    {#each record.source as source (source)}
                        <Badge rounded color="indigo" class="m-1">{source}</Badge>
                    {/each}
                </td>
                <td class="px-4 py-4">
                    <a
                        href={`/record/log?id=${record.id}`}
                        class="text-blue-600 hover:underline">{t("view_logs")}</a
                    >
                    <!--   -->
                    <Button class="ml-2" on:click={() => deleteRecord(record.id)}>
                        {t("delete")}
                    </Button>
                </td>
            </tr>
            {/each}
        </tbody>
    </table>
  </div>