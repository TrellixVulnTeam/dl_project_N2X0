#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Author  : Joshua
@Time    : 11/18/19 10:54 PM
@File    : dnn2_v1_forward.py
@Desc    : 双隐藏层前向传播

"""


import tensorflow as tf


"""
网络结构：
输入层 -> 隐藏层1（256神经元） -> 隐藏层2(256神经元) -> 输出层
Input:
input[None,784]
Layer1:
sigmoid[784, 256]
Layer2:
relu[256,256] 
Output:
softmax[256,10] -> out[None, 10]
"""

INPUT_NODE = 784
OUTPUT_NODE = 10
LAYER1_NODE = 256
LAYER2_NODE = 256


def get_weight(shape, regularizer):
    w = tf.Variable(tf.truncated_normal(shape, stddev=0.1))
    if regularizer != None:
        tf.add_to_collection("losses", tf.contrib.layers.l2_regularizer(regularizer)(w))
    return w


def get_bias(shape):
    b = tf.Variable(tf.zeros(shape))
    return b


def forward(x, regularizer):
    w1 = get_weight([INPUT_NODE, LAYER1_NODE], regularizer)
    b1 = get_bias([LAYER1_NODE])
    y1 = tf.nn.sigmoid(tf.matmul(x, w1) + b1)

    w2 = get_weight([LAYER1_NODE, LAYER2_NODE], regularizer)
    b2 = get_bias([LAYER2_NODE])
    y2 = tf.nn.relu(tf.matmul(y1, w2) + b2)

    w = get_weight([LAYER2_NODE, OUTPUT_NODE], regularizer)
    b = get_bias(OUTPUT_NODE)
    y = tf.matmul(y2, w) + b

    return y
