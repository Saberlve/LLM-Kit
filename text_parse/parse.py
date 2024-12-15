import os


from utils.hyparams import HyperParams

def text_parse(file_path,save_path):
    with open(file_path,'r',encoding='utf-8') as f:
        data = f.readlines()
    print(f"Parsing text file and saving results to {save_path}")
    file_name=file_path.split('/')[-1]
    with open(os.path.join(save_path,file_name),'w',encoding='utf-8') as f:
        for line in data:
            f.write(line)


def ocr_parse(file_path,save_path):
    # Example implementation for OCR parsing
    print(f"Performing OCR on PDF and saving results to {save_path}")
    # Actual OCR logic would go here

def parse(hparams: HyperParams) -> str:
    assert os.path.exists(hparams.file_path), "File does not exist. Please check the file_path_or_name."
    file_type = hparams.file_path.split('.')[-1].lower()
    # Define save path
    save_path = os.path.join(hparams.save_path + '/parsed_file')
    os.makedirs(save_path, exist_ok=True)

    if file_type in {'tex', 'txt', 'json'}:
        text_parse(hparams.file_path,save_path)
    elif file_type == 'pdf':
        ocr_parse(hparams.file_path,save_path)
    else:
        raise ValueError(f"Unsupported file type: {file_type}. Supported types are: tex, txt, json, pdf.")

    return save_path
hparam=HyperParams.from_hparams('../hyparams/config.yaml')
parse(hparam)