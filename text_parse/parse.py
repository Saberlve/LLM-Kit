import os


from utils.hyparams import HyperParams

def text_parse(file_path,save_path):
    # 读取文件内容
    with open(file_path, 'r', encoding='utf-8') as f:
        data = f.readlines()

    print(f"Parsing text file and saving results to {save_path}")

    # 获取文件名并构造保存路径
    file_name = file_path.split('/')[-1]  # 提取文件名
    base_name = file_name.split('.')[0]  # 提取不带扩展名的部分
    save_file_path = os.path.join(save_path, base_name + '.txt')  # 拼接完整路径

    # 确保保存路径的目录存在
    os.makedirs(save_path, exist_ok=True)
    # 写入文件
    with open(save_file_path, 'w', encoding='utf-8') as f:
        for line in data:
            f.write(line)
    return save_file_path

def ocr_parse(file_path,save_path):
    # Example implementation for OCR parsing
    print(f"Performing OCR on PDF and saving results to {save_path}")
    # Actual OCR logic would go here

def parse(hparams: HyperParams) :
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


