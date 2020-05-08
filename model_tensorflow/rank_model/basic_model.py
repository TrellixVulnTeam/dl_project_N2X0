#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Author  : Joshua
@Time    : 5/7/20 2:37 PM
@File    : basic_model.py
@Desc    : 

"""



import tensorflow as tf
from tensorflow.python.ops import string_ops, array_ops, math_ops
from tensorflow.python.saved_model import signature_constants
from tensorflow.python.estimator.export import export_output
from tensorflow.python.ops import init_ops
from tensorflow.python.estimator.canned import head
from tensorflow.python.ops.losses import losses
from tensorflow.python.framework import ops
from tensorflow.python.feature_column import feature_column
from model_tensorflow.rank_model.transform_feature import FeatureBuilder
from model_tensorflow.tf_utils import PReLU, get_input_schema_spec, dice

import random
import collections

from abc import ABCMeta, abstractproperty

CLASSES = 'classes'
CLASS_IDS = 'class_ids'

_DEFAULT_SERVING_KEY = signature_constants.DEFAULT_SERVING_SIGNATURE_DEF_KEY
_CLASSIFY_SERVING_KEY = 'classification'
_PREDICT_SERVING_KEY = 'predict'
_REGRESS_SERVING_KEY = 'regression'

class BaseModel(object):
    __metaclass__ = ABCMeta

    def __init__(self, features,labels,params,mode):
        self.field_nums = []
        self.features = features
        self.labels =labels
        self.params = params
        self.mode = mode
        self.model_features = params["FEATURES_DICT"]
        self.logits = None
        # self.Linear_Features,\
        # self.Deep_Features = self._get_feature_embedding
        self.embedding_layer = None


    @abstractproperty
    def _model_fn(self):
        """
        model function 实现模型主题结构，必须在子类中对该函数进行实现
        :return:
        """
        # raise NotImplementedError
        pass

    @property
    def _get_feature_embedding(self):
        """
        解析model_feature.json文件中的特征，这里所有的特征分为两类
        :return:
        """
        Feature_Columns = FeatureBuilder(self.model_features)
        LinearFeas,DeepFeas = Feature_Columns.get_feature_columns()
        return LinearFeas, DeepFeas

    def get_input_layer(self, feature_columns):
        """
        输入层数据，上层网络共享底层输入的embedding数据
        :param feature_columns:
        :return:
        """
        embedding_layer = tf.feature_column.input_layer(self.features, feature_columns)
        return embedding_layer

    def _classification_output(self, scores, n_classes, label_vocabulary=None):
        """
        定义分类输出格式
        :param scores:
        :param n_classes:
        :param label_vocabulary:
        :return:
        """
        batch_size = array_ops.shape(scores)[0]
        if label_vocabulary:
            export_class_list = label_vocabulary
        else:
            export_class_list = string_ops.as_string(math_ops.range(n_classes))
        export_output_classes = array_ops.tile(
            input=array_ops.expand_dims(input=export_class_list, axis=0),
            multiples=[batch_size, 1])
        return export_output.ClassificationOutput(
            scores=scores,
            # `ClassificationOutput` requires string classes.
            classes=export_output_classes)

    def embedding_table(self, bucket_size, embedding_size, col):
        """
        生成矩阵
        :param bucket_size:
        :param embedding_size:
        :param col:
        :return:
        """
        embeddings = tf.get_variable(
            shape=[bucket_size, embedding_size],
            initializer=init_ops.glorot_uniform_initializer(),
            dtype=tf.float32,
            name="deep_embedding_" + col)
        return embeddings
    def get_activation(self,activation):
        """
        激活函数
        :param activation:
        :return:
        """
        if activation==None:
            act = None
        elif activation == 'prelu':
            act = PReLU
        elif activation == 'relu':
            act = tf.nn.relu
        else:
            act = tf.nn.sigmoid
        return act

    # get_optimizer_instance
    def fc_net(self, net, last_num=1, activation=None):
        """
        MLP全连接网络
        :param net:
        :param last_num:
        :param activation:
        :return:
        """

        act = self.get_activation(activation)
        net = tf.layers.batch_normalization(inputs=net, name='bn1', training=True)
        for units in self.params['HIDDEN_UNITS']:
            net = tf.layers.dense(net, units=units, activation=PReLU)
            if 'DROPOUT_RATE' in self.params and self.params['DROPOUT_RATE'] > 0.0:
                net = tf.layers.dropout(net, self.params['DROPOUT_RATE'], training=(self.mode == tf.estimator.ModeKeys.TRAIN))
        logits = tf.layers.dense(net, last_num, activation=act)
        return logits

    def cross_layer(self, x0, x, name):
        """
        deep cross net中的单层cross结构
        :param x0:
        :param x:
        :param name:
        :return:
        """
        with tf.variable_scope(name):
            input_dim = x0.get_shape().as_list()[1]
            w = tf.get_variable("weight", [input_dim], initializer=tf.truncated_normal_initializer(stddev=0.01))
            b = tf.get_variable("bias", [input_dim], initializer=tf.truncated_normal_initializer(stddev=0.01))
            xb = tf.tensordot(tf.reshape(x, [-1, 1, input_dim]), w, 1)
            return x0 * xb + b + x

    def cross_net(self, net, cross_layer_num):
        '''deep cross net中的cross侧网络结构'''
        '''cross network'''
        x0 = net
        for i in range(cross_layer_num):
            net = self.cross_layer(x0, net, 'cross_{}'.format(i))
        return net

    @property
    def build_estimator_spec(self):
        """
        Build EstimatorSpec 返回一个EstimatorSpec
        :return:
        """
        my_head = head._binary_logistic_head_with_sigmoid_cross_entropy_loss(  # pylint: disable=protected-access
                loss_reduction=losses.Reduction.SUM)
        optimizer = tf.train.AdagradOptimizer(learning_rate=self.params['LEARNING_RATE'])
        return my_head.create_estimator_spec(
            features=self.features,
            mode=self.mode,
            labels=self.labels,
            optimizer=optimizer,
            logits=self.logits)

    # tf.estimator.DNNLinearCombinedClassifier（）
    def _check_logits_final_dim(self,logits, expected_logits_dimension):
        """
        Checks that logits shape is [D0, D1, ... DN, logits_dimension]
        :param logits:
        :param expected_logits_dimension:
        :return:
        """
        with ops.name_scope(None, 'logits', (logits,)) as scope:
            logits = tf.to_float(logits)
            logits_shape = tf.shape(logits)
            assert_rank = tf.assert_rank_at_least(
                logits, 2, data=[logits_shape],
                message='logits shape must be [D0, D1, ... DN, logits_dimension]')
            with ops.control_dependencies([assert_rank]):
                static_shape = logits.shape
                if static_shape.ndims is not None and static_shape[-1] is not None:
                    if static_shape[-1] != expected_logits_dimension:
                        raise ValueError(
                            'logits shape must be [D0, D1, ... DN, logits_dimension], '
                            'got %s.' % (static_shape,))
                    return logits
                assert_dimension = tf.assert_equal(
                    expected_logits_dimension, logits_shape[-1], data=[logits_shape],
                    message='logits shape must be [D0, D1, ... DN, logits_dimension]')
                with ops.control_dependencies([assert_dimension]):
                    return tf.identity(logits, name=scope)

    def attention_layer(self, seq_ids, tid, bucket_size, embedding_size, attention_hidden_units, id_type):
        """
        attention 结构
        :param seq_ids: 序列id
        :param tid: 目标id
        :param bucket_size:
        :param embedding_size:
        :param attention_hidden_units:
        :param id_type:
        :return:
        """
        ''''''
        with tf.variable_scope("attention_" + id_type):
            embeddings = self.embedding_table(bucket_size, embedding_size, id_type)
            seq_emb = tf.nn.embedding_lookup(embeddings,
                                                 seq_ids)  # shape(batch_size, max_seq_len, embedding_size)
            u_emb = tf.reshape(seq_emb, shape=[-1, embedding_size])

            tid_emb = tf.nn.embedding_lookup(embeddings, tid)  # shape(batch_size, embedding_size)
            max_seq_len = tf.shape(seq_ids)[1]  # padded_dim
            a_emb = tf.reshape(tf.tile(tid_emb, [1, max_seq_len]), shape=[-1, embedding_size])

            net = tf.concat([u_emb, a_emb, u_emb - a_emb, u_emb * a_emb], axis=1)
            for units in attention_hidden_units:
                net = tf.layers.dense(net, units=units, activation=tf.nn.relu)
            att_wgt = tf.layers.dense(net, units=1, activation=tf.sigmoid)
            att_wgt = tf.reshape(att_wgt, shape=[-1, max_seq_len, 1], name="weight")
            wgt_emb = tf.multiply(seq_emb, att_wgt)  # shape(batch_size, max_seq_len, embedding_size)
            # masks = tf.sequence_mask(seq_len, max_seq_len, dtype=tf.float32)
            masks = tf.expand_dims(tf.cast(seq_ids >= 0, tf.float32), axis=-1)
            att_emb = tf.reduce_sum(tf.multiply(wgt_emb, masks), 1, name="weighted_embedding")
            return att_emb, tid_emb

    def auxiliary_net(self, in_, stag='auxiliary_net'):
        bn1 = tf.layers.batch_normalization(inputs=in_, name='bn1' + stag, reuse=tf.AUTO_REUSE)
        dnn1 = tf.layers.dense(bn1, 100, activation=None, name='f1' + stag, reuse=tf.AUTO_REUSE)
        print("dnn1:", dnn1.get_shape().as_list())
        dnn1 = tf.nn.sigmoid(dnn1)
        dnn2 = tf.layers.dense(dnn1, 50, activation=None, name='f2' + stag, reuse=tf.AUTO_REUSE)
        dnn2 = tf.nn.sigmoid(dnn2)
        dnn3 = tf.layers.dense(dnn2, 2, activation=None, name='f3' + stag, reuse=tf.AUTO_REUSE)
        y_hat = tf.nn.softmax(dnn3) + 0.00000001
        print("y_hat:", y_hat.get_shape().as_list())
        return y_hat

    def auxiliary_loss(self, h_states, click_seq, noclick_seq, mask, stag=None):
        mask = tf.cast(mask, tf.float32)
        click_input_ = tf.concat([h_states, click_seq], -1)
        #shape [seqlen-1,embedding*2]
        print("click_input:", click_input_.get_shape().as_list())
        noclick_input_ = tf.concat([h_states, noclick_seq], -1)

        click_prop_ = self.auxiliary_net(click_input_, stag=stag)[:, :, 0]
        noclick_prop_ = self.auxiliary_net(noclick_input_, stag=stag)[:, :, 0]
        print("click_prop:", click_prop_.get_shape().as_list())
        click_loss_ = - tf.reshape(tf.log(click_prop_), [-1, tf.shape(click_seq)[1]]) * mask
        noclick_loss_ = - tf.reshape(tf.log(1.0 - noclick_prop_), [-1, tf.shape(noclick_seq)[1]]) * mask
        loss_ = tf.reduce_sum(click_loss_ + noclick_loss_)
        return loss_

    def din_fcn_attention(self, query, facts, attention_size, mask, stag='null', mode='SUM', softmax_stag=1,
                          time_major=False,
                          return_alphas=False, forCnn=False):
        if isinstance(facts, tuple):
            # In case of Bi-RNN, concatenate the forward and the backward RNN outputs.
            facts = tf.concat(facts, 2)
        if len(facts.get_shape().as_list()) == 2:
            facts = tf.expand_dims(facts, 1)

        # if time_major:
        #     # (T,B,D) => (B,T,D)
        #     facts = tf.array_ops.transpose(facts, [1, 0, 2])
        # Trainable parameters
        mask = tf.equal(mask, tf.ones_like(mask))
        facts_size = facts.get_shape().as_list()[-1]  # D value - hidden size of the RNN layer
        querry_size = query.get_shape().as_list()[-1]
        query = tf.layers.dense(query, facts_size, activation=None, name='f1' + stag)
        query = PReLU(query)
        queries = tf.tile(query, [1, tf.shape(facts)[1]])
        queries = tf.reshape(queries, tf.shape(facts))
        din_all = tf.concat([queries, facts, queries - facts, queries * facts], axis=-1)
        d_layer_1_all = tf.layers.dense(din_all, 80, activation=tf.nn.sigmoid, name='f1_att' + stag)
        d_layer_2_all = tf.layers.dense(d_layer_1_all, 40, activation=tf.nn.sigmoid, name='f2_att' + stag)
        d_layer_3_all = tf.layers.dense(d_layer_2_all, 1, activation=None, name='f3_att' + stag)
        d_layer_3_all = tf.reshape(d_layer_3_all, [-1, 1, tf.shape(facts)[1]])
        scores = d_layer_3_all
        # Mask
        # key_masks = tf.sequence_mask(facts_length, tf.shape(facts)[1])   # [B, T]
        key_masks = tf.expand_dims(mask, 1)  # [B, 1, T]
        paddings = tf.ones_like(scores) * (-2 ** 32 + 1)
        if not forCnn:
            scores = tf.where(key_masks, scores, paddings)  # [B, 1, T]

        # Scale
        # scores = scores / (facts.get_shape().as_list()[-1] ** 0.5)

        # Activation
        if softmax_stag:
            scores = tf.nn.softmax(scores)  # [B, 1, T]

        # Weighted sum
        if mode == 'SUM':
            output = tf.matmul(scores, facts)  # [B, 1, H]
            # output = tf.reshape(output, [-1, tf.shape(facts)[-1]])
        else:
            scores = tf.reshape(scores, [-1, tf.shape(facts)[1]])
            output = facts * tf.expand_dims(scores, -1)
            output = tf.reshape(output, tf.shape(facts))
        if return_alphas:
            return output, scores
        return output
    def _check_columns_dimension(self, feature_columns):
        if isinstance(feature_columns, collections.Iterator):
            feature_columns = list(feature_columns)
        column_num = len(feature_columns)
        if column_num < 2:
            raise ValueError('feature_columns must have as least two elements.')
        dimension = -1
        for column in feature_columns:
            if not isinstance(column, feature_column._EmbeddingColumn):
                raise ValueError('Items of feature_columns must be a EmbeddingColumn. '
                                 'Given (type {}): {}.'.format(type(column), column))
            if dimension != -1 and column.dimension != dimension:
                raise ValueError('FM_feature_columns must have the same dimension.{}.vs{}'.format(str(dimension),str(column.dimension)))
            dimension = column.dimension
        return dimension

    def cin_net(self, net, direct=True, residual=True):
        """
        xDeepFM中的CIN网络
        :param net:
        :param direct:
        :param residual:
        :return:
        """

        self.final_result = []
        self.dimension = self._check_columns_dimension(self.Deep_Features)
        self.column_num = len(self.Deep_Features)
        print("column_num:{column_num},dimension:{dimension}".format(column_num=self.column_num,dimension=self.dimension))

        x_0 = tf.reshape(net, (-1, self.column_num, self.dimension), "inputs_x0")
        split_x_0 = tf.split(x_0, self.dimension * [1], 2)
        next_hidden = x_0
        for idx, field_num in enumerate(self.field_nums):
            current_out = self.cin_block(split_x_0, next_hidden, 'cross_{}'.format(idx), field_num)

            if direct:
                next_hidden = current_out
                current_output = current_out
            else:
                field_num = int(field_num / 2)
                if idx != len(self.field_nums) - 1:
                    next_hidden, current_output = tf.split(current_out, 2 * [field_num], 1)

                else:
                    next_hidden = 0
                    current_output = current_out

            self.final_result.append(current_output)
        result = tf.concat(self.final_result, axis=1)
        result = tf.reduce_sum(result, -1)
        if residual:
            exFM_out1 = tf.layers.dense(result, 128, 'relu')
            exFM_in = tf.concat([exFM_out1, result], axis=1, name="user_emb")
            exFM_out = tf.layers.dense(exFM_in, 1)
            return exFM_out
        else:
            exFM_out = tf.layers.dense(result, 1)
            return exFM_out



    def cin_block(self, x_0, current_x, name=None, next_field_num=None, reduce_D=False, f_dim=2, bias=True, direct=True):

        split_current_x = tf.split(current_x, self.dimension * [1], 2)
        dot_result_m = tf.matmul(x_0, split_current_x, transpose_b=True)
        current_field_num = current_x.get_shape().as_list()[1]
        dot_result_o = tf.reshape(dot_result_m, shape=[self.dimension, -1, self.column_num * current_field_num])
        dot_result = tf.transpose(dot_result_o, perm=[1, 0, 2])

        if reduce_D:
            filters0 = tf.get_variable("f0_" + str(name),
                                       shape=[1, next_field_num,  self.column_num, f_dim],
                                       dtype=tf.float32)
            filters_ = tf.get_variable("f__" + str(name),
                                       shape=[1, next_field_num, f_dim, current_field_num],
                                       dtype=tf.float32)
            filters_m = tf.matmul(filters0, filters_)
            filters_o = tf.reshape(filters_m, shape=[1, next_field_num, self.column_num * current_field_num])
            filters = tf.transpose(filters_o, perm=[0, 2, 1])
        else:
            filters = tf.get_variable(name="f_" + str(name),
                                      shape=[1, current_field_num * self.column_num, next_field_num],
                                      dtype=tf.float32)

        curr_out = tf.nn.conv1d(dot_result, filters=filters, stride=1, padding='VALID')
        if bias:
            b = tf.get_variable(name="f_b" + str(name),
                                shape=[next_field_num],
                                dtype=tf.float32,
                                initializer=tf.zeros_initializer())
            curr_out = tf.nn.bias_add(curr_out, b)

        curr_out = tf.nn.sigmoid(curr_out)
        curr_out = tf.transpose(curr_out, perm=[0, 2, 1])
        return curr_out




class BST(BaseModel):
    ''' todo '''
    pass

class PNN(BaseModel):
    pass

class IRGAN(BaseModel):
    pass

# class DSIN(BaseModel):
#     pass

class youtube_net(BaseModel):
    '''MMoE'''
    pass

# class dien(object):
#     def __init__(self, features,labels,params,mode):
#         self.features = features
#         self.labels =labels
#         self.params = params
#         self.mode = mode
#         self.model_features = params["FEATURES_DICT"]
#
#         self.din_user_goods_seq = features["seq_goods_id_seq"]
#         self.din_target_goods_id = features["goods_id"]
#         self.din_user_class_seq = features["class_seq"]
#         self.din_target_class_id = features["class_id"]
#
#     def get_feature_columns(self):
#         Feature_Columns = FeatureBuilder(self.model_features)
#         _,DeepFeatures = Feature_Columns.get_feature_columns()
#         return DeepFeatures
#
#     def _classification_output(self,scores, n_classes, label_vocabulary=None):
#         batch_size = array_ops.shape(scores)[0]
#         if label_vocabulary:
#             export_class_list = label_vocabulary
#         else:
#             export_class_list = string_ops.as_string(math_ops.range(n_classes))
#         export_output_classes = array_ops.tile(
#             input=array_ops.expand_dims(input=export_class_list, axis=0),
#             multiples=[batch_size, 1])
#         return export_output.ClassificationOutput(
#             scores=scores,
#             # `ClassificationOutput` requires string classes.
#             classes=export_output_classes)
#
#     def embedding_table(self,bucket_size,embedding_size,col):
#         embeddings = tf.get_variable(
#             shape=[bucket_size, embedding_size],
#             initializer=init_ops.glorot_uniform_initializer(),
#             dtype=tf.float32,
#             name="deep_embedding_" + col)
#         return embeddings
#
#     def fc_net(self,net):
#         '''MLP'''
#         net = tf.layers.batch_normalization(inputs=net, name='bn1', training=True)
#         for units in self.params['HIDDEN_UNITS']:
#             net = tf.layers.dense(net, units=units, activation=PReLU)
#             if 'DROPOUT_RATE' in self.params and self.params['DROPOUT_RATE'] > 0.0:
#                 net = tf.layers.dropout(net, self.params['DROPOUT_RATE'], training=(self.mode == tf.estimator.ModeKeys.TRAIN))
#         logits = tf.layers.dense(net, 1, activation=None)
#         return logits
#
#
#     def Din_model(self,feature_columns):
#         # feature_columns not include attention feature
#         common_layer = tf.feature_column.input_layer(self.features, feature_columns)
#         din_user_seq = tf.string_to_hash_bucket_fast(self.din_user_goods_seq)
#         din_target_id = tf.string_to_hash_bucket_fast(self.din_target_goods_id)
#         din_useq_embedding,din_tid_embedding = self.attention_layer(din_user_seq,din_target_id,id_type="click_seq")
#         din_net = tf.concat([common_layer,din_useq_embedding,din_tid_embedding],axis=1)
#         logits = self.fc_net(din_net)
#         return logits
#
#     def attention_layer(self, seq_ids, tid, id_type):
#         with tf.variable_scope("attention_" + id_type):
#             embedding_size = 16
#             bucket_size = 10000000
#             embeddings = self.embedding_table(bucket_size,embedding_size,id_type)
#             seq_emb = tf.nn.embedding_lookup(embeddings, seq_ids)  # shape(batch_size, max_seq_len, embedding_size)
#             u_emb = tf.reshape(seq_emb, shape=[-1, embedding_size])
#
#             tid_emb = tf.nn.embedding_lookup(embeddings, tid)  # shape(batch_size, embedding_size)
#             max_seq_len = tf.shape(seq_ids)[1]  # padded_dim
#             a_emb = tf.reshape(tf.tile(tid_emb, [1, max_seq_len]), shape=[-1, embedding_size])
#
#             net = tf.concat([u_emb, a_emb,u_emb - a_emb,u_emb * a_emb], axis=1)
#             attention_hidden_units = [50,25]
#             for units in attention_hidden_units:
#                 net = tf.layers.dense(net, units=units, activation=tf.nn.relu)
#             att_wgt = tf.layers.dense(net, units=1, activation=tf.sigmoid)
#             att_wgt = tf.reshape(att_wgt, shape=[-1, max_seq_len, 1], name="weight")
#             wgt_emb = tf.multiply(seq_emb, att_wgt)  # shape(batch_size, max_seq_len, embedding_size)
#             # masks = tf.sequence_mask(seq_len, max_seq_len, dtype=tf.float32)
#             masks = tf.expand_dims(tf.cast(seq_ids >= 0, tf.float32), axis=-1)
#             att_emb = tf.reduce_sum(tf.multiply(wgt_emb, masks), 1, name="weighted_embedding")
#             return att_emb, tid_emb
#
#     def dien_layer(self,seq_ids,tid,id_type):
#         with tf.variable_scope("RNN_layer_" + id_type):
#             embedding_size = 16
#             bucket_size = 10000000
#             sequence_length = 20
#             embeddings = self.embedding_table(bucket_size, embedding_size, id_type)
#             seq_emb = tf.nn.embedding_lookup(embeddings, seq_ids)  # shape(batch_size, max_seq_len, embedding_size)
#             u_emb = tf.reshape(seq_emb, shape=[-1, embedding_size])
#
#             rnn_outputs, _ = dynamic_rnn(GRUCell(embedding_size), inputs=u_emb,
#                                          sequence_length=sequence_length, dtype=tf.float32,
#                                          scope="GRU1")
#             tf.summary.histogram('GRU_outputs', rnn_outputs)
#
#
#             return
#
#     def Dien_model(self,feature_columns):
#         common_layer = tf.feature_column.input_layer(self.features, feature_columns)
#         din_user_seq = tf.string_to_hash_bucket_fast(self.din_user_goods_seq)
#         din_target_id = tf.string_to_hash_bucket_fast(self.din_target_goods_id)
#         din_useq_embedding,din_tid_embedding = self.dien_layer(din_user_seq,din_target_id,id_type="click_seq")
#         din_net = tf.concat([common_layer,din_useq_embedding,din_tid_embedding],axis=1)
#         logits = self.fc_net(din_net)
#         return logits
#
#
#     def dcn_model(self):
#         '''dcn model '''
#         pass
#
#     def Dnn_Model(self,feature_columns):
#         '''dnn model'''
#         net = tf.feature_column.input_layer(self.features, feature_columns)
#         # Build the hidden layers, sized according to the 'hidden_units' param.
#         logits = self.fc_net(net)
#         return logits

    # def Build_EstimatorSpec(self):
    #     '''Build EstimatorSpec'''
    #     with tf.variable_scope('embedding_module'):
    #         feature_columns = self.get_feature_columns()
    #         print("feature_columns:", feature_columns)
    #     with tf.variable_scope('ctr_model'):
    #         ctr_logits = self.Dien_model(feature_columns)
    #
    #     ctr_predictions = tf.sigmoid(ctr_logits, name="CTR")
    #     cvr_predictions = tf.sigmoid(cvr_logits, name="CVR")
    #     prop = tf.multiply(ctr_predictions, cvr_predictions, name="CTCVR")
    #     if self.mode == tf.estimator.ModeKeys.PREDICT:
    #         CLASSES = 'classes'
    #         CLASS_IDS = 'class_ids'
    #         two_class_ctcvr_prob = tf.concat(
    #             (tf.subtract(1.0, prop), prop),
    #             # (array_ops.zeros_like(ctcvr_prob), ctcvr_prob),
    #             axis=-1, name='two_class_logits')
    #         class_ids = tf.argmax(two_class_ctcvr_prob, axis=-1, name=CLASS_IDS)
    #         class_ids = tf.expand_dims(class_ids, axis=-1)
    #
    #         classes = tf.as_string(class_ids, name='str_classes')
    #         classifier_output = self._classification_output(
    #             scores=two_class_ctcvr_prob, n_classes=2,
    #             label_vocabulary=None)
    #         predictions = {
    #             'probabilities': prop,
    #             CLASS_IDS: class_ids,
    #             CLASSES: classes,
    #             'ctr_probabilities': ctr_predictions,
    #             'cvr_probabilities': cvr_predictions
    #         }
    #         _DEFAULT_SERVING_KEY = signature_constants.DEFAULT_SERVING_SIGNATURE_DEF_KEY
    #         _CLASSIFY_SERVING_KEY = 'classification'
    #         _REGRESS_SERVING_KEY = 'regression'
    #         _PREDICT_SERVING_KEY = 'predict'
    #         export_outputs = {
    #             _DEFAULT_SERVING_KEY: classifier_output,
    #             _CLASSIFY_SERVING_KEY: classifier_output,
    #             _PREDICT_SERVING_KEY: tf.estimator.export.PredictOutput(predictions)
    #         }
    #         return tf.estimator.EstimatorSpec(self.mode, predictions=predictions, export_outputs=export_outputs)
    #
    #     y = self.labels['cvr']
    #     cvr_loss = tf.reduce_sum(tf.keras.backend.binary_crossentropy(tf.reshape(y,(-1,1)), prop), name="cvr_loss")
    #     ctr_loss = tf.reduce_sum(tf.nn.sigmoid_cross_entropy_with_logits(labels=tf.reshape(self.labels['ctr'],(-1,1)), logits=ctr_logits),
    #                              name="ctr_loss")
    #     loss = tf.add(ctr_loss, cvr_loss, name="ctcvr_loss")
    #
    #     ctr_accuracy = tf.metrics.accuracy(labels=self.labels['ctr'],
    #                                        predictions=tf.to_float(tf.greater_equal(ctr_predictions, 0.5)))
    #     cvr_accuracy = tf.metrics.accuracy(labels=y, predictions=tf.to_float(tf.greater_equal(prop, 0.5)))
    #     ctr_auc = tf.metrics.auc(self.labels['ctr'], ctr_predictions)
    #     cvr_auc = tf.metrics.auc(y, prop)
    #
    #     # ctcvr_auc = tf.metrics.auc(tf.reshape(label_cvr, (-1, 1)), ctcvr_prob)
    #     # ctr_recall = tf.metrics.recall(labels=tf.reshape(label_ctr, (-1, 1)),
    #     #                                predictions=tf.to_float(tf.greater_equal(ctr_prob, 0.5)))
    #     # cvr_recall = tf.metrics.recall(labels=tf.reshape(label_cvr, (-1, 1)),
    #     #                                predictions=tf.to_float(tf.greater_equal(cvr_prob, 0.5)))
    #     # ctcvr_recall = tf.metrics.recall(labels=tf.reshape(label_cvr, (-1, 1)),
    #     #                                  predictions=tf.to_float(tf.greater_equal(ctcvr_prob, 0.5)))
    #     metrics = {'cvr_accuracy': cvr_accuracy, 'ctr_accuracy': ctr_accuracy, 'ctr_auc': ctr_auc, 'cvr_auc': cvr_auc}
    #     tf.summary.scalar('ctr_accuracy', ctr_accuracy[1])
    #     tf.summary.scalar('cvr_accuracy', cvr_accuracy[1])
    #     tf.summary.scalar('ctr_auc', ctr_auc[1])
    #     tf.summary.scalar('cvr_auc', cvr_auc[1])
    #     if self.mode == tf.estimator.ModeKeys.EVAL:
    #         return tf.estimator.EstimatorSpec(self.mode, loss=loss, eval_metric_ops=metrics)
    #
    #     # Create training op.
    #     assert self.mode == tf.estimator.ModeKeys.TRAIN
    #     optimizer = tf.train.AdagradOptimizer(learning_rate=self.params['LEARNING_RATE'])
    #     update_ops = tf.get_collection(tf.GraphKeys.UPDATE_OPS)
    #     with tf.control_dependencies(update_ops):
    #         train_op = optimizer.minimize(loss, global_step=tf.train.get_global_step())
    #     return tf.estimator.EstimatorSpec(self.mode, loss=loss, train_op=train_op)


class export_model(object):
    '''to do'''
    def __init__(self,model=None,input_schema=None,servable_model_dir=None,drop_cols = ['click', 'buy']):
        self.model = model
        self.input_schema = input_schema
        self.servable_model_dir =servable_model_dir
        self.drop_cols = drop_cols
        self.path = self._export
        print("*********** Done Exporting at PAth - %s", self.path)

    @property
    def _export(self):
        feature_spec = get_input_schema_spec(self.input_schema)
        for col in self.drop_cols:
            del feature_spec[col]
        export_input_fn = tf.estimator.export.build_parsing_serving_input_receiver_fn(feature_spec)
        servable_model_path = self.model.export_savedmodel(self.servable_model_dir, export_input_fn)
        return servable_model_path




class testw(object):
    '''test case'''
    def __init__(self):
        self.a = 1
    def build_mode(self):
        rand = random.random()
        return rand
        # print(rand)
    def mymodel(self):
        a = self.build_mode()
        b = self.build_mode()
        print(a)
        print(b)
if __name__ == '__main__':
    ss =testw()
    ss.mymodel()