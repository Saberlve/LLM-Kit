import json
import os
import argparse
from Levenshtein import ratio
import re
from judge_qa import is_explicit, is_medical

prompts = {
    'low_similarity': """1, please create some <question> closely consistent with the provided <text>. 
    Make sure that <question> is expressed in Chinese and does not explicitly cite the text. 
    You can include a specific scenario or context in <question>, 
    but make sure that <text> can be used as a comprehensive and accurate answer to the question.\n
    2. Then, you play the role of a doctor, who has in-depth knowledge in medicine. 
    Your task is to answer the user's <question> directly in Chinese. 
    In forming your response, you must use references to the <text> thoughtfully, 
    ensuring that <answer> comes from text and do not add other unnecessary content. 
    Please be careful to avoid including anything that may raise ethical issues.\n
    3. Output standard json format {{"question":<question>, "answer":<answer>}}
    <text>:{}""",
    'low_coverage': 'please'

}
# 相似度和覆盖率
similarity_rate = 0.8
coverage_rate = 0.9


def remove_non_chinese(text):
    if not isinstance(text, str):
        text = str(text)
    pattern = re.compile(r'[^\u4e00-\u9fa5]')

    chinese_only = re.sub(pattern, '', text)
    return chinese_only


def dis(str1, str2):
    return ratio(remove_non_chinese(str1), remove_non_chinese(str2))


def correct(qa, nearby_qas):
    ratio = 0
    count = 0
    while (ratio < similarity_rate and count < 10):
        try:
            answer_list = qa['answer'].split('。')
            text_list = qa['text'].split('。')
            if 'ratio' not in qa:
                ratio = max([dis(j, k) for j in text_list for k in answer_list])  # 计算相似度
            else:
                ratio = qa['ratio']

            if ratio >= similarity_rate:
                qa['ratio'] = ratio

            else:  # 小于阈值，重新生成
                qa = regenerate_qa(qa, nearby_qas)
                count += 1
                continue

            if is_explicit(qa['question']) == False:  # 若不明确，重新生成
                qa = regenerate_qa(qa, nearby_qas)
                count += 1
                continue
                
            if is_medical(qa['question']) == False:  # 若与医学无关，重新生成
                qa = regenerate_qa(qa, nearby_qas)
                count += 1
                continue
        except Exception as e:
            count+=1
            print(e)
            continue
        return qa
    return None



def regenerate_qa(qa, nearby_qas):
    try:
        response = reprocess_qa(qa, prompts['low_similarity'])  # 结果可能是列表，也可能是字典               
    
        if len(response)==1:  # 若是字典，进入下一次迭代
            _qa = response[0]

        elif isinstance(response, list):  # 若是列表，从中找一个和临近问答对相似度最低的当作qa
            _qa = find_suitable_qa(response, nearby_qas)

        _qa['text']=qa['text']
        return _qa

    except Exception as e:
        print('ERROR', end=':')
        print(e)

    

def find_suitable_qa(new_qas, nearby_qas):
    index = 0
    min_ratio = 1
    for i,new_qa in enumerate(new_qas):
        for old_qa in nearby_qas:
            distance = dis(new_qa['question'], old_qa['question'])
            if distance < min_ratio:
                min_ratio = distance
                index = i
    return new_qas[index]
