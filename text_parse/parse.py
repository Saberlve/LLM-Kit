import os
import fitz  # PyMuPDF
from PIL import Image
import io
import sys
import os

from utils.hyparams import HyperParams

def single_ocr(file_path):
    from modelscope import AutoModel, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained('AI-ModelScope/GOT-OCR2_0', trust_remote_code=True)
    model = AutoModel.from_pretrained('AI-ModelScope/GOT-OCR2_0', trust_remote_code=True, low_cpu_mem_usage=True, device_map='cuda', use_safetensors=True, pad_token_id=tokenizer.eos_token_id)
    model = model.eval().cuda()


    image_file = '/data/shuxun/Snipaste_2025-01-08_19-43-07.png'

    res = model.chat(tokenizer, image_file, ocr_type='format')
    return res

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

def pdf_parse(file_path,save_path):
    """
    图片类文档解析
    :param file_path: 文件原始路径
    :param save_path: 解析后文件路径
    :return: 解析后文件路径
    """
 
    
    # 获取文件名并构造保存路径
    file_name = file_path.split('/')[-1]  # 提取文件名
    base_name = file_name.split('.')[0]  # 提取不带扩展名的部分
    save_file_path = os.path.join(save_path, base_name + '.txt').replace('\\', '/')
    
    # 确保保存路径存在
    os.makedirs(save_path, exist_ok=True)
    
    # 打开PDF文件
    pdf_document = fitz.open(file_path)
    
    # 检查是否为纯图片PDF
    is_scanned = True
    for page in pdf_document:
        if page.get_text().strip():
            is_scanned = False
            break
            
    if is_scanned:
        results = []
        for page_num in range(pdf_document.page_count):
            page = pdf_document[page_num]
            pix = page.get_pixmap()
            img_data = pix.tobytes()
            img = Image.frombytes("RGB", [pix.width, pix.height], img_data)
            # 对图片进行OCR识别
            text = single_ocr(img)
            results.append(text)
            
        # 保存识别结果
        with open(save_file_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(results))
            
    else:
        # 处理文字PDF
        text = ""
        for page in pdf_document:
            text += page.get_text()
            
        # 保存提取的文本
        with open(save_file_path, 'w', encoding='utf-8') as f:
            f.write(text)
            
    pdf_document.close()
    return save_file_path
    
    
    
    
    
    # Example implementation for OCR parsing
    print(f"Performing OCR on PDF and saving results to {save_path}")
    # Actual OCR logic would go here

def parse(hparams: HyperParams) :
    """
    文件解析函数，通过调用不同类型的解析，以统一到解析位置，传递给下一个模块
    :param hparams: 超参数
    :return: 解析后文件路径
    """

    assert os.path.exists(hparams.file_path), "File does not exist. Please check the file_path_or_name."
    file_type = hparams.file_path.split('.')[-1].lower()
    # Define save path
    save_path = os.path.join(hparams.save_path + '/parsed_file')
    os.makedirs(save_path, exist_ok=True)

    if file_type in {'tex', 'txt', 'json'}:
        return text_parse(hparams.file_path,save_path)
    elif file_type == 'pdf':
        return ocr_parse(hparams.file_path,save_path)
    else:
        raise ValueError(f"Unsupported file type: {file_type}. Supported types are: tex, txt, json, pdf.")


