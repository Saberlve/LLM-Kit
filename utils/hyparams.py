from dataclasses import dataclass
import yaml

@dataclass
class HyperParams:
    file_path: str
    save_path: str
    SK: list[str]
    AK: list[str]
    parallel_num: int  # 单个文件的并行数量，要与SK,AK长度相等
    convert_to_tex: bool=True# 是否先将源文本转成latex格式，有利于提升问答对质量
    model_name: str="erine"  #调用的模型名字
    save_steps: int=100 #生成100个问答对保存一次



    @classmethod
    def from_hparams(cls, hparams_name_or_path: str):

        if '.yaml' not in hparams_name_or_path:
            hparams_name_or_path = hparams_name_or_path + '.yaml'
        with open(hparams_name_or_path, "r") as stream:
            config = yaml.safe_load(stream)
        return cls(**config)