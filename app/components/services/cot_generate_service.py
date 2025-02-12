from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from utils.helper import generate
import json
import os

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
            # 构造提示词
            prompt = begin_prompt.format(text=content)
            # 调用API
            response = generate(prompt, model_name, 'ToCOT', ak, sk)
            # 解析JSON响应
            cot_result = json.loads(response)

            if not cot_result:
                raise Exception("No COT result generated")

            # 构建保存路径
            base_filename = filename.rsplit('.', 1)[0]
            save_dir_path = os.path.join('result', 'cot')
            os.makedirs(save_dir_path, exist_ok=True)
            final_save_path = os.path.join(save_dir_path, f"{base_filename}_cot.json")

            # 保存结果到文件
            with open(final_save_path, 'w', encoding='utf-8') as f:
                json.dump(cot_result, f, ensure_ascii=False, indent=4)

            return {
                "filename": os.path.basename(final_save_path),
                "cot_result": cot_result
            }

        except Exception as e:
            raise Exception(f"生成COT失败: {str(e)}")

    async def get_cot_content(self, filename: str):
        """获取COT文件内容"""
        try:
            parsed_dir = os.path.join("result", "cot")
            raw_filename = filename.split('.')[0]
            parsed_filename = f"{raw_filename}_cot.json"
            target_path = os.path.join(parsed_dir, parsed_filename)
            
            if not os.path.isfile(target_path):
                raise FileNotFoundError("COT file not found")
                
            with open(target_path, 'r', encoding='utf-8') as f:
                content = json.load(f)
                
            return content
        except Exception as e:
            raise Exception(f"获取COT内容失败: {str(e)}")

    async def delete_cot_file(self, filename: str):
        """删除COT文件"""
        try:
            parsed_dir = os.path.join("result", "cot")
            raw_filename = filename.split('.')[0]
            parsed_filename = f"{raw_filename}_cot.json"
            target_path = os.path.join(parsed_dir, parsed_filename)
            
            if os.path.exists(target_path):
                os.remove(target_path)
                return True
            return False
        except Exception as e:
            raise Exception(f"删除COT文件失败: {str(e)}")
