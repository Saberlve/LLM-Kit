<script>
    import ActionPageTitle from '../components/ActionPageTitle.svelte'; // Assuming this component exists
    import { Accordion, AccordionItem } from 'flowbite-svelte'; // Assuming flowbite-svelte is used
    import { Table, TableHead, TableHeadCell, TableBody, TableBodyCell } from 'flowbite-svelte'; // Assuming flowbite-svelte is used
    import { Button } from 'flowbite-svelte'; // Assuming flowbite-svelte is used
    import { Progressbar } from 'flowbite-svelte'; // Assuming flowbite-svelte is used
    import { Modal } from 'flowbite-svelte'; // Assuming flowbite-svelte is used
    import { Dropzone } from 'flowbite-svelte'; // Assuming flowbite-svelte is used, though not directly used in the final output

    // Mock translation function - replace with your actual i18n implementation
    const t = (key) => {
        const translations = {
            "data.uploader.title": "Data Uploader",
            "data.uploader.uploaded_files": "Uploaded Files",
            "data.uploader.parse_button": "Parse",
            "data.uploader.delete_button": "Delete",
            "data.uploader.parse_status": "Parse Status",
            "data.uploader.completed": "Completed",
            "data.uploader.failed": "Failed",
            "data.uploader.click": "Click to upload",
            "data.uploader.or": " or ",
            "data.uploader.p1": "browse",
            "data.uploader.p2": " your files",
            "data.uploader.uploading": "Uploading files...",
            "data.uploader.delete_confirmation_title": "Delete Confirmation",
            "data.uploader.delete_confirmation_message": "Are you sure you want to delete this file?",
            "data.uploader.delete_confirm_button": "Yes, delete",
            "data.uploader.delete_cancel_button": "Cancel",
            "deduplication.zone": "Deduplication Zone",
            "quality_eval.parallel_num": "Parallel Number",
            "quality_eval.AK": "API Key",
            "quality_eval.SK": "Secret Key",
            "quality_eval.optional": "Optional",
            "quality_eval.model_name": "Model Name",
            "quality_eval.name": "Name",
            "quality_eval.des": "Description",
            "quality_eval.similarity_rate": "Similarity Rate",
            "quality_eval.coverage_rate": "Coverage Rate",
            "quality_eval.max_attempts": "Max Attempts",
            "data.uploader.parsed": "Parsed",
            "data.uploader.processed": "Processed",
            "data.uploader.pending": "Pending"
        };
        return translations[key] || key;
    };

    let errorMessage = null;
    let uploadedFiles = []; // Removed actual file data
    let uploaded_file_heads = ["Filename", "Type", "Size", "Created At", "Status"]; // Removed Action headers
    let showDeleteConfirmation = false;
    let fileToDelete = null;

    // Configuration variables
    let parallel_num = 1;
    let api_keys = [""]; // Initialize with one empty API Key input
    let secret_keys = [""]; // Initialize with one empty Secret Key input
    let modelname = "option1"; // Default model name
    let name = "";
    let description = "";
    let similarity_rate = 0.8;
    let coverage_rate = 0.9;
    let max_attempts = 3;

    const modelOptions = [
        { value: 'option1', label: 'Option 1' },
        { value: 'option2', label: 'Option 2' },
        { value: 'option3', label: 'Option 3' },
    ];

    // Removed file handling functions (dropHandle, changeHandle, formatFileSize, handleParseButtonClick, handleDeleteButtonClick, confirmDelete, cancelDelete)

</script>

<ActionPageTitle returnTo={"/data"} title={t("data.uploader.title")} />


<div class="w-full flex flex-col">
    {#if errorMessage}
        <div class="m-4 p-4 bg-red-100 border border-red-400 text-red-700 rounded">
            {errorMessage}
        </div>
    {/if}
    <div class="m-2">
        <Accordion>
            <AccordionItem open={true}>
                <span slot="header">{t("data.uploader.uploaded_files")}</span>
                <div class="overflow-x-auto" style="max-height: 600px;">
                    <Table striped={true}>
                        <TableHead>
                            {#each uploaded_file_heads as head}
                                <TableHeadCell>{head}</TableHeadCell>
                            {/each}
                        </TableHead>
                        <TableBody>
                            {#each uploadedFiles as file}
                                <tr>
                                    <TableBodyCell  style="overflow-x: auto; white-space: nowrap; max-width: 300px;">
                                        <div style="overflow-x: auto; white-space: nowrap;">{file.filename}</div>
                                    </TableBodyCell>
                                    <TableBodyCell>{file.file_type || file.mime_type}</TableBodyCell>
                                    <TableBodyCell>{file.size}</TableBodyCell>
                                    <TableBodyCell>{file.created_at}</TableBodyCell>
                                    <TableBodyCell>
                                        {file.status === 'parsed' ? t("data.uploader.parsed") : (file.status === 'processed' ? t("data.uploader.processed") : t("data.uploader.pending"))}
                                    </TableBodyCell>
                                </tr>
                                {#if file.parseStatus}
                                    <tr>
                                        <td colspan="7">
                                            <div class="flex flex-row items-center gap-2">
                                                <span>{t("data.uploader.parse_status")}: {file.parseStatus}</span>
                                                {#if file.parseStatus === 'processing'}
                                                    <Progressbar progress={file.parseProgress} size="sm" />
                                                {:else if file.parseStatus === 'completed'}
                                                    <span class="text-green-500">({t("data.uploader.completed")})</span>
                                                {:else if file.parseStatus === 'failed'}
                                                    <span class="text-red-500">({t("data.uploader.failed")})</span>
                                                {/if}
                                            </div>
                                        </td>
                                    </tr>
                                {/if}
                            {/each}
                        </TableBody>
                    </Table>
                </div>
            </AccordionItem>
        </Accordion>
    </div>

    <div class="m-2">
        <Accordion>
            <AccordionItem open={true}>
                <span slot="header">{t("deduplication.zone")}</span>
                <div class="justify-end items-center text-black">
                    <div class="m-2 p-2">
                        <span>{t("quality_eval.parallel_num")}</span>
                        <input
                                type="number"
                                id="parallel_num"
                                aria-describedby="helper-text-explanation"
                                class="bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white dark:focus:ring-blue-500 dark:focus:border-blue-500"
                                style="width: 100px;"
                                bind:value={parallel_num}
                                min="1"
                        />
                    </div>

                    {#each api_keys as api_key, index}
                        <div class="m-2 p-2">
                            <span>{t("quality_eval.AK") + " " + (index + 1)}</span>
                            <input
                                    type="text"
                                    id="API KEY-{index}"
                                    aria-describedby="helper-text-explanation"
                                    class="bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white dark:focus:ring-blue-500 dark:focus:border-blue-500"
                                    style="width: 300px;"
                                    bind:value={api_keys[index]}
                            />
                        </div>
                    {/each}

                    {#each secret_keys as secret_key, index}
                        <div class="m-2 p-2">
                            <span>{t("quality_eval.SK") + " " + (index + 1)}</span>
                            <input
                                    id="SCERET KEY-{index}"
                                    type="text"
                                    aria-describedby="helper-text-explanation"
                                    class="bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white dark:focus:ring-blue-500 dark:focus:border-blue-500"
                                    style="width: 300px;"
                                    bind:value={secret_keys[index]}
                                    placeholder={t("quality_eval.optional")}
                            />
                        </div>
                    {/each}
                    <div class="m-2 p-2">
                        <span>{t("quality_eval.model_name")}</span>
                        <select
                                id="model-name-select"
                                class={`bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white dark:focus:ring-blue-500 dark:focus:border-blue-500`}
                                bind:value={modelname}
                        >
                            {#each modelOptions as option}
                                <option value={option.value}>{option.label}</option>
                            {/each}
                        </select>
                    </div>
                    <div class="m-2 p-2">
                        <span>{t("quality_eval.name")}</span>
                        <input
                                type="text"
                                aria-describedby="helper-text-explanation"
                                class={`bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white dark:focus:ring-blue-500 dark:focus:border-blue-500`}
                                bind:value={name}
                        />
                    </div>

                    <div class="m-2 p-2">
                        <span>{t("quality_eval.des")}</span>
                        <input
                                type="text"
                                aria-describedby="helper-text-explanation"
                                class={`bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white dark:focus:ring-blue-500 dark:focus:border-blue-500`}
                                bind:value={description}
                        />
                    </div>

                    <div class="w-full flex flex-row">
                        <div class="m-2 p-2">
                            <span>{t("quality_eval.similarity_rate")}</span>
                        </div>
                        <div class="w-7/12 flex-row">
                            <div class="relative w-full mx-2">
                                <input
                                        type="range"
                                        bind:value={similarity_rate}
                                        min={0}
                                        max={1}
                                        step={0.01}
                                        class="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer dark:bg-gray-700"
                                />
                                <span
                                        class="text-sm text-gray-500 dark:text-gray-400 absolute start-0 -bottom-6"
                                >0</span
                                >
                                <span
                                        class="text-sm text-gray-500 dark:text-gray-400 absolute end-0 -bottom-6"
                                >1</span
                                >
                            </div>
                        </div>
                        <div class="mx-8">
                            <input
                                    type="number"
                                    aria-describedby="helper-text-explanation"
                                    class={`bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white dark:focus:ring-blue-500 dark:focus:border-blue-500`}
                                    bind:value={similarity_rate}
                                    min={0}
                                    max={1}
                                    step={0.001}
                            />
                        </div>
                    </div>

                    <div class="w-full flex flex-row">
                        <div class="m-2 p-2">
                            <span>{t("quality_eval.coverage_rate")}</span>
                        </div>
                        <div class="w-7/12 flex-row">
                            <div class="relative w-full mx-2">
                                <input
                                        type="range"
                                        bind:value={coverage_rate}
                                        min={0}
                                        max={1}
                                        step={0.01}
                                        class="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer dark:bg-gray-700"
                                />
                                <span
                                        class="text-sm text-gray-500 dark:text-gray-400 absolute start-0 -bottom-6"
                                >0</span
                                >
                                <span
                                        class="text-sm text-gray-500 dark:text-gray-400 absolute end-0 -bottom-6"
                                >1</span
                                >
                            </div>
                        </div>
                        <div class="mx-8">
                            <input
                                    type="number"
                                    aria-describedby="helper-text-explanation"
                                    class={`bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white dark:focus:ring-blue-500 dark:focus:border-blue-500`}
                                    bind:value={coverage_rate}
                                    min={0}
                                    max={1}
                                    step={0.001}
                            />
                        </div>
                    </div>

                    <div class="m-2 p-2">
                        <span>{t("quality_eval.max_attempts")}</span>
                        <input
                                type="number"
                                id="max_attempts_number"
                                aria-describedby="helper-text-explanation"
                                class="bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white dark:focus:ring-blue-500 dark:focus:border-blue-500"
                                style="width: 100px;"
                                bind:value={max_attempts}
                                min="1"
                                max="10"
                        />
                    </div>
            </AccordionItem>
        </Accordion>
    </div>
    content_copy
    download
    Use code with caution.
</div>