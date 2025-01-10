import requests
import json
import time
from model_api.prompts import PROMPT_DICT
url = "https://api.siliconflow.cn/v1/chat/completions"

def generate_Qwen(text, API_KEY, prompt_choice):
    time.sleep(0.3)
    content = PROMPT_DICT[prompt_choice]
    content = content.format(text)
    print(content)
    payload = {
        "model": "Qwen/QVQ-72B-Preview",
        "messages": [
                    {
                        "role": "user",
                        "content": content
                    }
                ],
        "stream": False,
        "max_tokens": 1024,
        "temperature": 0.7,
        "top_p": 0.7,
        "top_k": 50,
        "frequency_penalty": 0.5,
        "response_format": {"type": "text"}
    }
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    response = requests.request("POST", url, json=payload, headers=headers)
    print(response.text)
    return response.json()['choices'][0]['message']['content']

#"sk-qeeatnpqrrqcbfyxteazthdmbjumfmxutkpgfrswirukrmxk"