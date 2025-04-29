from dataclasses import dataclass
import yaml

@dataclass
class HyperParams:
    file_path: str
    save_path: str
    parallel_num: int=1  # Number of parallel processes per file, must equal the length of SK,AK
    SK: list[str]=None
    AK: list[str]=None
    convert_to_tex: bool=True  # Whether to convert source text to LaTeX format, helps improve QA pair quality
    model_name: str="erine"  # Name of the model to call
    save_steps: int=100  # Save after generating 100 QA pairs
    similarity_rate: float=0.8  # Similarity threshold
    coverage_rate: float=0.9  # Coverage threshold
    max_attempts: int=3
    domain: str="medical"  # Domain


    @classmethod
    def from_hparams(cls, hparams_name_or_path: str):

        if '.yaml' not in hparams_name_or_path:
            hparams_name_or_path = hparams_name_or_path + '.yaml'
        with open(hparams_name_or_path, "r") as stream:
            config = yaml.safe_load(stream)
        return cls(**config)

@dataclass
class DedupParams:
    input_file: list[str]
    output_file: str
    dedup_by_answer: bool
    min_answer_length: int
    deleted_pairs_file: str
    dedup_threshold: float=0.8  # Deduplication threshold
    dedup_num_perm: int=128

    @classmethod
    def from_dedup_yaml(cls, dedup_yaml_path: str):
        with open(dedup_yaml_path, "r") as stream:
            config = yaml.safe_load(stream)
        return cls(**config)
