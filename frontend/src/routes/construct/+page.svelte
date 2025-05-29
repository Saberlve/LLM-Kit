<script lang="ts">
    import ActionPageTitle from '../components/ActionPageTitle.svelte';
    import { Accordion, AccordionItem } from 'flowbite-svelte';
    import { Table, TableHead, TableHeadCell, TableBody, TableBodyCell } from 'flowbite-svelte';
    import { Button } from 'flowbite-svelte';
    import { Modal } from 'flowbite-svelte';
    import { getContext } from "svelte";
    import axios from "axios";
    import { onMount, onDestroy } from 'svelte';
    import { createEventDispatcher } from 'svelte';
    import { goto } from '$app/navigation';
    const dispatch = createEventDispatcher();

    const t: any = getContext("t");
    if (!t("construct.title")) {
        t.add({
            "construct.title": "Dataset Construction",
            "construct.main_settings": "Construction Settings",
            "construct.uploaded_files": "Parsed Files",
            "construct.filename": "Filename",
            "construct.upload_status": "Status",
            "construct.select_all": "Select All",
            "construct.deselect_all": "Deselect All",
            "construct.status_generated": "Generated",
            "construct.status_generating": "Generating...",
            "construct.status_unknown": "Not Generated",
            "construct.delete_qa_button": "Delete QA",
            "construct.delete_cot_button": "Delete COT",
            "construct.delete_button": "Delete Selected",
            "construct.latex_converting": "Converting LaTeX...",
            "construct.qa_generating": "Generating QA Pairs...",
            "construct.qa_generated_success": "QA Generation Complete",
            "construct.qa_generation_failed": "QA Generation Failed",
            "construct.qa_generation_network_error": "Network Error During QA Generation",
            "construct.latex_conversion_failed": "LaTeX Conversion Failed",
            "construct.latex_conversion_network_error": "Network Error During LaTeX Conversion",
            "construct.qa_generation_settings": "QA Generation Settings",
            "construct.cot_generation_settings": "CoT Generation Settings",
            "construct.parallel_num": "Parallel Processing Threads",
            "construct.model_name": "Model",
            "construct.erine": "ERNIE",
            "construct.flash": "Flash",
            "construct.lite": "Lite",
            "construct.qwen": "Qwen",
            "construct.sk": "Secret Key",
            "construct.ak": "Access Key",
            "construct.domain": "Domain",
            "construct.domain_placeholder": "Enter domain (optional)",
            "construct.generate_qa_button": "Generate QA Pairs",
            "construct.generating_qa": "Generating QA Pairs...",
            "construct.qa_delete_success": "QA file deleted successfully",
            "construct.qa_delete_failed": "Failed to delete QA file",
            "construct.qa_delete_network_error": "Network error deleting QA file",
            "construct.qa_preview_failed": "Failed to preview QA file",
            "construct.qa_preview_network_error": "Network error previewing QA file",
            "construct.generate_cot_button": "Generate CoT Data",
            "construct.generating_cot": "Generating CoT Data...",
            "construct.preview_title": "Preview Content",
            "construct.question": "Question",
            "construct.answer": "Answer",
            "construct.context": "Context",
            "construct.reasoning": "Reasoning",
            "construct.action": "Action",
            "construct.content": "Content",
            "construct.previous": "Previous",
            "construct.next": "Next",
            "construct.page": "Page",
            "construct.go_to": "Go to page:",
            "construct.no_content": "No content available",
            "construct.loading": "Loading...",
            "construct.raw_preview_title": "Raw Content",
            "construct.download": "Download",
            "construct.download_error": "Download failed",
            "construct.cot_delete_success": "CoT file deleted successfully",
            "construct.cot_delete_failed": "Failed to delete CoT file",
            "construct.cot_delete_network_error": "Network error deleting CoT file",
            "construct.cot_preview_failed": "Failed to preview CoT file",
            "construct.cot_preview_network_error": "Network error previewing CoT file",
            "general.close": "Close"
        });
    }
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
    let selectedModel = 'erine';
    let activeTab = 'qa'; // 添加activeTab变量，默认显示QA标签页
    
    // Add new variables for preview modal
    let previewModalOpen = false;
    let previewModalTitle = '';
    let previewContent = [];
    let previewContentType = ''; // 'qa', 'cot', or 'raw'
    let previewErrorMessage = null;
    let previewLoading = false;
    let previewCurrentPage = 1;
    let previewTotalPages = 1;
    let previewItemsPerPage = 10;
    let previewPageInput = '1';
    let previewDatasetId = '';
    let rawContent = '';

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
    let errorTimeoutId: number | null = null;
    const errorDuration = 500;
    $: showSKInputs = (selectedModel =='erine');
    $: showSKInputs1 = (selectedModel =='erine');

    let uploaded_file_heads = [t("construct.filename"),
        t("data.uploader.file_type"),
        t("data.uploader.size"),
        t("data.uploader.created_at"),
        t("construct.upload_status")
    ];

    let selectAllChecked = false;
    $: selectedFiles = selectedFiles;
    $: selectedFiles1= selectedFiles;
    let isGeneratingQA = false;
    let isGeneratingCOT = false;

    let progressIntervals: { [filename: string]: number } = {};
    // Function to toggle selection of a single file
    const toggleSelection = (file) => {
        console.log("Toggling selection for", file.name);
        selectedFiles = selectedFiles.includes(file)
            ? selectedFiles.filter(f => f !== file)
            : [...selectedFiles, file];
        selectedFiles1 = selectedFiles;
        updateSelectAllCheckbox();
    };

    const toggleSelectAll = () => {
        if (uploadedFiles.length === 0) return;

        selectAllChecked = !selectAllChecked;

        if (selectAllChecked) {

            selectedFiles = [...uploadedFiles];
            selectedFiles1 = [...uploadedFiles];
        } else {
            selectedFiles = [];
            selectedFiles1 = [];
        }

        updateSelectAllCheckbox();
    };
    const updateSelectAllCheckbox = () => {
        if (!uploadedFiles.length) {
            selectAllChecked = false;
            return;
        }
        selectAllChecked = selectedFiles.length === uploadedFiles.length;
    };


    const handleError = (error: any) => {
        let errorMessageToShow = (error.response && error.response.data && error.response.data.detail) || t("construct.qa_generation_network_error");
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
                        status: {
                            1: statusResponse.data.exists, // QA状态
                            2: statusResponse1.data.exists // COT状态
                        },
                        qa_status_message: null,
                        cot_status_message: null
                    };
                } catch (error) {
                    console.error('Error fetching status for file', file.name, error);
                    return { 
                        ...file, 
                        status: {
                            1: 0, // 初始化QA状态为未生成
                            2: 0  // 初始化COT状态为未生成
                        }, 
                        qa_status_message: null, 
                        cot_status_message: null
                    };
                }
            }));

            uploadedFiles = filesWithStatus;
            updateSelectAllCheckbox(); // Update "select all" checkbox after loading files
        } catch (error) {
            errorMessage = 'Failed to load files';
            console.error("Error fetching files:", error);
        }
    };


    //  
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
                        const errorData = response.data;
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
            errorMessage = t("construct.no_file_selected");
            return;
        }

        isGeneratingQA = true;

        let updatedFiles = uploadedFiles.map(file => {
            if (selectedFiles.includes(file)) {
                return {...file, qa_status_message: t("construct.qa_generating")}; // 直接设置状态为QA生成中
            }
            return file;
        });
        uploadedFiles = updatedFiles;

        try {
            const selectedFileNames = selectedFiles.map(f => f.name);
            
            // 逐个文件处理
            for (let i = 0; i < selectedFileNames.length; i++) {
                const filename = selectedFileNames[i];
                let currentFileIndex = uploadedFiles.findIndex(file => file.name === filename);
                
                try {
                    // 直接发送QA生成请求，后端会自动处理LaTeX转换
                    const requestData = {
                        filename: filename,
                        SK: showSKInputs ? SKs : new Array(AKs.length).fill('a'),
                        AK: AKs.length > 0 ? AKs : [],
                        parallel_num: parallelNum,
                        model_name: selectedModel,
                        domain: domain,
                    };
                    
                    uploadedFiles = uploadedFiles.map((file, index) => 
                        index === currentFileIndex 
                            ? {...file, qa_status_message: t("construct.qa_generating")} 
                            : file
                    );
                    
                    const response = await axios.post('http://127.0.0.1:8000/qa/generate_qa', requestData, {
                        headers: {
                            'Content-Type': 'application/json',
                        }
                    });
                    
                    if (response.status === 200) {
                        dispatch('qaGenerated', response.data);
                        uploadedFiles = uploadedFiles.map((file, index) => 
                            index === currentFileIndex 
                                ? {...file, qa_status_message: t("construct.qa_generated_success"), status: {...file.status, 1: 1}} 
                                : file
                        );
                        
                        // 从选中列表中移除已处理的文件
                        selectedFiles = selectedFiles.filter(f => f.name !== filename);
                        
                        // 显示成功消息
                        successMessage = t("construct.qa_all_generated_success");
                        setTimeout(() => {
                            successMessage = null;
                        }, 2000);
                    } else {
                        const errorData = response.data;
                        const message = errorData.detail || t('construct.qa_generation_failed');
                        uploadedFiles = uploadedFiles.map((file, index) => 
                            index === currentFileIndex 
                                ? {...file, qa_status_message: message} 
                                : file
                        );
                    }
                } catch (error) {
                    console.error('Error generating QA pairs:', error);
                    const errorMsg = (error.response && error.response.data && error.response.data.detail) 
                        ? error.response.data.detail 
                        : t('construct.qa_generation_network_error');
                    
                    uploadedFiles = uploadedFiles.map((file, index) => 
                        index === currentFileIndex 
                            ? {...file, qa_status_message: errorMsg} 
                            : file
                    );
                }
            }
            
            await fetchFiles(); // 刷新文件状态
            
        } catch (error) {
            console.error('Unexpected error in generateQAPairs:', error);
            handleError(error);
            errorMessage = t('construct.unexpected_error');
        } finally {
            isGeneratingQA = false;
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
                successMessage = t("construct.qa_delete_success");
                setTimeout(() => {
                    successMessage = null;
                }, 2000);
                await fetchFiles(); // Refresh file list to update status
            } else {
                const errorData = response.data;
                errorMessage = errorData.detail || t("construct.qa_delete_failed");
            }
        } catch (error) {
            console.error('Error deleting QA file:', error);
            handleError(error);
            errorMessage = t("construct.qa_delete_network_error");
        }
    };

    const previewQaFile = async (filename: string) => {
        previewModalTitle = `${t("construct.preview_title")}: ${filename}`;
        previewContentType = 'qa';
        previewLoading = true;
        previewErrorMessage = null;
        previewModalOpen = true;
        previewCurrentPage = 1;
        previewDatasetId = filename;
        
        await fetchQaContent();
    };

    // const previewCotFile = async (filename: string) => {
    //     previewModalTitle = `${t("construct.preview_title")}: ${filename}`;
    //     previewContentType = 'cot';
    //     previewLoading = true;
    //     previewErrorMessage = null;
    //     previewModalOpen = true;
    //     previewCurrentPage = 1;
    //     previewDatasetId = filename;
        
    //     await fetchCotContent();
    // };

    const previewRawFile = async (filename: string) => {
        previewModalTitle = `${filename}`;
        previewContentType = 'raw';
        previewLoading = true;
        previewErrorMessage = null;
        previewModalOpen = true;
        
        await fetchRawContent(filename);
    };

    const fetchQaContent = async () => {
        try {
            const response = await axios.get(`http://127.0.0.1:8000/qa/preview/${previewDatasetId}?page=${previewCurrentPage}&page_size=${previewItemsPerPage}`);
            if (response.status === 200) {
                previewContent = response.data.items || [];
                previewTotalPages = response.data.total_pages || 1;
            } else {
                previewErrorMessage = t("construct.qa_preview_failed") + (response.data?.detail ? `: ${response.data.detail}` : '');
            }
        } catch (error) {
            console.error('Error fetching QA content:', error);
            previewErrorMessage = t("construct.qa_preview_network_error");
        } finally {
            previewLoading = false;
        }
    };

    const fetchCotContent = async () => {
        try {
            const response = await axios.get(`http://127.0.0.1:8000/cot/preview/${previewDatasetId}?page=${previewCurrentPage}&page_size=${previewItemsPerPage}`);
            if (response.status === 200) {
                previewContent = response.data.items || [];
                previewTotalPages = response.data.total_pages || 1;
            } else {
                previewErrorMessage = t("construct.cot_preview_failed") + (response.data?.detail ? `: ${response.data.detail}` : '');
            }
        } catch (error) {
            console.error('Error fetching COT content:', error);
            previewErrorMessage = t("construct.cot_preview_network_error");
        } finally {
            previewLoading = false;
        }
    };

    const fetchRawContent = async (filename: string) => {
        try {
            const response = await axios.get(`http://127.0.0.1:8000/parse/preview_raw/${filename}`);
            if (response.status === 200 && response.data.status === "success") {
                rawContent = response.data.data.content || '';
            } else {
                previewErrorMessage = t("construct.preview_error") + (response.data?.detail ? `: ${response.data.detail}` : '');
            }
        } catch (error) {
            console.error('Error fetching raw content:', error);
            previewErrorMessage = t("construct.preview_network_error");
        } finally {
            previewLoading = false;
        }
    };

    const goToPage = (page) => {
        if (page >= 1 && page <= previewTotalPages) {
            previewCurrentPage = page;
            if (previewContentType === 'qa') {
                fetchQaContent();
            } else if (previewContentType === 'cot') {
                fetchCotContent();
            }
        }
    };

    const handlePageInputChange = () => {
        const newPage = parseInt(previewPageInput);
        if (!isNaN(newPage) && newPage >= 1 && newPage <= previewTotalPages) {
            goToPage(newPage);
        }
    };

    const downloadContent = async () => {
        try {
            let url = '';
            if (previewContentType === 'qa') {
                url = `http://127.0.0.1:8000/qa/download/${previewDatasetId}`;
            } else if (previewContentType === 'cot') {
                url = `http://127.0.0.1:8000/cot/download/${previewDatasetId}`;
            } else if (previewContentType === 'raw') {
                // 支持原始内容下载
                if (!rawContent) {
                    previewErrorMessage = t("construct.download_error");
                    return;
                }
                const blob = new Blob([rawContent], { type: 'text/plain' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `${previewModalTitle.replace(/\s+/g, '_')}.txt`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
                return;
            } else {
                return; // 不支持其他类型内容下载
            }
            
            window.open(url, '_blank');
        } catch (error) {
            console.error('Error downloading content:', error);
            previewErrorMessage = t("construct.download_error");
        }
    };

    // COT Functions
    const generateCOTs = async () => {
        if (selectedFiles1.length === 0) {
            errorMessage = t("construct.no_file_selected");
            return;
        }

        isGeneratingCOT = true;

        let updatedFiles = uploadedFiles.map(file => {
            if (selectedFiles1.includes(file)) {
                return {...file, cot_status_message: t("construct.cot_generating")}; // Set initial status for selected files
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
                        const errorData = toTexResponse.data;
                        const message = errorData.detail || t('construct.latex_conversion_failed');
                        uploadedFiles = uploadedFiles.map((file, index) => index === currentFileIndex ? {...file, cot_status_message: message} : file);
                        continue; // Skip to next file if to_tex fails
                    }

                } catch (toTexError) {
                    console.error('Error converting to LaTeX:', toTexError);
                    const message = t('construct.latex_conversion_network_error');
                    uploadedFiles = uploadedFiles.map((file, index) => index === currentFileIndex ? {...file, cot_status_message: message} : file);
                    continue; // Skip to next file if to_tex network error
                }


                const requestData1 = {
                    filename: filename,
                    SK: showSKInputs ? SKs1  :new Array(AKs1.length).fill('a'), //Handle empty array
                    AK: AKs1.length > 0 ? AKs1 : [],  // Ensure 'files' is an array
                    parallel_num: parallelNum1,
                    model_name: selectedModel,
                    domain: domain1,
                };

                uploadedFiles = uploadedFiles.map((file, index) => index === currentFileIndex ? {...file, cot_status_message: t("construct.cot_generating")} : file);


                try {
                    const response = await axios.post('http://127.0.0.1:8000/cot/generate', requestData1, {
                        headers: {
                            'Content-Type': 'application/json',
                        }
                    });

                    if (response.status === 200) {
                        dispatch('cotGenerated', response.data); // Dispatch a new event for COT if needed
                        uploadedFiles = uploadedFiles.map((file, index) => index === currentFileIndex ? {...file, cot_status_message: t("construct.cot_generated_success"), status: {...file.status, 2: 1}} : file);
                        selectedFiles1 = selectedFiles1.filter(f => f.name !== filename);
                        selectedFiles = selectedFiles1; // sync selectedFiles with selectedFiles1
                        successMessage = t("construct.cot_all_generated_success"); // Global success message for COT
                        setTimeout(() => {
                            successMessage = null;
                        }, 2000);


                    } else {

                        const errorData = response.data;
                        const message = errorData.detail || t('construct.cot_generation_failed');
                        uploadedFiles = uploadedFiles.map((file, index) => index === currentFileIndex ? {...file, cot_status_message: message} : file);
                        await fetchFiles(); // Refresh file status in case backend status is not correctly updated.
                        continue;
                    }
                } catch (error) {
                    console.error('Error generating COT:', error);
                    handleError(error);
                    const message = t('construct.cot_generation_network_error');
                    uploadedFiles = uploadedFiles.map((file, index) => index === currentFileIndex ? {...file, cot_status_message: message} : file);
                    await fetchFiles(); // Refresh file status in case backend status is not correctly updated.
                    continue;
                }
            }
            await fetchFiles(); // Refresh file status after all files are processed to update status based on backend.
        } catch (error) {
            console.error('Unexpected error in generateCOTs:', error);
            handleError(error);
            errorMessage = t('construct.unexpected_error');
        } finally {
            isGeneratingCOT = false;
            // successMessage = null; // Clear global success message after all files are processed (or errors occurred) - No global success message anymore
        }
    };


    const deleteCotFile = async (filename: string) => {
        try {
            const response = await axios.delete(`http://127.0.0.1:8000/cot/file/${filename}`); // Using DELETE endpoint
            if (response.status === 200) {
                successMessage = t("construct.cot_delete_success");
                setTimeout(() => {
                    successMessage = null;
                }, 2000);
                await fetchFiles();
            } else {
                const errorData = response.data;
                errorMessage = errorData.detail || t("construct.cot_delete_failed");
            }
        } catch (error) {
            console.error('Error deleting COT file:', error);
            handleError(error);
            errorMessage = t("construct.cot_delete_network_error");
        }
    };

    const previewCotFile = async (filename: string) => {
        try {
            const response = await axios.get(`http://127.0.0.1:8000/cot/content/${filename}`);
            if (response.status === 200) {
                const cotContent = response.data.data;
                goto(`/construct/cot-preview?filename=${filename}&content=${encodeURIComponent(cotContent)}`); // Pass content as query param
            } else {
                const errorData = response.data;
                errorMessage = errorData.detail || t("construct.cot_preview_failed");
            }
        } catch (error) {
            console.error('Error previewing COT file:', error);
            handleError(error);
            errorMessage = t("construct.cot_preview_network_error");
        }
    };

    function init() {
        t.set({
            "construct.filename": "Filename",
            "construct.parsed": "Parsed",
            "construct.file_type": "File Type",
            "construct.status": "Status",
            "construct.qa_generated": "QA Generated",
            "construct.cot_generated": "COT Generated",
            "construct.manage": "Manage",
            "construct.delete": "Delete",
            "construct.preview": "Preview",
            "construct.qa_generate": "Generate QA Pairs",
            "construct.cot_generate": "Generate COT",
            "construct.download": "Download",
            "construct.download_error": "Download failed",
            "construct.no_file_selected": "No file selected",
            "construct.no_content": "No content available",
            "construct.loading": "Loading...",
            "construct.raw_preview_title": "Raw Content",
            "construct.preview_title": "Preview",
            "construct.preview_error": "Failed to preview file",
            "construct.preview_network_error": "Network error previewing file",
            "construct.qa_generating": "Generating QA Pairs...",
            "construct.cot_generating": "Generating COT...",
            "construct.latex_converting": "Converting to LaTeX...",
            "construct.latex_conversion_failed": "LaTeX conversion failed",
            "construct.latex_conversion_network_error": "Network error during LaTeX conversion",
            "construct.latex_conversion_complete": "LaTeX conversion complete",
            "construct.latex_conversion_progress": "LaTeX conversion progress",
            "construct.generating_cot": "Generating COT...",
            "construct.qa_generated_success": "QA Pairs Generated Successfully",
            "construct.cot_generated_success": "COT Generated Successfully",
            "construct.qa_all_generated_success": "All QA Pairs Generated Successfully",
            "construct.cot_all_generated_success": "All COT Generated Successfully",
            "construct.qa_generation_failed": "Failed to generate QA Pairs",
            "construct.cot_generation_failed": "Failed to generate COT",
            "construct.qa_generation_network_error": "Network error generating QA Pairs",
            "construct.cot_generation_network_error": "Network error generating COT",
            "construct.unexpected_error": "An unexpected error occurred",
            "construct.qa_delete_success": "QA file deleted successfully",
            "construct.cot_delete_success": "COT file deleted successfully",
            "construct.qa_delete_failed": "Failed to delete QA file",
            "construct.cot_delete_failed": "Failed to delete COT file",
            "construct.qa_delete_network_error": "Network error deleting QA file",
            "construct.cot_delete_network_error": "Network error deleting COT file",
            "construct.qa_preview_failed": "Failed to preview QA file",
            "construct.cot_preview_failed": "Failed to preview COT file",
            "construct.next": "Next",
            "construct.prev": "Prev",
            "construct.go": "Go",
            "construct.page_of": "of",
            "general.close": "Close",
        });
    }

    onDestroy(() => {
        // 清理QA生成进度计时器
        for (const filename in progressIntervals) {
            clearInterval(progressIntervals[filename]);
        }
    });
</script>

<ActionPageTitle returnTo="/construct/" title={t("construct.title")} />

<div class="w-full flex flex-col space-y-6 p-4">
    <!-- Error Message Section -->
    {#if errorMessage}
        <div class="p-4 bg-red-100 border-l-4 border-red-500 text-red-700 rounded shadow-md">
            <div class="flex items-center">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 mr-2" viewBox="0 0 20 20" fill="currentColor">
                    <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
                </svg>
                <span>{errorMessage}</span>
            </div>
        </div>
    {/if}

    <!-- Success Message Section -->
    {#if successMessage}
        <div class="p-4 bg-green-100 border-l-4 border-green-500 text-green-700 rounded shadow-md">
            <div class="flex items-center">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 mr-2" viewBox="0 0 20 20" fill="currentColor">
                    <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd" />
                </svg>
                <span><strong class="font-bold">{t("general.success")}!</strong> {successMessage}</span>
            </div>
        </div>
    {/if}

    <!-- Statistics Overview -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <div class="bg-white rounded-lg shadow-md p-4 flex items-center">
            <div class="p-3 rounded-full bg-blue-100 text-blue-500 mr-4">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
            </div>
            <div>
                <p class="text-gray-500 text-sm">Total Files</p>
                <p class="text-2xl font-semibold">{uploadedFiles.length}</p>
            </div>
        </div>

        <div class="bg-white rounded-lg shadow-md p-4 flex items-center">
            <div class="p-3 rounded-full bg-green-100 text-green-500 mr-4">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                </svg>
            </div>
            <div>
                <p class="text-gray-500 text-sm">QA Generated</p>
                <p class="text-2xl font-semibold">{uploadedFiles.filter(f => f.status && f.status[1] === 1).length}</p>
            </div>
        </div>

        <div class="bg-white rounded-lg shadow-md p-4 flex items-center">
            <div class="p-3 rounded-full bg-purple-100 text-purple-500 mr-4">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z" />
                </svg>
            </div>
            <div>
                <p class="text-gray-500 text-sm">CoT Generated</p>
                <p class="text-2xl font-semibold">{uploadedFiles.filter(f => f.status && f.status[2] === 1).length}</p>
            </div>
        </div>
    </div>
    
    <!-- Main Content - Left/Right Layout -->
    <div class="flex flex-col md:flex-row gap-6">
        <!-- Left Side - File List -->
        <div class="w-full md:w-1/2">
            <div class="bg-white rounded-lg shadow-md overflow-hidden">
                <div class="px-6 py-4 bg-gray-50 border-b border-gray-200">
                    <h2 class="text-lg font-semibold text-gray-700">{t("construct.uploaded_files")}</h2>
                </div>
                
                <div class="flex justify-between items-center px-4 py-3 border-b border-gray-200 bg-gray-50">
                    <div>
                        <span class="text-sm text-gray-500">{uploadedFiles.length} files, {selectedFiles.length} selected</span>
                    </div>
                    <div class="flex space-x-2">
                        <Button
                            color={selectAllChecked ? "yellow" : "blue"}
                            size="xs"
                            on:click={toggleSelectAll}
                        >
                            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 mr-1" viewBox="0 0 20 20" fill="currentColor">
                                <path d="M9 2a1 1 0 000 2h2a1 1 0 100-2H9z" />
                                <path fill-rule="evenodd" d="M4 5a2 2 0 012-2 3 3 0 003 3h2a3 3 0 003-3 2 2 0 012 2v11a2 2 0 01-2 2H6a2 2 0 01-2-2V5zm2 6a1 1 0 011-1h6a1 1 0 110 2H7a1 1 0 01-1-1zm1 3a1 1 0 100 2h6a1 1 0 100-2H7z" clip-rule="evenodd" />
                            </svg>
                            {selectAllChecked ? t("construct.deselect_all") : t("construct.select_all")}
                        </Button>
                        <Button
                            color="red"
                            size="xs"
                            on:click={() => {
                                showDeleteConfirmation = true;
                            }}
                            disabled={selectedFiles.length === 0}
                        >
                            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 mr-1" viewBox="0 0 20 20" fill="currentColor">
                                <path fill-rule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clip-rule="evenodd" />
                            </svg>
                            {t("construct.delete_button")} ({selectedFiles.length})
                        </Button>
                    </div>
                </div>
                <div class="overflow-x-auto" style="max-height: 600px;">
                    <Table striped={true} hoverable={true}>
                        <TableHead class="bg-gray-50 sticky top-0 z-10">
                            <TableHeadCell class="w-10">
                                <input type="checkbox" class="rounded border-gray-300 text-blue-600 shadow-sm focus:border-blue-300 focus:ring focus:ring-blue-200 focus:ring-opacity-50" bind:checked={selectAllChecked} on:change={toggleSelectAll} />
                            </TableHeadCell>
                            {#each uploaded_file_heads as head}
                                <TableHeadCell>{head}</TableHeadCell>
                            {/each}
                        </TableHead>
                        <TableBody>
                            {#each uploadedFiles as file}
                                <tr class="hover:bg-gray-50 transition-colors">
                                    <TableBodyCell>
                                        <input
                                            type="checkbox"
                                            class="rounded border-gray-300 text-blue-600 shadow-sm focus:border-blue-300 focus:ring focus:ring-blue-200 focus:ring-opacity-50"
                                            checked={selectedFiles.includes(file)}
                                            on:change={() => toggleSelection(file)}
                                        />
                                    </TableBodyCell>
                                    <TableBodyCell>
                                        <div class="flex items-center">
                                            <!-- File type icon -->
                                            <span class="mr-2">
                                                {#if file.type === 'txt'}
                                                    <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-gray-500" viewBox="0 0 20 20" fill="currentColor">
                                                        <path fill-rule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4zm2 6a1 1 0 011-1h6a1 1 0 110 2H7a1 1 0 01-1-1zm1 3a1 1 0 100 2h6a1 1 0 100-2H7z" clip-rule="evenodd" />
                                                    </svg>
                                                {:else if file.type === 'json'}
                                                    <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-yellow-500" viewBox="0 0 20 20" fill="currentColor">
                                                        <path fill-rule="evenodd" d="M2 5a2 2 0 012-2h12a2 2 0 012 2v10a2 2 0 01-2 2H4a2 2 0 01-2-2V5zm3.293 1.293a1 1 0 011.414 0l3 3a1 1 0 010 1.414l-3 3a1 1 0 01-1.414-1.414L7.586 10 5.293 7.707a1 1 0 010-1.414zM11 12a1 1 0 100 2h3a1 1 0 100-2h-3z" clip-rule="evenodd" />
                                                    </svg>
                                                {:else if file.type === 'tex'}
                                                    <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-blue-500" viewBox="0 0 20 20" fill="currentColor">
                                                        <path fill-rule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z" clip-rule="evenodd" />
                                                    </svg>
                                                {:else}
                                                    <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-gray-400" viewBox="0 0 20 20" fill="currentColor">
                                                        <path fill-rule="evenodd" d="M4 4a2 2 0 012-2h8a2 2 0 012 2v12a2 2 0 01-2 2H6a2 2 0 01-2-2V4z" clip-rule="evenodd" />
                                                    </svg>
                                                {/if}
                                            </span>
                                            <button class="text-blue-600 hover:text-blue-800 hover:underline" on:click={() => previewRawFile(file.name)}>
                                                {file.name}
                                            </button>
                                        </div>
                                    </TableBodyCell>
                                    <TableBodyCell>{file.type}</TableBodyCell>
                                    <TableBodyCell>{formatFileSize(file.size)}</TableBodyCell>
                                    <TableBodyCell>{new Date(file.modification_time).toLocaleString()}</TableBodyCell>
                                    <TableBodyCell>
                                        <div class="flex flex-wrap gap-2">
                                            {#if file.status && file.status[1] === 1}
                                                <div class="flex">
                                                    <Button color="green" size="xs" class="mr-1" on:click={() => previewQaFile(file.name)}>
                                                        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 mr-1" viewBox="0 0 20 20" fill="currentColor">
                                                            <path d="M10 12a2 2 0 100-4 2 2 0 000 4z" />
                                                            <path fill-rule="evenodd" d="M.458 10C1.732 5.943 5.522 3 10 3s8.268 2.943 9.542 7c-1.274 4.057-5.064 7-9.542 7S1.732 14.057.458 10zM14 10a4 4 0 11-8 0 4 4 0 018 0z" clip-rule="evenodd" />
                                                        </svg>
                                                        QA
                                                    </Button>
                                                    <Button color="red" size="xs" on:click={() => deleteQaFile(file.name)}>
                                                        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 mr-1" viewBox="0 0 20 20" fill="currentColor">
                                                            <path fill-rule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clip-rule="evenodd" />
                                                        </svg>
                                                    </Button>
                                                </div>
                                            {:else if file.qa_status_message && file.qa_status_message === t("construct.qa_generating")}
                                                <span class="px-2 py-1 text-xs font-semibold rounded-full bg-yellow-100 text-yellow-800">
                                                    {t("construct.status_generating")}
                                                </span>
                                            {:else}
                                                <span class="px-2 py-1 text-xs font-semibold rounded-full bg-gray-100 text-gray-800">
                                                    {t("construct.status_unknown")}
                                                </span>
                                            {/if}
                                            
                                            {#if file.status && file.status[2] === 1}
                                                <div class="flex ml-2">
                                                    <Button color="purple" size="xs" class="mr-1" on:click={() => previewCotFile(file.name)}>
                                                        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 mr-1" viewBox="0 0 20 20" fill="currentColor">
                                                            <path d="M10 12a2 2 0 100-4 2 2 0 000 4z" />
                                                            <path fill-rule="evenodd" d="M.458 10C1.732 5.943 5.522 3 10 3s8.268 2.943 9.542 7c-1.274 4.057-5.064 7-9.542 7S1.732 14.057.458 10zM14 10a4 4 0 11-8 0 4 4 0 018 0z" clip-rule="evenodd" />
                                                        </svg>
                                                        CoT
                                                    </Button>
                                                    <Button color="red" size="xs" on:click={() => deleteCotFile(file.name)}>
                                                        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 mr-1" viewBox="0 0 20 20" fill="currentColor">
                                                            <path fill-rule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clip-rule="evenodd" />
                                                        </svg>
                                                    </Button>
                                                </div>
                                            {:else if file.cot_status_message && file.cot_status_message === t("construct.cot_generating")}
                                                <span class="px-2 py-1 text-xs font-semibold rounded-full bg-yellow-100 text-yellow-800 ml-2">
                                                    {t("construct.status_generating")}
                                                </span>
                                            {/if}
                                        </div>
                                    </TableBodyCell>
                                </tr>
                                {#if file.qa_status_message}
                                    <tr class="bg-gray-50">
                                        <td colspan="6" class="px-4 py-2">
                                            <div class="flex items-center text-sm">
                                                <span class="status-message"
                                                    class:text-blue-600={file.qa_status_message === t("construct.latex_converting") || file.qa_status_message === t("construct.qa_generating")}
                                                    class:text-green-600={file.qa_status_message === t("construct.qa_generated_success")}
                                                    class:text-red-600={
                                                        file.qa_status_message === t('construct.qa_generation_failed') ||
                                                        file.qa_status_message === t('construct.qa_generation_network_error') ||
                                                        file.qa_status_message === t('construct.latex_conversion_failed') ||
                                                        file.qa_status_message === t('construct.latex_conversion_network_error')
                                                    }>
                                                    {file.qa_status_message}
                                                </span>
                                            </div>
                                        </td>
                                    </tr>
                                {/if}
                            {/each}
                        </TableBody>
                    </Table>
                </div>
            </div>
        </div>
        
        <!-- Right Side - Parameter Settings -->
        <div class="w-full md:w-1/2">
            <div class="bg-white rounded-lg shadow-md overflow-hidden">
                <div class="border-b border-gray-200">
                    <ul class="flex flex-wrap -mb-px">
                        <li class="mr-2">
                            <button
                                class={`inline-block py-4 px-4 text-sm font-medium text-center ${activeTab === 'qa' ? 'text-blue-600 border-b-2 border-blue-600' : 'text-gray-500 hover:text-gray-600 hover:border-gray-300 border-b-2 border-transparent'}`}
                                on:click={() => activeTab = 'qa'}
                            >
                                <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 mr-1 inline-block" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                                </svg>
                                {t("construct.qa_generation_settings")}
                            </button>
                        </li>
                        <li class="mr-2">
                            <button
                                class={`inline-block py-4 px-4 text-sm font-medium text-center ${activeTab === 'cot' ? 'text-purple-600 border-b-2 border-purple-600' : 'text-gray-500 hover:text-gray-600 hover:border-gray-300 border-b-2 border-transparent'}`}
                                on:click={() => activeTab = 'cot'}
                            >
                                <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 mr-1 inline-block" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                                </svg>
                                {t("construct.cot_generation_settings")}
                            </button>
                        </li>
                    </ul>
                </div>
                
                <!-- QA Generation Settings -->
                {#if activeTab === 'qa'}
                    <div class="p-6 space-y-4">
                        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 mb-4">
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-2">{t("construct.parallel_num")}</label>
                                <input
                                    type="number"
                                    min="1"
                                    max={AKs.length}
                                    bind:value={parallelNum}
                                    class="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
                                />
                            </div>

                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-2">{t("construct.domain")}</label>
                                <input
                                    type="text"
                                    bind:value={domain}
                                    placeholder={t("construct.domain_placeholder")}
                                    class="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
                                />
                            </div>
                        </div>

                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-2">{t("construct.model_name")}</label>
                            <select 
                                bind:value={selectedModel} 
                                on:change={handleModelChange}
                                class="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                            >
                                {#each modelOptions as option}
                                    <option value={option.name}>{t(`construct.${option.name}`)}</option>
                                {/each}
                            </select>
                        </div>

                        {#if showSKInputs}
                            <div class="border-t border-gray-200 pt-4">
                                <h3 class="text-md font-medium text-gray-700 mb-3">{t("construct.sk")}</h3>
                                <div class="space-y-3">
                                    {#each Array(numSKAKInputs) as _, i}
                                        <input
                                            type="password"
                                            placeholder={`SK ${i + 1}`}
                                            bind:value={SKs[i]}
                                            class="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                                        />
                                    {/each}
                                </div>
                            </div>

                            <div class="border-t border-gray-200 pt-4">
                                <h3 class="text-md font-medium text-gray-700 mb-3">{t("construct.ak")}</h3>
                                <div class="space-y-3">
                                    {#each Array(numSKAKInputs) as _, i}
                                        <input
                                            type="password"
                                            placeholder={`AK ${i + 1}`}
                                            bind:value={AKs[i]}
                                            class="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                                        />
                                    {/each}
                                </div>
                            </div>
                        {/if}

                        <div class="flex justify-center pt-4">
                            <Button 
                                color="green" 
                                class="px-6 py-2 flex items-center w-full"
                                disabled={isGeneratingQA || selectedFiles.length === 0} 
                                on:click={generateQAPairs}
                            >
                                {#if isGeneratingQA}
                                    <div class="mr-2 animate-spin h-4 w-4 border-2 border-white rounded-full border-t-transparent"></div>
                                    {t("construct.generating_qa")}
                                {:else}
                                    <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 mr-2" viewBox="0 0 20 20" fill="currentColor">
                                        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-11a1 1 0 10-2 0v2H7a1 1 0 100 2h2v2a1 1 0 102 0v-2h2a1 1 0 100-2h-2V7z" clip-rule="evenodd" />
                                    </svg>
                                    {t("construct.generate_qa_button")}
                                {/if}
                            </Button>
                        </div>
                    </div>
                {/if}

                <!-- CoT Generation Settings -->
                {#if activeTab === 'cot'}
                    <div class="p-6 space-y-4">
                        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 mb-4">
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-2">{t("construct.parallel_num")}</label>
                                <input
                                    type="number"
                                    min="1"
                                    max={AKs1.length}
                                    bind:value={parallelNum1}
                                    class="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
                                />
                            </div>

                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-2">{t("construct.domain")}</label>
                                <input
                                    type="text"
                                    bind:value={domain1}
                                    placeholder={t("construct.domain_placeholder")}
                                    class="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
                                />
                            </div>
                        </div>

                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-2">{t("construct.model_name")}</label>
                            <select 
                                bind:value={selectedModel} 
                                on:change={handleModelChange}
                                class="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                            >
                                {#each modelOptions as option}
                                    <option value={option.name}>{t(`construct.${option.name}`)}</option>
                                {/each}
                            </select>
                        </div>

                        {#if showSKInputs1}
                            <div class="border-t border-gray-200 pt-4">
                                <h3 class="text-md font-medium text-gray-700 mb-3">{t("construct.sk")}</h3>
                                <div class="space-y-3">
                                    {#each Array(numSKAKInputs1) as _, i}
                                        <input
                                            type="password"
                                            placeholder={`SK ${i + 1}`}
                                            bind:value={SKs1[i]}
                                            class="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                                        />
                                    {/each}
                                </div>
                            </div>

                            <div class="border-t border-gray-200 pt-4">
                                <h3 class="text-md font-medium text-gray-700 mb-3">{t("construct.ak")}</h3>
                                <div class="space-y-3">
                                    {#each Array(numSKAKInputs1) as _, i}
                                        <input
                                            type="password"
                                            placeholder={`AK ${i + 1}`}
                                            bind:value={AKs1[i]}
                                            class="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                                        />
                                    {/each}
                                </div>
                            </div>
                        {/if}

                        <div class="flex justify-center pt-4">
                            <Button 
                                color="purple" 
                                class="px-6 py-2 flex items-center w-full"
                                disabled={isGeneratingCOT || selectedFiles.length === 0} 
                                on:click={generateCOTs}
                            >
                                {#if isGeneratingCOT}
                                    <div class="mr-2 animate-spin h-4 w-4 border-2 border-white rounded-full border-t-transparent"></div>
                                    {t("construct.generating_cot")}
                                {:else}
                                    <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 mr-2" viewBox="0 0 20 20" fill="currentColor">
                                        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-11a1 1 0 10-2 0v2H7a1 1 0 100 2h2v2a1 1 0 102 0v-2h2a1 1 0 100-2h-2V7z" clip-rule="evenodd" />
                                    </svg>
                                    {t("construct.generate_cot_button")}
                                {/if}
                            </Button>
                        </div>
                    </div>
                {/if}
            </div>
        </div>
    </div>


    {#if errorModalVisible}
        <div class="fixed inset-0 z-50 flex items-center justify-center bg-gray-800 bg-opacity-50">
            <div class="bg-white p-6 rounded shadow-lg w-1/3 text-center">
                <p class="text-lg font-medium mb-4">{errorMessage}</p>
            </div>
        </div>
    {/if}


    {#if showDeleteConfirmation}
        <Modal bind:open={showDeleteConfirmation} size="md" autoclose={false} class="rounded-lg">
            <h3 slot="header" class="text-xl font-bold text-gray-900">
                {t("construct.delete_confirmation_title")}
            </h3>
            <div class="my-6 text-gray-600">
                <div class="flex items-center mb-4">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-12 w-12 text-red-500 mr-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                    <p>{t("construct.delete_confirmation_message")}</p>
                </div>

                {#if selectedFiles.length > 0}
                    <div class="bg-gray-100 p-3 rounded-lg mb-4">
                        <h4 class="font-medium text-gray-700 mb-2">Selected files ({selectedFiles.length}):</h4>
                        <ul class="max-h-40 overflow-y-auto">
                            {#each selectedFiles.slice(0, 5) as file}
                                <li class="flex items-center py-1">
                                    <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 text-gray-500 mr-2" viewBox="0 0 20 20" fill="currentColor">
                                        <path fill-rule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4zm2 6a1 1 0 011-1h6a1 1 0 110 2H7a1 1 0 01-1-1zm1 3a1 1 0 100 2h6a1 1 0 100-2H7z" clip-rule="evenodd" />
                                    </svg>
                                    <span class="text-sm">{file.name}</span>
                                </li>
                            {/each}
                            {#if selectedFiles.length > 5}
                                <li class="text-sm text-gray-500 italic mt-1">And {selectedFiles.length - 5} more file(s)...</li>
                            {/if}
                        </ul>
                    </div>
                {/if}
            </div>
            <div slot="footer" class="flex justify-end gap-2">
                <Button color="light" on:click={() => showDeleteConfirmation = false}>{t("construct.delete_cancel_button")}</Button>
                <Button color="red" on:click={deleteSelectedFiles}>
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 mr-1" viewBox="0 0 20 20" fill="currentColor">
                        <path fill-rule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clip-rule="evenodd" />
                    </svg>
                    {t("construct.delete_confirm_button")}
                </Button>
            </div>
        </Modal>
    {/if}

    <!-- Add Preview Modal -->
    <Modal bind:open={previewModalOpen} size="xl" autoclose={false} class="w-full max-w-5xl">
        <h3 slot="header" class="text-xl font-semibold text-gray-900 dark:text-white">
            {previewModalTitle}
        </h3>

        <div class="space-y-4">
            {#if previewErrorMessage}
                <div class="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4">{previewErrorMessage}</div>
            {/if}

            {#if previewLoading}
                <div class="flex justify-center items-center py-8">
                    <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
                    <span class="ml-3 text-gray-700">{t("construct.loading")}</span>
                </div>
            {:else if previewContentType === 'raw'}
                <div class="bg-gray-50 rounded-lg p-4 h-[70vh] overflow-auto">
                    <pre class="whitespace-pre-wrap text-sm font-mono">{rawContent}</pre>
                </div>
            {:else if previewContentType === 'qa' && previewContent && previewContent.length > 0}
                <div class="bg-white rounded-lg overflow-hidden mb-4">
                    <Table striped={true}>
                        <TableHead>
                            <TableHeadCell class="table-cell-border">{t("construct.question")}</TableHeadCell>
                            <TableHeadCell class="table-cell-border">{t("construct.answer")}</TableHeadCell>
                            <TableHeadCell class="table-cell-border">{t("construct.context")}</TableHeadCell>
                        </TableHead>
                        <TableBody class="divide-y">
                            {#each previewContent as item}
                                <tr>
                                    <TableBodyCell class="whitespace-normal break-words max-w-xs">{item.question}</TableBodyCell>
                                    <TableBodyCell class="whitespace-normal break-words max-w-xs">{item.answer}</TableBodyCell>
                                    <TableBodyCell class="whitespace-normal break-words max-w-xs">{item.context}</TableBodyCell>
                                </tr>
                            {/each}
                        </TableBody>
                    </Table>
                </div>

                <div class="flex items-center justify-between">
                    <Button color="blue" disabled={previewCurrentPage === 1} on:click={() => goToPage(previewCurrentPage - 1)}>
                        {t("construct.previous")}
                    </Button>
                    <span class="text-gray-700">
                        {t("construct.page")} {previewCurrentPage} / {previewTotalPages}
                    </span>
                    <Button color="blue" disabled={previewCurrentPage === previewTotalPages} on:click={() => goToPage(previewCurrentPage + 1)}>
                        {t("construct.next")}
                    </Button>
                    <div class="flex items-center ml-4">
                        <label for="pageInput" class="mr-2">{t("construct.go_to")}</label>
                        <input
                            id="pageInput"
                            type="number"
                            class="w-16 px-2 py-1 border border-gray-300 rounded"
                            min="1"
                            max={previewTotalPages}
                            bind:value={previewPageInput}
                            on:change={handlePageInputChange}
                        />
                    </div>
                </div>
            {:else if previewContentType === 'cot' && previewContent && previewContent.length > 0}
                <div class="bg-white rounded-lg overflow-hidden mb-4">
                    <Table striped={true}>
                        <TableHead>
                            <TableHeadCell class="table-cell-border">{t("construct.action")}</TableHeadCell>
                            <TableHeadCell class="table-cell-border">{t("construct.content")}</TableHeadCell>
                        </TableHead>
                        <TableBody class="divide-y">
                            {#each previewContent as item}
                                {#each item.reasoning as step}
                                    <tr>
                                        <TableBodyCell class="whitespace-normal break-words font-medium">{step.action}</TableBodyCell>
                                        <TableBodyCell class="whitespace-normal break-words max-w-lg">
                                            {#if step.title}
                                                <div class="font-semibold mb-2">{step.title}</div>
                                            {/if}
                                            <div>{step.content}</div>
                                        </TableBodyCell>
                                    </tr>
                                {/each}
                            {/each}
                        </TableBody>
                    </Table>
                </div>

                <div class="flex items-center justify-between">
                    <Button color="blue" disabled={previewCurrentPage === 1} on:click={() => goToPage(previewCurrentPage - 1)}>
                        {t("construct.previous")}
                    </Button>
                    <span class="text-gray-700">
                        {t("construct.page")} {previewCurrentPage} / {previewTotalPages}
                    </span>
                    <Button color="blue" disabled={previewCurrentPage === previewTotalPages} on:click={() => goToPage(previewCurrentPage + 1)}>
                        {t("construct.next")}
                    </Button>
                    <div class="flex items-center ml-4">
                        <label for="pageInput" class="mr-2">{t("construct.go_to")}</label>
                        <input
                            id="pageInput"
                            type="number"
                            class="w-16 px-2 py-1 border border-gray-300 rounded"
                            min="1"
                            max={previewTotalPages}
                            bind:value={previewPageInput}
                            on:change={handlePageInputChange}
                        />
                    </div>
                </div>
            {:else}
                <p class="text-center py-8 text-gray-500">{t("construct.no_content")}</p>
            {/if}
        </div>

        <svelte:fragment slot="footer">
            <div class="flex justify-between w-full">
                <Button color="blue" on:click={downloadContent} disabled={(previewContentType === 'qa' || previewContentType === 'cot') ? (!previewContent || previewContent.length === 0) : (previewContentType === 'raw' ? !rawContent : true)}>
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                    </svg>
                    {t("Download")}
                </Button>
                <Button color="alternative" on:click={() => previewModalOpen = false}>
                    {t("Close")}
                </Button>
            </div>
        </svelte:fragment>
    </Modal>
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
