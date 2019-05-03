import json
import subprocess
import logging

from executor import SERVICE_NAME, __version__
from executor.config import ExecutorConfig
from transpiler.bai_knowledge import create_job_yaml_spec
from bai_kafka_utils.events import BenchmarkEvent, FetcherPayload, ExecutorPayload, BenchmarkJob
from bai_kafka_utils.kafka_client import create_kafka_consumer_producer
from bai_kafka_utils.kafka_service import KafkaServiceCallback, KafkaService, KafkaServiceConfig
from bai_kafka_utils.utils import DEFAULT_ENCODING

logger = logging.getLogger(SERVICE_NAME)


class ExecutorEventHandler(KafkaServiceCallback):
    def __init__(self, executor_config):
        self.executor_config = executor_config

    def handle_event(self, event: BenchmarkEvent, kafka_service: KafkaService):
        descriptor_contents = json.loads(event.payload.toml.contents)
        fetched_data_sources = event.payload.data_sets

        yaml, job_id = create_job_yaml_spec(descriptor_contents,
                                            self.executor_config,
                                            fetched_data_sources)

        self._kubernetes_apply(yaml)

        job = BenchmarkJob(
            id=job_id,
            status='SUBMITTED',
            k8s_yaml=yaml
        )

        result_payload = ExecutorPayload.from_fetcher_payload(event.payload, job)
        return BenchmarkEvent.from_event_new_payload(event, result_payload)

    def _kubernetes_apply(self, yaml):
        cmd = ["kubectl", "apply", "--kubeconfig", self.executor_config.kubeconfig, "-f", "-"]
        logger.info(f"Applying yaml file using ${' '.join(cmd)}")
        result = subprocess.check_output(cmd, input=yaml.encode(DEFAULT_ENCODING))
        logger.info(f"Response from kubectl: {result}")  # TODO: Do something with this response?

    def cleanup(self):
        pass


def create_executor(common_kafka_cfg: KafkaServiceConfig,
                    executor_config: ExecutorConfig) -> KafkaService:

    callbacks = [
        ExecutorEventHandler(executor_config)
    ]

    consumer, producer = create_kafka_consumer_producer(common_kafka_cfg, FetcherPayload)

    return KafkaService(SERVICE_NAME,
                        __version__,
                        common_kafka_cfg.producer_topic,
                        callbacks, consumer, producer)
