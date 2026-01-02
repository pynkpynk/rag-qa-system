from __future__ import annotations

import math
from typing import Any, Tuple


def _is_nonfinite(value: Any) -> bool:
    try:
        if isinstance(value, (float, int)):
            return isinstance(value, float) and not math.isfinite(value)
        if hasattr(value, "item"):
            coerced = value.item()
            return isinstance(coerced, float) and not math.isfinite(coerced)
        return False
    except Exception:
        return False


def sanitize_nonfinite_floats(obj: Any) -> Tuple[Any, list[str]]:
    paths: list[str] = []

    def _walk(value: Any, path: str) -> Any:
        if isinstance(value, dict):
            new_dict = {}
            for key, val in value.items():
                child_path = f"{path}.{key}" if path else key
                new_dict[key] = _walk(val, child_path)
            return new_dict
        if isinstance(value, list):
            new_list = []
            for idx, item in enumerate(value):
                child_path = f"{path}[{idx}]"
                new_list.append(_walk(item, child_path))
            return new_list
        if isinstance(value, tuple):
            new_tuple = []
            for idx, item in enumerate(value):
                child_path = f"{path}[{idx}]"
                new_tuple.append(_walk(item, child_path))
            return tuple(new_tuple)
        if _is_nonfinite(value):
            paths.append(path or "<root>")
            return None
        return value

    sanitized = _walk(obj, "")
    return sanitized, paths
