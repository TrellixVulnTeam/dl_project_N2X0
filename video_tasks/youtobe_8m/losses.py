#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Author  : Joshua
@Time    : 19-9-5 上午11:19
@File    : losses.py
@Desc    : Provides definitions for non-regularized training or test losses.
"""


import tensorflow as tf


class BaseLoss(object):
  """Inherit from this class when implementing new losses."""

  def calculate_loss(self, unused_predictions, unused_labels, **unused_params):
    """Calculates the average loss of the examples in a mini-batch.
     Args:
      unused_predictions: a 2-d tensor storing the prediction scores, in which
        each row represents a sample in the mini-batch and each column
        represents a class.
      unused_labels: a 2-d tensor storing the labels, which has the same shape
        as the unused_predictions. The labels must be in the range of 0 and 1.
      unused_params: loss specific parameters.
    Returns:
      A scalar loss tensor.
    """
    raise NotImplementedError()


class CrossEntropyLoss(BaseLoss):
  """Calculate the cross entropy loss between the predictions and labels."""

  def calculate_loss(self,
                     predictions,
                     labels,
                     label_weights=None,
                     **unused_params):
    with tf.name_scope("loss_xent"):
      epsilon = 1e-5
      float_labels = tf.cast(labels, tf.float32)
      cross_entropy_loss = float_labels * tf.math.log(predictions + epsilon) + (
          1 - float_labels) * tf.math.log(1 - predictions + epsilon)
      cross_entropy_loss = tf.negative(cross_entropy_loss)
      if label_weights is not None:
        cross_entropy_loss *= label_weights
      return tf.reduce_mean(tf.reduce_sum(cross_entropy_loss, 1))


class HingeLoss(BaseLoss):
  """Calculate the hinge loss between the predictions and labels.
  Note the subgradient is used in the backpropagation, and thus the optimization
  may converge slower. The predictions trained by the hinge loss are between -1
  and +1.
  """

  def calculate_loss(self, predictions, labels, b=1.0, **unused_params):
    with tf.name_scope("loss_hinge"):
      float_labels = tf.cast(labels, tf.float32)
      all_zeros = tf.zeros(tf.shape(float_labels), dtype=tf.float32)
      all_ones = tf.ones(tf.shape(float_labels), dtype=tf.float32)
      sign_labels = tf.subtract(tf.scalar_mul(2, float_labels), all_ones)
      hinge_loss = tf.maximum(
          all_zeros,
          tf.scalar_mul(b, all_ones) - sign_labels * predictions)
      return tf.reduce_mean(tf.reduce_sum(hinge_loss, 1))


class SoftmaxLoss(BaseLoss):
  """Calculate the softmax loss between the predictions and labels.
  The function calculates the loss in the following way: first we feed the
  predictions to the softmax activation function and then we calculate
  the minus linear dot product between the logged softmax activations and the
  normalized ground truth label.
  It is an extension to the one-hot label. It allows for more than one positive
  labels for each sample.
  """

  def calculate_loss(self, predictions, labels, **unused_params):
    with tf.name_scope("loss_softmax"):
      epsilon = 10e-8
      float_labels = tf.cast(labels, tf.float32)
      # l1 normalization (labels are no less than 0)
      label_rowsum = tf.maximum(tf.reduce_sum(float_labels, 1, keep_dims=True),
                                epsilon)
      norm_float_labels = tf.div(float_labels, label_rowsum)
      softmax_outputs = tf.nn.softmax(predictions)
      softmax_loss = tf.negative(
          tf.reduce_sum(tf.multiply(norm_float_labels, tf.log(softmax_outputs)),
                        1))
    return tf.reduce_mean(softmax_loss)