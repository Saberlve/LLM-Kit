import os
import re
import json
import requests
from typing import List, Dict, Union, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from Levenshtein import ratio
from tqdm import tqdm
import tiktoken
from model_api.erine.erine import generate
from utils.helper import extract_qa
from utils.hyparams import HyperParams

class QAQualityGenerator:
    def __init__(self, qa_path: str, hparams: HyperParams):
        # 基础配置
        self.hparams = hparams
        self.qa_path = qa_path
        self.save_dir_path = os.path.join('result', 'qas_iterated', f"qa_iteratedfor_{os.path.basename(qa_path).split('.')[0]}")
        os.makedirs(self.save_dir_path, exist_ok=True)
        
        # API 相关
        self.ak_list = hparams.AK
        self.sk_list = hparams.SK
        self.parallel_num = hparams.parallel_num
        self._validate_keys()
        
        # 质量控制参数
        self.similarity_rate = hparams.similarity_rate
        self.coverage_rate = hparams.coverage_rate
        self.max_attempts = hparams.max_attempts
        

    def _validate_keys(self):
        """验证 API 密钥配置"""
        if len(self.ak_list) != len(self.sk_list):
            raise ValueError('AKs and SKs must have the same length!')
        if len(self.ak_list) < self.parallel_num:
            raise ValueError('请添加足够数量的 AK 和 SK！')


    @staticmethod
    def remove_non_chinese(text: str) -> str:
        """移除非中文字符"""
        if not isinstance(text, str):
            text = str(text)
        pattern = re.compile(r'[^\u4e00-\u9fa5]')
        return re.sub(pattern, '', text)

    def calculate_coverage(self, qa: Dict, nearby_qas: List[Dict]) -> float:
        """计算覆盖率"""
        #这个chunk包含m1个token，你把chunk中出现的answer都去掉，剩下m2个token。m2/m1就是这个chunk的覆盖率）
        # 1. 计算文本的token数量
        tokenizer = tiktoken.encoding_for_model("gpt-3.5-turbo")
        text_tokens = tokenizer.encode(qa['text'])
        answer_tokens = []
        for nearby_qa in nearby_qas:
            answer_tokens.extend(tokenizer.encode(nearby_qa['answer']))
        answer_tokens = set(answer_tokens)
        text_tokens = set(text_tokens)
        # 2. 计算覆盖率
        remaining_tokens = text_tokens - answer_tokens
        coverage = 1- len(remaining_tokens) / len(text_tokens)
        return coverage

    def calculate_similarity(self, str1: str, str2: str) -> float:
        """计算两个字符串的相似度"""
        return ratio(self.remove_non_chinese(str1), self.remove_non_chinese(str2))

    def is_medical(self, question: str, ak: str, sk: str) -> bool:
        """
        问题是否与医学相关
        :param question:
        :param ak:
        :param sk:
        :return: true or false
        """
        response = generate(question, ak, sk,prompt_choice='MEDICAL')
        if response.count('0')>response.count('1'):
            # print('question:{},reason:{}'.format(question,response['result']))
            return False
        return True

    def is_explicit(self, question: str, ak: str, sk: str) -> bool:
        """
        问题是否清晰
        :param question:
        :param ak:
        :param sk:
        :return: true or false
        """
        response = generate(question, ak, sk,prompt_choice='EXPLICIT')
        if response.count('0')>response.count('1'):
            # print('question:{},reason:{}'.format(question,response['result']))
            return False
        return True

    def find_suitable_qa(self, new_qas: List[Dict], nearby_qas: List[Dict]) -> Dict:
        """从候选问答对中找出最合适的一个"""
        index = 0
        min_ratio = 1
        for i, new_qa in enumerate(new_qas):
            for old_qa in nearby_qas:
                distance = self.calculate_similarity(new_qa['question'], old_qa['question'])
                if distance < min_ratio:
                    min_ratio = distance
                    index = i
        return new_qas[index]

    def regenerate_qa(self, qa: Dict, nearby_qas: List[Dict], ak: str, sk: str) -> Optional[Dict]:
        """重新生成问答对"""
        try:
            response = generate(qa['text'], ak, sk,'ToQA')
            #由于API返回的可能有多个问答对，显然不能再用和之前问答对一样的了，所以要重新找一个和他相似度比较低的替换
            if response:
                new_qa=extract_qa(response)
                selected_qa = self.find_suitable_qa(new_qa, nearby_qas) if len(new_qa) > 1 else new_qa[0]
                selected_qa['text'] = qa['text']
                return selected_qa
            
        except Exception as e:
            print(f'重新生成问答对时出错: {e}')
        return None

    def generate_more_qas(self, qa: Dict, nearby_qas: List[Dict], ak: str, sk: str) -> Optional[Dict]:
        """
        生成更多问答对
        """
        for i in range(self.max_attempts):
            try:
                response = generate(qa['text'], ak, sk,prompt_choice='MORE_QA')
                if response:
                    new_qa=extract_qa(response)
                    return new_qa
            except Exception as e:
                print(f'生成更多问答对时出错: {e}')
        return None
        
        

    def evaluate_qa_and_regenerate(self, qa: Dict, nearby_qas: List[Dict], ak: str, sk: str) -> Optional[Dict]:
        """
        评估当前qa，并且新生成
        :param qa: 一条问答对
        :param nearby_qas: 附近问答对
        :param ak:
        :param sk:
        :return: 新生成的问答底
        """
        for attempt in range(self.max_attempts):
            try:
                # 检查答案与文本相似度
                answer_list = qa['answer'].split('。')
                text_list = qa['text'].split('。')
                ratio = max(self.calculate_similarity(j, k) for j in text_list for k in answer_list)
                qa['ratio'] = ratio

                #检查问题质量，从明确性和医学相关性两个维度
                is_explicit = self.is_explicit(qa['question'], ak, sk)
                is_medical = self.is_medical(qa['question'], ak, sk)

                #如果相似度低于阈值，或者问题不明确或不医学相关，则重新生成
                if qa['ratio'] < self.similarity_rate or \
                   not is_explicit or not is_medical:
                    qa = self.regenerate_qa(qa, nearby_qas, ak, sk)
                    if not qa:
                        return None
                    continue
            
                    
            except Exception as e:
                print(f'质量检查时出错: {e}')
                attempt += 1

        return qa

    def check_coverage_and_regenerate(self, qa: Dict, nearby_qas: List[Dict], ak: str, sk: str) :
        """检查覆盖率"""
        coverage_rate = self.calculate_coverage(qa, nearby_qas)
        if coverage_rate < self.coverage_rate:
            new_qas = self.generate_more_qas(qa, nearby_qas, ak, sk)
            if new_qas:
                return new_qas
        return qa

    def iterate_optim_qa(self) -> None:
        """并行处理文件中的问答对，对每个问答对进行质量评估和优化。

        该函数从指定路径读取JSON格式的问答对数据，使用线程池并行处理每个问答对。
        对于每个问答对，会进行质量评估，如果不满足质量要求则重新生成。
        最终将优化后的问答对保存到指定目录。

        Args:
            None

        Returns:
            None

        Raises:
            json.JSONDecodeError: 如果输入文件不是有效的JSON格式
            IOError: 如果文件读写出现错误
        """
        from typing import List, Dict

        def get_nearby_qas(qas: List[Dict], i: int) -> List[Dict]:
            """
            获取与 qas[i] 文本相似的附近问答对（处理连续相同 text 的情况）。

            Args:
                qas: 问答对列表，每个问答对是一个字典，包含 'text' 字段。
                i: 当前问答对的索引。

            Returns:
                包含相似文本的附近问答对列表。
            """
            target_text = qas[i]['text']
            nearby_qas = []
            nearby_qas.append(qas[i])
            # 向前检查
            j = i - 1
            while j >= 0 and target_text in qas[j]['text']:
                nearby_qas.append(qas[j])
                j -= 1
            # 向后检查
            j = i + 1
            while j < len(qas) and target_text in qas[j]['text']:
                nearby_qas.append(qas[j])
                j += 1
            return nearby_qas
        
        
        """读取文件中的问答对，并行进行迭代"""
        with open(self.qa_path, "r", encoding='utf-8') as f:
            qas = json.load(f)

        print(f"开始处理 {os.path.basename(self.qa_path)}")
        qa_result = []

        #每对ak，sk循环使用
        with ThreadPoolExecutor(max_workers=self.parallel_num) as executor:
            futures = []
            for i, qa in enumerate(qas):
                ak = self.ak_list[i % len(self.ak_list)]
                sk = self.sk_list[i % len(self.sk_list)]
                nearby_qas = get_nearby_qas(qas, i)
                futures.append(
                    executor.submit(
                        lambda q, n, a, s: self.check_coverage_and_regenerate(
                            self.evaluate_qa_and_regenerate(q, n, a, s),
                            n, a, s
                        ),
                        qa,
                        nearby_qas,
                        ak,
                        sk,
                    )
                )
            with tqdm(total=len(futures), desc="质量控制问答对") as pbar:
                for future in as_completed(futures):
                    result = future.result()
                    if isinstance(result, list):
                        qa_result.extend(result)
                    elif result:
                        qa_result.append(result)
                    pbar.update(1)

        # 保存结果
        save_file_path = os.path.join(
            self.save_dir_path,
            os.path.basename(self.qa_path)
        )
        with open(save_file_path, "w", encoding="utf-8") as f:
            json.dump(qa_result, f, ensure_ascii=False, indent=4)