from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from utils.helper import generate, extract_qa
import json
import os
import logging
import asyncio

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

    async def process_chunk_with_api(self, text: str, ak: str, sk: str, model_name: str, domain: str, begin_prompt: str):
        """处理单个文本块并生成COT"""
        max_retries = 5
        
        for attempt in range(max_retries):
            try:
                # 构造提示词
                print(begin_prompt)
                prompt = begin_prompt.replace('{text}',text)
                
                # 调用API
                response = generate(prompt, model_name, 'ToCOT', ak, sk)
                result = extract(response)
                return result
            except Exception as e:
                if attempt == max_retries - 1:
                    print(f"处理文本块失败: {str(e)}")
                    raise
        return None

    async def process_chunks_parallel(self, chunks: list, ak_list: list, sk_list: list, 
                                    parallel_num: int, model_name: str, domain: str, begin_prompt: str):
        """并行处理多个文本块"""
        tasks = set()
        total_chunks = len(chunks)
        processed_chunks = 0
        results = []

        async def process_single_chunk(chunk, ak, sk):
            nonlocal processed_chunks
            result = await self.process_chunk_with_api(chunk, ak, sk, model_name, domain, begin_prompt)
            processed_chunks += 1
            return result

        for i, chunk in enumerate(chunks):
            ak = ak_list[i % len(ak_list)]
            sk = sk_list[i % len(sk_list)]
            
            if len(tasks) >= parallel_num:
                # 等待一个任务完成后再添加新任务
                done, pending = await asyncio.wait(
                    tasks, 
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                for task in done:
                    result = await task
                    if result:
                        results.append(result)
                tasks = pending
            
            task = asyncio.create_task(process_single_chunk(chunk, ak, sk))
            tasks.add(task)
        
        # 等待所有剩余任务完成
        if tasks:
            done, _ = await asyncio.wait(tasks)
            for task in done:
                result = await task
                if result:
                    results.append(result)
                    
        return results

    async def generate_cot(
            self,
            content: str,
            filename: str,
            model_name: str,
            ak_list: list,
            sk_list: list,
            parallel_num: int,
            begin_prompt: str,
            domain: str = "医学"
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
            if not ak_list or not sk_list:
                raise ValueError("API密钥不能为空")
            if len(ak_list) != len(sk_list):
                raise ValueError("AK和SK的数量必须相同")
            if parallel_num > len(ak_list):
                raise ValueError("并行数量不能大于API密钥对数量")

            # 解析JSON内容获取chunks
            try:
                content_json = json.loads(content)
                chunks = [item.get("chunk", "") for item in content_json if item.get("chunk")]
            except json.JSONDecodeError as e:
                logger.error(f"解析内容JSON失败：{str(e)}")
                raise ValueError("输入内容必须是有效的JSON格式")
            except Exception as e:
                logger.error(f"处理输入内容失败：{str(e)}")
                raise

            if not chunks:
                raise ValueError("没有找到有效的文本块")

            # 并行处理所有文本块
            cot_results = await self.process_chunks_parallel(
                chunks,
                ak_list,
                sk_list,
                parallel_num,
                model_name,
                domain,
                begin_prompt
            )

            if not cot_results:
                logger.error("生成结果为空")
                raise Exception("No COT result generated")

            # 构建最终结果数组
            final_results = []
            for i, result in enumerate(cot_results):
                if result and "推理" in result:
                    final_results.append({
                        "id": i + 1,
                        "content": chunks[i],
                        "result": result
                    })

            # 构建保存路径
            try:
                base_filename = filename.rsplit('.', 1)[0]
                save_dir_path = os.path.join('result', 'cot')
                os.makedirs(save_dir_path, exist_ok=True)
                final_save_path = os.path.join(save_dir_path, f"{base_filename}_cot.json")

                # 保存结果到文件
                with open(final_save_path, 'w', encoding='utf-8') as f:
                    json.dump(final_results, f, ensure_ascii=False, indent=4)
                logger.info(f"COT结果已保存到：{final_save_path}")
            except Exception as e:
                logger.error(f"保存文件失败：{str(e)}")
                raise Exception(f"保存COT结果失败：{str(e)}")

            return {
                "filename": os.path.basename(final_save_path),
                "cot_result": final_results
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
            parsed_filename = f"{raw_filename}"
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
            parsed_filename = f"{raw_filename}_cot.json"
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
