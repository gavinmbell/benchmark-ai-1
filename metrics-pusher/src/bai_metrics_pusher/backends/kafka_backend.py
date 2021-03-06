#  Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License").
#  You may not use this file except in compliance with the License.
#  A copy of the License is located at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  or in the "license" file accompanying this file. This file is distributed
#  on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
#  express or implied. See the License for the specific language governing
#  permissions and limitations under the License.
from typing import Optional, Dict, List

import datetime
import logging
import dataclasses
from dataclasses_json import dataclass_json

from bai_kafka_utils.kafka_client import create_kafka_producer
from bai_metrics_pusher.backends.backend_interface import AcceptedMetricTypes, Backend

logger = logging.getLogger("backend.kafka")


@dataclass_json
@dataclasses.dataclass
class KafkaExporterMetric:
    name: str
    value: float
    timestamp: Optional[int]
    labels: Dict[str, str]


class KafkaBackend(Backend):
    """
    Exports metrics as described by https://github.com/ogibayashi/kafka-topic-exporter

    From the docs:

    Each record in the topics should be the following format. timestamp and labels are optional.

    {
      "name": "<metric_name>",
      "value": <metric_value>,
      "timestamp": <epoch_value_with_millis>,
      "labels: {
        "foolabel": "foolabelvalue",
        "barlabel": "barlabelvalue"
      }
    }

    Then the following item will be exported.

    <kafka_topic_name>_<metric_name>{foolabel="foolabelvalue", barlabel="barlabelvalue"} <metric_value> <epoch_value>
    """

    def __init__(
        self,
        action_id: str,
        client_id: str,
        labels: Dict[str, str],
        *,
        topic: str,
        bootstrap_servers: List[str] = None,
        key: str = None
    ):
        self.labels = {"action-id": action_id, "client-id": client_id, **labels}
        if bootstrap_servers is None:
            bootstrap_servers = ["localhost:9092"]
        self._producer = create_kafka_producer(bootstrap_servers)
        self._key = key
        self._topic = topic

    def emit(self, metrics: Dict[str, AcceptedMetricTypes]):
        now = datetime.datetime.utcnow()
        timestamp_in_millis = int(now.timestamp()) * 1000
        for metric_name, metric_value in metrics.items():
            metric_object = KafkaExporterMetric(
                name=metric_name, value=metric_value, timestamp=timestamp_in_millis, labels=self.labels
            )

            # TODO: Handle KafkaTimeoutError
            logger.info("Pushing metric %s", metric_object)
            self._producer.send(self._topic, value=metric_object, key=self._key)

    def close(self):
        logger.info("Closing producer")
        self._producer.close()
