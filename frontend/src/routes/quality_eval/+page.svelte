<script lang="ts">
    import { onMount } from "svelte";
    import type EvalEntry from "../../class/EvalEntry";
    import ActionPageTitle from "../components/ActionPageTitle.svelte";
    import axios from "axios";
    import { Button } from "flowbite-svelte";
    import { PlusOutline } from "flowbite-svelte-icons";
    import { getContext } from "svelte";
    const t: any = getContext("t");
    let eval_entries: Array<EvalEntry> = [];
    onMount(async () => {
      eval_entries = (await axios.get("/api/eval")).data;
    });
  </script>

<ActionPageTitle
  title={t("eval.title")}
  subtitle={t("eval.subtitle")}
>
  <svelte:fragment slot="right">
    <div class="flex gap-2">
      <Button color="blue" href="/eval/tasks">
        <PlusOutline class="sm" />
        {t("eval.create_task")}
      </Button>
    </div>
  </svelte:fragment>
</ActionPageTitle>