
import os

from deduplication.qa_deduplication import QADeduplication
from generate_qas.qa_generator import QAGenerator
from quality_control.quality_control import QAQualityGenerator
from text_parse.parse import parse
from text_parse.to_tex import LatexConverter
from utils.hparams import DedupParams, HyperParams

def dedup():
    hparams=DedupParams.from_dedup_yaml('hparams/dedup.yaml')
    qa_dedup=QADeduplication(hparams)
    qa_dedup.process_qa_file(hparams)

def main():
    try:
        hparams = HyperParams.from_hparams('hyparams/config.yaml')

        file_list = []
        if os.path.isdir(hparams.file_path):
            files = os.listdir(hparams.file_path)
            for file in files:
                file_list.append(file)
        elif os.path.isfile(hparams.file_path):
            file_list.append(hparams.file_path)

        for file in file_list:
            try:
                print('Start iterative optimization of ' + os.path.basename(file))
                parsed_file_path = parse(hparams)
                latex_converter = LatexConverter(parsed_file_path, hparams)

                if file.split('.')[-1] != 'tex' and hparams.convert_to_tex:
                    latex_converter.convert_to_latex()

                qa_generator = QAGenerator(latex_converter.save_path, hparams)
                qa_path = qa_generator.convert_tex_to_qas()

                quality_control = QAQualityGenerator(qa_path, hparams)
                it_path = quality_control.iterate_optim_qa()

            except Exception as e:
                import traceback
                error_msg = f"Error processing file {file}: {str(e)}"
                stack_trace = traceback.format_exc()
               
                import asyncio
                loop = asyncio.get_event_loop()
                loop.run_until_complete(log_error(error_msg, "main_process", stack_trace))
                print(error_msg)
                continue

    except Exception as e:
        import traceback
        error_msg = f"Main process error: {str(e)}"
        stack_trace = traceback.format_exc()
        loop = asyncio.get_event_loop()
        loop.run_until_complete(log_error(error_msg, "main_process", stack_trace))
        print(error_msg)

if __name__=='__main__':
    main()














