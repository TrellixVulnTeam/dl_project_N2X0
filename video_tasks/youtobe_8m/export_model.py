#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Author  : Joshua
@Time    : 19-9-5 上午11:18
@File    : export_model.py
@Desc    : Utilities to export a model for batch prediction.
"""


import tensorflow as tf
import tensorflow.contrib.slim as slim

from tensorflow.python.saved_model import builder as saved_model_builder
from tensorflow.python.saved_model import signature_constants
from tensorflow.python.saved_model import signature_def_utils
from tensorflow.python.saved_model import tag_constants
from tensorflow.python.saved_model import utils as saved_model_utils

_TOP_PREDICTIONS_IN_OUTPUT = 20


class ModelExporter(object):

  def __init__(self, frame_features, model, reader):
    self.frame_features = frame_features
    self.model = model
    self.reader = reader

    with tf.Graph().as_default() as graph:
      self.inputs, self.outputs = self.build_inputs_and_outputs()
      self.graph = graph
      self.saver = tf.train.Saver(tf.trainable_variables(), sharded=True)

  def export_model(self, model_dir, global_step_val, last_checkpoint):
    """Exports the model so that it can used for batch predictions."""

    with self.graph.as_default():
      with tf.Session() as session:
        session.run(tf.global_variables_initializer())
        self.saver.restore(session, last_checkpoint)

        signature = signature_def_utils.build_signature_def(
            inputs=self.inputs,
            outputs=self.outputs,
            method_name=signature_constants.PREDICT_METHOD_NAME)

        signature_map = {
            signature_constants.DEFAULT_SERVING_SIGNATURE_DEF_KEY: signature
        }

        model_builder = saved_model_builder.SavedModelBuilder(model_dir)
        model_builder.add_meta_graph_and_variables(
            session,
            tags=[tag_constants.SERVING],
            signature_def_map=signature_map,
            clear_devices=True)
        model_builder.save()

  def build_inputs_and_outputs(self):
    if self.frame_features:
      serialized_examples = tf.placeholder(tf.string, shape=(None,))

      fn = lambda x: self.build_prediction_graph(x)
      video_id_output, top_indices_output, top_predictions_output = (tf.map_fn(
          fn, serialized_examples, dtype=(tf.string, tf.int32, tf.float32)))

    else:
      serialized_examples = tf.placeholder(tf.string, shape=(None,))

      video_id_output, top_indices_output, top_predictions_output = (
          self.build_prediction_graph(serialized_examples))

    inputs = {
        "example_bytes":
            saved_model_utils.build_tensor_info(serialized_examples)
    }

    outputs = {
        "video_id":
            saved_model_utils.build_tensor_info(video_id_output),
        "class_indexes":
            saved_model_utils.build_tensor_info(top_indices_output),
        "predictions":
            saved_model_utils.build_tensor_info(top_predictions_output)
    }

    return inputs, outputs

  def build_prediction_graph(self, serialized_examples):
    input_data_dict = (
        self.reader.prepare_serialized_examples(serialized_examples))
    video_id = input_data_dict["video_ids"]
    model_input_raw = input_data_dict["video_matrix"]
    labels_batch = input_data_dict["labels"]
    num_frames = input_data_dict["num_frames"]

    feature_dim = len(model_input_raw.get_shape()) - 1
    model_input = tf.nn.l2_normalize(model_input_raw, feature_dim)

    with tf.variable_scope("tower"):
      result = self.model.create_model(model_input,
                                       num_frames=num_frames,
                                       vocab_size=self.reader.num_classes,
                                       labels=labels_batch,
                                       is_training=False)

      for variable in slim.get_model_variables():
        tf.summary.histogram(variable.op.name, variable)

      predictions = result["predictions"]

      top_predictions, top_indices = tf.nn.top_k(predictions,
                                                 _TOP_PREDICTIONS_IN_OUTPUT)
    return video_id, top_indices, top_predictions