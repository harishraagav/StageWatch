"""PyTorch integration helpers (install with ``stagewatch[torch]``)."""
from __future__ import annotations
from typing import Any
from ..inspection import inspect_value


def inspect_tensor(value: Any, *, deep_scan_limit_bytes: int = 1_000_000, inspect_gpu: bool = False) -> dict[str, Any]:
    import torch
    if not isinstance(value, torch.Tensor):
        raise TypeError("inspect_tensor expects a torch.Tensor")
    return inspect_value(value, deep_scan_limit_bytes=deep_scan_limit_bytes, inspect_gpu=inspect_gpu)
