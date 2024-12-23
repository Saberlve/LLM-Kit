import os
import requests
from tqdm import tqdm
import time
import json

import launcher

API_KEY=launcher.get_AK()
SECRET_KEY=launcher.get_SK()



def is_medical(question):
    # 定义prompt模板，并插入用户提供的标题组
    global wrongtime
    time.sleep(0.3)
    url = (
        "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/ernie-speed-128k?access_token="
        + get_access_token()
    )
    content="""请基于所给的问题<question>判断，其是否可能出现在临床场景中。根据下面两种情况给出<reply>:若可能，<reply>为1；若不太可能，<reply>为0。
    下面是两个例子
    1.<question>:哪些生长因子对单核细胞具有趋化作用
    <reply>:1
    2.<question>:如何处理和准备心电图图片以用于论文发表？
    <reply>:0
    <question>:{}
    <reply>:"""
    content = content.format(question)
    payload = json.dumps(
        {
            "messages": [
                {
                    "role": "user",
                    "content": content,
                }
            ],
            "system": ""
        }
    )
    headers = {"Content-Type": "application/json"}

    response = requests.request("POST", url, headers=headers, data=payload)

    response = json.loads(response.text)
    if response['result'].count('0')>response['result'].count('1'):
        # print('question:{},reason:{}'.format(question,response['result']))
        return False
    return True


def is_explicit(question):
    # 定义prompt模板，并插入用户提供的标题组
    global wrongtime
    time.sleep(0.3)
    url = (
        "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/ernie-speed-128k?access_token="
        + get_access_token()
    )
    content="""请基于所给的问题<question>判断，该问题是否包含一个明确的实体内容，或者是否涉及到一个明确的概念或领域，又或者是否提供了足够的上下文信息以确定一个具体的问题。根据下面两种情况给出<reply>:若问题具体且明确，或者涉及到明确的群体或概念，<reply>为1；若问题含糊不清，缺乏明确的实体或概念，<reply>为0。
    <question>:{}
    <reply>:"""
    content = content.format(question)
    payload = json.dumps(
        {
            "messages": [
                {
                    "role": "user",
                    "content": content,
                }
            ],
            "system": ""
        }
    )
    headers = {"Content-Type": "application/json"}

    response = requests.request("POST", url, headers=headers, data=payload)

    response = json.loads(response.text)
    if response['result'].count('0')>response['result'].count('1'):
        # print('question:{},reason:{}'.format(question,response['result']))
        return False
    return True


def get_access_token():
    """
    使用 AK，SK 生成鉴权签名（Access Token）
    :return: access_token，或是None(如果错误)
    """
    url = "https://aip.baidubce.com/oauth/2.0/token"
    params = {
        "grant_type": "client_credentials",
        "client_id": API_KEY,
        "client_secret": SECRET_KEY,
    }
    return str(requests.post(url, params=params).json().get("access_token"))


