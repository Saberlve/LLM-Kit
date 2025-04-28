import json
import math

import tiktoken
from model_api.erine.erine import generate_erine
from model_api.flash.flash import generate_flash
from model_api.lite.lite import generate_lite
from model_api.Qwen.Qwen import generate_Qwen


def split_chunk_by_tokens(chunk: str, max_tokens: int) -> list:
    """
    Split text blocks by token limit, preferably at line breaks.

    Args:
        chunk (str): Input text block.
        max_tokens (int): Maximum number of tokens per segment.

    Returns:
        list: List of split text blocks, each containing no more than max_tokens tokens.
    """
    enc = tiktoken.get_encoding("o200k_base")

    # Split text by lines
    lines = chunk.splitlines()
    sub_chunks = []
    current_chunk = []
    current_tokens = 0

    for line in lines:
        # Calculate token count for current line
        line_tokens = enc.encode(line)
        line_token_count = len(line_tokens)

        # If adding current line exceeds max_tokens, save current chunk and start a new one
        if current_tokens + line_token_count > max_tokens:
            sub_chunks.append("\n".join(current_chunk))
            current_chunk = []
            current_tokens = 0

        # Add current line to the chunk
        current_chunk.append(line)
        current_tokens += line_token_count

    # Add the last chunk
    if current_chunk:
        sub_chunks.append("\n".join(current_chunk))

    return sub_chunks


def split_text_into_chunks(parallel_num, text: str) -> list:
    """Split text into chunks, each chunk processed by one set of API keys"""
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