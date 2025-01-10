import requests
import json
import time
from model_api.prompts import PROMPT_DICT

def generate_lite(text, API_KEY, prompt_choice):

    time.sleep(0.3)
    url = "https://spark-api-open.xf-yun.com/v1/chat/completions"

    content = PROMPT_DICT[prompt_choice]
    content = content.format(text)

    data = {
            "model": "Lite", # 指定请求的模型
            "messages": [
                {
                    "role": "user",
                    "content": content
                }
            ],
        }

    header = {
        "Authorization": f"Bearer {API_KEY}"
    }
    response = requests.post(url, headers=header, json=data)
    response_dict = json.loads(response.text)

    return response_dict['choices'][0]['message']['content']

# "TonmZeZHCbYecrRWdxCj:XnqDwTsNWzeYEbpzCGoa"