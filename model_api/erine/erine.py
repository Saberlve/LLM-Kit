import requests
import time
import json
import logging
import traceback

from model_api.prompts import PROMPT_DICT

# 获取logger
logger = logging.getLogger(__name__)

def generate_erine(text, API_KEY, SECRET_KEY, prompt_choice):
    """
    Call the model based on prompt and API keys
    :param text: Input text
    :param API_KEY: API key
    :param SECRET_KEY: Secret key
    :param prompt_choice: Prompt option
    :return: Model response
    """
    max_retries = 3
    retry_delay = 1.0  # 初始重试延迟（秒）
    
    for retry in range(max_retries):
        try:
            logger.info(f"调用ERNIE模型，尝试 {retry+1}/{max_retries}")
            
            # 添加等待时间避免API限流
            if retry > 0:
                sleep_time = retry_delay * (2 ** (retry - 1))  # 指数退避
                logger.info(f"等待 {sleep_time} 秒后重试")
                time.sleep(sleep_time)
            else:
                time.sleep(0.3)
                
            # 获取访问令牌
            access_token = get_access_token(API_KEY, SECRET_KEY)
            if not access_token:
                logger.error("获取访问令牌失败")
                continue
                
            url = f"https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/ernie-speed-128k?access_token={access_token}"

            # 准备请求内容
            if prompt_choice == 'ToCOT':
                content = text
            else:
                content = PROMPT_DICT[prompt_choice]
                content = content.format(text)
                
            logger.info(f"使用提示词类型: {prompt_choice}, 输入长度: {len(text)}")

            payload = json.dumps({
                "messages": [
                    {
                        "role": "user",
                        "content": content,
                    }
                ],
                "system": "",
            })
            headers = {"Content-Type": "application/json"}

            # 发送请求
            response = requests.request("POST", url, headers=headers, data=payload, timeout=30)
            
            # 检查HTTP状态码
            if response.status_code != 200:
                logger.error(f"API请求失败，HTTP状态码: {response.status_code}, 响应内容: {response.text}")
                continue
                
            # 解析响应
            try:
                response_data = json.loads(response.text)
                logger.info(f"API响应成功，响应长度: {len(response.text)}")
            except json.JSONDecodeError as e:
                logger.error(f"JSON解析错误: {e}, 响应内容: {response.text}")
                continue
                
            # 检查响应结构
            if "result" not in response_data:
                error_msg = f"API返回无效响应，缺少'result'字段: {response_data}"
                logger.error(error_msg)
                # 如果有错误信息，记录下来
                if "error_code" in response_data:
                    logger.error(f"API错误码: {response_data['error_code']}, 错误消息: {response_data.get('error_msg', '未知错误')}")
                continue
                
            # 成功获取结果
            return response_data["result"]
            
        except requests.RequestException as e:
            logger.error(f"请求异常 (尝试 {retry+1}/{max_retries}): {str(e)}")
        except Exception as e:
            logger.error(f"处理异常 (尝试 {retry+1}/{max_retries}): {str(e)}")
            logger.error(traceback.format_exc())
    
    # 所有重试都失败后
    logger.error(f"在 {max_retries} 次尝试后仍无法获取API响应")
    return None  # 返回None表示调用失败


def get_access_token(API_KEY, SECRET_KEY):
    """获取百度API访问令牌"""
    try:
        url = "https://aip.baidubce.com/oauth/2.0/token"
        params = {
            "grant_type": "client_credentials",
            "client_id": API_KEY,
            "client_secret": SECRET_KEY,
        }
        
        response = requests.post(url, params=params, timeout=10)
        
        # 检查HTTP状态码
        if response.status_code != 200:
            logger.error(f"获取令牌失败，HTTP状态码: {response.status_code}, 响应内容: {response.text}")
            return None
            
        # 解析响应
        try:
            data = response.json()
        except json.JSONDecodeError as e:
            logger.error(f"解析令牌响应JSON失败: {e}, 响应内容: {response.text}")
            return None
            
        # 获取令牌
        access_token = data.get("access_token")
        if not access_token:
            logger.error(f"响应中没有access_token字段: {data}")
            return None
            
        return access_token
        
    except Exception as e:
        logger.error(f"获取访问令牌时出现异常: {str(e)}")
        logger.error(traceback.format_exc())
        return None
