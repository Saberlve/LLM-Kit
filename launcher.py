import argparse
import os
import time
parser=argparse.ArgumentParser()
parser.add_argument('--file_path_or_name',type=str,default='/data/shuxun/chinese_med2qas/ToQA/qa_result.json')  #问答对文件的目录或名字
parser.add_argument('--save_path',type=str,default='/data/shuxun/iterative_optim/my_che_med_result/14000_new')
parser.add_argument('--AK',type=str,default='VO747o78RXDXUJ75ke8IyU8C')
parser.add_argument('--SK',type=str,default='xlixWWlSJdenv0KrfBYpHWWPo8kvsfJF')
parser.add_argument('--start_index',type=int,default=14000)
parser.add_argument('--end_index',type=int,default=19999)
args=parser.parse_args()


def get_AK():
    return args.AK
def get_SK():
    return args.SK
def get_start_index():
    return args.start_index
def get_end_index():
    return args.end_index
def get_file_path_or_name():
    return args.file_path_or_name
def get_save_path():
    return args.save_path





if __name__=='__main__':
    

    os.system("python /data/shuxun/iterative_optim/main.py")
    