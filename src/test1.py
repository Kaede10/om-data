import json
import os
import torch
from chat_api.configs import configs
from chat_api.logs import MyLogger
from transformers import AutoTokenizer, AutoModel, AutoConfig


class ChatGLM:
    def __init__(self) -> None:
        self.configs = configs
        self.base_model_path = self.configs.get('chat_glm', 'base_model_path')
        self.checkpoint_path = self.configs.get('chat_glm', 'checkpoint_path')
        self.pre_seq_len = self.configs.getint('chat_glm', 'pre_seq_len', fallback=128)
        self.max_length = self.configs.getint('chat_glm', 'max_length', fallback=2048)
        self.top_p = self.configs.getfloat('chat_glm', 'top_p')
        self.temperature = self.configs.getfloat('chat_glm', 'temperature')
        self.config = AutoConfig.from_pretrained(self.base_model_path, trust_remote_code=True)
        self.config.pre_seq_len = self.pre_seq_lens
        self.tokenizer = AutoTokenizer.from_pretrained(self.base_model_path, trust_remote_code=True)
        self.model = None

    def init_model(self):
        self.model = AutoModel.from_pretrained(self.base_model_path, config=self.config, trust_remote_code=True)
        self.model.half().cuda()
        self.model.eval()
        
        filtered_entries = [entry for entry in dictionary_list if entry.hour < 22]      
        if filtered_entries:
            max_hour_time = max(filtered_entries, key=lambda x: x.hour)
        else:
            max_hour_time = max(dictionary_list, key=lambda x: x.hour) 
        filtered_entries = [entry for entry in dictionary_list if entry.hour == max_hour_time.hour]
        return max(filtered_entries, key=lambda x: x.minute)
