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
    # 确保返回的是字符串类型
    return str(res) if res is not None else ""

def text_parse(file_path,save_path):
    """
    文本文档的解析，其实就是将文件复制一份
    :param file_path: 文件原始路径
    :param save_path: 解析后文件路径
    :return: 解析后文件路径
    """

    # 读取文件内容
    with open(file_path, 'r', encoding='utf-8') as f:
        data = f.readlines()

    print(f"Parsing text file and saving results to {save_path}")

    # 获取文件名并构造保存路径
    file_name = file_path.split('/')[-1]  # 提取文件名
    base_name = file_name.split('.')[0]  # 提取不带扩展名的部分
    save_file_path = os.path.join(save_path, base_name + '.txt').replace('\\', '/') # 拼接完整路径

    # 确保保存路径的目录存在
    os.makedirs(save_path, exist_ok=True)
    # 写入文件
    with open(save_file_path, 'w', encoding='utf-8') as f:
        for line in data:
            f.write(line)
    return save_file_path

def pdf_parse(file_path, save_path, progress_callback=None):
    """PDF文件解析，支持进度回调"""
    import fitz
    
    # 打开PDF文件
    pdf_document = fitz.open(file_path)
    total_pages = pdf_document.page_count
    
    # 检查是否为纯图片PDF
    is_scanned = True
    for page in pdf_document:
        if page.get_text().strip():
            is_scanned = False
            break
    
    results = []
    if is_scanned:
        for page_num in range(total_pages):
            # 处理每一页
            page = pdf_document[page_num]
            pix = page.get_pixmap()
            img_data = pix.tobytes()
            img = Image.frombytes("RGB", [pix.width, pix.height], img_data)
            
            # OCR识别
            text = single_ocr(img)
            results.append(text)
            
            if progress_callback:
                # 更新进度，预留20%给文件保存阶段
                progress = int((page_num + 1) / total_pages * 80)
                progress_callback(progress)
    else:
        # 处理文字PDF
        for page_num in range(total_pages):
            page = pdf_document[page_num]
            text = page.get_text()
            results.append(text)
            
            if progress_callback:
                # 更新进度，预留20%给文件保存阶段
                progress = int((page_num + 1) / total_pages * 80)
                progress_callback(progress)
    
    # 保存结果
    save_file_path = os.path.join(
        save_path, 
        f"{os.path.splitext(os.path.basename(file_path))[0]}.txt"
    )
    
    with open(save_file_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(results))
    
    if progress_callback:
        progress_callback(100)  # 完成
        
    pdf_document.close()
    return save_file_path
    
    
   

def parse(hparams: HyperParams, progress_callback=None):
    """
    文件解析函数，支持进度回调
    :param hparams: 超参数
    :param progress_callback: 进度回调函数
    :return: 解析后文件路径
    """
    assert os.path.exists(hparams.file_path), "File does not exist."
    file_type = hparams.file_path.split('.')[-1].lower()
    save_path = os.path.join(hparams.save_path, 'parsed_file')
    os.makedirs(save_path, exist_ok=True)

    if file_type in {'tex', 'txt', 'json'}:
        # 使用文件大小而不是行数来估算进度
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
                    progress_callback(min(progress, 70))  # 确保不超过70%
        
        # 保存处理后的内容
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


