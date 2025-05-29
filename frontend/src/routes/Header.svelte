<script lang="ts">
  import "../app.css";
  import { onMount } from "svelte";
  import { getContext } from "svelte";
  import { type i18n as i18nType } from "i18next"; // Renamed the type import
  import type { Writable } from "svelte/store";


  const i18n: Writable<i18nType> = getContext("i18n"); // Use the renamed type
  const t = $i18n.t;
  
  // 导航项
  const navItems = [
    { text: t("nav.home"), link: "/" },
    { text: t("nav.data"), link: "/data" },
    { text: t("nav.construct"), link: "/construct" },
    { text: t("nav.quality"), link: "/quality_eval" },
    { text: t("nav.dedup"), link: "/deduplication" }
  ];
</script>

<div class="header w-full h-16 justify-between bg-gray-000 flex">
  <div class="left w-100 h-5/6 text-center pt-2 px-2 flex">
    <!-- <img src="/logo.jpg" alt="" width="8%" height="8%"/> -->
    <img src="/logo.jpg" alt=""/>
    <span class="logo text-3xl pt-1 text-black-400 border-blue-400 font-bold"
    >&nbsp;&nbsp;{t("root.title")}</span
    >
    <!-- <span class="logo text-2xl pt-2 text-black-400 border-blue-400 text-center"
			>&nbsp;&nbsp;{t("root.subtitle")}</span
		> -->
  </div>
  <div class="right w-100 h-2/3 text-center pt-4 px-2 flex items-center">
    <!-- 导航栏 -->
    <div class="flex">
      {#each navItems as item}
        <a href={item.link} class="mx-3 text-gray-700 hover:text-blue-600 font-medium">{item.text}</a>
      {/each}
    </div>
  </div>
</div><hr />
