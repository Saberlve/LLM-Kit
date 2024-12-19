import os
import re
import json

from setuptools.sandbox import save_path
from tqdm import tqdm

from utils.hyparams import HyperParams


class QAGenerator:
    def __init__(self,chunks_path,hparams:HyperParams):
        self.latex_symbols = [
            "\\alpha", "\\beta", "\\gamma", "\\theta", "\\varepsilon", "\\delta", "\\mu", "\\nu", "\\eta", "\\zeta",
            "\\lambda", "\\psi", "\\sigma", "\\xi", "\\tau", "\\phi", "\\varphi", "\\rho", "\\chi", "\\omega", "\\pi",
            "\\Sigma", "\\Pi", "\\Delta", "\\Gamma", "\\Psi", "\\Theta", "\\Lambda", "\\Omega", "\\Phi", "\\Xi",
            "\\mathrm{ABCdef}", "\\mathbf{ABCdef}", "\\mathit{ABCdef}", "\\pmb{ABCdef}", "\\mathscr{ABCdef}",
            "\\mathcal{ABCdef}", "\\mathfrak{ABCdef}", "\\mathbb{ABCdef}", "\\log()", "\\ln()", "\\lg()", "\\max", "\\min",
            "\\lim_{x \\to \\infty}", "\\arg\\max_{c \\in C}", "\\arg\\min_{c \\in C}", "\\exp",
        ]

        self.titles_patterns = [
            r"\\part\\{.*?\\}", r"\\chapter\\{.*?\\}", r"\\section\\{.*?\\}", r"\\subsection\\{.*?\\}",
            r"\\subsubsection\\{.*?\\}", r"\\paragraph\\{.*?\\}", r"\\subparagraph\\{.*?\\}", r"\\section\\*\\{.*?\\}"
        ]

        self.titles = [
            r"\\part", r"\\chapter", r"\\section", r"\\subsection", r"\\subsubsection", r"\\paragraph", r"\\subparagraph",
        ]
        self.hparams = hparams
        self.chunks_path = chunks_path
        self.save_dir_path = os.path.join('result', 'qas', f"qa_for_{os.path.basename(chunks_path) }")
        os.makedirs(self.save_dir_path, exist_ok=True)

    def clean_latex_and_preserve_titles_bold(self, latex):
        titles = []
        for pattern in self.titles_patterns:
            for match in re.finditer(pattern, latex):
                titles.append((match.start(), match.end(), match.group()))

        latex = re.sub(r'\\begin\\{.*?\\}.*?\\end\\{.*?\\}', "", latex, flags=re.DOTALL)
        latex = re.sub(r"\\textbf\\{(.*?)\\}", r"\\1", latex)

        titles_placeholder = []
        for i, (start, end, title_text) in enumerate(titles):
            titles_placeholder.append(f"__TITLE_PLACEHOLDER_{i}__")
            latex = latex[:start] + f"__TITLE_PLACEHOLDER_{i}__" + latex[end:]

        latex = re.sub(r"\\\\[a-zA-Z]+\\{.*?\\}", "", latex)
        latex = re.sub(r"\\\\[a-zA-Z]+\\[.*?\\]", "", latex)
        latex = re.sub(r"\\\\[a-zA-Z]+", "", latex)
        latex = re.sub(r"\\{.*?\\}", "", latex)

        for i, (start, end, title_text) in enumerate(titles):
            latex = latex.replace(titles_placeholder[i], title_text)

        latex = re.sub(r"\\n+", " ", latex).strip() + "\\n"
        reference_pos = latex.find("参 考 文 献")
        latex = latex[:reference_pos] if reference_pos != -1 else latex

        return latex

    def get_text_between_titles(self, start, latex):
        end = len(latex)
        for title in self.titles:
            now_pos = latex.find(title, start + 1)
            if now_pos != -1:
                end = min(end, now_pos)

        return end, latex[start:end]

    def filter_text(self, text):
        if "参考文献" in text or "参 考 文 献" in text:
            return False

        if len(text) > 1 and text[-2:] in ["：", "\\uFF1A"]:
            return False

        if r"\\section*" in text:
            return False

        content_len = len(text) - text.find("}")
        return content_len >= 18

    def convert_to_pure_qa_format(self, latex):
        start = 0
        total_length = len(latex)
        qa_pairs = []

        pbar = tqdm(total=total_length, position=0)
        while start < total_length - 1:
            wrongtime = 0
            previous_start = start
            start, text = self.get_text_between_titles(start, latex)
            text = self.clean_latex_and_preserve_titles_bold(text)
            if not self.filter_text(text):
                continue

            while wrongtime < 5:
                try:
                    qa = self.generate_question_methond3(text)  # Placeholder method
                    if isinstance(qa, dict):
                        qa["text"] = text
                        qa_pairs.append(qa)
                    elif isinstance(qa, list):
                        for qa_pair in qa:
                            qa_pair["text"] = text
                            qa_pairs.append(qa_pair)
                    break
                except Exception as e:
                    print(e)
                    wrongtime += 1

            pbar.n = previous_start + 1
            pbar.refresh()

        pbar.close()
        return qa_pairs

    def convert_tex_to_qas(self):
        with open(self.chunks_path, "r",encoding='utf-8') as f:
            chunks=json.load(f)


        print(f"开始处理 {root_path.split('/')[-2]}/{file}")
        file_path = os.path.join(root_path, file)

        with open(file_path, "r", encoding="utf-8") as f:
            latex_content = f.read()

        pure_qa_content = self.convert_to_pure_qa_format(latex_content)

        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as save_file:
            json.dump(pure_qa_content, save_file, ensure_ascii=False, indent=4)

