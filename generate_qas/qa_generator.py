import os
import re
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple, Dict, Any
from dataclasses import dataclass, field

from tqdm import tqdm

from utils.helper import generate
from model_api.prompts import PROMPT_DICT
from utils.helper import  extract_qa
from utils.hyparams import HyperParams

@dataclass
class QAGenerator:
    chunks_path: str
    hparams: HyperParams
    latex_symbols: List[str] = field(default_factory=lambda: [
        "\\alpha", "\\beta", "\\gamma", "\\theta", "\\varepsilon", "\\delta", "\\mu", "\\nu",
        # ... 其他符号
    ])
    title_patterns: List[str] = field(default_factory=lambda: [
        r"\\part\{.*?\}", r"\\chapter\{.*?\}", r"\\section\{.*?\}",
        r"\\subsection\{.*?\}", r"\\subsubsection\{.*?\}", r"\\paragraph\{.*?\}",
        r"\\subparagraph\{.*?\}", r"\\section\*\{.*?\}"
    ])
    title_commands: List[str] = field(default_factory=lambda: [
        r"\\part", r"\\chapter", r"\\section", r"\\subsection",
        r"\\subsubsection", r"\\paragraph", r"\\subparagraph",
    ])

    def __post_init__(self):
        """初始化后的额外设置"""
        self.save_dir_path = os.path.join('result', 'qas', f"qa_for_{os.path.basename(self.chunks_path).split('.')[0]}")
        os.makedirs(self.save_dir_path, exist_ok=True)
        self.ak_list = self.hparams.AK
        self.sk_list = self.hparams.SK
        self.parallel_num = self.hparams.parallel_num
        self._validate_keys()

    def _validate_keys(self) -> None:
        """验证 API 密钥配置"""
        if len(self.ak_list) != len(self.sk_list):
            raise ValueError('AKs 和 SKs 数量必须相同！')
        if len(self.ak_list) < self.parallel_num:
            raise ValueError('请添加足够数量的 AK 和 SK！')

    def clean_latex_preserve_titles_bold(self, latex: str) -> str:
        """清理 LaTeX 文本，保留标题和加粗内容"""
        # 保存标题
        titles = [(m.start(), m.end(), m.group()) 
                 for pattern in self.title_patterns 
                 for m in re.finditer(pattern, latex)]
        
        # 使用占位符替换标题
        for i, (_, _, title_text) in enumerate(titles):
            latex = latex.replace(title_text, f"__TITLE_{i}__")
        
        # 清理 LaTeX 命令
        patterns_to_clean = [
            (r'\\begin\{.*?\}.*?\\end\{.*?\}', "", re.DOTALL),  # 环境内容
            (r"\\textbf\{(.*?)\}", r"\1"),  # 加粗命令
            (r"\\\\[a-zA-Z]+\{.*?\}", ""),  # 带花括号的命令
            (r"\\\\[a-zA-Z]+\[.*?\]", ""),  # 带方括号的命令
            (r"\\\\[a-zA-Z]+", ""),  # 普通命令
            (r"\\\{.*?\\\}", ""),  # 花括号内容
        ]
        
        for pattern, repl, *flags in patterns_to_clean:
            latex = re.sub(pattern, repl, latex, *flags)
        
        # 恢复标题
        for i, (_, _, title_text) in enumerate(titles):
            latex = latex.replace(f"__TITLE_{i}__", title_text)
            
        return latex.strip()

    def get_text_between_titles(self, start: int, latex: str) -> Tuple[int, str]:
        """获取标题之间的文本，即latex两级标题间文本"""
        end = len(latex)
        for title_cmd in self.title_commands:
            pos = latex.find(title_cmd, start + 1)
            if pos != -1:
                end = min(end, pos)
        return end, latex[start:end]

    def filter_text(self, text: str) -> bool:
        """过滤无效文本，待添加规则"""
        if not text.strip():
            return False
            
        invalid_conditions = [
            lambda t: any(kw in t for kw in ["参考文献", "参 考 文 献"]),
            lambda t: len(t) > 1 and t[-2:] in ["：", "\\uFF1A"],
            lambda t: "\\section*" in t,
            lambda t: len(t) - t.find("}") < 18
        ]
        
        return not any(condition(text) for condition in invalid_conditions)


    def process_chunk_with_api(self, text: str, ak: str, sk: str) -> List[Dict[str, Any]]:
        """
        具体调用api，process_latex_chunk的子函数，为了多线程设置的
        :param text:
        :param ak:
        :param sk:
        :return:
        """
        qa_pairs = []
        max_retries = 5
        
        for attempt in range(max_retries):
            try:
                response = generate(text,self.hparams.model_name, 'ToQA', ak, sk)
                qas=extract_qa(response)
                for qa_pair in qas:
                    qa_pair["text"] = text
                    qa_pairs.append(qa_pair)
                break

            except Exception as e:
                print(f"第 {attempt + 1} 次尝试失败: {str(e)}")
                if attempt == max_retries - 1:
                    print(f"达到最大重试次数，跳过此文本块: {text[:50]}...")
        
        return qa_pairs

    def process_latex_chunk(self, latex: str) -> List[Dict[str, Any]]:
        """
        处理LaTeX 块并生成问答对
        :param latex: latex文本
        :return: 列表，问答对
        """
        text_chunks = []
        start = 0
        
        # 分割文本
        while start < len(latex) - 1:
            end, text = self.get_text_between_titles(start, latex)
            text = self.clean_latex_preserve_titles_bold(text)
            if self.filter_text(text):
                text_chunks.append(text)
            start = end

        # 并行处理文本块
        qa_pairs = []
        with ThreadPoolExecutor(max_workers=self.parallel_num) as executor:
            futures = [
                executor.submit(
                    self.process_chunk_with_api,
                    text,
                    self.ak_list[i % len(self.ak_list)],
                    self.sk_list[i % len(self.sk_list)]
                )
                for i, text in enumerate(text_chunks)
            ]


            for future in as_completed(futures):
                qa_pairs.extend(future.result())


        return qa_pairs

    
    
    def convert_tex_to_qas(self) :
        """将 LaTeX 文件转换为问答对并保存"""
        try:
            with open(self.chunks_path, "r", encoding='utf-8') as f:
                chunks = json.load(f)
        except Exception as e:
            print(f"读取文件失败: {str(e)}")
            return
        PROMPT_DICT['RELATIVE']=PROMPT_DICT['RELATIVE'].replace('{domain}',self.hparams.domain)
        PROMPT_DICT['ToQA']=PROMPT_DICT['ToQA'].replace('{domain}',self.hparams.domain)
            # 保存结果
        save_file_path = os.path.join(
            self.save_dir_path,
            os.path.basename(self.chunks_path)
        )
        if os.path.exists(save_file_path):
            return save_file_path  #不重复生成


        print(f"开始处理文件: {os.path.basename(self.chunks_path)}")
        qa_result = []
        
        for chunk in tqdm(chunks, desc="生成问答对"):
            qas = self.process_latex_chunk(chunk.get("chunk", ""))
            qa_result.extend(qas)


        
        try:
            with open(save_file_path, "w", encoding="utf-8") as f:
                json.dump(qa_result, f, ensure_ascii=False, indent=4)
            print(f"结果已保存至: {save_file_path}")
        except Exception as e:
            print(f"保存结果失败: {str(e)}")
        return save_file_path

    

