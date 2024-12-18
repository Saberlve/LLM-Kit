import os

from text_parse.parse import parse
from text_parse.to_tex import LatexConverter
from utils.hyparams import HyperParams

hparams=HyperParams.from_hparams('hyparams/config.yaml')

file_list=[]  #待处理文件路径
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
    else:
        pass
        #将文件复制到目录下



        
        
        
    

            
                
    
 
        
    
