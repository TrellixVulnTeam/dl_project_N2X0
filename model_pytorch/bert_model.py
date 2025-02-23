#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Author  : Joshua
@Time    : 3/19/20 5:00 PM
@File    : bert_model.py
@Desc    : 

"""


import torch
import torch.nn as nn
from model_pytorch.pretrained import BertModel, BertTokenizer
from model_pytorch.basic_config import ConfigBase



class Config(ConfigBase):
    """bert_dpcnn_pytorch配置参数"""
    def __init__(self, config_file, section):
        super(Config, self).__init__(config_file, section=section)

        self.tokenizer = BertTokenizer.from_pretrained(self.init_checkpoint_path)


class Model(nn.Module):

    def __init__(self, config):
        super(Model, self).__init__()
        self.bert = BertModel.from_pretrained(config.init_checkpoint_path)
        for param in self.bert.parameters():
            param.requires_grad = True
        self.fc = nn.Linear(config.hidden_size, config.num_labels)

    def forward(self, x):
        context = x[0]  # 输入的句子
        mask = x[2]  # 对padding部分进行mask，和句子一个size，padding部分用0表示，如：[1, 1, 1, 1, 0, 0]
        _, pooled = self.bert(context, attention_mask=mask, output_all_encoded_layers=False)
        out = self.fc(pooled)
        return out
