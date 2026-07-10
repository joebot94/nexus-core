from .base import ActionResult, ActionSpec, DeviceAdapter, UnsupportedAction
from .dms3600 import DMS3600Adapter
from .extron_sis import ExtronSISAdapter
from .matrix12800 import Matrix12800Adapter
from .mgp import MGP464Adapter
from .smx import SMXAdapter

# Registry `type` field → adapter class. New device families register here.
# `extron_sis` is the generic fallback: any Extron box can join the registry
# with it and immediately gets universal preset recall + identity queries;
# a dedicated subclass is only needed for model-specific commands.
ADAPTER_TYPES: dict[str, type[DeviceAdapter]] = {
    "extron_sis": ExtronSISAdapter,
    "mgp464": MGP464Adapter,
    "matrix12800": Matrix12800Adapter,
    "smx": SMXAdapter,
    "dms3600": DMS3600Adapter,
}

__all__ = ["ActionResult", "ActionSpec", "DeviceAdapter", "UnsupportedAction",
           "ExtronSISAdapter", "MGP464Adapter", "Matrix12800Adapter", "SMXAdapter",
           "DMS3600Adapter", "ADAPTER_TYPES"]
