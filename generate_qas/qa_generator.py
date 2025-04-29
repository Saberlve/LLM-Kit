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
from utils.hparams import HyperParams

@dataclass
class QAGenerator:
    chunks_path: str
    hparams: HyperParams
    latex_symbols: List[str] = field(default_factory=lambda: [
        "\\alpha", "\\beta", "\\gamma", "\\theta", "\\varepsilon", "\\delta", "\\mu", "\\nu",
        # ... other symbols
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
    progress_callback: callable = None  # Add progress callback parameter

    def __post_init__(self):
        """Additional setup after initialization"""
        self.save_dir_path = os.path.join('result', 'qas', f"qa_for_{os.path.basename(self.chunks_path).split('.')[0]}")
        os.makedirs(self.save_dir_path, exist_ok=True)
        self.ak_list = self.hparams.AK
        self.sk_list = self.hparams.SK
        self.parallel_num = self.hparams.parallel_num
        self._validate_keys()


    def _validate_keys(self) -> None:
        """Validate API key configuration"""
        if len(self.ak_list) != len(self.sk_list):
            raise ValueError('AKs and SKs must have the same length!')
        if len(self.ak_list) < self.parallel_num:
            raise ValueError('Please add enough AK and SK!')

    def clean_latex_preserve_titles_bold(self, latex: str) -> str:
        """Clean LaTeX text, preserving titles and bold content"""
        # Save titles
        titles = [(m.start(), m.end(), m.group())
                 for pattern in self.title_patterns
                 for m in re.finditer(pattern, latex)]

        # Replace titles with placeholders
        for i, (_, _, title_text) in enumerate(titles):
            latex = latex.replace(title_text, f"__TITLE_{i}__")

        # Clean LaTeX commands
        patterns_to_clean = [
            (r'\\begin\{.*?\}.*?\\end\{.*?\}', "", re.DOTALL),  # Environment content
            (r"\\textbf\{(.*?)\}", r"\1"),  # Bold command
            (r"\\\\[a-zA-Z]+\{.*?\}", ""),  # Commands with braces
            (r"\\\\[a-zA-Z]+\[.*?\]", ""),  # Commands with brackets
            (r"\\\\[a-zA-Z]+", ""),  # Regular commands
            (r"\\\{.*?\\\}", ""),  # Content in braces
        ]

        for pattern, repl, *flags in patterns_to_clean:
            latex = re.sub(pattern, repl, latex, *flags)

        # Restore titles
        for i, (_, _, title_text) in enumerate(titles):
            latex = latex.replace(f"__TITLE_{i}__", title_text)

        return latex.strip()

    def get_text_between_titles(self, start: int, latex: str) -> Tuple[int, str]:
        """Get text between titles, i.e., text between two LaTeX section headings"""
        end = len(latex)
        for title_cmd in self.title_commands:
            pos = latex.find(title_cmd, start + 1)
            if pos != -1:
                end = min(end, pos)
        return end, latex[start:end]

    def filter_text(self, text: str) -> bool:
        """Filter invalid text, rules to be added"""
        if not text.strip():
            return False

        invalid_conditions = [
            lambda t: any(kw in t for kw in ["References", "Bibliography"]),
            lambda t: len(t) > 1 and t[-2:] in ["：", "\\uFF1A"],
            lambda t: "\\section*" in t,
            lambda t: len(t) - t.find("}") < 18
        ]

        return not any(condition(text) for condition in invalid_conditions)


    def process_chunk_with_api(self, text: str, ak: str, sk: str, chunk_index: int, total_chunks: int) -> List[Dict[str, Any]]:
        """Process a single text chunk and update progress"""
        qa_pairs = []
        max_retries = 5

        # Define progress stages
        base_progress = 20      # Initial stage
        process_range = 70      # Processing stage

        for attempt in range(max_retries):
            try:
                response = generate(text, self.hparams.model_name, 'ToQA', ak, sk)
                qas = extract_qa(response)
                for qa_pair in qas:
                    qa_pair["text"] = text
                    qa_pairs.append(qa_pair)

                # Update progress - using more precise progress calculation
                if self.progress_callback:
                    # Calculate current chunk progress, ensuring it doesn't exceed the processing stage limit
                    current_progress = base_progress + int((chunk_index + 1) / float(total_chunks) * process_range)
                    self.progress_callback(min(current_progress, base_progress + process_range))
                break
            except Exception as e:
                print(f"Attempt {attempt + 1} failed: {str(e)}")
                if attempt == max_retries - 1:
                    print(f"Maximum retry attempts reached, skipping this text chunk: {text[:50]}...")

        return qa_pairs

    def process_latex_chunk(self, latex: str) -> List[Dict[str, Any]]:
        """
        Process LaTeX chunk and generate QA pairs
        :param latex: LaTeX text
        :return: List of QA pairs
        """
        text_chunks = []
        start = 0

        # Split text
        while start < len(latex) - 1:
            end, text = self.get_text_between_titles(start, latex)
            text = self.clean_latex_preserve_titles_bold(text)
            if self.filter_text(text):
                text_chunks.append(text)
            start = end

        # Process text chunks in parallel
        qa_pairs = []
        with ThreadPoolExecutor(max_workers=self.parallel_num) as executor:
            futures = [
                executor.submit(
                    self.process_chunk_with_api,
                    text,
                    self.ak_list[i % len(self.ak_list)],
                    self.sk_list[i % len(self.sk_list)],
                    i,
                    len(text_chunks)
                )
                for i, text in enumerate(text_chunks)
            ]


            for future in as_completed(futures):
                qa_pairs.extend(future.result())


        return qa_pairs



    def convert_tex_to_qas(self) :
        """Convert LaTeX file to QA pairs and save"""
        try:
            # Update initial progress
            if self.progress_callback:
                self.progress_callback(10)

            with open(self.chunks_path, "r", encoding='utf-8') as f:
                chunks = json.load(f)

            if self.progress_callback:
                self.progress_callback(20)  # File reading completed

            save_file_path = os.path.join(
                self.save_dir_path,
                os.path.basename(self.chunks_path)
            )

            if os.path.exists(save_file_path):
                if self.progress_callback:
                    self.progress_callback(100)  # File already exists, complete directly
                return save_file_path

            print(f"Starting to process file: {os.path.basename(self.chunks_path)}")
            qa_result = []
            total_chunks = len(chunks)

            # Process text chunks in parallel
            with ThreadPoolExecutor(max_workers=self.parallel_num) as executor:
                futures = [
                    executor.submit(
                        self.process_chunk_with_api,
                        chunk.get("chunk", ""),
                        self.ak_list[i % len(self.ak_list)],
                        self.sk_list[i % len(self.sk_list)],
                        i,
                        total_chunks
                    )
                    for i, chunk in enumerate(chunks)
                ]

                for future in as_completed(futures):
                    qa_result.extend(future.result())

            # Save results
            try:
                with open(save_file_path, "w", encoding="utf-8") as f:
                    json.dump(qa_result, f, ensure_ascii=False, indent=4)
                if self.progress_callback:
                    self.progress_callback(100)  # Completed
                print(f"Results saved to: {save_file_path}")
            except Exception as e:
                print(f"Failed to save results: {str(e)}")
                raise e

            return save_file_path
        except Exception as e:
            raise e



