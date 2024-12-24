import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from tqdm import tqdm  # 用于显示进度条

from model_api.erine.erine import generate
from utils.helper import split_chunk_by_tokens, split_text_into_chunks
from utils.hyparams import HyperParams

class LatexConverter:
    def __init__(self,parsed_file_path, hparams: HyperParams):

        self.hparams = hparams
        self.ak_list = hparams.AK
        self.sk_list = hparams.SK
        self.parallel_num = hparams.parallel_num
        self.parsed_file_path = parsed_file_path
        self.save_path=None
        assert len(self.ak_list) == len(self.sk_list), 'AKs and SKs must have the same length!'
        assert len(self.ak_list) >= self.parallel_num, 'Please add enough AK and SK!'

    def process_chunk_with_api(self, chunk: str, ak: str, sk: str, max_tokens: int = 650) -> list:
        """
        用指定的 AK 和 SK 调用 API 对文本块进行处理，确保每段不超过指定的 token 数量。

        Args:
            chunk (str): 输入的文本块。
            ak (str): API Key。
            sk (str): Secret Key。
            max_tokens (int): 每段的最大 token 数量，默认值为 650。

        Returns:
            list: 处理后的结果，每段的处理结果为一个字符串。
        """
        sub_chunks = split_chunk_by_tokens(chunk, max_tokens)
        results = []

        for sub_chunk in tqdm(sub_chunks,desc='Processing chunk'):
            print(f"调用 API：\nAK: {ak}, SK: {sk}\n处理文本块: {sub_chunk[:30]}...")  # 显示前30字符
            for attempt in range(3):  # 尝试3次处理
                try:
                    tex_text = generate(sub_chunk, ak, sk, 'ToTex')
                    results.append(self.clean_result(tex_text))
                    break
                except Exception as e:
                    print(f"尝试 {attempt + 1} 次失败: {e}")

        return results

    def convert_to_latex(self):
        """
        将解析后的文件内容转为 LaTeX 格式，并保存

        Args:
            parsed_file_path (str): 待处理文件路径。
        """
        with open(self.parsed_file_path, "r", encoding="utf-8") as f:
            text = f.read()

        file_name = os.path.basename(self.parsed_file_path)
        print(f"开始转成latex格式：{file_name}")

        save_path = os.path.join(
            self.hparams.save_path, 'tex_files', file_name.split('.')[0] + '.json'
        )
        self.save_path=save_path
        os.makedirs(os.path.dirname(save_path), exist_ok=True)

        # 切分文本
        text_chunks = split_text_into_chunks(self.parallel_num, text)

        print(f"文本被分为 {len(text_chunks)} 段，每段大小接近均匀")

        # 并行处理文本块
        results = []
        with ThreadPoolExecutor(max_workers=self.parallel_num) as executor:
            futures = [
                executor.submit(
                    self.process_chunk_with_api, chunk, self.ak_list[i], self.sk_list[i]
                )
                for i, chunk in enumerate(text_chunks)
            ]

            for future in tqdm(as_completed(futures), total=len(futures), desc="Processing chunks"):
                results.extend(future.result())

        import json

        # 准备保存数据的结构
        data_to_save = []
        for i, result in enumerate(results):
            data_to_save.append({
                "id": i + 1,  # id 从 1 开始
                "chunk": result  # 每个块的内容
            })
        with open(save_path, 'w', encoding='utf-8') as json_file:
            json.dump(data_to_save, json_file, ensure_ascii=False, indent=4)

        print("所有文本段已处理完成并保存！")

    def clean_result(self, text: str) -> str:
        """
        清理结果文本，提取 LaTeX 内容。

        Args:
            text (str): 原始文本。

        Returns:
            str: 清理后的 LaTeX 文本。
        """
        # 尝试找到起始位置
        start_index = max(
            text.find('```') + 3 if '```' in text else -1,
            0  # 默认从头开始
        )
        # 尝试找到结束位置
        end_index = text.rfind('```')
        # 提取并返回清理后的文本
        return text[start_index:end_index].strip()


