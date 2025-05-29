<script lang="ts">
  import { getContext, onMount } from "svelte";
  import { fade, fly } from "svelte/transition";

  const t: any = getContext("t");
  
  // 功能模块
  const features = [
    {
      title: t("home.features.data.title"),
      description: t("home.features.data.description"),
      icon: "📊",
      link: "/data"
    },
    {
      title: t("home.features.construct.title"),
      description: t("home.features.construct.description"),
      icon: "🔧",
      link: "/construct"
    },
    {
      title: t("home.features.quality.title"),
      description: t("home.features.quality.description"),
      icon: "✅",
      link: "/quality_eval"
    },
    {
      title: t("home.features.dedup.title"),
      description: t("home.features.dedup.description"),
      icon: "🔍",
      link: "/deduplication"
    }
  ];

  // 打字机动画相关变量
  let titleText = t("home.hero.title");
  let displayedTitle = "";
  let cursorVisible = true;
  let titleComplete = false;

  // 打字机动画函数
  onMount(() => {
    let index = 0;
    const typingInterval = setInterval(() => {
      if (index < titleText.length) {
        displayedTitle = titleText.substring(0, index + 1);
        index++;
      } else {
        titleComplete = true;
        clearInterval(typingInterval);
      }
    }, 100);

    // 光标闪烁效果
    setInterval(() => {
      cursorVisible = !cursorVisible;
    }, 500);
  });
</script>

<!-- 主标题区域 - 标题放大，添加打字机效果 -->
<div class="py-20 bg-gradient-to-r from-blue-600 via-indigo-500 to-purple-600 text-white text-center rounded-xl shadow-2xl mb-16 relative overflow-hidden">
  <!-- 背景装饰 -->
  <div class="absolute top-0 left-0 w-full h-full bg-grid-pattern opacity-10"></div>
  <div class="absolute -top-24 -right-24 w-64 h-64 bg-white opacity-10 rounded-full blur-3xl"></div>
  <div class="absolute -bottom-32 -left-32 w-96 h-96 bg-blue-300 opacity-10 rounded-full blur-3xl"></div>
  
  <div class="relative z-10">
    <h1 class="text-5xl md:text-6xl font-bold mb-8 min-h-[80px] inline-flex items-center justify-center">
      <img src="/knowledge-sharing.png" alt="Knowledge Sharing" class="h-20 w-20 mr-6 filter drop-shadow-lg" />
      {displayedTitle}{#if !titleComplete}<span class={cursorVisible ? "opacity-100" : "opacity-0"}>|</span>{/if}
    </h1>
    <p class="text-xl md:text-2xl max-w-3xl mx-auto mb-8 font-light">{t("home.hero.subtitle")}</p>
    <div class="mt-12">
      <a href="/data" class="bg-white text-blue-600 hover:bg-blue-50 font-medium py-4 px-10 rounded-full inline-flex items-center mr-4 text-lg shadow-lg hover:shadow-xl transition-all transform hover:-translate-y-1">
        {t("home.hero.get_started")}
        <svg class="w-5 h-5 ml-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3"></path>
        </svg>
      </a>
    </div>
  </div>
</div>

<!-- 功能模块区域 -->
<div class="mb-20" in:fade={{ duration: 800 }}>
  <h2 class="text-3xl font-bold text-center mb-12 text-gray-800">{t("home.features.heading")}</h2>
  <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8">
    {#each features as feature, i}
      <a href={feature.link} 
         class="bg-white p-8 rounded-xl shadow-lg hover:shadow-xl transition-all duration-300 border border-gray-100 transform hover:-translate-y-2 group"
         in:fly={{ y: 20, duration: 300, delay: i * 150 }}>
        <div class="text-4xl mb-5 text-blue-500 group-hover:scale-110 transition-transform duration-300">{feature.icon}</div>
        <h3 class="text-xl font-semibold mb-3 text-gray-800 group-hover:text-blue-600 transition-colors">{feature.title}</h3>
        <p class="text-gray-600">{feature.description}</p>
      </a>
    {/each}
  </div>
</div>

<!-- 底部说明区域 -->
<div class="bg-gradient-to-b from-gray-50 to-gray-100 p-10 rounded-xl text-center shadow-inner border border-gray-200">
  <h3 class="text-2xl font-semibold mb-4 text-gray-800">{t("home.about.title")}</h3>
  <p class="text-gray-700 max-w-4xl mx-auto leading-relaxed">{t("home.about.description")}</p>
</div>
