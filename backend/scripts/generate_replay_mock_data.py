#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import random
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import delete, select

# Make `app` importable when running the script directly.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal
from app.models import DataWarehouse, EventMetric, OpSegment, Tenant, WellRun


CHANNELS = [
    "standpipe_pressure",
    "bit_vibration",
    "wob",
    "rpm",
    "inclination",
    "azimuth",
    "torque",
]


@dataclass
class SegmentPlan:
    segment_type: str
    start_idx: int
    end_idx: int


def _pick_tenant(db, tenant_id_text: str | None) -> Tenant:
    if tenant_id_text:
        tenant_id = uuid.UUID(tenant_id_text)
        tenant = db.get(Tenant, tenant_id)
    else:
        tenant = db.execute(select(Tenant).order_by(Tenant.created_at.asc()).limit(1)).scalar_one_or_none()
    if tenant is None:
        raise RuntimeError("No tenant found. Create tenant first.")
    return tenant


def _find_or_create_warehouse(db, *, tenant_id: uuid.UUID, name: str) -> DataWarehouse:
    row = db.execute(
        select(DataWarehouse).where(
            DataWarehouse.tenant_id == tenant_id,
            DataWarehouse.name == name,
        )
    ).scalar_one_or_none()
    if row is not None:
        return row
    row = DataWarehouse(
        tenant_id=tenant_id,
        name=name,
        description="Synthetic warehouse for replay demo",
    )
    db.add(row)
    db.flush()
    return row


def _find_or_create_well_run(
    db,
    *,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    name: str,
    started_at: datetime,
    ended_at: datetime,
    replace: bool,
) -> WellRun:
    existing = db.execute(
        select(WellRun).where(
            WellRun.tenant_id == tenant_id,
            WellRun.name == name,
        )
    ).scalar_one_or_none()

    if existing is None:
        run = WellRun(
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name=name,
            well_name="WellVision-Demo-01",
            section="12-1/4in",
            status="active",
            started_at=started_at,
            ended_at=ended_at,
            details={},
        )
        db.add(run)
        db.flush()
        return run

    existing.warehouse_id = warehouse_id
    existing.well_name = "WellVision-Demo-01"
    existing.section = "12-1/4in"
    existing.status = "active"
    existing.started_at = started_at
    existing.ended_at = ended_at

    if replace:
        db.execute(
            delete(EventMetric).where(
                EventMetric.tenant_id == tenant_id,
                EventMetric.well_run_id == existing.id,
            )
        )
        db.execute(
            delete(OpSegment).where(
                OpSegment.tenant_id == tenant_id,
                OpSegment.well_run_id == existing.id,
            )
        )
    return existing


def _plan_segments(total_points: int) -> list[SegmentPlan]:
    if total_points < 10:
        return [SegmentPlan(segment_type="drilling", start_idx=0, end_idx=max(0, total_points - 1))]

    cut1 = int(total_points * 0.33)
    cut2 = int(total_points * 0.38)
    cut3 = int(total_points * 0.70)
    cut4 = int(total_points * 0.78)
    return [
        SegmentPlan("drilling", 0, cut1),
        SegmentPlan("connection", cut1 + 1, cut2),
        SegmentPlan("drilling", cut2 + 1, cut3),
        SegmentPlan("circulation", cut3 + 1, cut4),
        SegmentPlan("drilling", cut4 + 1, total_points - 1),
    ]


def _segment_of_idx(idx: int, plans: list[SegmentPlan]) -> str:
    for plan in plans:
        if plan.start_idx <= idx <= plan.end_idx:
            return plan.segment_type
    return plans[-1].segment_type


def _drilling_signals(i: int, md: float, md0: float, noise: random.Random) -> dict[str, float]:
    pressure = 3300.0 + 380.0 * math.sin(i / 26.0) + 0.6 * (md - md0) + noise.gauss(0, 45.0)
    wob = 88.0 + 14.0 * math.sin(i / 18.0) + noise.gauss(0, 3.2)
    rpm = 120.0 + 9.0 * math.sin(i / 15.0) + noise.gauss(0, 2.0)
    vibration = 2.2 + abs(math.sin(i / 8.0)) * 1.8 + 0.013 * abs(rpm) + 0.004 * abs(wob) + noise.gauss(0, 0.25)
    torque = 13.0 + 0.09 * wob + 0.015 * rpm + noise.gauss(0, 0.8)
    return {
        "standpipe_pressure": max(500.0, pressure),
        "bit_vibration": max(0.05, vibration),
        "wob": max(3.0, wob),
        "rpm": max(0.0, rpm),
        "torque": max(0.1, torque),
    }


def _connection_signals(i: int, noise: random.Random) -> dict[str, float]:
    pressure = 220.0 + 40.0 * math.sin(i / 12.0) + noise.gauss(0, 9.0)
    wob = 1.8 + abs(noise.gauss(0, 0.5))
    rpm = 3.0 + abs(noise.gauss(0, 0.8))
    vibration = 0.16 + abs(noise.gauss(0, 0.06))
    torque = 0.9 + abs(noise.gauss(0, 0.2))
    return {
        "standpipe_pressure": max(50.0, pressure),
        "bit_vibration": vibration,
        "wob": wob,
        "rpm": rpm,
        "torque": torque,
    }


def _circulation_signals(i: int, noise: random.Random) -> dict[str, float]:
    pressure = 2300.0 + 240.0 * math.sin(i / 20.0) + noise.gauss(0, 30.0)
    wob = 5.0 + abs(noise.gauss(0, 1.0))
    rpm = 26.0 + 6.0 * math.sin(i / 16.0) + noise.gauss(0, 1.5)
    vibration = 0.9 + abs(math.sin(i / 12.0)) * 0.8 + noise.gauss(0, 0.15)
    torque = 4.5 + 0.02 * rpm + noise.gauss(0, 0.35)
    return {
        "standpipe_pressure": max(300.0, pressure),
        "bit_vibration": max(0.05, vibration),
        "wob": wob,
        "rpm": max(0.0, rpm),
        "torque": max(0.2, torque),
    }


def generate_mock_data(
    *,
    tenant_id_text: str | None,
    warehouse_name: str,
    well_run_name: str,
    duration_minutes: int,
    step_seconds: int,
    seed: int,
    replace: bool,
) -> dict[str, str | int]:
    duration_minutes = max(10, duration_minutes)
    step_seconds = max(1, step_seconds)
    total_seconds = duration_minutes * 60
    total_points = total_seconds // step_seconds + 1
    start_ts = datetime.now(timezone.utc) - timedelta(seconds=total_seconds)
    end_ts = start_ts + timedelta(seconds=(total_points - 1) * step_seconds)

    plans = _plan_segments(total_points)
    rng = random.Random(seed)
    base_md = 1500.0
    current_md = base_md
    ts_series: list[datetime] = []
    md_series: list[float] = []

    with SessionLocal() as db:
        tenant = _pick_tenant(db, tenant_id_text)
        warehouse = _find_or_create_warehouse(db, tenant_id=tenant.id, name=warehouse_name)
        run = _find_or_create_well_run(
            db,
            tenant_id=tenant.id,
            warehouse_id=warehouse.id,
            name=well_run_name,
            started_at=start_ts,
            ended_at=end_ts,
            replace=replace,
        )

        metric_rows: list[dict] = []
        for idx in range(total_points):
            seg = _segment_of_idx(idx, plans)
            ts = start_ts + timedelta(seconds=idx * step_seconds)

            if seg == "drilling":
                md_rate_mps = 0.046 + 0.006 * math.sin(idx / 60.0) + rng.gauss(0, 0.0018)
            elif seg == "circulation":
                md_rate_mps = 0.002 + rng.gauss(0, 0.0004)
            else:
                md_rate_mps = 0.0
            current_md += max(0.0, md_rate_mps) * step_seconds

            if seg == "drilling":
                signals = _drilling_signals(idx, current_md, base_md, rng)
            elif seg == "circulation":
                signals = _circulation_signals(idx, rng)
            else:
                signals = _connection_signals(idx, rng)

            inclination = 6.0 + 0.016 * (current_md - base_md) + 0.45 * math.sin(idx / 170.0) + rng.gauss(0, 0.08)
            azimuth = (35.0 + 0.028 * (current_md - base_md) + 2.2 * math.sin(idx / 95.0) + rng.gauss(0, 0.4)) % 360.0
            signals["inclination"] = max(0.0, min(88.0, inclination))
            signals["azimuth"] = azimuth

            ts_series.append(ts)
            md_series.append(current_md)

            for channel in CHANNELS:
                metric_rows.append(
                    {
                        "id": uuid.uuid4(),
                        "created_at": ts,
                        "event_id": None,
                        "tenant_id": tenant.id,
                        "warehouse_id": warehouse.id,
                        "well_run_id": run.id,
                        "field": channel,
                        "channel": channel,
                        "source": "surface",
                        "md": current_md,
                        "quality_code": 0,
                        "value": float(signals[channel]),
                    }
                )

        run.details = {
            "mock_data": {
                "seed": seed,
                "duration_minutes": duration_minutes,
                "step_seconds": step_seconds,
            },
            "geology": {
                "layers": [
                    {"name": "Soft Clay", "top": 1500.0, "bottom": 1585.0, "color": "#c89a6d"},
                    {"name": "Sandstone", "top": 1585.0, "bottom": 1710.0, "color": "#b17e4f"},
                    {"name": "Shale", "top": 1710.0, "bottom": 1820.0, "color": "#87705a"},
                    {"name": "Limestone", "top": 1820.0, "bottom": 1940.0, "color": "#c4b49a"},
                ]
            },
        }

        for plan in plans:
            start_idx = max(0, min(plan.start_idx, total_points - 1))
            end_idx = max(0, min(plan.end_idx, total_points - 1))
            if end_idx < start_idx:
                continue
            db.add(
                OpSegment(
                    tenant_id=tenant.id,
                    warehouse_id=warehouse.id,
                    well_run_id=run.id,
                    segment_type=plan.segment_type,
                    source="simulator",
                    confidence=0.98,
                    start_ts=ts_series[start_idx],
                    end_ts=ts_series[end_idx],
                    md_start=float(md_series[start_idx]),
                    md_end=float(md_series[end_idx]),
                    details={"generator": "generate_replay_mock_data.py"},
                )
            )

        batch_size = 5000
        for offset in range(0, len(metric_rows), batch_size):
            db.bulk_insert_mappings(EventMetric, metric_rows[offset : offset + batch_size])

        db.commit()
        return {
            "tenant_id": str(tenant.id),
            "warehouse_id": str(warehouse.id),
            "well_run_id": str(run.id),
            "points": total_points,
            "metrics_inserted": len(metric_rows),
            "segments_inserted": len(plans),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic well-run metrics for Drill Replay.")
    parser.add_argument("--tenant-id", type=str, default=None, help="Target tenant UUID. Defaults to oldest tenant.")
    parser.add_argument("--warehouse-name", type=str, default="Replay Demo Warehouse", help="Warehouse name.")
    parser.add_argument("--well-run-name", type=str, default="Replay Demo Run", help="Well run name.")
    parser.add_argument("--duration-minutes", type=int, default=120, help="Replay duration in minutes.")
    parser.add_argument("--step-seconds", type=int, default=2, help="Sampling step in seconds.")
    parser.add_argument("--seed", type=int, default=20260219, help="Random seed for deterministic data.")
    parser.add_argument(
        "--append",
        action="store_true",
        help="Do not clear existing metrics/segments when well run name already exists.",
    )
    args = parser.parse_args()

    result = generate_mock_data(
        tenant_id_text=args.tenant_id,
        warehouse_name=args.warehouse_name.strip() or "Replay Demo Warehouse",
        well_run_name=args.well_run_name.strip() or "Replay Demo Run",
        duration_minutes=args.duration_minutes,
        step_seconds=args.step_seconds,
        seed=args.seed,
        replace=not args.append,
    )
    print(result)


if __name__ == "__main__":
    main()
