import os

from PIL import Image
import io
import sys
import os

from utils.hparams import HyperParams

def single_ocr(file_path):
    from modelscope import AutoModel, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained('AI-ModelScope/GOT-OCR2_0', trust_remote_code=True)
    model = AutoModel.from_pretrained('AI-ModelScope/GOT-OCR2_0', trust_remote_code=True, low_cpu_mem_usage=True, device_map='cuda', use_safetensors=True, pad_token_id=tokenizer.eos_token_id)
    model = model.eval()


    image_file = file_path

    res = model.chat(tokenizer, image_file, ocr_type='format')
    # Ensure the return value is a string type
    return str(res) if res is not None else ""

def text_parse(file_path,save_path):
    """
    Text document parsing, which is essentially making a copy of the file
    :param file_path: Original file path
    :param save_path: Path for the parsed file
    :return: Path of the parsed file
    """

    # Read file content
    with open(file_path, 'r', encoding='utf-8') as f:
        data = f.readlines()

    print(f"Parsing text file and saving results to {save_path}")

    # Get filename and construct save path
    file_name = file_path.split('/')[-1]  # Extract filename
    base_name = file_name.split('.')[0]  # Extract part without extension
    save_file_path = os.path.join(save_path, base_name + '.txt').replace('\\', '/') # Concatenate full path

    # Ensure the save path directory exists
    os.makedirs(save_path, exist_ok=True)
    # Write to file
    with open(save_file_path, 'w', encoding='utf-8') as f:
        for line in data:
            f.write(line)
    return save_file_path

def pdf_parse(file_path, save_path, progress_callback=None):
    """PDF file parsing, supports progress callback"""
    import fitz

    # Open PDF file
    pdf_document = fitz.open(file_path)
    total_pages = pdf_document.page_count

    # Check if it's a scanned image PDF
    is_scanned = True
    for page in pdf_document:
        if page.get_text().strip():
            is_scanned = False
            break

    results = []
    if is_scanned:
        for page_num in range(total_pages):
     
            page = pdf_document[page_num]
            pix = page.get_pixmap()
            img_data = pix.tobytes()
            img = Image.frombytes("RGB", [pix.width, pix.height], img_data)

            text = single_ocr(img)
            results.append(text)

            if progress_callback:
                # Update progress, reserve 20% for file saving phase
                progress = int((page_num + 1) / total_pages * 80)
                progress_callback(progress)
    else:
        # Process text PDF
        for page_num in range(total_pages):
            page = pdf_document[page_num]
            text = page.get_text()
            results.append(text)

            if progress_callback:
                # Update progress, reserve 20% for file saving phase
                progress = int((page_num + 1) / total_pages * 80)
                progress_callback(progress)

    # Save results
    save_file_path = os.path.join(
        save_path,
        f"{os.path.splitext(os.path.basename(file_path))[0]}.txt"
    )

    with open(save_file_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(results))

    if progress_callback:
        progress_callback(100)  # Complete

    pdf_document.close()
    return save_file_path




def parse(hparams: HyperParams, progress_callback=None):
    """
    File parsing function, supports progress callback
    :param hparams: Hyperparameters
    :param progress_callback: Progress callback function
    :return: Path of the parsed file
    """
    assert os.path.exists(hparams.file_path), "File does not exist."
    file_type = hparams.file_path.split('.')[-1].lower()
    save_path = os.path.join(hparams.save_path, 'parsed_file')
    os.makedirs(save_path, exist_ok=True)

    if file_type in {'tex', 'txt', 'json'}:
        # Use file size instead of line count to estimate progress
        CHUNK_SIZE = 1024 * 1024  # 1MB
        file_size = os.path.getsize(hparams.file_path)
        read_bytes = 0
        content = []

        with open(hparams.file_path, 'r', encoding='utf-8') as f:
            while chunk := f.read(CHUNK_SIZE):
                content.append(chunk)
                read_bytes += len(chunk.encode('utf-8'))
                if progress_callback:
                    progress = int((read_bytes/file_size) * 70)
                    progress_callback(min(progress, 70))  # Ensure it doesn't exceed 70%

        # Save processed content
        save_file_path = os.path.join(
            save_path,
            f"{os.path.splitext(os.path.basename(hparams.file_path))[0]}.txt"
        )

        with open(save_file_path, 'w', encoding='utf-8') as f:
            f.writelines(content)

        if progress_callback:
            progress_callback(100)
        return save_file_path

    elif file_type == 'pdf':
        return pdf_parse(hparams.file_path, save_path, progress_callback)
    else:
        raise ValueError(f"Unsupported file type: {file_type}")


