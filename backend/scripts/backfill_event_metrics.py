#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text

# Make `app` importable when running the script directly.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal
from app.services.event_metrics import build_metric_rows, persist_metric_rows


@dataclass
class BackfillStats:
    batches: int = 0
    events: int = 0
    metrics: int = 0


def _load_missing_events(batch_size: int) -> Sequence[dict]:
    stmt = text(
        """
        SELECT e.id, e.tenant_id, e.warehouse_id, e.well_run_id, e.source, e.created_at, e.payload
        FROM events e
        LEFT JOIN LATERAL (
          SELECT 1
          FROM event_metrics m
          WHERE m.event_id = e.id
          LIMIT 1
        ) mm ON TRUE
        WHERE mm IS NULL
        ORDER BY e.created_at ASC
        LIMIT :batch_size
        """
    )
    with SessionLocal() as db:
        return db.execute(stmt, {"batch_size": batch_size}).mappings().all()


def _write_metric_rows(events: Sequence[dict]) -> int:
    metric_rows = build_metric_rows(events)
    if not metric_rows:
        return 0
    with SessionLocal() as db:
        persist_metric_rows(db, metric_rows)
        db.commit()
    return len(metric_rows)


def run_backfill(batch_size: int, max_batches: int) -> BackfillStats:
    stats = BackfillStats()
    while True:
        if max_batches > 0 and stats.batches >= max_batches:
            break

        events = _load_missing_events(batch_size)
        if not events:
            break

        inserted_metrics = _write_metric_rows(events)
        stats.batches += 1
        stats.events += len(events)
        stats.metrics += inserted_metrics

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill event_metrics and 1-minute rollups from events.")
    parser.add_argument("--batch-size", type=int, default=2000, help="Events processed per batch.")
    parser.add_argument(
        "--max-batches",
        type=int,
        default=0,
        help="Maximum batches to process; 0 means no limit.",
    )
    args = parser.parse_args()

    batch_size = max(1, args.batch_size)
    max_batches = max(0, args.max_batches)

    stats = run_backfill(batch_size=batch_size, max_batches=max_batches)
    print(
        {
            "batches": stats.batches,
            "backfilled_events": stats.events,
            "inserted_metrics": stats.metrics,
        }
    )


if __name__ == "__main__":
    main()
