import tiktoken


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
