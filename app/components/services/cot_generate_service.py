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
    Extract JSON content between ```json and ``` from API response

    Args:
        response (str): Raw response text from API

    Returns:
        dict: Parsed JSON object

    Raises:
        json.JSONDecodeError: When JSON parsing fails
        ValueError: When response format is incorrect
    """
    try:
        # Find content between ```json and ```
        start_marker = "```json"
        end_marker = "```"

        start_idx = response.find(start_marker)
        if start_idx == -1:
            raise ValueError("JSON start marker not found")

        # Start searching after start_marker
        start_idx += len(start_marker)
        end_idx = response.find(end_marker, start_idx)

        if end_idx == -1:
            raise ValueError("JSON end marker not found")

        # Extract JSON string and parse
        json_str = response[start_idx:end_idx].strip()
        result = json.loads(json_str)

        return result

    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing failed: {str(e)}")
        raise
    except ValueError as e:
        logger.error(f"Response format error: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Error occurred during extraction: {str(e)}")
        raise


class COTGenerateService:
    def __init__(self, db: AsyncIOMotorClient):
        self.db = db

    async def process_chunk_with_api(self, text: str, ak: str, sk: str, model_name: str, domain: str,
                                     begin_prompt: str):
        """Process a single text chunk and generate COT"""
        max_retries = 5

        for attempt in range(max_retries):
            try:
                # Construct prompt
                print(begin_prompt)
                prompt = begin_prompt.replace('{text}', text)

                # Call API
                response = generate(prompt, model_name, 'ToCOT', ak, sk)
                result = extract(response)
                return result
            except Exception as e:
                if attempt == max_retries - 1:
                    print(f"Failed to process text chunk: {str(e)}")
                    raise
        return None

    async def process_chunks_parallel(self, chunks: list, ak_list: list, sk_list: list,
                                      parallel_num: int, model_name: str, domain: str, begin_prompt: str):
        """Process multiple text chunks in parallel"""
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
                # Wait for one task to complete before adding a new one
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

        # Wait for all remaining tasks to complete
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
            domain: str = "Medicine"
    ):
        """Generate COT reasoning and save"""
        try:
            logger.info(f"Starting COT generation, model: {model_name}, filename: {filename}")

            # Parameter validation
            if not content or not content.strip():
                raise ValueError("Content cannot be empty")
            if not filename or not filename.strip():
                raise ValueError("Filename cannot be empty")
            if not model_name or not model_name.strip():
                raise ValueError("Model name cannot be empty")
            if not ak_list or not sk_list:
                raise ValueError("API keys cannot be empty")
            if len(ak_list) != len(sk_list):
                raise ValueError("Number of AK and SK must be the same")
            if parallel_num > len(ak_list):
                raise ValueError("Parallel number cannot be greater than the number of API key pairs")

            # Parse JSON content to get chunks
            try:
                content_json = json.loads(content)
                chunks = [item.get("chunk", "") for item in content_json if item.get("chunk")]
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse content JSON: {str(e)}")
                raise ValueError("Input content must be valid JSON format")
            except Exception as e:
                logger.error(f"Failed to process input content: {str(e)}")
                raise

            if not chunks:
                raise ValueError("No valid text chunks found")

            # Process all text chunks in parallel
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
                logger.error("Generated result is empty")
                raise Exception("No COT result generated")

            # Build final results array
            final_results = []
            for i, result in enumerate(cot_results):
                if result and "reasoning" in result:
                    final_results.append({
                        "id": i + 1,
                        "content": chunks[i],
                        "result": result
                    })

            # Build save path
            try:
                base_filename = filename.rsplit('.', 1)[0]
                save_dir_path = os.path.join('result', 'cot')
                os.makedirs(save_dir_path, exist_ok=True)
                final_save_path = os.path.join(save_dir_path, f"{base_filename}_cot.json")

                # Save results to file
                with open(final_save_path, 'w', encoding='utf-8') as f:
                    json.dump(final_results, f, ensure_ascii=False, indent=4)
                logger.info(f"COT results saved to: {final_save_path}")
            except Exception as e:
                logger.error(f"Failed to save file: {str(e)}")
                raise Exception(f"Failed to save COT results: {str(e)}")

            return {
                "filename": os.path.basename(final_save_path),
                "cot_result": final_results
            }

        except Exception as e:
            logger.error(f"Failed to generate COT: {str(e)}")
            raise Exception(f"Failed to generate COT: {str(e)}")

    async def get_cot_content(self, filename: str):
        """Get COT file content"""
        try:
            if not filename or not filename.strip():
                raise ValueError("Filename cannot be empty")

            parsed_dir = os.path.join("result", "cot")
            raw_filename = filename.split('.')[0]
            parsed_filename = f"{raw_filename}"
            target_path = os.path.join(parsed_dir, parsed_filename)

            if not os.path.isfile(target_path):
                logger.error(f"File does not exist: {target_path}")
                raise FileNotFoundError("COT file not found")

            with open(target_path, 'r', encoding='utf-8') as f:
                content = json.load(f)

            return content
        except Exception as e:
            logger.error(f"Failed to get COT content: {str(e)}")
            raise Exception(f"Failed to get COT content: {str(e)}")

    async def delete_cot_file(self, filename: str):
        """Delete COT file"""
        try:
            if not filename or not filename.strip():
                raise ValueError("Filename cannot be empty")

            parsed_dir = os.path.join("result", "cot")
            raw_filename = filename.split('.')[0]
            parsed_filename = f"{raw_filename}_cot.json"
            target_path = os.path.join(parsed_dir, parsed_filename)

            PARSED_FILES_DIR1 = f"{filename}\\tex_files"

            parsed_filename1 = f"{raw_filename}.json"
            file_path1 = os.path.join(PARSED_FILES_DIR1, parsed_filename1)

            if os.path.exists(target_path):
                os.remove(target_path)
                if os.path.exists(file_path1):
                    os.remove(file_path1)
                logger.info(f"Successfully deleted file: {target_path}")
                return True
            logger.info(f"File does not exist: {target_path}")
            return False
        except Exception as e:
            logger.error(f"Failed to delete COT file: {str(e)}")
            raise Exception(f"Failed to delete COT file: {str(e)}")