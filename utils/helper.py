import json
import math

import tiktoken
from model_api.erine.erine import generate_erine
from model_api.flash.flash import generate_flash
from model_api.lite.lite import generate_lite
from model_api.Qwen.Qwen import generate_Qwen


def split_chunk_by_tokens(chunk: str, max_tokens: int) -> list:
    """
    将文本块按 token 限制分割成多个部分，尽量从换行符处分割。

    Args:
        chunk (str): 输入的文本块。
        max_tokens (int): 每段的最大 token 数量。

    Returns:
        list: 分割后的文本块列表，每块不超过 max_tokens 个 token。
    """
    enc = tiktoken.get_encoding("o200k_base")

    # 按行分割文本
    lines = chunk.splitlines()
    sub_chunks = []
    current_chunk = []
    current_tokens = 0

    for line in lines:
        # 计算当前行的 token 数量
        line_tokens = enc.encode(line)
        line_token_count = len(line_tokens)

        # 如果加入当前行后超过 max_tokens，则保存当前块并开始新块
        if current_tokens + line_token_count > max_tokens:
            sub_chunks.append("\n".join(current_chunk))
            current_chunk = []
            current_tokens = 0

        # 将当前行加入到块中
        current_chunk.append(line)
        current_tokens += line_token_count

    # 添加最后一个块
    if current_chunk:
        sub_chunks.append("\n".join(current_chunk))

    return sub_chunks


def split_text_into_chunks(parallel_num, text: str) -> list:
#将文本拆分为段，每段由一组AK处理
    lines = text.splitlines()
    length = len(text)
    chunk_size = math.ceil(length / parallel_num)

    text_chunks = []
    current_chunk = []
    current_length = 0

    for line in lines:
        current_chunk.append(line)
        current_length += len(line)
        if current_length >= chunk_size and len(text_chunks) < parallel_num - 1:
            text_chunks.append("\n".join(current_chunk))
            current_chunk = []
            current_length = 0

    if current_chunk:
        text_chunks.append("\n".join(current_chunk))

    return text_chunks


def extract_qa(response):
    start_i = response.find('{')
    end_i = response.find('}') + 1
    qa_pairs = []
    while end_i != 0:
        try:
            qa_pairs.append(json.loads(response[start_i:end_i]))
        except:
            print("response format error")
        start_i = response.find('{', end_i)
        end_i = response.find('}', end_i) + 1
    return qa_pairs


def generate(text, Model_Name, prompt_choice, API_KEY, SECRET_KEY=None):
    # 转换为小写并赋值
    model_name = Model_Name.lower()

    if model_name == "erine":
        return generate_erine(text, API_KEY, SECRET_KEY, prompt_choice)
    elif model_name == "flash":
        return generate_flash(text, API_KEY, prompt_choice)
    elif model_name == "lite":
        return generate_lite(text, API_KEY, prompt_choice)
    elif model_name == "qwen":
        return generate_Qwen(text, API_KEY, prompt_choice)
    else:
        raise ValueError(f"不支持的模型名称：{Model_Name}，支持的模型包括：erine, flash, lite, qwen")