import requests
import time
import json

from model_api.prompts import PROMPT_DICT


def generate(text, API_KEY, SECRET_KEY,prompt_choice):
    # 定义prompt模板，并插入用户提供的标题组

    time.sleep(0.3)
    url = (
        "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/ernie-speed-128k?access_token="
        + get_access_token(API_KEY,SECRET_KEY)
    )

    # system = """Output standard and clean json format {{"question":<question>, "answer":<answer>}}"""

    content = PROMPT_DICT[prompt_choice]
    content = content.format(text)
    # print(prompt)

    payload = json.dumps(
        {
            "messages": [
                {
                    "role": "user",
                    "content": content,
                }
            ],
            "system": "",
        }
    )
    headers = {"Content-Type": "application/json"}

    response = requests.request("POST", url, headers=headers, data=payload)
    
    response = json.loads(response.text)
    return response["result"]
       
        
def get_access_token(API_KEY,SECRET_KEY):
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
