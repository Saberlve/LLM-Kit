import json
import math

import tiktoken
from model_api.erine.erine import generate_erine
from model_api.flash.flash import generate_flash
from model_api.lite.lite import generate_lite
from model_api.Qwen.Qwen import generate_Qwen


def split_chunk_by_tokens(chunk: str, max_tokens: int) -> list:
    # Use a supported encoding model (cl100k_base is used by gpt-4, gpt-3.5-turbo)
    try:
        enc = tiktoken.get_encoding("cl100k_base")
    except:
        # Fallback to p50k_base which is commonly available
        enc = tiktoken.get_encoding("p50k_base")

    lines = chunk.splitlines()
    sub_chunks = []
    current_chunk = []
    current_tokens = 0

    for line in lines:
        line_tokens = enc.encode(line)
        line_token_count = len(line_tokens)

        if current_tokens + line_token_count > max_tokens:
            sub_chunks.append("\n".join(current_chunk))
            current_chunk = []
            current_tokens = 0

        current_chunk.append(line)
        current_tokens += line_token_count


    if current_chunk:
        sub_chunks.append("\n".join(current_chunk))

    return sub_chunks


def split_text_into_chunks(parallel_num, text: str) -> list:

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
    # Convert to lowercase and assign
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
        raise ValueError(f"Unsupported model name: {Model_Name}, supported models include: erine, flash, lite, qwen")