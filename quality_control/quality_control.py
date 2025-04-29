import os
import re
import json
import requests
from typing import List, Dict, Union, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from Levenshtein import ratio
from tqdm import tqdm
import tiktoken
from utils.helper import generate
from utils.helper import extract_qa
from utils.hparams import HyperParams
from model_api.prompts import PROMPT_DICT

class QAQualityGenerator:
    def __init__(self, qa_path: str, hparams: HyperParams):
        # Basic configuration
        # Basic configuration
        self.hparams = hparams
        self.qa_path = qa_path
        self.save_dir_path = os.path.join('result', 'qas_iterated',
                                          f"qa_iteratedfor_{os.path.basename(qa_path).split('.')[0]}")
        os.makedirs(self.save_dir_path, exist_ok=True)
        self.model_name = hparams.model_name
        # API related
        # API related
        self.ak_list = hparams.AK
        self.sk_list = hparams.SK
        self.parallel_num = hparams.parallel_num
        self._validate_keys()
        PROMPT_DICT['RELATIVE'] = PROMPT_DICT['RELATIVE'].replace("'domain'", self.hparams.domain)
        PROMPT_DICT['ToQA'] = PROMPT_DICT['ToQA'].replace("'domain'", self.hparams.domain)

        self.similarity_rate = hparams.similarity_rate
        self.coverage_rate = hparams.coverage_rate
        self.max_attempts = hparams.max_attempts

    def _validate_keys(self):
        if len(self.ak_list) != len(self.sk_list):
            raise ValueError('AKs and SKs must have the same length!')
        if len(self.ak_list) < self.parallel_num:
            raise ValueError('Please add enough AK and SK!')
            raise ValueError('Please add enough AK and SK!')


    def calculate_coverage(self, qa: Dict, nearby_qas: List[Dict]) -> float:
        tokenizer = tiktoken.encoding_for_model("gpt-3.5-turbo")
        text_tokens = tokenizer.encode(qa['text'])
        answer_tokens = []
        for nearby_qa in nearby_qas:
            answer_tokens.extend(tokenizer.encode(nearby_qa['answer']))
        answer_tokens = set(answer_tokens)
        text_tokens = set(text_tokens)
    
        remaining_tokens = text_tokens - answer_tokens
        coverage = 1 - len(remaining_tokens) / len(text_tokens)
        return coverage

    def calculate_similarity(self, str1: str, str2: str) -> float:
        return ratio(str1, str2)

    def is_relative(self, question: str, ak: str, sk: str) -> bool:
        response = generate(question, self.model_name, 'RELATIVE', ak, sk)
        if response.count('0') > response.count('1'):
            # print('question:{},reason:{}'.format(question,response['result']))
            return False
        return True

    def is_explicit(self, question: str, ak: str, sk: str) -> bool:
        response = generate(question, self.model_name, 'EXPLICIT', ak, sk)
        if response.count('0') > response.count('1'):
            # print('question:{},reason:{}'.format(question,response['result']))
            return False
        return True

    def find_suitable_qa(self, new_qas: List[Dict], nearby_qas: List[Dict]) -> Dict:
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
        try:
            response = generate(qa['text'], self.model_name, 'ToQA', ak, sk)
            if response:
                new_qa = extract_qa(response)
                selected_qa = self.find_suitable_qa(new_qa, nearby_qas) if len(new_qa) > 1 else new_qa[0]
                selected_qa['text'] = qa['text']
                return selected_qa
        except Exception as e:
            print(f'Error regenerating QA pair: {e}')
            print(f'Error regenerating QA pair: {e}')
        return None

    def generate_more_qas(self, qa: Dict, nearby_qas: List[Dict], ak: str, sk: str) -> Optional[Dict]:
        for i in range(self.max_attempts):
            try:
                response = generate(qa['text'], self.model_name, 'MORE_QA', ak, sk)
                if response:
                    new_qa = extract_qa(response)
                    return new_qa
            except Exception as e:
                print(f'Error generating more QA pairs: {e}')
                print(f'Error generating more QA pairs: {e}')
        return None

    def evaluate_qa_and_regenerate(self, qa: Dict, nearby_qas: List[Dict], ak: str, sk: str) -> Optional[Dict]:
        for attempt in range(self.max_attempts):
            try:
                print(qa)
                answer_list = qa['answer'].split('。')
                text_list = qa['text'].split('。')
                ratio = max(self.calculate_similarity(j, k) for j in text_list for k in answer_list)
                qa['ratio'] = ratio

                is_explicit = self.is_explicit(qa['question'], ak, sk)
                is_medical = self.is_relative(qa['question'], ak, sk)

                if qa['ratio'] < self.similarity_rate or \
                        not is_explicit or not is_medical:
                    qa = self.regenerate_qa(qa, nearby_qas, ak, sk)
                    if not qa:
                        return None
                    continue
            except Exception as e:
                print(f'Error during quality check: {e}')
                print(f'Error during quality check: {e}')
                attempt += 1
        return qa

    def check_coverage_and_regenerate(self, qa: Dict, nearby_qas: List[Dict], ak: str, sk: str):
        coverage_rate = self.calculate_coverage(qa, nearby_qas)
        if coverage_rate < self.coverage_rate:
            new_qas = self.generate_more_qas(qa, nearby_qas, ak, sk)
            if new_qas:
                return new_qas
        return qa

    def iterate_optim_qa(self):
        try:
            if self.progress_callback:
                self.progress_callback(10)

            with open(self.qa_path, "r", encoding='utf-8') as f:
                qas = json.load(f)

            if self.progress_callback:
                self.progress_callback(20) 

            print(f"Starting processing {os.path.basename(self.qa_path)}")
            qa_result = []
            total_qas = len(qas)

            with ThreadPoolExecutor(max_workers=1) as executor: 
                futures = []
                for i, qa in enumerate(qas):
                    ak = self.ak_list[0] 
                    sk = self.sk_list[0]  
                    nearby_qas = self.get_nearby_qas(qas, i)
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

                with tqdm(total=len(futures), desc="Quality control QA pairs") as pbar:
                    for i, future in enumerate(as_completed(futures)):
                        result = future.result()
                        if isinstance(result, list):
                            qa_result.extend(result)
                        elif result:
                            qa_result.append(result)
                        pbar.update(1)

                        if self.progress_callback:
                            progress = int(20 + (i + 1) / total_qas * 70)  
                            self.progress_callback(progress)

            save_file_path = os.path.join(
                self.save_dir_path,
                os.path.basename(self.qa_path)
            )
            with open(save_file_path, "w", encoding="utf-8") as f:
                json.dump(qa_result, f, ensure_ascii=False, indent=4)

            if self.progress_callback:
                self.progress_callback(100)  

            return save_file_path

        except Exception as e:
            print(f"Quality control processing failed: {str(e)}")
            print(f"Quality control processing failed: {str(e)}")
            raise e

    @staticmethod
    def get_nearby_qas(qas: List[Dict], i: int) -> List[Dict]:
        target_text = qas[i]['text']
        nearby_qas = []
        nearby_qas.append(qas[i])
        # Check backward
        # Check backward
        j = i - 1
        while j >= 0 and target_text in qas[j]['text']:
            nearby_qas.append(qas[j])
            j -= 1
        # Check forward
        # Check forward
        j = i + 1
        while j < len(qas) and target_text in qas[j]['text']:
            nearby_qas.append(qas[j])
            j += 1
        return nearby_qas