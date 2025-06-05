from pdf2image import convert_from_path
from PIL import Image
from transformers import AutoTokenizer, AutoModel
import torch
import os
import tempfile # 用于创建临时文件

# --- 配置 ---
PDF_FILE_PATH = r"D:\A王树勋\保研\王树勋个人简历.pdf"  # 替换成你的 PDF 文件路径
OUTPUT_TEXT_FILE = "extracted_text_trocr.txt" # 输出文本文件名


MODEL_NAME = 'ucaslcl/GOT-OCR2_0' 
# 如果你有 GPU，可以使用 GPU 加速
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Using device: {DEVICE}")



# --- 初始化模型和处理器 ---
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
model = AutoModel.from_pretrained(MODEL_NAME, trust_remote_code=True, low_cpu_mem_usage=True, device_map=DEVICE, use_safetensors=True, pad_token_id=tokenizer.eos_token_id)
model = model.eval().to(DEVICE)
print(f"成功加载模型: {MODEL_NAME}")



# --- PDF 转图片并进行 OCR ---
def extract_text_with_trocr(pdf_path, output_txt_path):

    if not (tokenizer and model):
        print("模型或处理器未能初始化，无法继续。")
        return

    
    print(f"正在将 PDF '{pdf_path}' 转换为图片...")
    images = convert_from_path(pdf_path) # 可以尝试添加 dpi=300 等参数提高图像质量
    print(f"PDF 共 {len(images)} 页已转换为图片。")

    all_text = ""

    for i, image in enumerate(images):
        print(f"正在识别第 {i+1} 页...")
        temp_image_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_image_file:
                image.save(tmp_image_file.name, format="PNG")
                temp_image_path = tmp_image_file.name

            res = model.chat(tokenizer, temp_image_path, ocr_type='ocr')

            all_text += f"--- 第 {i+1} 页 ---\n"
            all_text += res + "\n\n"
            print(f"第 {i+1} 页识别完成。")
            print(f"识别内容预览: {res[:100]}...") # 打印部分识别内容
        finally:
            if temp_image_path and os.path.exists(temp_image_path):
                os.unlink(temp_image_path)


    # 4. 将提取的文本保存到文件
    with open(output_txt_path, "w", encoding="utf-8") as f:
        f.write(all_text)
    print(f"提取的文本已保存到: {output_txt_path}")

    

# --- 主程序 ---
if __name__ == "__main__":
    if not os.path.exists(PDF_FILE_PATH):
        print(f"错误: PDF 文件 '{PDF_FILE_PATH}' 不存在。请检查路径。")
    else:
        extract_text_with_trocr(PDF_FILE_PATH, OUTPUT_TEXT_FILE)