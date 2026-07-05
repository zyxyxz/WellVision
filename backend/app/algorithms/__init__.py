from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Dict

from app.algorithms.base import AlgorithmResult, AlgorithmSpec


def load_algorithms() -> Dict[str, AlgorithmSpec]:
    algorithms: Dict[str, AlgorithmSpec] = {}
    package_dir = Path(__file__).parent
    for path in package_dir.glob("*.py"):
        if path.name.startswith("__") or path.stem in {"base"}:
            continue
        module = import_module(f"app.algorithms.{path.stem}")
        module_algorithms = getattr(module, "ALGORITHMS", None)
        if isinstance(module_algorithms, dict):
            algorithms.update(module_algorithms)
    return algorithms


__all__ = ["AlgorithmResult", "AlgorithmSpec", "load_algorithms"]
