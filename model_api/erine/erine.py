import requests
import time
import json

from model_api.prompts import PROMPT_DICT


def generate_erine(text, API_KEY, SECRET_KEY,prompt_choice):
    """
    Call the model based on prompt and API keys
    :param text: Input text
    :param API_KEY: API key
    :param SECRET_KEY: Secret key
    :param prompt_choice: Prompt option
    :return: Model response
    """
    # Define prompt template and insert user-provided title groups

    time.sleep(0.3)
    url = (
        "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/ernie-speed-128k?access_token="
        + get_access_token(API_KEY,SECRET_KEY)
    )

    # system = """Output standard and clean json format {{"question":<question>, "answer":<answer>}}"""
    if prompt_choice == 'ToCOT':
        content=text
    else:
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
    print(response.content)
    response = json.loads(response.text)
    print(response)
    return response["result"]


def get_access_token(API_KEY,SECRET_KEY):
   
    url = "https://aip.baidubce.com/oauth/2.0/token"
    params = {
        "grant_type": "client_credentials",
        "client_id": API_KEY,
        "client_secret": SECRET_KEY,
    }
    return str(requests.post(url, params=params).json().get("access_token"))
