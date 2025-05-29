<!-- frontend/src/routes/construct/raw-preview/+page.svelte -->
<script lang="ts">
    import { onMount } from 'svelte';
    import axios from 'axios';
    import { page } from '$app/stores';
    import ActionPageTitle from '../../components/ActionPageTitle.svelte';
    import { Button } from 'flowbite-svelte';
    import { getContext } from "svelte";

    const t: any = getContext("t");
    let filename: string = '';
    let rawContent = '';
    let fileType = '';
    let fileSize = '';
    let createdAt = '';
    let errorMessage = null;
    let isLoading = true;

    onMount(async () => {
        filename = $page.url.searchParams.get('filename') || '';
        if (filename) {
            await fetchFileContent();
        } else {
            errorMessage = "未提供文件名参数";
            isLoading = false;
        }
    });

    const fetchFileContent = async () => {
        try {
            isLoading = true;
            errorMessage = null;
            
            console.log(`尝试获取文件: ${filename}`);
            // 使用encodeURIComponent确保文件名正确编码
            const encodedFilename = encodeURIComponent(filename);
            console.log(`编码后的文件名: ${encodedFilename}`);
            
            const response = await axios.get(`http://127.0.0.1:8000/parse/preview_raw/${encodedFilename}`);
            console.log('API响应:', response);
            
            if (response.status === 200 && response.data.status === "success") {
                // 处理新的API响应格式
                rawContent = response.data.data.content;
                fileType = response.data.data.file_type || '';
                fileSize = response.data.data.size ? formatFileSize(response.data.data.size) : '';
                createdAt = response.data.data.created_at || '';
            } else {
                errorMessage = t("construct.preview_raw_fetch_failed") + (response.data?.detail ? `: ${response.data.detail}` : '');
                console.error('获取文件内容失败:', response.data);
            }
        } catch (error) {
            console.error('Error fetching raw file content:', error);
            rawContent = ''; // 确保清空内容
            
            if (error.response) {
                console.error('错误响应:', error.response.data);
                if (error.response.status === 404) {
                    errorMessage = `文件 "${filename}" 未找到。请确认文件名正确并且文件已经上传。`;
                } else {
                    errorMessage = `${t("construct.preview_raw_network_error")}: ${error.response.data.detail || error.message}`;
                }
            } else if (error.request) {
                errorMessage = "服务器没有响应，请检查后端服务是否运行";
            } else {
                errorMessage = `请求错误: ${error.message}`;
            }
        } finally {
            isLoading = false;
        }
    };

    const formatFileSize = (sizeInBytes: number): string => {
        if (sizeInBytes < 1024) {
            return `${sizeInBytes} B`;
        } else if (sizeInBytes < 1024 * 1024) {
            return `${(sizeInBytes / 1024).toFixed(2)} KB`;
        } else {
            return `${(sizeInBytes / (1024 * 1024)).toFixed(2)} MB`;
        }
    };

    const retry = () => {
        fetchFileContent();
    };
</script>

<ActionPageTitle returnTo=" /construct" title={t("construct.raw_file_preview_title")} />

<div class="container mx-auto px-4 py-6">
    {#if errorMessage}
        <div class="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4 flex flex-col">
            <div>{errorMessage}</div>
            <div class="mt-2">
                <Button color="red" size="xs" on:click={retry}>重试</Button>
            </div>
        </div>
    {/if}

    <h2 class="text-2xl font-bold mb-4">{t("construct.raw_file_preview_for_file")} {filename}</h2>

    {#if isLoading}
        <div class="flex justify-center items-center py-12">
            <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-gray-900"></div>
        </div>
    {:else if rawContent}
        <!-- 文件元数据 -->
        <div class="bg-gray-50 p-4 rounded-lg mb-4 flex flex-wrap gap-4">
            {#if fileType}
                <div>
                    <span class="font-semibold">文件类型:</span> {fileType}
                </div>
            {/if}
            {#if fileSize}
                <div>
                    <span class="font-semibold">文件大小:</span> {fileSize}
                </div>
            {/if}
            {#if createdAt}
                <div>
                    <span class="font-semibold">创建时间:</span> {new Date(createdAt).toLocaleString()}
                </div>
            {/if}
        </div>
        <!-- 文件内容 -->
        <div class="bg-white shadow-md rounded-lg p-6 overflow-auto max-h-[600px] whitespace-pre-wrap">{rawContent}</div>
    {:else}
        <div class="bg-yellow-50 border border-yellow-400 text-yellow-700 p-4 rounded-lg">
            <p class="font-semibold">找不到文件内容</p>
            <p class="mt-2">{t("construct.no_raw_content_available")}</p>
            <p class="mt-2">请确保文件已上传并且已经解析。</p>
        </div>
    {/if}
</div>