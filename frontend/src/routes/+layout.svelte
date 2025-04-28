<script lang="ts">
  import { onMount, setContext } from "svelte";
  import "../app.css";
  import Header from "./Header.svelte";
  import Sidebar from "./Sidebar.svelte";
  import axios from "axios";
  import getI18nStore from "../locales/index";
  import { Button } from "flowbite-svelte";

  const i18n = getI18nStore();
  const t = $i18n.t;
  setContext("i18n", i18n);
  setContext("t", t);

  
  let loaded = true; true，

  
  onMount(() => {
  });
  
</script>

<Header />
{#if loaded}
  <div class="w-full h-screen pt-2 flex flex-row">

    <div>
      <Sidebar />
    </div>
    <div class="w-full p-2">
      <slot />
    </div>
  </div>
{/if}
