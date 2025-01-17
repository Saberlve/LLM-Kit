<script lang="ts">
  import { onMount, setContext } from "svelte";
  import "../app.css";
  import Header from "./Header.svelte";
  import Sidebar from "./Sidebar.svelte";
  import axios from "axios";
  import getI18nStore from "../locales/index";
  import Login from "./Login.svelte";
  import Signup from "./Signup.svelte";
  import { Button } from "flowbite-svelte";

  const i18n = getI18nStore();
  const t = $i18n.t;
  setContext("i18n", i18n);
  setContext("t", t);

  // 移除登录状态相关的变量和逻辑
  let loaded = true; // 直接设置为true，表示页面已加载

  // 如果需要保留某些初始化逻辑，可以在这里进行
  onMount(() => {
    // 可以在此处添加一些初始化操作，但不再依赖登录状态
  });
  
</script>

<Header />
{#if loaded}
  <div class="w-full h-screen pt-2 flex flex-row">
    <!-- 始终显示侧边栏 -->
    <div>
      <Sidebar />
    </div>
    <div class="w-full p-2">
      <slot />
    </div>
  </div>
{/if}