import logging

from addict import addict
from bai_kafka_utils.executors.descriptor import BenchmarkDescriptor, MLFramework, DistributedStrategy
from sagemaker import Session
from sagemaker.estimator import EstimatorBase, Framework
from sagemaker.mxnet import MXNet
from sagemaker.tensorflow import TensorFlow
from typing import Callable

from sm_executor.args import SageMakerExecutorConfig

MPI_OPTIONS = "-x HOROVOD_HIERARCHICAL_ALLREDUCE=1 -x HOROVOD_FUSION_THRESHOLD=16777216 -x TF_CPP_MIN_LOG_LEVEL=0"

EstimatorFactory = Callable[[Session, BenchmarkDescriptor, str, SageMakerExecutorConfig], EstimatorBase]

logger = logging.getLogger(__name__)


def get_custom_params(descriptor: BenchmarkDescriptor):
    hps = {}
    if descriptor.custom_params:
        hps = descriptor.custom_params.hyper_params
    return hps


def create_tensorflow_estimator(
    session: Session, descriptor: BenchmarkDescriptor, source_dir: str, config: SageMakerExecutorConfig
) -> Framework:
    kwargs = _create_common_estimator_args(session, descriptor, source_dir, config)

    if descriptor.hardware.strategy == DistributedStrategy.HOROVOD:
        kwargs.distributions.mpi = addict.Dict(
            enabled=True,
            processes_per_host=int(descriptor.hardware.processes_per_instance),
            custom_mpi_options=MPI_OPTIONS,
        )
    hps = get_custom_params(descriptor)
    kwargs.script_mode = True
    logger.info(f"Creating TF Estimator with parameters {kwargs}")
    return TensorFlow(**kwargs, hyperparameters=hps, enable_sagemaker_metrics=True, enable_cloudwatch_metrics=True)


def create_mxnet_estimator(
    session: Session, descriptor: BenchmarkDescriptor, source_dir: str, config: SageMakerExecutorConfig
) -> Framework:
    kwargs = _create_common_estimator_args(session, descriptor, source_dir, config)
    logger.info(f"Creating MXNet Estimator with parameters {kwargs}")
    hps = get_custom_params(descriptor)
    return MXNet(**kwargs, hyperparameters=hps)


def _create_common_estimator_args(
    session: Session, descriptor: BenchmarkDescriptor, source_dir: str, config: SageMakerExecutorConfig
) -> addict.Dict:
    py_version = "py3"
    metrics = None
    if descriptor.custom_params:
        py_version = descriptor.custom_params.python_version
        metrics = descriptor.custom_params.metric_definitions
    return addict.Dict(
        source_dir=source_dir,
        entry_point="tmp_entry.py",
        sagemaker_session=session,
        image_name=descriptor.env.docker_image,
        py_version=py_version or "py3",
        framework_version=descriptor.ml.framework_version or "",  # None is not a valid value
        train_instance_type=descriptor.hardware.instance_type,
        train_instance_count=descriptor.hardware.distributed.num_instances,
        role=config.sm_role,
        output_path=f"s3://{config.s3_output_bucket}",
        security_group_ids=config.security_group_ids,
        subnets=config.subnets,
        metric_definitions=metrics or None
    )


def create_estimator(
    session: Session, descriptor: BenchmarkDescriptor, source_dir: str, config: SageMakerExecutorConfig
) -> EstimatorBase:
    factories = {MLFramework.MXNET: create_mxnet_estimator, MLFramework.TENSORFLOW: create_tensorflow_estimator}
    try:
        factory: EstimatorFactory = factories[descriptor.ml.framework]
    except KeyError:
        logger.exception(
            f"Descriptor framework seems to be unknown. This should never happen. Supported: {factories.keys()}"
        )
        raise
    return factory(session, descriptor, source_dir, config)
