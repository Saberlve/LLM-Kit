<script lang="ts">
	import ActionPageTitle from '../components/ActionPageTitle.svelte';
	import { Accordion, AccordionItem } from 'flowbite-svelte';
	import { Table, TableHead, TableHeadCell, TableBody, TableBodyCell } from 'flowbite-svelte';
	import { Button } from 'flowbite-svelte';
	import { Modal } from 'flowbite-svelte';
	import { getContext } from "svelte";
	import axios from "axios";
	import { onMount } from 'svelte';
	import { createEventDispatcher } from 'svelte';
	const dispatch = createEventDispatcher();

	const t: any = getContext("t");
	let errorMessage = null;
	let uploadedFiles = [];
	let selectedFiles = [];
	let showDeleteConfirmation = false;
	let filesLoaded = false;
	let successMessage = null;
	let parallelNum = 1; // 并行数量
	let modelName = '';
	let domain = '';
    let savePath = ''; // 保存路径
    let SKs = []; // API 密钥
    let AKs = []; // API 密钥
    let errorModalVisible = false; // Flag to show the modal
    let errorTimeoutId: NodeJS.Timeout | null = null; // To store timeout ID
    const errorDuration = 500; // 5 seconds

    // 调整表头与后端字段对应
    let uploaded_file_heads = ["Name", "Type", "Size", "Modification Time"];

    // 切换文件选择状态
    const toggleSelection = (file) => {
        console.log("Toggling selection for", file.name); // Debugging
        selectedFiles = selectedFiles.includes(file)
            ? selectedFiles.filter(f => f !== file)
            : [...selectedFiles, file];
    };

    const handleError = (error: any) => {
        // Extract error message from Axios error object or use a default if needed
        let errorMessageToShow = (error.response && error.response.data && error.response.data.detail) || t("data.construct.qa_generation_network_error");
        errorModalVisible = true;
        errorMessage = errorMessageToShow;
        clearTimeout(errorTimeoutId); // Clear any existing timeout

        // Set a timeout to automatically hide the modal
        errorTimeoutId = setTimeout(() => {
            errorModalVisible = false;
            errorMessage = null;
        }, errorDuration);
    };

    const validateSKAK = () => {
        if (parallelNum > SKs.length || parallelNum > AKs.length) {
            errorMessage = t("data.construct.invalid_sk_ak");
            return false;
        }
        return true;
    };

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

    onMount(async () => {
        await fetchFiles();
        filesLoaded = true;
    });

    const fetchFiles = async () => {
        try {
            const response = await fetch('http://127.0.0.1:8000/parse/parse_files');
            if (!response.ok) {
                const errorData = await response.json();
                errorMessage = errorData.detail || "Failed to load files.";
                return;
            }
            const data = await response.json();
            uploadedFiles = data;
        } catch (error) {
            errorMessage = 'Failed to load files';
            console.error("Error fetching files:", error);
        }
    };

    // 删除选中文件
    const deleteSelectedFiles = async () => {
        if (selectedFiles.length === 0) {
            console.log("No files selected"); // Debugging
            return; // Don't proceed if no files are selected
        }

        try {
            const fileNamesToDelete = selectedFiles.map(file => file.name);
            const response = await axios.post(
                'http://127.0.0.1:8000/parse/delete_files',
                { files: fileNamesToDelete },
                { headers: { "Content-Type": "application/json" } }
            );

            if (response.status === 200) {

                selectedFiles = []; // Clear selected files
                await fetchFiles(); // Refresh file list
                showDeleteConfirmation = false; // Close the modal

                // 2秒后自动清除成功消息
                setTimeout(() => {
                    successMessage = null;
                }, 2000);
            } else {
                const errorData = await response.json();
                console.error('Error deleting files:', response.status, errorData);
                errorMessage = errorData.detail || "Failed to delete files";
            }
        } catch (error) {
            console.error('Error deleting files:', error);
            errorMessage = "Network error deleting files";
        }
    };

    const generateQAPairs = async () => {
        if (selectedFiles.length === 0) {
            errorMessage = t("data.construct.no_file_selected");
            return;
        }
        if (!validateSKAK()) {
            return;
        }
        try {
            const selectedFileNames = selectedFiles.map(f => f.name);
            const requestData = {
                files: selectedFileNames,
                parallel_num: parallelNum,
                model_name: modelName,
                domain: domain,
                save_path: savePath || selectedFileNames[0], // Default to first filename
                SK: SKs,
                AK: AKs
            };
            const response = await axios.post('http://127.0.0.1:8000/qa/generate_qa', requestData);
            if (response.status === 200) {
                dispatch('qaGenerated', response.data); // 向父组件发送成功事件
                successMessage = t("data.construct.qa_generated_success"); // 清理成功消息
                selectedFiles = [];
                setTimeout(() => {
                    successMessage = null;
                }, 2000);

                await fetchFiles();
            } else {
                const errorData = await response.json();
                errorMessage = errorData.detail || t('data.construct.qa_generation_failed');
            }
        } catch (error) {
            console.error('Error generating QA pairs:', error);
            handleError(error);
            errorMessage = t('data.construct.qa_generation_network_error');
        }
    };
</script>

<ActionPageTitle returnTo="/data" title={t("data.construct.title")} />

<div class="w-full flex flex-col">
    {#if errorMessage}
        <div class="m-4 p-4 bg-red-100 border border-red-400 text-red-700 rounded">
            {errorMessage}
        </div>
    {/if}

    {#if successMessage}
        <!-- 显示删除成功的提示消息 -->
        <div class="m-4 p-4 bg-green-100 border border-green-400 text-green-700 rounded">
            {successMessage}
        </div>
    {/if}

    <div class="m-2">
        <Accordion>
            <AccordionItem open={true}>
                <span slot="header">{t("data.construct.uploaded_files")}</span>
                <div class="overflow-x-auto" style="max-height: 600px;">
                    <Table striped={true}>
                        <TableHead>
                            <TableHeadCell></TableHeadCell>
                            {#each uploaded_file_heads as head}
                                <TableHeadCell>{t(`data.construct.${head.toLowerCase().replace(' ', '_')}`)}</TableHeadCell>
                            {/each}
                        </TableHead>
                        <TableBody>
                            {#each uploadedFiles as file}
                                <tr>
                                    <TableBodyCell>
                                        <input
                                            type="checkbox"
                                            checked={selectedFiles.includes(file)}
                                            on:change={() => toggleSelection(file)}
                                        />
                                    </TableBodyCell>
                                    <TableBodyCell>{file.name}</TableBodyCell>
                                    <TableBodyCell>{file.type}</TableBodyCell>
                                    <TableBodyCell>{formatFileSize(file.size)} </TableBodyCell>
                                    <TableBodyCell>
                                        {new Date(file.modification_time).toLocaleString()}
                                    </TableBodyCell>
                                </tr>
                            {/each}
                        </TableBody>
                    </Table>
                </div>
            </AccordionItem>
        </Accordion>
    </div>

    <div class="m-2 p-2 flex justify-end">
        <Button
            color="red"
            on:click={() => {
                showDeleteConfirmation = true;
            }}
            disabled={selectedFiles.length === 0}
        >
            {t("data.construct.delete_button")} ({selectedFiles.length})
        </Button>
    </div>

    <!-- Input for parallel_num, model_name, and domain -->
    <div class="mb-4">
        <label class="block text-sm font-medium text-gray-700">{t("data.construct.parallel_num")}</label>
        <input
                type="number"
                min="1"
                bind:value={parallelNum}
                class="mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring focus:ring-indigo-200 focus:ring-opacity-50"
        />
    </div>
    <div class="mb-4">
        <label class="block text-sm font-medium text-gray-700">{t("data.construct.sk")}</label>
        {#each Array(parallelNum) as _, i}
            <input
                    type="text"
                    placeholder={`SK ${i + 1}`}
                    bind:value={SKs[i]}
                    class="mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring focus:ring-indigo-200 focus:ring-opacity-50"
            />
        {/each}
    </div>

    {#if errorModalVisible}
        <div class="fixed inset-0 z-50 flex items-center justify-center bg-gray-800 bg-opacity-50">
            <div class="bg-white p-6 rounded shadow-lg w-1/3 text-center">
                <p class="text-lg font-medium mb-4">{errorMessage}</p>
            </div>
        </div>
    {/if}

    <div class="mb-4">
        <label class="block text-sm font-medium text-gray-700">{t("data.construct.ak")}</label>
        {#each Array(parallelNum) as _, i}
            <input
                    type="text"
                    placeholder={`AK ${i + 1}`}
                    bind:value={AKs[i]}
                    class="mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring focus:ring-indigo-200 focus:ring-opacity-50"
            />
        {/each}
    </div>
    <!-- Input field for savePath -->
    <div class="mb-4">
        <label class="block text-sm font-medium text-gray-700">{t("data.construct.save_path")}</label>
        <input
                type="text"
                bind:value={savePath}
                placeholder={t("data.construct.save_path_placeholder")}
                class="mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring focus:ring-indigo-200 focus:ring-opacity-50"
        />
    </div>

    <div class="mb-4">
        <label class="block text-sm font-medium text-gray-700">{t("data.construct.model_name")}</label>
        <input
                type="text"
                bind:value={modelName}
                class="mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring focus:ring-indigo-200 focus:ring-opacity-50"
        />
    </div>
    <div class="mb-4">
        <label class="block text-sm font-medium text-gray-700">{t("data.construct.domain")}</label>
        <input
                type="text"
                bind:value={domain}
                class="mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring focus:ring-indigo-200 focus:ring-opacity-50"
        />
    </div>


    <!-- Button for generating QA pairs -->
    <Button
            color="blue"
            on:click={generateQAPairs}
            disabled={selectedFiles.length === 0 || !validateSKAK()}
    >
        {t("data.construct.generate_button")}
    </Button>
    {#if showDeleteConfirmation}
        <!-- Confirm Delete Modal -->
        <div class="fixed inset-0 z-50 flex justify-center items-center bg-gray-800 bg-opacity-50">
            <div class="bg-white p-6 rounded-lg shadow-lg w-1/3">
                <h3 class="text-xl font-bold mb-4">{t("data.uploader.delete_confirmation_title")}</h3>
                <p class="mb-4">
                    {t("data.uploader.delete_confirmation_message", { count: selectedFiles.length })}
                </p>
                <div class="flex justify-end gap-3">
                    <Button color="red" on:click={deleteSelectedFiles}>
                        {t("data.uploader.delete_confirm_button")}
                    </Button>
                    <Button color="gray" on:click={() => showDeleteConfirmation = false}>
                        {t("data.uploader.delete_cancel_button")}
                    </Button>
                </div>
            </div>
        </div>
    {/if}
</div>
