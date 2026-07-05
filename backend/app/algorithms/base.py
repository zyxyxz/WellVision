from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from app.schemas.analysis import AlgorithmInfo, SeriesPoint


@dataclass(frozen=True)
class AlgorithmResult:
    result_series: list[SeriesPoint]
    metrics: dict[str, float | int | str]
    result_points: list[dict[str, float]] | None = None
    x_axis: str | None = None


AlgorithmFn = Callable[[Sequence[SeriesPoint], dict], AlgorithmResult]


@dataclass(frozen=True)
class AlgorithmSpec:
    info: AlgorithmInfo
    fn: AlgorithmFn
