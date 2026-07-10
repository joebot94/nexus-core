from .base import ActionResult, ActionSpec, DeviceAdapter, UnsupportedAction
from .mgp import MGP464Adapter

# Registry `type` field → adapter class. New device families register here.
ADAPTER_TYPES: dict[str, type[DeviceAdapter]] = {
    "mgp464": MGP464Adapter,
}

__all__ = ["ActionResult", "ActionSpec", "DeviceAdapter", "UnsupportedAction",
           "MGP464Adapter", "ADAPTER_TYPES"]
