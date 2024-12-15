
import requests
import qianfan
import time
import json

API_KEY=launcher.get_AK()
SECRET_KEY=launcher.get_SK()
def correct_json(json_text):
    json_text = json_text.replace('{“q', '"{q')
    json_text = json_text.replace('question”', 'question"')
    json_text = json_text.replace('answer”', 'answer"')
    json_text = json_text.replace('“an', '"an"')
    json_text = json_text.replace('}”', '}"')
    json_text = json_text.replace(': “',': "')
    json_text = json_text.replace('”,','",')
    return json_text

def reprocess_qa(qa,prompt):
    # 定义prompt模板，并插入用户提供的标题组

    time.sleep(0.3)
    url = (
        "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/ernie-speed-128k?access_token="
        + get_access_token(API_KEY,SECRET_KEY)
    )

    # system = """Output standard and clean json format {{"question":<question>, "answer":<answer>}}"""

    content = prompt
    content = content.format(qa['text'])
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

    

    start=response["result"].find('{')
    end=response["result"].find('}')+1
    
    qa_pairs=[]
    
    while end!=0:
        tmp=correct_json(response["result"][start:end])
        
        try:
            qa_pairs.append(json.loads(tmp))
        except:
            print("error")
        start=response["result"].find('{',end)
        end=response["result"].find('}',end)+1
    
    
    print(qa_pairs)
    return qa_pairs
       
        
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

