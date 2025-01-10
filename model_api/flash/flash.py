import requests
import json
import time
from model_api.prompts import PROMPT_DICT

#api_key = "96989a8fc0944410bb11f30384473e37.dhqaTiu4jwORzuBR"


def generate_flash(text, API_KEY, prompt_choice):
    time.sleep(0.3)
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }

    content = PROMPT_DICT[prompt_choice]
    content = content.format(text)

    data = {
        "model": "glm-4-flash",
        "messages": [
            {
                "role": "user",
                "content": content,
            }
        ]
    }

    response = requests.post(url, headers=headers, data=json.dumps(data))

    return response.json()['choices'][0]['message']['content']
