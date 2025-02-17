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
    import { goto } from '$app/navigation';
    const dispatch = createEventDispatcher();

    const t: any = getContext("t");
    let errorMessage = null;
    let uploadedFiles = [];
    let selectedFiles = [];
    let selectedFiles1 = [];
    let domain1 = '';
    let showDeleteConfirmation = false;
    let filesLoaded = false;
    let successMessage = null; // Remove global success message for generation
    let parallelNum = 1;
    let parallelNum1 = 1;
    let domain = '';
    let savePath = '';
    let selectedModel = 'erine';
    $: parallelNum = parseInt(String(parallelNum), 10) || 1;
    $: parallelNum1 = parseInt(String(parallelNum1), 10) || 1;
    $: numSKAKInputs = parallelNum;
    $: numSKAKInputs1 = parallelNum1;
    $: updatedSKs = [...Array(numSKAKInputs).keys()].map(() => '');

    let modelOptions = [
        { name: 'erine', secretKeyRequired: true },
        { name: 'flash', secretKeyRequired: false },
        { name: 'lite', secretKeyRequired: false },
        { name: 'qwen', secretKeyRequired: false },
    ];
    let SKs = [];
    let AKs = [];
    let SKs1 = [];
    let AKs1 = [];
    let errorModalVisible = false;
    let errorTimeoutId: NodeJS.Timeout | null = null;
    const errorDuration = 500;
    $: showSKInputs = (selectedModel =='erine');
    $: showSKInputs1 = (selectedModel =='erine');

    let uploaded_file_heads = [t("data.construct.filename"),
        t("data.uploader.file_type"),
        t("data.uploader.size"),
        t("data.uploader.created_at"),
        t("data.construct.upload_status")
    ];

    let selectAllChecked = false;
    $: selectedFiles = selectedFiles;
    $: selectedFiles1= selectedFiles;
    let isGeneratingQA = false;
    let isGeneratingCOT = false;


    // Function to toggle selection of a single file
    const toggleSelection = (file) => {
        console.log("Toggling selection for", file.name);
        selectedFiles = selectedFiles.includes(file)
            ? selectedFiles.filter(f => f !== file)
            : [...selectedFiles, file];
        selectedFiles1 = selectedFiles; // sync selectedFiles1 with selectedFiles
        updateSelectAllCheckbox(); // Update the "select all" checkbox state
    };

    // Function to toggle selection of all files
    const toggleSelectAll = () => {
        console.log("toggleSelectAll function CALLED. Current selectAllChecked:", selectAllChecked);
        console.log("Current uploadedFiles:", uploadedFiles);

        selectAllChecked = !selectAllChecked;
        console.log("selectAllChecked TOGGLED to:", selectAllChecked);

        if (selectAllChecked) {
            console.log("selectAllChecked is TRUE - Attempting to select ALL files.");
            selectedFiles = [...uploadedFiles];
            selectedFiles1 = [...uploadedFiles]; // sync selectedFiles1 with selectedFiles
            console.log("selectedFiles AFTER select ALL:", selectedFiles);
        } else {
            console.log("selectAllChecked is FALSE - Attempting to DESELECT ALL files.");
            selectedFiles = [];
            selectedFiles1 = []; // sync selectedFiles1 with selectedFiles
            console.log("selectedFiles AFTER deselect ALL files.");
        }

        updateSelectAllCheckbox();
        console.log("After updateSelectAllCheckbox, selectAllChecked is:", selectAllChecked);
        console.log("Final selectedFiles after toggleSelectAll:", selectedFiles);

        // 尝试强制组件重新评估 selectedFiles
        selectedFiles = selectedFiles; // 关键行: 重新赋值 selectedFiles
        selectedFiles1 = selectedFiles1; // 关键行: 重新赋值 selectedFiles1
    };
    const updateSelectAllCheckbox = () => {
        if (!uploadedFiles.length) {
            selectAllChecked = false;
            return;
        }
        selectAllChecked = selectedFiles.length === uploadedFiles.length; // Check if all files are selected
    };


    const handleError = (error: any) => {
        let errorMessageToShow = (error.response && error.response.data && error.response.data.detail) || t("data.construct.qa_generation_network_error");
        errorModalVisible = true;
        errorMessage = errorMessageToShow;
        clearTimeout(errorTimeoutId);
        errorTimeoutId = setTimeout(() => {
            errorModalVisible = false;
            errorMessage = null;
        }, errorDuration);
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

            const filesWithStatus = await Promise.all(data.map(async (file) => {
                try {
                    const statusResponse = await axios.post('http://127.0.0.1:8000/qa/qashistory', {
                        filename: file.name
                    });
                    const statusResponse1 = await axios.post('http://127.0.0.1:8000/cot/cothistory', {
                        filename: file.name
                    });
                    return {
                        ...file,
                        status:{1:statusResponse.data.exists,2:statusResponse1.data.exists},
                        qa_status_message: null, // Initialize qa_status_message
                        cot_status_message: null // Initialize cot_status_message
                    };
                } catch (error) {
                    console.error('Error fetching status for file', file.name, error);
                    return { ...file, status:{1:-1,2:-1}, qa_status_message: null, cot_status_message: null}; // Initialize with null status message
                }
            }));


            uploadedFiles = filesWithStatus;

            updateSelectAllCheckbox(); // Update "select all" checkbox after loading files
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
            // Loop through each file and send a delete request one by one
            for (const file of selectedFiles) {
                try {
                    const response = await axios.post(
                        'http://127.0.0.1:8000/parse/delete_files',
                        { files: [file.name] }, // Send only one file name at a time
                        { headers: { "Content-Type": "application/json" } }
                    );

                    if (response.status === 200) {
                        console.log(`File ${file.name} deleted successfully`);
                    } else {
                        const errorData = await response.json();
                        console.error(`Error deleting file ${file.name}:`, response.status, errorData);
                        throw new Error(errorData.detail || `Failed to delete file ${file.name}`);
                    }
                } catch (error) {
                    console.error(`Error deleting file ${file.name}:`, error);
                    errorMessage = `Network error deleting file ${file.name}`;
                    // Optionally, you can break the loop here if you want to stop on the first error
                    // break;
                }
            }

            // After all files are processed, update the UI
            selectedFiles = [];
            selectedFiles1 = [];
            selectAllChecked = false;
            await fetchFiles();
            showDeleteConfirmation = false;

            // Clear success message after 2 seconds
            setTimeout(() => {
                successMessage = null;
            }, 2000);

        } catch (error) {
            console.error('Error during file deletion process:', error);
            errorMessage = "An error occurred during the file deletion process";
        }
    };
    const generateQAPairs = async () => {
        if (selectedFiles.length === 0) {
            errorMessage = t("data.construct.no_file_selected");
            return;
        }

        isGeneratingQA = true;


        let updatedFiles = uploadedFiles.map(file => {
            if (selectedFiles.includes(file)) {
                return {...file, qa_status_message: t("data.construct.latex_converting")}; // Set initial status for selected files
            }
            return file;
        });
        uploadedFiles = updatedFiles;

        try {
            const selectedFileNames = selectedFiles.map(f => f.name);
            for (let i = 0; i < selectedFileNames.length; i++) {
                const filename = selectedFileNames[i];
                let currentFileIndex = uploadedFiles.findIndex(file => file.name === filename);


                const toTexRequestData = {
                    filename: filename,
                    content: "",
                    save_path: savePath || selectedFileNames[0],
                    SK: showSKInputs ? SKs : new Array(AKs.length).fill('a'),
                    AK: AKs.length > 0 ? AKs : [],
                    parallel_num: parallelNum,
                    model_name: selectedModel,
                };

                try {
                    const toTexResponse = await axios.post('http://127.0.0.1:8000/to_tex/to_tex', toTexRequestData, {
                        headers: {
                            'Content-Type': 'application/json',
                        }
                    });

                    if (toTexResponse.status !== 200) {
                        const errorData = await toTexResponse.json();
                        const message = errorData.detail || t('data.construct.latex_conversion_failed');
                        uploadedFiles = uploadedFiles.map((file, index) => index === currentFileIndex ? {...file, qa_status_message: message} : file);
                        continue; // Skip to next file if to_tex fails
                    }

                } catch (toTexError) {
                    console.error('Error converting to LaTeX:', toTexError);
                    const message = t('data.construct.latex_conversion_network_error');
                    uploadedFiles = uploadedFiles.map((file, index) => index === currentFileIndex ? {...file, qa_status_message: message} : file);
                    continue; // Skip to next file if to_tex network error
                }


                const requestData = {
                    filename: filename,
                    save_path: savePath || selectedFileNames[0],
                    SK: showSKInputs ? SKs  :new Array(AKs.length).fill('a'), //Handle empty array
                    AK: AKs.length > 0 ? AKs : [],  // Ensure 'files' is an array
                    parallel_num: parallelNum,
                    model_name: selectedModel,
                    domain: domain,
                };

                uploadedFiles = uploadedFiles.map((file, index) => index === currentFileIndex ? {...file, qa_status_message:  t("data.construct.qa_generating")} : file);


                try {
                    const response = await axios.post('http://127.0.0.1:8000/qa/generate_qa', requestData, {
                        headers: {
                            'Content-Type': 'application/json',
                        }
                    });

                    if (response.status === 200) {
                        dispatch('qaGenerated', response.data);
                        uploadedFiles = uploadedFiles.map((file, index) => index === currentFileIndex ? {...file, qa_status_message: t("data.construct.qa_generated_success"), status: {...file.status, 1: 1}} : file);

                        selectedFiles = selectedFiles.filter(f => f.name !== filename); // remove this file from selectedFiles after success
                        selectedFiles1 = selectedFiles; // sync selectedFiles1 with selectedFiles
                        successMessage = t("data.construct.qa_all_generated_success"); // Global success message for QA
                        setTimeout(() => {
                            successMessage = null;
                        }, 2000);


                    } else {
                        const errorData = await response.json();
                        const message = errorData.detail || t('data.construct.qa_generation_failed');
                        uploadedFiles = uploadedFiles.map((file, index) => index === currentFileIndex ? {...file, qa_status_message: message} : file);
                        await fetchFiles(); // Refresh file status in case backend status is not correctly updated.
                        continue;  // Continue to next file even if QA generation fails for one
                    }

                } catch (error) {
                    console.error('Error generating QA pairs:', error);
                    const message = t('data.construct.qa_generation_network_error');
                    uploadedFiles = uploadedFiles.map((file, index) => index === currentFileIndex ? {...file, qa_status_message: message} : file);
                    await fetchFiles(); // Refresh file status in case backend status is not correctly updated.
                    continue; // Continue to next file even if QA generation fails for one
                }
            }
            await fetchFiles(); // Refresh file status after all files are processed to update status based on backend.
        } catch (error) {
            // This catch block should handle errors outside of the file processing loop
            console.error('Unexpected error in generateQAPairs:', error);
            handleError(error);
            errorMessage = t('data.construct.unexpected_error'); //Generic error
        } finally {
            isGeneratingQA = false;
            // successMessage = null; // Clear global success message after all files are processed (or errors occurred) - No global success message anymore
        }
    };

    const handleModelChange = (event: Event) => {
        const selectedOption = event.target as HTMLSelectElement;
        selectedModel = selectedOption.value;
        SKs = [];
        AKs = [];
        SKs1 = [];
        AKs1 = [];
        parallelNum = 1;
    };

    const deleteQaFile = async (filename: string) => {
        try {
            const response = await axios.post('http://127.0.0.1:8000/qa/delete_file', {
                filename: filename
            });
            if (response.status === 200) {
                successMessage = t("data.construct.qa_delete_success");
                setTimeout(() => {
                    successMessage = null;
                }, 2000);
                await fetchFiles(); // Refresh file list to update status
            } else {
                const errorData = await response.json();
                errorMessage = errorData.detail || t("data.construct.qa_delete_failed");
            }
        } catch (error) {
            console.error('Error deleting QA file:', error);
            handleError(error);
            errorMessage = t("data.construct.qa_delete_network_error");
        }
    };

    const previewQaFile = (filename: string) => {
        goto(`/construct/qa-preview?filename=${filename}`); // Navigate to preview page
    };

    const previewcotFile = (filename: string) => {
        goto(`/construct/cot-preview?filename=${filename}`); // Navigate to preview page
    };

    const previewRawFile = (filename: string) => {
        goto(`/construct/raw-preview?filename=${filename}`); // Navigate to raw preview page
    };

    // COT Functions
    const generateCOTs = async () => {
        if (selectedFiles1.length === 0) {
            errorMessage = t("data.construct.no_file_selected");
            return;
        }

        isGeneratingCOT = true;

        let updatedFiles = uploadedFiles.map(file => {
            if (selectedFiles1.includes(file)) {
                return {...file, cot_status_message: t("data.construct.latex_converting")}; // Set initial status for selected files
            }
            return file;
        });
        uploadedFiles = updatedFiles;


        try {
            const selectedFileNames = selectedFiles1.map(f => f.name);
            for (let i = 0; i < selectedFileNames.length; i++) {
                const filename = selectedFileNames[i];
                let currentFileIndex = uploadedFiles.findIndex(file => file.name === filename);


                const toTexRequestData = {
                    filename: filename,
                    content: "",
                    save_path: savePath || selectedFileNames[0],
                    SK: showSKInputs ? SKs1 : new Array(AKs1.length).fill('a'),
                    AK: AKs1.length > 0 ? AKs1 : [],
                    parallel_num: parallelNum,
                    model_name: selectedModel,
                };

                try {
                    const toTexResponse = await axios.post('http://127.0.0.1:8000/to_tex/to_tex', toTexRequestData, {
                        headers: {
                            'Content-Type': 'application/json',
                        }
                    });

                    if (toTexResponse.status !== 200) {
                        const errorData = await toTexResponse.json();
                        const message = errorData.detail || t('data.construct.latex_conversion_failed');
                        uploadedFiles = uploadedFiles.map((file, index) => index === currentFileIndex ? {...file, cot_status_message: message} : file);
                        continue; // Skip to next file if to_tex fails
                    }

                } catch (toTexError) {
                    console.error('Error converting to LaTeX:', toTexError);
                    const message = t('data.construct.latex_conversion_network_error');
                    uploadedFiles = uploadedFiles.map((file, index) => index === currentFileIndex ? {...file, cot_status_message: message} : file);
                    continue; // Skip to next file if to_tex network error
                }


                const requestData1 = {
                    filename: filename,
                    save_path: savePath || selectedFileNames[0],
                    SK: showSKInputs ? SKs1  :new Array(AKs1.length).fill('a'), //Handle empty array
                    AK: AKs1.length > 0 ? AKs1 : [],  // Ensure 'files' is an array
                    parallel_num: parallelNum1,
                    model_name: selectedModel,
                    domain: domain1,
                };

                uploadedFiles = uploadedFiles.map((file, index) => index === currentFileIndex ? {...file, cot_status_message: t("data.construct.cot_generating")} : file);


                try {
                    const response = await axios.post('http://127.0.0.1:8000/cot/generate', requestData1, {
                        headers: {
                            'Content-Type': 'application/json',
                        }
                    });

                    if (response.status === 200) {
                        dispatch('cotGenerated', response.data); // Dispatch a new event for COT if needed
                        uploadedFiles = uploadedFiles.map((file, index) => index === currentFileIndex ? {...file, cot_status_message: t("data.construct.cot_generated_success"), status: {...file.status, 2: 1}} : file);
                        selectedFiles1 = selectedFiles1.filter(f => f.name !== filename);
                        selectedFiles = selectedFiles1; // sync selectedFiles with selectedFiles1
                        successMessage = t("data.construct.cot_all_generated_success"); // Global success message for COT
                        setTimeout(() => {
                            successMessage = null;
                        }, 2000);


                    } else {

                        const errorData = await response.json();
                        const message = errorData.detail || t('data.construct.cot_generation_failed');
                        uploadedFiles = uploadedFiles.map((file, index) => index === currentFileIndex ? {...file, cot_status_message: message} : file);
                        await fetchFiles(); // Refresh file status in case backend status is not correctly updated.
                        continue;
                    }
                } catch (error) {
                    console.error('Error generating COT:', error);
                    handleError(error);
                    const message = t('data.construct.cot_generation_network_error');
                    uploadedFiles = uploadedFiles.map((file, index) => index === currentFileIndex ? {...file, cot_status_message: message} : file);
                    await fetchFiles(); // Refresh file status in case backend status is not correctly updated.
                    continue;
                }
            }
            await fetchFiles(); // Refresh file status after all files are processed to update status based on backend.
        } catch (error) {
            console.error('Unexpected error in generateCOTs:', error);
            handleError(error);
            errorMessage = t('data.construct.unexpected_error');
        } finally {
            isGeneratingCOT = false;
            // successMessage = null; // Clear global success message after all files are processed (or errors occurred) - No global success message anymore
        }
    };


    const deleteCotFile = async (filename: string) => {
        try {
            const response = await axios.delete(`http://127.0.0.1:8000/cot/file/${filename}`); // Using DELETE endpoint
            if (response.status === 200) {
                successMessage = t("data.construct.cot_delete_success");
                setTimeout(() => {
                    successMessage = null;
                }, 2000);
                await fetchFiles();
            } else {
                const errorData = await response.json();
                errorMessage = errorData.detail || t("data.construct.cot_delete_failed");
            }
        } catch (error) {
            console.error('Error deleting COT file:', error);
            handleError(error);
            errorMessage = t("data.construct.cot_delete_network_error");
        }
    };

    const previewCotFile = async (filename: string) => {
        try {
            const response = await axios.get(`http://127.0.0.1:8000/cot/content/${filename}`);
            if (response.status === 200) {
                const cotContent = response.data.data;
                goto(`/construct/cot-preview?filename=${filename}&content=${encodeURIComponent(cotContent)}`); // Pass content as query param
            } else {
                const errorData = await response.json();
                errorMessage = errorData.detail || t("data.construct.cot_preview_failed");
            }
        } catch (error) {
            console.error('Error previewing COT file:', error);
            handleError(error);
            errorMessage = t("data.construct.cot_preview_network_error");
        }
    };


</script>

<ActionPageTitle returnTo="/construct/" title={t("data.construct.title")} />

<div class="w-full flex flex-col">
    {#if errorMessage}
        <div class="m-4 p-4 bg-red-100 border border-red-400 text-red-700 rounded">
            {errorMessage}
        </div>
    {/if}

    {#if successMessage}
        <!-- 显示成功的提示消息 -->
        <div class="m-4 p-4 bg-green-100 border border-green-400 text-green-700 rounded">
            <strong class="font-bold">{t("general.success")}!</strong> {successMessage}
        </div>
    {/if}

    <div class="m-2">
        <Accordion>
            <AccordionItem open={false}>
                <span slot="header">{t("data.construct.main_settings")}</span>
                <div class="p-4 space-y-4">
                    <Accordion>
                        <AccordionItem open={true}>
                            <span slot="header">{t("data.construct.uploaded_files")}</span>
                            <div class="overflow-x-auto max-h-[250px]">
                                <Table striped={false}>
                                    <TableHead>
                                        <TableHeadCell>
                                            <input type="checkbox" bind:checked={selectAllChecked} on:change={toggleSelectAll} />
                                        </TableHeadCell>
                                        {#each uploaded_file_heads as head}
                                            <TableHeadCell>{head.toLowerCase().replace(' ', '_')}</TableHeadCell>
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
                                                <TableBodyCell>
                                                    <Button color="blue" size="xs" on:click={() => previewRawFile(file.name)}>
                                                        {file.name}
                                                    </Button>
                                                </TableBodyCell>
                                                <TableBodyCell>{file.type}</TableBodyCell>
                                                <TableBodyCell>{formatFileSize(file.size)} </TableBodyCell>
                                                <TableBodyCell>
                                                    {new Date(file.modification_time).toLocaleString()}
                                                </TableBodyCell>
                                                <TableBodyCell>
                                                    {#if file.status[1]===1 }
                                                        <Button color="green" size="xs" on:click={() => previewQaFile(file.name)}>
                                                            {t("data.construct.status_generated")}
                                                        </Button>
                                                    {:else}
                                                        <span class="status-indicator"
                                                              class:status-generating={file.status[1]===0}
                                                              class:status-unknown={file.status[1]===-1}>
                                                            {#if file.status[1] === 0}
                                                                {t("data.construct.status_generating")}
                                                            {:else}
                                                                {t("data.construct.status_unknown")}
                                                            {/if}
                                                        </span>
                                                    {/if}
                                                    {#if file.status[1]===1}
                                                        <Button color="red" size="xs" on:click={() => deleteQaFile(file.name)}>
                                                            {t("data.construct.delete_qa_button")}
                                                        </Button>
                                                    {/if}
                                                </TableBodyCell>
                                            </tr>
                                            {#if file.qa_status_message}
                                                <tr>
                                                    <TableBodyCell colspan="6" class="text-sm italic text-gray-500 text-center">
                                                        <span class="status-message"
                                                              class:status-converting={file.qa_status_message === t("data.construct.latex_converting")}
                                                              class:status-generating-qa={file.qa_status_message === t("data.construct.qa_generating")}
                                                              class:status-generated-success={file.qa_status_message === t("data.construct.qa_generated_success")}
                                                              class:status-generation-failed={
                                                                  file.qa_status_message === t('data.construct.qa_generation_failed') ||
                                                                  file.qa_status_message === t('data.construct.qa_generation_network_error') ||
                                                                  file.qa_status_message === t('data.construct.latex_conversion_failed') ||
                                                                  file.qa_status_message === t('data.construct.latex_conversion_network_error')
                                                              }>
                                                            {file.qa_status_message}
                                                        </span>
                                                    </TableBodyCell>
                                                </tr>
                                            {/if}
                                        {/each}
                                    </TableBody>
                                </Table>
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
                        </AccordionItem>
                        <AccordionItem open={false}>
                            <span slot="header">{t("data.construct.qa_generation_settings")}</span>
                            <div class="p-4 space-y-4">
                                <div>
                                    <label class="block text-sm font-medium text-gray-700">{t("data.construct.parallel_num")}</label>
                                    <input
                                            type="number"
                                            min="1"
                                            bind:value={parallelNum}
                                            class="mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring focus:ring-indigo-200 focus:ring-opacity-50"
                                    />
                                </div>

                                <div>
                                    <label class="block text-sm font-medium text-gray-700">{t("data.construct.save_path")}</label>
                                    <input
                                            type="text"
                                            bind:value={savePath}
                                            placeholder={t("data.construct.save_path_placeholder")}
                                            class="mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring focus:ring-indigo-200 focus:ring-opacity-50"
                                    />
                                </div>

                                <div>
                                    <label class="block text-sm font-medium text-gray-700">{t("data.construct.model_name")}</label>
                                    <select bind:value={selectedModel} on:change={handleModelChange}
                                            class="mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring focus:ring-indigo-200 focus:ring-opacity-50">
                                        {#each modelOptions as option}
                                            <option value={option.name}>{t(`data.construct.${option.name}`)}</option>
                                        {/each}
                                    </select>
                                </div>


                                {#if showSKInputs}
                                    <div>
                                        <label class="block text-sm font-medium text-gray-700">{t("data.construct.sk")}</label>
                                        {#each Array(numSKAKInputs) as _, i}
                                            <input
                                                    type="text"
                                                    placeholder={`SK ${i + 1}`}
                                                    bind:value={SKs[i]}
                                                    class="mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring focus:ring-indigo-200 focus:ring-opacity-50"
                                            />
                                        {/each}
                                    </div>
                                {/if}

                                <div>
                                    <label class="block text-sm font-medium text-gray-700">{t("data.construct.ak")}</label>
                                    {#each Array(numSKAKInputs) as _, i}
                                        <input
                                                type="text"
                                                placeholder={`AK ${i + 1}`}
                                                bind:value={AKs[i]}
                                                class="mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring focus:ring-indigo-200 focus:ring-opacity-50"
                                        />
                                    {/each}
                                </div>
                                <div>
                                    <label class="block text-sm font-medium text-gray-700">{t("data.construct.domain")}</label>
                                    <input
                                            type="text"
                                            bind:value={domain}
                                            class="mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring focus:ring-indigo-200 focus:ring-opacity-50"
                                    />
                                </div>


                                <Button
                                        color="blue"
                                        on:click={generateQAPairs}
                                        disabled={selectedFiles.length === 0 || isGeneratingQA}
                                >
                                    {#if isGeneratingQA}
                                        {t("data.construct.generating_button_text")}
                                    {:else}
                                        {t("data.construct.generate_button")}
                                    {/if}
                                </Button>
                            </div>
                        </AccordionItem>
                    </Accordion>
                </div>
            </AccordionItem>
        </Accordion>
    </div>


    {#if errorModalVisible}
        <div class="fixed inset-0 z-50 flex items-center justify-center bg-gray-800 bg-opacity-50">
            <div class="bg-white p-6 rounded shadow-lg w-1/3 text-center">
                <p class="text-lg font-medium mb-4">{errorMessage}</p>
            </div>
        </div>
    {/if}


    {#if showDeleteConfirmation}

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

<div class="w-full flex flex-col">
    {#if errorMessage}
        <div class="m-4 p-4 bg-red-100 border border-red-400 text-red-700 rounded">
            {errorMessage}
        </div>
    {/if}

    {#if successMessage}
        <!-- 显示成功的提示消息 -->
        <div class="m-4 p-4 bg-green-100 border border-green-400 text-green-700 rounded">
            <strong class="font-bold">{t("general.success")}!</strong> {successMessage}
        </div>
    {/if}

    <div class="m-2">
        <Accordion>
            <AccordionItem open={false}>
                <span slot="header">{t("data.construct.cotgenerate")}</span>
                <div class="p-4 space-y-4">
                    <Accordion>
                        <AccordionItem open={false}>
                            <span slot="header">{t("data.construct.uploaded_files")}</span>
                            <div class="overflow-x-auto max-h-[250px]">
                                <Table striped={false}>
                                    <TableHead>
                                        <TableHeadCell>
                                            <input type="checkbox" bind:checked={selectAllChecked} on:change={toggleSelectAll} />
                                        </TableHeadCell>
                                        {#each uploaded_file_heads as head}
                                            <TableHeadCell>{head.toLowerCase().replace(' ', '_')}</TableHeadCell>
                                        {/each}
                                    </TableHead>
                                    <TableBody>
                                        {#each uploadedFiles as file}
                                            <tr>
                                                <TableBodyCell>
                                                    <input
                                                            type="checkbox"
                                                            checked={selectedFiles1.includes(file)}
                                                            on:change={() => toggleSelection(file)}
                                                    />
                                                </TableBodyCell>
                                                <TableBodyCell>
                                                    <Button color="blue" size="xs" on:click={() => previewRawFile(file.name)}>
                                                        {file.name}
                                                    </Button>
                                                </TableBodyCell>
                                                <TableBodyCell>{file.type}</TableBodyCell>
                                                <TableBodyCell>{formatFileSize(file.size)} </TableBodyCell>
                                                <TableBodyCell>
                                                    {new Date(file.modification_time).toLocaleString()}
                                                </TableBodyCell>
                                                <TableBodyCell>
                                                    {#if file.status[2]===1 }
                                                        <Button color="green" size="xs" on:click={() => previewcotFile(file.name)}>
                                                            {t("data.construct.status_generated")}
                                                        </Button>
                                                    {:else}
                                                        <span class="status-indicator"
                                                              class:status-generating={file.status[2]===0}
                                                              class:status-unknown={file.status[2]===-1}>
                                                            {#if file.status[2] === 0}
                                                                {t("data.construct.status_generating")}
                                                            {:else}
                                                                {t("data.construct.status_unknown")}
                                                            {/if}
                                                        </span>
                                                    {/if}
                                                    {#if file.status[2]===1}
                                                        <Button color="red" size="xs" on:click={() => deleteCotFile(file.name)}>
                                                            {t("data.construct.delete_qa_button")}
                                                        </Button>
                                                    {/if}
                                                </TableBodyCell>
                                            </tr>
                                            {#if file.cot_status_message}
                                                <tr>
                                                    <TableBodyCell colspan="6" class="text-sm italic text-gray-500 text-center">
                                                        <span class="status-message"
                                                              class:status-converting={file.cot_status_message === t("data.construct.latex_converting")}
                                                              class:status-generating-cot={file.cot_status_message === t("data.construct.cot_generating")}
                                                              class:status-generated-success={file.cot_status_message === t("data.construct.cot_generated_success")}
                                                              class:status-generation-failed={
                                                                  file.cot_status_message === t('data.construct.cot_generation_failed') ||
                                                                  file.cot_status_message === t('data.construct.cot_generation_network_error') ||
                                                                  file.cot_status_message === t('data.construct.latex_conversion_failed') ||
                                                                  file.cot_status_message === t('data.construct.latex_conversion_network_error')
                                                              }>
                                                            {file.cot_status_message}
                                                        </span>
                                                    </TableBodyCell>
                                                </tr>
                                            {/if}
                                        {/each}
                                    </TableBody>
                                </Table>
                            </div>
                            <div class="m-2 p-2 flex justify-end">
                                <Button
                                        color="red"
                                        on:click={() => {
                                        showDeleteConfirmation = true;
                                    }}
                                        disabled={selectedFiles1.length === 0}
                                >
                                    {t("data.construct.delete_button")} ({selectedFiles1.length})
                                </Button>
                            </div>
                        </AccordionItem>
                        <AccordionItem open={false}>
                            <span slot="header">{t("data.construct.qa_generation_settings")}</span>
                            <div class="p-4 space-y-4">
                                <div>
                                    <label class="block text-sm font-medium text-gray-700">{t("data.construct.parallel_num")}</label>
                                    <input
                                            type="number"
                                            min="1"
                                            bind:value={parallelNum1}
                                            class="mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring focus:ring-indigo-200 focus:ring-opacity-50"
                                    />
                                </div>


                                <div>
                                    <label class="block text-sm font-medium text-gray-700">{t("data.construct.model_name")}</label>
                                    <select bind:value={selectedModel} on:change={handleModelChange}
                                            class="mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring focus:ring-indigo-200 focus:ring-opacity-50">
                                        {#each modelOptions as option}
                                            <option value={option.name}>{t(`data.construct.${option.name}`)}</option>
                                        {/each}
                                    </select>
                                </div>


                                {#if showSKInputs1}
                                    <div>
                                        <label class="block text-sm font-medium text-gray-700">{t("data.construct.sk")}</label>
                                        {#each Array(numSKAKInputs1) as _, i}
                                            <input
                                                    type="text"
                                                    placeholder={`SK ${i + 1}`}
                                                    bind:value={SKs1[i]}
                                                    class="mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring focus:ring-indigo-200 focus:ring-opacity-50"
                                            />
                                        {/each}
                                    </div>
                                {/if}

                                <div>
                                    <label class="block text-sm font-medium text-gray-700">{t("data.construct.ak")}</label>
                                    {#each Array(numSKAKInputs1) as _, i}
                                        <input
                                                type="text"
                                                placeholder={`AK ${i + 1}`}
                                                bind:value={AKs1[i]}
                                                class="mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring focus:ring-indigo-200 focus:ring-opacity-50"
                                        />
                                    {/each}
                                </div>
                                <div>
                                    <label class="block text-sm font-medium text-gray-700">{t("data.construct.domain")}</label>
                                    <input
                                            type="text"
                                            bind:value={domain1}
                                            placeholder={`如: 医疗`}
                                            class="mt-1 block w-full rounded-md border border-gray-300 shadow-sm focus:border-indigo-500 focus:ring focus:ring-indigo-200 focus:ring-opacity-50"
                                    />
                                </div>


                                <Button
                                        color="blue"
                                        on:click={generateCOTs}
                                        disabled={selectedFiles1.length === 0 || isGeneratingCOT}
                                >
                                    {#if isGeneratingCOT}
                                        {t("data.construct.generating_button_text")}
                                    {:else}
                                        {t("data.construct.generate_button")}
                                    {/if}
                                </Button>
                            </div>
                        </AccordionItem>
                    </Accordion>
                </div>
            </AccordionItem>
        </Accordion>
    </div>


    {#if errorModalVisible}
        <div class="fixed inset-0 z-50 flex items-center justify-center bg-gray-800 bg-opacity-50">
            <div class="bg-white p-6 rounded shadow-lg w-1/3 text-center">
                <p class="text-lg font-medium mb-4">{errorMessage}</p>
            </div>
        </div>
    {/if}


    {#if showDeleteConfirmation}

        <div class="fixed inset-0 z-50 flex justify-center items-center bg-gray-800 bg-opacity-50">
            <div class="bg-white p-6 rounded-lg shadow-lg w-1/3">
                <h3 class="text-xl font-bold mb-4">{t("data.uploader.delete_confirmation_title")}</h3>
                <p class="mb-4">
                    {t("data.uploader.delete_confirmation_message", { count: selectedFiles.length+ selectedFiles1.length})}
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

<style>
    .space-y-4 > * + * {
        margin-top: 1rem;
    }
    .status-indicator {
        @apply px-2 py-1 text-sm rounded-full inline-block;
    }
    .status-indicator.status-generating {
        @apply bg-yellow-100 text-yellow-800;
    }
    .status-indicator.status-unknown {
        @apply bg-gray-100 text-gray-800;
    }

    .status-message {
        @apply px-2 py-1 text-sm rounded inline-block;
    }
    .status-message.status-converting {
        @apply bg-yellow-200 text-yellow-900;
    }
    .status-message.status-generating-qa, .status-message.status-generating-cot {
        @apply bg-blue-200 text-blue-900;
    }
    .status-message.status-generated-success {
        @apply bg-green-200 text-green-900;
    }
    .status-message.status-generation-failed {
        @apply bg-red-200 text-red-900;
    }

</style>
