from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from utils.helper import generate, extract_qa
import json
import os
import logging

logger = logging.getLogger(__name__)

def extract(response: str) -> dict:
    """
    从API响应中提取```json和```之间的JSON内容
    
    Args:
        response (str): API返回的原始响应文本
    
    Returns:
        dict: 解析后的JSON对象
    
    Raises:
        json.JSONDecodeError: 当JSON解析失败时
        ValueError: 当响应格式不正确时
    """
    try:
        # 查找```json和```之间的内容
        start_marker = "```json"
        end_marker = "```"
        
        start_idx = response.find(start_marker)
        if start_idx == -1:
            raise ValueError("未找到JSON开始标记")
            
        # 从start_marker后开始查找
        start_idx += len(start_marker)
        end_idx = response.find(end_marker, start_idx)
        
        if end_idx == -1:
            raise ValueError("未找到JSON结束标记")
            
        # 提取JSON字符串并解析
        json_str = response[start_idx:end_idx].strip()
        result = json.loads(json_str)
        
        return result
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON解析失败: {str(e)}")
        raise
    except ValueError as e:
        logger.error(f"响应格式错误: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"提取过程中发生错误: {str(e)}")
        raise

class COTGenerateService:
    def __init__(self, db: AsyncIOMotorClient):
        self.db = db

    async def generate_cot(
            self,
            content: str,
            filename: str,
            model_name: str,
            ak: str,
            sk: str,
            begin_prompt: str
    ):
        """生成COT推理并保存"""
        try:
            logger.info(f"开始生成COT，模型：{model_name}，文件名：{filename}")
            
            # 参数验证
            if not content or not content.strip():
                raise ValueError("内容不能为空")
            if not filename or not filename.strip():
                raise ValueError("文件名不能为空")
            if not model_name or not model_name.strip():
                raise ValueError("模型名称不能为空")
            if not ak or not sk:
                raise ValueError("API密钥不能为空")

            # 构造提示词
            prompt = begin_prompt
            logger.debug(f"构造的提示词：{prompt}")

            # 调用API
            try:
                response = generate(prompt, model_name, 'ToCOT', ak, sk)
                logger.debug(f"API响应：{response}")
            except Exception as e:
                logger.error(f"调用API失败：{str(e)}")
                raise Exception(f"调用生成API失败：{str(e)}")

            # 解析JSON响应
            try:
                print(response)
                cot_result = extract(response)
            except json.JSONDecodeError as e:
                logger.error(f"JSON解析失败：{str(e)}，原始响应：{response}")
                raise Exception("API返回的结果格式不正确")

            if not cot_result:
                logger.error("生成结果为空")
                raise Exception("No COT result generated")

            # 构建保存路径
            try:
                base_filename = filename.rsplit('.', 1)[0]
                save_dir_path = os.path.join('result', 'cot')
                os.makedirs(save_dir_path, exist_ok=True)
                final_save_path = os.path.join(save_dir_path, f"{base_filename}_cot.json")

                # 保存结果到文件
                with open(final_save_path, 'w', encoding='utf-8') as f:
                    json.dump(cot_result, f, ensure_ascii=False, indent=4)
                logger.info(f"COT结果已保存到：{final_save_path}")
            except Exception as e:
                logger.error(f"保存文件失败：{str(e)}")
                raise Exception(f"保存COT结果失败：{str(e)}")

            return {
                "filename": os.path.basename(final_save_path),
                "cot_result": cot_result
            }

        except Exception as e:
            logger.error(f"生成COT失败：{str(e)}")
            raise Exception(f"生成COT失败: {str(e)}")

    async def get_cot_content(self, filename: str):
        """获取COT文件内容"""
        try:
            if not filename or not filename.strip():
                raise ValueError("文件名不能为空")

            parsed_dir = os.path.join("result", "cot")
            raw_filename = filename.split('.')[0]
            parsed_filename = f"{raw_filename}_cot.json"
            target_path = os.path.join(parsed_dir, parsed_filename)
            
            if not os.path.isfile(target_path):
                logger.error(f"文件不存在：{target_path}")
                raise FileNotFoundError("COT file not found")
                
            with open(target_path, 'r', encoding='utf-8') as f:
                content = json.load(f)
                
            return content
        except Exception as e:
            logger.error(f"获取COT内容失败：{str(e)}")
            raise Exception(f"获取COT内容失败: {str(e)}")

    async def delete_cot_file(self, filename: str):
        """删除COT文件"""
        try:
            if not filename or not filename.strip():
                raise ValueError("文件名不能为空")

            parsed_dir = os.path.join("result", "cot")
            raw_filename = filename.split('.')[0]
            parsed_filename = f"{raw_filename}"
            target_path = os.path.join(parsed_dir, parsed_filename)
            
            if os.path.exists(target_path):
                os.remove(target_path)
                logger.info(f"成功删除文件：{target_path}")
                return True
            logger.info(f"文件不存在：{target_path}")
            return False
        except Exception as e:
            logger.error(f"删除COT文件失败：{str(e)}")
            raise Exception(f"删除COT文件失败: {str(e)}")
