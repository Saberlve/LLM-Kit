import os
import re
import json
import requests
from typing import List, Dict, Union, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from Levenshtein import ratio
from tqdm import tqdm

from model_api.erine.erine import generate
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
        self.similarity_rate = 0.8
        self.coverage_rate = 0.9
        

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
            response = generate(qa['text'], ak, sk,'TOQA')
            #由于API返回的可能有多个问答对，显然不能再用和之前问答对一样的了，所以要重新找一个和他相似度比较低的替换
            if response:
                selected_qa = self.find_suitable_qa(response, nearby_qas) if len(response) > 1 else response[0]
                selected_qa['text'] = qa['text']
                return selected_qa
            
        except Exception as e:
            print(f'重新生成问答对时出错: {e}')
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
        max_attempts = 10
        for attempt in range(max_attempts):
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
                return qa

            except Exception as e:
                print(f'质量检查时出错: {e}')
                attempt += 1

        return None


    def iterate_optim_qa(self):
        def get_nearby_qas(qas, i):
            start_index = max(0, i - 3)
            end_index = min(len(qas), i + 3)
            return qas[start_index:end_index]

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
                nearby_qas= get_nearby_qas(qas, i)
                futures.append(
                    executor.submit(
                        self.evaluate_qa_and_regenerate,
                        qa,
                        nearby_qas,
                        ak,
                        sk,
                    )
                )

            for future in tqdm(as_completed(futures), total=len(futures), desc="生成并质量控制问答对"):
                qa_result.extend(future.result())

        # 保存结果
        save_file_path = os.path.join(
            self.save_dir_path,
            os.path.basename(self.qa_path)
        )
        with open(save_file_path, "w", encoding="utf-8") as f:
            json.dump(qa_result, f, ensure_ascii=False, indent=4)