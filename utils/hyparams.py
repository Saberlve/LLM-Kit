from dataclasses import dataclass
import yaml


@dataclass
class HyperParams:
    file_path: str
    save_path: str
    model_name: str
    SK: str
    AK: str
    save_steps: str

    @classmethod
    def from_hparams(cls, hparams_name_or_path: str):

        if '.yaml' not in hparams_name_or_path:
            hparams_name_or_path = hparams_name_or_path + '.yaml'

        with open(hparams_name_or_path, "r") as stream:
            config = yaml.safe_load(stream)

        return cls(**config)