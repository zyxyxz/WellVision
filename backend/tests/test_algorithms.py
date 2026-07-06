from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from app.algorithms.builtin import moving_average, rate_of_change
from app.schemas.analysis import SeriesPoint


def _points(values: list[float]) -> list[SeriesPoint]:
    start = datetime(2026, 7, 6, tzinfo=timezone.utc)
    return [
        SeriesPoint(ts=start + timedelta(seconds=idx), value=value)
        for idx, value in enumerate(values)
    ]


class BuiltinAlgorithmTests(unittest.TestCase):
    def test_moving_average_clamps_window_and_keeps_point_count(self) -> None:
        result = moving_average(_points([1, 3, 5]), {"window": 1})

        self.assertEqual(len(result.result_series), 3)
        self.assertEqual(result.metrics["window"], 2)
        self.assertEqual([p.value for p in result.result_series], [1, 2, 4])

    def test_rate_of_change_skips_non_positive_time_steps(self) -> None:
        result = rate_of_change(_points([10, 12, 18]), {})

        self.assertEqual(result.metrics["count"], 2)
        self.assertEqual([p.value for p in result.result_series], [2, 6])


if __name__ == "__main__":
    unittest.main()
