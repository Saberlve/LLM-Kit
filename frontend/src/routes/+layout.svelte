<script lang="ts">
  import { onMount, setContext } from "svelte";
  import "../app.css";
  import Header from "./Header.svelte";
  import axios from "axios";
  import getI18nStore from "../locales/index";
  import { Button } from "flowbite-svelte";

  const i18n = getI18nStore();
  const t = $i18n.t;
  setContext("i18n", i18n);
  setContext("t", t);

  let loaded = true;
  
  onMount(() => {
  });
  
</script>

<Header />
{#if loaded}
  <div class="w-full min-h-screen bg-gray-50">
    <div class="container mx-auto px-4 py-6">
      <slot />
    </div>
  </div>
{/if}
