import os

from generate_qas.qa_generator import QAGenerator
from quality_control.quality_control import QAQualityGenerator
from text_parse.parse import parse
from text_parse.to_tex import LatexConverter
from utils.hyparams import HyperParams

def main():
    hparams=HyperParams.from_hparams('hyparams/config.yaml')

    file_list=[]  #待处理文件列表
    if os.path.isdir(hparams.file_path):
        files=os.listdir(hparams.file_path)
        for file in files:
            file_list.append(file)
    elif os.path.isfile(hparams.file_path):
        file_list.append(hparams.file_path)


    for file in file_list:
        print('Start iterative optimization of ' + os.path.basename(file))
        parsed_file_path=parse(hparams)  #对原始材料进行解析，返回解析后文本数据
        latex_converter=LatexConverter(parsed_file_path, hparams)
        if file.split('.')[-1]!='tex' and hparams.convert_to_tex==True:
            latex_converter.convert_to_latex()
        elif file.split('.')[-1]=='tex':
            pass
            # 仍然将文本拆分成chunk，搞到json中

        qa_generator=QAGenerator(latex_converter.save_path, hparams)
        qa_path=qa_generator.convert_tex_to_qas()

        # 质量控制
        quality_control=QAQualityGenerator(qa_path, hparams)
        quality_control.iterate_optim_qa()

            #将文件复制到目录下

if __name__=='__main__':
    main()

        
        
        
    

            
                
    
 
        
    
