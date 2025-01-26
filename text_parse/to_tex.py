import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from tqdm import tqdm  # 用于显示进度条
import json
from utils.helper import generate
from utils.helper import split_chunk_by_tokens, split_text_into_chunks
from utils.hparams import HyperParams

class LatexConverter:
    def __init__(self, parsed_file_path, hparams: HyperParams, progress_callback=None):
        self.hparams = hparams
        self.ak_list = hparams.AK
        self.sk_list = hparams.SK
        self.parallel_num = hparams.parallel_num
        self.parsed_file_path = parsed_file_path
        self.save_path = None
        self.progress_callback = progress_callback
        assert len(self.ak_list) == len(self.sk_list), 'AKs and SKs must have the same length!'
        assert len(self.ak_list) >= self.parallel_num, 'Please add enough AK and SK!'

    def process_chunk_with_api(self, chunk: str, ak: str, sk: str, chunk_index: int, total_chunks: int, max_tokens: int = 650) -> list:
        """处理单个文本块并更新进度"""
        sub_chunks = split_chunk_by_tokens(chunk, max_tokens)
        results = []

        for i, sub_chunk in enumerate(sub_chunks):
            for attempt in range(3):
                try:
                    tex_text = generate(sub_chunk, self.hparams.model_name, 'ToTex', ak, sk)
                    results.append(self.clean_result(tex_text))
                    
                    # 更新进度 - 使用浮点数计算以提高精度
                    if self.progress_callback:
                        # 当前块的基础进度 (0-80)
                        base_progress = (chunk_index / float(total_chunks)) * 80
                        # 当前子块的进度
                        sub_progress = ((i + 1) / float(len(sub_chunks))) * (80 / float(total_chunks))
                        # 合并进度并确保不超过80
                        progress = min(int(base_progress + sub_progress), 80)
                        self.progress_callback(progress)
                    break
                except Exception as e:
                    if attempt == 2:
                        raise e

        return results

    def convert_to_latex(self):
        """将解析后的文件内容转为LaTeX格式"""
        try:
            with open(self.parsed_file_path, "r", encoding="utf-8") as f:
                text = f.read()

            # 更新初始进度
            if self.progress_callback:
                self.progress_callback(10)  # 文件读取完成

            file_name = os.path.basename(self.parsed_file_path)
            save_path = os.path.join(
                self.hparams.save_path, 'tex_files', 
                file_name.split('.')[0] + '.json'
            )
            self.save_path = save_path

            if os.path.exists(self.save_path):
                if self.progress_callback:
                    self.progress_callback(100)  # 文件已存在，直接完成
                return save_path

            # 切分文本
            text_chunks = split_text_into_chunks(self.parallel_num, text)
            total_chunks = len(text_chunks)

            if self.progress_callback:
                self.progress_callback(20)  # 文本分块完成

            # 并行处理文本块
            results = []
            with ThreadPoolExecutor(max_workers=self.parallel_num) as executor:
                futures = [
                    executor.submit(
                        self.process_chunk_with_api, 
                        chunk, 
                        self.ak_list[i], 
                        self.sk_list[i],
                        i,
                        total_chunks
                    )
                    for i, chunk in enumerate(text_chunks)
                ]

                for future in as_completed(futures):
                    results.extend(future.result())

            # 准备保存数据
            data_to_save = [
                {"id": i + 1, "chunk": result}
                for i, result in enumerate(results)
            ]

            # 保存结果
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, 'w', encoding='utf-8') as json_file:
                json.dump(data_to_save, json_file, ensure_ascii=False, indent=4)

            if self.progress_callback:
                self.progress_callback(100)  # 完成

            return save_path

        except Exception as e:
            raise e

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


