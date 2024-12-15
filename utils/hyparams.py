from dataclasses import dataclass
import yaml


@dataclass
class HyperParams:
    file_path: str
    save_path: str
    SK: str
    AK: str
    model_name: str="Erine "  #调用的模型名字
    save_steps: int=100 #生成100个问答对保存一次



    @classmethod
    def from_hparams(cls, hparams_name_or_path: str):

        if '.yaml' not in hparams_name_or_path:
            hparams_name_or_path = hparams_name_or_path + '.yaml'
        with open(hparams_name_or_path, "r") as stream:
            config = yaml.safe_load(stream)
        return cls(**config)