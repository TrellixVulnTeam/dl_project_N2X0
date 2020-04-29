#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Author  : Joshua
@Time    : 19-9-5 上午11:36
@File    : model_utils.py
@Desc    : Contains a collection of util functions for model construction.
"""

import numpy
import tensorflow as tf
from tensorflow import logging
from tensorflow import flags
import tensorflow.contrib.slim as slim


def SampleRandomSequence(model_input, num_frames, num_samples):
  """Samples a random sequence of frames of size num_samples.
  Args:
    model_input: A tensor of size batch_size x max_frames x feature_size
    num_frames: A tensor of size batch_size x 1
    num_samples: A scalar
  Returns:
    `model_input`: A tensor of size batch_size x num_samples x feature_size
  """

  batch_size = tf.shape(model_input)[0]
  frame_index_offset = tf.tile(tf.expand_dims(tf.range(num_samples), 0),
                               [batch_size, 1])
  max_start_frame_index = tf.maximum(num_frames - num_samples, 0)
  start_frame_index = tf.cast(
      tf.multiply(tf.random_uniform([batch_size, 1]),
                  tf.cast(max_start_frame_index + 1, tf.float32)), tf.int32)
  frame_index = tf.minimum(start_frame_index + frame_index_offset,
                           tf.cast(num_frames - 1, tf.int32))
  batch_index = tf.tile(tf.expand_dims(tf.range(batch_size), 1),
                        [1, num_samples])
  index = tf.stack([batch_index, frame_index], 2)
  return tf.gather_nd(model_input, index)


def SampleRandomFrames(model_input, num_frames, num_samples):
  """Samples a random set of frames of size num_samples.
  Args:
    model_input: A tensor of size batch_size x max_frames x feature_size
    num_frames: A tensor of size batch_size x 1
    num_samples: A scalar
  Returns:
    `model_input`: A tensor of size batch_size x num_samples x feature_size
  """
  batch_size = tf.shape(model_input)[0]
  frame_index = tf.cast(
      tf.multiply(tf.random_uniform([batch_size, num_samples]),
                  tf.tile(tf.cast(num_frames, tf.float32), [1, num_samples])),
      tf.int32)
  batch_index = tf.tile(tf.expand_dims(tf.range(batch_size), 1),
                        [1, num_samples])
  index = tf.stack([batch_index, frame_index], 2)
  return tf.gather_nd(model_input, index)


def FramePooling(frames, method, **unused_params):
  """Pools over the frames of a video.
  Args:
    frames: A tensor with shape [batch_size, num_frames, feature_size].
    method: "average", "max", "attention", or "none".
  Returns:
    A tensor with shape [batch_size, feature_size] for average, max, or
    attention pooling. A tensor with shape [batch_size*num_frames, feature_size]
    for none pooling.
  Raises:
    ValueError: if method is other than "average", "max", "attention", or
    "none".
  """
  if method == "average":
    return tf.reduce_mean(frames, 1)
  elif method == "max":
    return tf.reduce_max(frames, 1)
  elif method == "none":
    feature_size = frames.shape_as_list()[2]
    return tf.reshape(frames, [-1, feature_size])
  else:
    raise ValueError("Unrecognized pooling method: %s" % method)