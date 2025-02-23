#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Author  : Joshua
@Time    : 4/24/20 9:43 PM
@File    : __init__.py.py
@Desc    : 

"""

from pyspark import SparkConf
from pyspark.sql import SparkSession
from pyspark import SparkContext
from pyspark.streaming import StreamingContext
from pyspark.streaming.kafka import KafkaUtils
from recommender_system.news_recommender.setting.default import DefaultConfig

# 1、创建spark streaming context conf
conf = SparkConf()
conf.setAll(DefaultConfig.SPARK_ONLINE_CONFIG)
sc = SparkContext(conf=conf)
stream_sc = StreamingContext(sc, 60)

# 2、配置与kafka读取的配置
similar_kafka = {"metadata.broker.list": DefaultConfig.KAFKA_SERVER, "group.id": 'similar'}
SIMILAR_DS = KafkaUtils.createDirectStream(stream_sc, ['click-trace'], similar_kafka)