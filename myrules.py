import os
import json
import re
from tqdm import tqdm
from use_erine_create_question import generate_question_methond3


latex_symbols = [
    # 小写希腊字母
    "\\alpha",
    "\\beta",
    "\\gamma",
    "\\theta",
    "\\varepsilon",
    "\\delta",
    "\\mu",
    "\\nu",
    "\\eta",
    "\\zeta",
    "\\lambda",
    "\\psi",
    "\\sigma",
    "\\xi",
    "\\tau",
    "\\phi",
    "\\varphi",
    "\\rho",
    "\\chi",
    "\\omega",
    "\\pi",
    # 大写希腊字母
    "\\Sigma",
    "\\Pi",
    "\\Delta",
    "\\Gamma",
    "\\Psi",
    "\\Theta",
    "\\Lambda",
    "\\Omega",
    "\\Phi",
    "\\Xi",
    # 常用字体
    "\\mathrm{ABCdef}",
    "\\mathbf{ABCdef}",
    "\\mathit{ABCdef}",
    "\\pmb{ABCdef}",
    "\\mathscr{ABCdef}",
    "\\mathcal{ABCdef}",
    "\\mathfrak{ABCdef}",
    "\\mathbb{ABCdef}",
    # 常见运算符
    "+",
    "-",
    "\\times",
    "\\pm",
    "\\cdot",
    "\\ast",
    "\\cup",
    "\\cap",
    "\\circ",
    "\\lor",
    "\\land",
    "\\lnot",
    "\\oplus",
    "\\ominus",
    "\\otimes",
    "\\odot",
    "\\oslash",
    "\\bullet",
    "\\sqrt{x}",
    "\\sqrt[n]{x}",
    # 大尺寸运算符
    "\\sum",
    "\\prod",
    "\\int",
    "\\bigcup",
    "\\bigcap",
    "\\oint",
    "\\bigvee",
    "\\bigwedge",
    "\\iint",
    "\\coprod",
    "\\bigsqcup",
    "\\oiint",
    # 常见关系符号
    "<",
    ">",
    "=",
    "\\leq",
    "\\geq",
    "\\neq",
    "\\ll",
    "\\gg",
    "\\equiv",
    "\\subset",
    "\\supset",
    "\\approx",
    "\\subseteq",
    "\\supseteq",
    "\\sim",
    "\\in",
    "\\ni",
    "\\propto",
    "\\vdash",
    "\\dashv",
    "\\models",
    "\\mid",
    "\\parallel",
    "\\perp",
    "\\notin",
    "\\Join",
    "\\nsim",
    "\\subsetneq",
    "\\supsetneq",
    # 数学模式重音符
    "\\hat{a}",
    "\\bar{a}",
    "\\tilde{a}",
    "\\vec{a}",
    "\\dot{a}",
    "\\ddot{a}",
    "\\widehat{abc}",
    "\\widetilde{abc}",
    "\\overline{abc}",
    # 箭头符号
    "\\leftarrow",
    "\\rightarrow",
    "\\leftrightarrow",
    "\\Leftarrow",
    "\\Rightarrow",
    "\\Leftrightarrow",
    "\\uparrow",
    "\\downarrow",
    "\\updownarrow",
    "\\Uparrow",
    "\\Downarrow",
    "\\Updownarrow",
    "\\leftharpoonup",
    "\\leftharpoondown",
    "\\rightharpoonup",
    "\\rightharpoondown",
    "\\rightleftharpoons",
    "\\leftrightharpoons",
    "\\iff",
    "\\mapsto",
    # 括号
    "\\left( \\right)",
    "\\left[ \\right]",
    "\\langle \\rangle",
    "\\lfloor\\rfloor",
    "\\lceil\\rceil",
    "\\overbrace{x_1x_2\\ldots x_n}^{n}",
    "\\underbrace{x_1x_2\\ldots x_n}_{n}",
    # 新增数学函数符号
    "\\log()",
    "\\ln()",
    "\\lg()",
    "\\max",
    "\\min",
    "\\lim_{x \\to \\infty}",
    "\\arg\\max_{c \\in C}",
    "\\arg\\min_{c \\in C}",
    "\\exp",
]





def clean_latex_and_preserve_titles_bold(latex):
    # 定义需要保留的标题模式
    titles_patterns = [
        r"\\part\{.*?\}",
        r"\\chapter\{.*?\}",
        r"\\section\{.*?\}",
        r"\\subsection\{.*?\}",
        r"\\subsubsection\{.*?\}",
        r"\\paragraph\{.*?\}",
        r"\\subparagraph\{.*?\}",
        r"\\section\*\{.*?\}",
    ]

    # 提取并保留标题
    titles = []
    for pattern in titles_patterns:
        for match in re.finditer(pattern, latex):
            titles.append((match.start(), match.end(), match.group()))

    # 删除图表插入段代码
    pattern = r'\\begin\{.*?\}.*?\\end\{.*?\}' 
    latex = re.sub(pattern, "", latex, flags=re.DOTALL)

    # 保留加粗内容中的文本
    latex = re.sub(r"\\textbf\{(.*?)}", r"\1", latex)

    # 构建正则表达式以保留LaTeX标题
    titles_placeholder = []
    for i, (start, end, title_text) in enumerate(titles):
        titles_placeholder.append(f"__TITLE_PLACEHOLDER_{i}__")
        latex = latex[:start] + f"__TITLE_PLACEHOLDER_{i}__" + latex[end:]

    # 删除所有其他LaTeX命令
    latex = re.sub(r"\\[a-zA-Z]+\{.*?}", "", latex)
    latex = re.sub(r"\\[a-zA-Z]+\[.*?]", "", latex)
    latex = re.sub(r"\\[a-zA-Z]+", "", latex)

    # 删除所有花括号及其中的内容
    latex = re.sub(r"\{.*?\}", "", latex)

    # 恢复标题
    for i, (start, end, title_text) in enumerate(titles):
        latex = latex.replace(titles_placeholder[i], title_text)

    # 去除段落内的所有换行符并在末尾添加一个
    latex = re.sub(r"\n+", " ", latex).strip() + "\n"

    reference_pos=latex.find("参 考 文 献")
    latex=latex[:reference_pos]
    return latex


titles = [
    r"\part",
    r"\chapter",
    r"\section",
    r"\subsection",
    r"\subsubsection",
    r"\paragraph",
    r"\subparagraph",
    
]


def get_text_between_titles(start, latex):
    end = len(latex)
    for title in titles:
        now_pos = latex.find(title, start + 1)
        if now_pos != -1:
            end = min(end, now_pos)

    return end, latex[start:end]


def filter_text(text):
    # 条件1：检查是否包含“参考文献”或“参 考 文 献”
    if "参考文献" in text:
        return False

    # 条件2：检查倒数第二个字符是否是冒号
    if len(text) > 1 and text[-2] == "：" or text[-1]=='：':
        return False

    # 条件3：检查是否包含 \section*
    if r"\section*" in text:
        return False

    # 过短
    content_len = len(text) - text.find("}")
    if content_len < 18:
        return False

    # 如果以上条件都不满足，返回 True
    return True


def convert_to_pure_qa_format(latex):

    start = 0

    total_length = len(latex)

    qa_pairs = []
    # 创建进度条，初始值为0
    pbar = tqdm(total=total_length, position=0)


    while start < total_length - 1:
        wrongtime = 0
        previous_start = start  # 记录上一个开始位置
        start, text = get_text_between_titles(start, latex)
        text = clean_latex_and_preserve_titles_bold(text)
        if filter_text(text) == False:
            continue
        while wrongtime < 5:
            try:
                qa = generate_question_methond3(text)
                # 检查 qa 的类型并加入 qa_pairs
                if isinstance(qa, dict):
                    # 如果 qa 是字典，直接加入 qa_pairs
                    qa["text"] = text
                    qa_pairs.append(qa)
                elif isinstance(qa, list):
                    # 如果 qa 是字典列表，将其扩展到 qa_pairs
                    for qa_pair in qa:
                        qa_pair["text"] = text
                        qa_pairs.append(qa_pair)
                break
            except Exception as e:
                print(e)
                wrongtime += 1
                # if wrongtime==5:assert 1 == 0, 'wrong'

        pbar.n = previous_start + 1  # 因为当前的 start 可能会变化
        pbar.refresh()  # 刷新进度条

    pbar.close()  # 关闭进度条
    return qa_pairs


def convert_tex_to_qs(root_path):
    files = os.listdir(root_path)  # 列出一本书中所有tex文件
    for file in files:
        if "appendix" in file:
            continue  # 忽略附录
        if os.path.exists("books2qas/result/" + root_path.split("/")[-2] + "/" + file.rsplit('.',1)[0]+'.json'):
            continue  # 忽略已经处理过的文件
        print("开始处理" + root_path.split("/")[-2] + "/" + file)
        file_path = os.path.join(root_path, file)
        # 读取文件
        with open(file_path, "r", encoding="utf-8") as file:
            latex_content = file.read()

        pure_qa_formatted_content = convert_to_pure_qa_format(latex_content)

        # 保存文件
        if not os.path.exists("./result"):  # 创建result文件夹
            os.mkdir("./result")

        dir_path = "./result/" + file_path.split("/")[-3]
        if not os.path.exists("./result/" + file_path.split("/")[-3]):
            os.mkdir("./result/" + file_path.split("/")[-3])
        save_path = dir_path + "/" + file_path.split("/")[-1].rsplit('.',1)[0]+'.json'

        jsons = json.dumps(pure_qa_formatted_content, ensure_ascii=False, indent=4)
        with open(save_path, "w", encoding="utf-8") as save_file:
            save_file.write(jsons)


books = os.listdir("books2qas/medical-books")
for book in books:
    if "idea" in book:
        continue
    root_path = "books2qas/medical-books/" + book + "/content"
    convert_tex_to_qs(root_path)
