from __future__ import annotations

import math
import unittest
import uuid
from datetime import datetime, timezone

from app.services.event_metrics import (
    NULL_WAREHOUSE_ID,
    UNKNOWN_SOURCE,
    build_metric_rows,
    build_rollup_rows_1m,
    extract_measured_depth,
    extract_numeric_payload,
)


class EventMetricsTests(unittest.TestCase):
    def test_extract_numeric_payload_filters_non_finite_and_bool(self) -> None:
        rows = extract_numeric_payload(
            {
                "rpm": "120.5",
                "torque": 31,
                "enabled": True,
                "note": "not numeric",
                "nan": math.nan,
            }
        )

        self.assertEqual(rows, [("rpm", 120.5), ("torque", 31.0)])

    def test_extract_measured_depth_uses_known_aliases(self) -> None:
        self.assertEqual(extract_measured_depth({"measuredDepth": "1530.25"}), 1530.25)
        self.assertIsNone(extract_measured_depth({"depth": "bad"}))

    def test_metric_and_rollup_rows_preserve_tenant_scope(self) -> None:
        tenant_id = uuid.uuid4()
        created_at = datetime(2026, 7, 6, 12, 34, 56, tzinfo=timezone.utc)
        metrics = build_metric_rows(
            [
                {
                    "tenant_id": tenant_id,
                    "warehouse_id": None,
                    "well_run_id": None,
                    "created_at": created_at,
                    "source": "",
                    "payload": {"rpm": 120, "md": 1000},
                }
            ]
        )

        self.assertEqual({row["field"] for row in metrics}, {"rpm", "md"})
        self.assertTrue(all(row["tenant_id"] == tenant_id for row in metrics))

        rollups = build_rollup_rows_1m(metrics)
        self.assertEqual(len(rollups), 2)
        self.assertTrue(all(row["tenant_id"] == tenant_id for row in rollups))
        self.assertTrue(all(row["warehouse_id"] == NULL_WAREHOUSE_ID for row in rollups))
        self.assertTrue(all(row["source"] == UNKNOWN_SOURCE for row in rollups))


if __name__ == "__main__":
    unittest.main()
