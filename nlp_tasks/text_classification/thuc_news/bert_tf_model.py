#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Author  : Joshua
@Time    : 3/13/20 5:48 PM
@File    : bert_tf_model.py
@Desc    : bert 分类模型(tensorflow版本)

"""


import os
import tensorflow as tf
from model_tensorflow.bert_model import modeling
from model_tensorflow.bert_model import optimization
import logging

class BertClassifier(object):

    def __init__(self, config, is_training=True, num_train_step=None, num_warmup_step=None, logger=None):

        self.__bert_config_path = config.bert_config_path
        self.__num_classes = config.num_classes
        self.__learning_rate = config.learning_rate
        self.__is_training = is_training
        self.__num_train_step = num_train_step
        self.__num_warmup_step = num_warmup_step

        if logger:
            self.log = logger
        else:
            self.log = logging.getLogger("bert_train_log")
            logging.basicConfig(format='%(asctime)s : %(levelname)s : %(message)s')
            logging.root.setLevel(level=logging.INFO)

        self.input_ids = tf.placeholder(dtype=tf.int32, shape=[None, None], name='input_ids')
        self.input_masks = tf.placeholder(dtype=tf.int32, shape=[None, None], name='input_mask')
        self.segment_ids = tf.placeholder(dtype=tf.int32, shape=[None, None], name='segment_ids')
        self.label_ids = tf.placeholder(dtype=tf.int32, shape=[None], name="label_ids")

        self.built_model()
        self.init_saver()


    def built_model(self):

        bert_config = modeling.BertConfig.from_json_file(self.__bert_config_path)

        model = modeling.BertModel(config=bert_config,
                                   is_training=self.__is_training,
                                   input_ids=self.input_ids,
                                   input_mask=self.input_masks,
                                   token_type_ids=self.segment_ids,
                                   use_one_hot_embeddings=False)
        # [batch_size, seq_length, embedding_size]
        # output_layer = model.get_sequence_output()

        # [batch_size, embedding_size]
        # output_layer = model.get_pooled_output()

        layer3_sequence_output = model.all_encoder_layers[2]
        output_layer = tf.squeeze(layer3_sequence_output[:, 0:1, :], axis=1)
        # self.log.info("******")
        # self.log.info("{}".format(output_layer.shape))
        # self.log.info("{}".format(output_layer))
        # self.log.info("******")

        hidden_size = output_layer.shape[-1].value
        if self.__is_training:
            # I.e., 0.1 dropout
            output_layer = tf.nn.dropout(output_layer, keep_prob=0.9)

        with tf.name_scope("output"):
            output_weights = tf.get_variable(
                "output_weights", [self.__num_classes, hidden_size],
                initializer=tf.truncated_normal_initializer(stddev=0.02))

            output_bias = tf.get_variable(
                "output_bias", [self.__num_classes], initializer=tf.zeros_initializer())

            logits = tf.matmul(output_layer, output_weights, transpose_b=True)
            logits = tf.nn.bias_add(logits, output_bias)
            self.predictions = tf.argmax(logits, axis=-1, name="predictions")

        if self.__is_training:

            with tf.name_scope("loss"):
                losses = tf.nn.sparse_softmax_cross_entropy_with_logits(logits=logits, labels=self.label_ids)
                self.loss = tf.reduce_mean(losses, name="loss")

            with tf.name_scope('train_op'):
                self.train_op = optimization.create_optimizer(
                    self.loss, self.__learning_rate, self.__num_train_step, self.__num_warmup_step, use_tpu=False)

    def init_saver(self):
        self.saver = tf.train.Saver(tf.global_variables())

    def train(self, sess, batch):
        """
        训练模型
        :param sess: tf的会话对象
        :param batch: batch数据
        :return: 损失和预测结果
        """

        feed_dict = {self.input_ids: batch["input_ids"],
                     self.input_masks: batch["input_masks"],
                     self.segment_ids: batch["segment_ids"],
                     self.label_ids: batch["label_ids"]}

        # 训练模型
        _, loss, predictions = sess.run([self.train_op, self.loss, self.predictions], feed_dict=feed_dict)
        return loss, predictions

    def eval(self, sess, batch):
        """
        验证模型
        :param sess: tf中的会话对象
        :param batch: batch数据
        :return: 损失和预测结果
        """
        feed_dict = {self.input_ids: batch["input_ids"],
                     self.input_masks: batch["input_masks"],
                     self.segment_ids: batch["segment_ids"],
                     self.label_ids: batch["label_ids"]}

        loss, predictions = sess.run([self.loss, self.predictions], feed_dict=feed_dict)
        return loss, predictions

    def infer(self, sess, batch):
        """
        预测新数据
        :param sess: tf中的会话对象
        :param batch: batch数据
        :return: 预测结果
        """
        feed_dict = {self.input_ids: batch["input_ids"],
                     self.input_masks: batch["input_masks"],
                     self.segment_ids: batch["segment_ids"]}

        predict = sess.run(self.predictions, feed_dict=feed_dict)

        return predict