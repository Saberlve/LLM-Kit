import json
import re
import jieba
from datasketch import MinHash, MinHashLSH
from datetime import datetime
from utils.hparams import DedupParams

class QADeduplication:
    def __init__(self,hparams:DedupParams):
        self.threshold = hparams.dedup_threshold
        self.num_perm = hparams.dedup_num_perm
        self.lsh = MinHashLSH(threshold=self.threshold, num_perm=self.num_perm)
        self.stopwords = self._load_stopwords()
        self.priority_dict = {}
        
    def _load_stopwords(self):
        input_file_name = './hit_stopwords.txt'
        with open(input_file_name, 'r', encoding='utf-8') as f:
            return f.read().splitlines()
    
    def split_word(self, sentence):
        sentence = re.sub(r'[^\w\s]', '', sentence)
        words = list(jieba.cut(sentence))
        return [word for word in words if word not in self.stopwords]
    
    def get_qa_pairs(self, file_path):
        qa_pairs = []
        with open(file_path, 'r', encoding='utf-8') as f:
            data_list = json.load(f)
            for data in data_list:
                qa_pairs.append({
                    'question': data.get('question', ''),
                    'answer': data.get('answer', ''),
                    'id': data.get('id', '')
                })
        print(f"Total data processed: {len(qa_pairs)}")
        return qa_pairs
    
    def set_priority_order(self, filenames):
        """
        设置文件名的优先级顺序
        
        Args:
            filenames (list): 文件名列表，按优先级从高到低排序
            
        Example:
            qa_dedup.set_priority_order(['dataset1.json', 'dataset2.json', 'dataset3.json'])
        """
        self.priority_dict = {filename: idx for idx, filename in enumerate(filenames)}
        
    def select_best_qa_pair(self, qa_pairs, by_answer_length=False):
        def sort_key(x):
            # 从id中提取源文件名
            try:
                # 假设id中包含源文件信息，格式可能是：
                # - filename_number
                # - path/filename_number
                # - 其他格式
                id_parts = x['id'].split('_')
                if len(id_parts) >= 2:
                    # 如果文件名本身包含下划线，需要重新组合
                    filename = '_'.join(id_parts[:-1])
                    if not filename.endswith('.json'):
                        filename += '.json'
                else:
                    # 处理异常情况
                    filename = id_parts[0] + '.json'
                
                priority = self.priority_dict.get(filename, len(self.priority_dict))
            except Exception as e:
                # 如果解析失败，给予最低优先级
                priority = len(self.priority_dict)
                
            return (
                priority,
                -len(x['answer'] if by_answer_length else x['question'])
            )
            
        sorted_qa_pairs = sorted(qa_pairs, key=sort_key)
        return sorted_qa_pairs[0] if sorted_qa_pairs else None
    
    def deduplicate_by_question(self, input_file, output_file, deleted_pairs_file=None):
        start_time = datetime.now()
        qa_pairs = self.get_qa_pairs(input_file)
        
        # 初始化LSH
        for idx, qa_pair in enumerate(qa_pairs):
            words = self.split_word(qa_pair['question'])
            minhash = MinHash(num_perm=self.num_perm)
            for word in words:
                minhash.update(word.encode('utf-8'))
            self.lsh.insert(f"qa_pair_{idx}", minhash)
        
        # 执行去重
        unique_qa_pairs, delete_qa_pairs = self._process_deduplication(qa_pairs, by_question=True)
        
        # 保存结果
        self._save_results(unique_qa_pairs, output_file)
        if deleted_pairs_file:
            self._save_results(delete_qa_pairs, deleted_pairs_file)
            
        print(f"Execution time: {datetime.now() - start_time}")
        return unique_qa_pairs
    
    def deduplicate_by_answer(self, input_file, output_file, min_answer_length=15):
        start_time = datetime.now()
        qa_pairs = self.get_qa_pairs(input_file)
        
        # 初始化LSH
        for idx, qa_pair in enumerate(qa_pairs):
            words = self.split_word(qa_pair['answer'])
            minhash = MinHash(num_perm=self.num_perm)
            for word in words:
                minhash.update(word.encode('utf-8'))
            self.lsh.insert(f"qa_pair_{idx}", minhash)
        
        # 执行去重
        unique_qa_pairs, _ = self._process_deduplication(
            qa_pairs, 
            by_question=False, 
            min_answer_length=min_answer_length
        )
        
        # 保存结果
        self._save_results(unique_qa_pairs, output_file)
        print(f"Execution time: {datetime.now() - start_time}")
        return unique_qa_pairs
    
    def _process_deduplication(self, qa_pairs, by_question=True, min_answer_length=0):
        unique_qa_pairs = []
        delete_qa_pairs = []
        seen_id = set()
        filtered_count = 0
        
        for idx, qa_pair in enumerate(qa_pairs):
            identity = f"qa_pair_{idx}"
            if identity in seen_id:
                filtered_count += 1
                continue
                
            if not by_question and len(qa_pair['answer']) < min_answer_length:
                seen_id.add(identity)
                continue
                
            text = qa_pair['question'] if by_question else qa_pair['answer']
            words = self.split_word(text)
            minhash = MinHash(num_perm=self.num_perm)
            for word in words:
                minhash.update(word.encode('utf-8'))
                
            result = self.lsh.query(minhash)
            similar_qa_pairs = self._get_similar_pairs(result, qa_pairs, idx, seen_id)
            
            if similar_qa_pairs:
                all_pairs = [qa_pair] + similar_qa_pairs
                selected_pair = self.select_best_qa_pair(
                    all_pairs, 
                    by_answer_length=not by_question
                )
                if selected_pair and selected_pair not in unique_qa_pairs:
                    unique_qa_pairs.append(selected_pair)
                    if by_question:
                        delete_qa_pairs.append(all_pairs)
            else:
                unique_qa_pairs.append(qa_pair)
                
        print(f"Number of filtered data: {filtered_count}")
        return unique_qa_pairs, delete_qa_pairs
    
    def _get_similar_pairs(self, result, qa_pairs, current_idx, seen_id):
        similar_pairs = []
        for res in result:
            if res in seen_id:
                continue
            if res != f"qa_pair_{current_idx}":
                index = int(res.split('_')[2])
                similar_pair = qa_pairs[index]
                seen_id.add(res)
                if similar_pair not in similar_pairs:
                    similar_pairs.append(similar_pair)
            else:
                seen_id.add(res)
        return similar_pairs
    
    def _save_results(self, data, file_path):
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2) 
    
    def process_qa_file(self, hparams:DedupParams):
        """
        处理QA文件的完整流程：加载、去重、保存
        
        Args:
            input_file (str): 输入文件路径
            output_file (str): 输出文件路径
            dedup_by_answer (bool): 是否按答案去重，默认按问题去重
            min_answer_length (int): 按答案去重时的最小答案长度
            deleted_pairs_file (str): 存储被删除问答对的文件路径（仅在按问题去重时可用）
        
        Returns:
            list: 去重后的问答对列表
        """
        if hparams.dedup_by_answer:
            return self.deduplicate_by_answer(
            input_file=hparams.input_file,
            output_file=hparams.output_file,
            min_answer_length=hparams.min_answer_length
        )
        else:
            return self.deduplicate_by_question(
            input_file=hparams.input_file,
            output_file=hparams.output_file,
                deleted_pairs_file=hparams.deleted_pairs_file
        ) 