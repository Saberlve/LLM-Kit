
import os
import asyncio
import traceback
import logging

from deduplication.qa_deduplication import QADeduplication
from generate_qas.qa_generator import QAGenerator
from quality_control.quality_control import QAQualityGenerator
from text_parse.parse import parse
from text_parse.to_tex import LatexConverter
from utils.hparams import DedupParams, HyperParams

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Error logging function
async def log_error(error_message: str, source: str, stack_trace: str = None):
    """Log error to console and potentially to a database in the future"""
    logger.error(f"Error in {source}: {error_message}")
    if stack_trace:
        logger.error(f"Stack trace: {stack_trace}")

def dedup():
    """Run the deduplication process"""
    try:
        logger.info("Loading deduplication parameters from hparams/dedup.yaml")
        hparams = DedupParams.from_dedup_yaml('hparams/dedup.yaml')

        logger.info("Initializing QA deduplication")
        qa_dedup = QADeduplication(hparams)

        logger.info("Processing QA files for deduplication")
        result = qa_dedup.process_qa_file(hparams)

        logger.info(f"Deduplication completed successfully")
        return result
    except Exception as e:
        error_msg = f"Error in deduplication: {str(e)}"
        stack_trace = traceback.format_exc()

        loop = asyncio.get_event_loop()
        loop.run_until_complete(log_error(error_msg, "deduplication", stack_trace))
        logger.error(error_msg)
        raise

def main():
    try:
        # 修正配置文件路径
        hparams = HyperParams.from_hparams('hparams/config.yaml')

        file_list = []
        if os.path.isdir(hparams.file_path):
            files = os.listdir(hparams.file_path)
            for file in files:
                file_list.append(os.path.join(hparams.file_path, file))
        elif os.path.isfile(hparams.file_path):
            file_list.append(hparams.file_path)

        logger.info(f"Processing {len(file_list)} files")

        for file in file_list:
            try:
                logger.info(f"Start iterative optimization of {os.path.basename(file)}")
                parsed_file_path = parse(hparams)
                latex_converter = LatexConverter(parsed_file_path, hparams)

                if file.split('.')[-1] != 'tex' and hparams.convert_to_tex:
                    latex_converter.convert_to_latex()

                qa_generator = QAGenerator(latex_converter.save_path, hparams)
                qa_path = qa_generator.convert_tex_to_qas()

                quality_control = QAQualityGenerator(qa_path, hparams)
                final_path = quality_control.iterate_optim_qa()

                logger.info(f"Completed processing file {os.path.basename(file)}")
                logger.info(f"Final output saved to {final_path}")

            except Exception as e:
                error_msg = f"Error processing file {file}: {str(e)}"
                stack_trace = traceback.format_exc()

                loop = asyncio.get_event_loop()
                loop.run_until_complete(log_error(error_msg, "file_processing", stack_trace))
                logger.error(error_msg)
                continue

    except Exception as e:
        error_msg = f"Main process error: {str(e)}"
        stack_trace = traceback.format_exc()

        loop = asyncio.get_event_loop()
        loop.run_until_complete(log_error(error_msg, "main_process", stack_trace))
        logger.error(error_msg)

def run_all():
    """Run both main processing and deduplication"""
    try:
        # First run the main processing
        logger.info("Starting main processing...")
        main()

        # Then run deduplication
        logger.info("Starting deduplication...")
        dedup()

        logger.info("All processing completed successfully")
    except Exception as e:
        error_msg = f"Error in run_all: {str(e)}"
        stack_trace = traceback.format_exc()

        loop = asyncio.get_event_loop()
        loop.run_until_complete(log_error(error_msg, "run_all", stack_trace))
        logger.error(error_msg)

if __name__=='__main__':
    # Uncomment the function you want to run
    # main()       # Run only the main processing
    # dedup()      # Run only the deduplication
    run_all()    # Run both main processing and deduplication

    # Testing main function
    # try:
    #     main()
    # except Exception as e:
    #     logger.error(f"Error running main: {e}")














