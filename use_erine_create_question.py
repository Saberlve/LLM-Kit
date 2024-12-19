import requests
import qianfan
import time
import json

API_KEY = "NDodQ4HrnTA0pV9nCf5cipaU"
SECRET_KEY = "cFLtpSn773bVJLx0JTA8P0aSLIYoFMQr"



wrongtime=0
def generate_question_methond3(answer=None):
    # 定义prompt模板，并插入用户提供的标题组
    global wrongtime
    time.sleep(0.7)
    url = (
        "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/ernie-speed-128k?access_token="
        + get_access_token()
    )

    system = """Output standard and clean json format {{"question":<question>, "answer":<answer>}}"""

    content = """1, please create some <question> closely consistent with the provided <text>. 
    Make sure that <question> is expressed in Chinese and does not explicitly cite the text. 
    You can include a specific scenario or context in <question>, 
    but make sure that <text> can be used as a comprehensive and accurate answer to the question.\n
    2. Then, you play the role of a doctor, who has in-depth knowledge in medicine. 
    Your task is to answer the user's <question> directly in Chinese. 
    In forming your response, you must use references to the <text> thoughtfully, 
    ensuring that <answer> comes from text and do not add other unnecessary content. 
    Please be careful to avoid including anything that may raise ethical issues.\n
    3. Output standard json format {{"question":<question>, "answer":<answer>}}
    <text>:{answer}"""
    content = content.format(answer=answer)
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
        print(tmp)
        try:
            qa_pairs.append(json.loads(tmp))
        except:
            print("error")
        start=response["result"].find('{',end)
        end=response["result"].find('}',end)+1
    
    
    print(qa_pairs)
    return qa_pairs
        
def correct_json(json_text):
    json_text = json_text.replace('{“q', '"{q')
    json_text = json_text.replace('question”', 'question"')
    json_text = json_text.replace('answer”', 'answer"')
    json_text = json_text.replace('“an', '"an"')
    json_text = json_text.replace('}”', '}"')
    json_text = json_text.replace(': “',': "')
    json_text = json_text.replace('”,','",')
    return json_text  
    


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
