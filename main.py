import json
import os
from tqdm import tqdm
from quailty_module import correct
import launcher



file_path_or_name=launcher.get_file_path_or_name()
save_path=launcher.get_save_path()
start_index=launcher.get_start_index()
end_index=launcher.get_end_index()

file_list=[]  #待处理文件路径
if os.path.isdir(file_path_or_name):
    files=os.listdir(file_path_or_name)
    for file in files:
        file_list.append(file)
elif os.path.isfile(file_path_or_name):
    file_list.append(file_path_or_name)
    
    
for file in file_list:
    print('Start iterative optimization of ' + os.path.basename(file))

    with open(file, 'r', encoding='utf-8') as f:
        qas_data = json.load(f)

    if end_index == -1:
        end_index = len(qas_data)

    if not os.path.exists(save_path):
        os.makedirs(save_path)

    output_file_path = os.path.join(save_path, os.path.basename(file))
    
    # Batch for temporary storing processed QAs
    buffer = []

    with open(output_file_path, 'w', encoding='utf-8') as f:
        f.write('[')

        for i in tqdm(range(start_index, end_index)):
            start_i = max(0, i - 10)
            end_i = min(len(qas_data), i + 11)
            corrected_qa = correct(qas_data[i], qas_data[start_i:end_i])

            if corrected_qa is not None:
                buffer.append(corrected_qa)

            if len(buffer) >= 100:
                # Write buffered QAs to file
                for qa in buffer:
                    if f.tell() > 1:  # Check if more than initial '[' is in file
                        f.write(',\n')
                    f.write(json.dumps(qa, ensure_ascii=False, indent=4))
                # Clear buffer
                buffer = []

        # Write remaining QAs in buffer
        if buffer:
            for qa in buffer:
                if f.tell() > 1:
                    f.write(',\n')
                f.write(json.dumps(qa, ensure_ascii=False, indent=4))

        f.write('\n]')
        
        
        
    

            
                
    
 
        
    
