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


CORE_CHANNELS = [
    "standpipe_pressure",
    "bit_vibration",
    "wob",
    "rpm",
    "inclination",
    "azimuth",
    "torque",
]

EXTRA_CHANNELS = [
    "flow_in",
    "rop",
    "bit_depth",
    "hookload",
    "differential_pressure",
    "mud_motor_rpm",
]

CHANNELS = CORE_CHANNELS + EXTRA_CHANNELS


@dataclass
class SegmentPlan:
    segment_type: str
    start_idx: int
    end_idx: int


@dataclass(frozen=True)
class ScenarioEvent:
    event_type: str
    title: str
    severity: str
    start_ratio: float
    end_ratio: float
    description: str
    recommendation: str


@dataclass(frozen=True)
class EventWindow:
    spec: ScenarioEvent
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


def _plan_segments(total_points: int, scenario: str) -> list[SegmentPlan]:
    if total_points < 10:
        return [SegmentPlan(segment_type="drilling", start_idx=0, end_idx=max(0, total_points - 1))]

    if scenario == "anomaly":
        cut1 = int(total_points * 0.18)
        cut2 = int(total_points * 0.23)
        cut3 = int(total_points * 0.45)
        cut4 = int(total_points * 0.56)
        cut5 = int(total_points * 0.72)
        cut6 = int(total_points * 0.80)
        return [
            SegmentPlan("drilling", 0, cut1),
            SegmentPlan("connection", cut1 + 1, cut2),
            SegmentPlan("drilling", cut2 + 1, cut3),
            SegmentPlan("stick_slip_mitigation", cut3 + 1, cut4),
            SegmentPlan("drilling", cut4 + 1, cut5),
            SegmentPlan("circulation", cut5 + 1, cut6),
            SegmentPlan("drilling", cut6 + 1, total_points - 1),
        ]

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


def _scenario_events(scenario: str) -> list[ScenarioEvent]:
    if scenario == "anomaly":
        return [
            ScenarioEvent(
                event_type="pressure_surge",
                title="Standpipe pressure surge",
                severity="warning",
                start_ratio=0.28,
                end_ratio=0.33,
                description="短时压力升高，伴随泵压波动和扭矩抬升。",
                recommendation="降低 WOB，确认喷嘴与环空返砂情况。",
            ),
            ScenarioEvent(
                event_type="stick_slip",
                title="Stick-slip oscillation",
                severity="critical",
                start_ratio=0.47,
                end_ratio=0.56,
                description="RPM 与扭矩呈反相振荡，钻头转动稳定性下降。",
                recommendation="提高转速窗口，降低钻压并观察振动衰减。",
            ),
            ScenarioEvent(
                event_type="high_vibration",
                title="High lateral vibration",
                severity="critical",
                start_ratio=0.74,
                end_ratio=0.80,
                description="横向振动上升，钻头受冲击风险增加。",
                recommendation="进入稳钻参数，必要时短时循环清洗井底。",
            ),
        ]

    return [
        ScenarioEvent(
            event_type="parameter_window",
            title="Stable drilling window",
            severity="info",
            start_ratio=0.42,
            end_ratio=0.52,
            description="WOB、RPM、泵压均处于推荐窗口，机械钻速稳定。",
            recommendation="维持当前参数，继续监控振动与扭矩趋势。",
        )
    ]


def _build_event_windows(total_points: int, scenario: str) -> list[EventWindow]:
    windows: list[EventWindow] = []
    last_idx = max(0, total_points - 1)
    for spec in _scenario_events(scenario):
        start_idx = max(0, min(last_idx, int(total_points * spec.start_ratio)))
        end_idx = max(start_idx, min(last_idx, int(total_points * spec.end_ratio)))
        windows.append(EventWindow(spec=spec, start_idx=start_idx, end_idx=end_idx))
    return windows


def _event_at_idx(idx: int, windows: list[EventWindow]) -> EventWindow | None:
    for window in windows:
        if window.start_idx <= idx <= window.end_idx:
            return window
    return None


def _event_intensity(idx: int, window: EventWindow) -> float:
    span = max(1, window.end_idx - window.start_idx)
    phase = (idx - window.start_idx) / span
    return max(0.0, math.sin(math.pi * phase))


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


def _mitigation_signals(i: int, md: float, md0: float, noise: random.Random) -> dict[str, float]:
    base = _drilling_signals(i, md, md0, noise)
    base["standpipe_pressure"] *= 0.92
    base["wob"] *= 0.72
    base["rpm"] *= 1.14
    base["torque"] *= 0.82
    base["bit_vibration"] *= 0.76
    return base


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


def _apply_event_to_signals(signals: dict[str, float], idx: int, window: EventWindow | None) -> dict[str, float]:
    if window is None:
        return signals

    intensity = _event_intensity(idx, window)
    event_type = window.spec.event_type
    adjusted = dict(signals)

    if event_type == "pressure_surge":
        adjusted["standpipe_pressure"] += 850.0 * intensity
        adjusted["torque"] *= 1.0 + 0.16 * intensity
        adjusted["bit_vibration"] *= 1.0 + 0.25 * intensity
    elif event_type == "stick_slip":
        wave = math.sin(idx * 0.8)
        adjusted["rpm"] = max(0.0, adjusted["rpm"] * (1.0 - 0.55 * intensity) + 34.0 * intensity * abs(wave))
        adjusted["torque"] *= 1.0 + 0.9 * intensity * (0.45 + abs(wave))
        adjusted["bit_vibration"] *= 1.0 + 1.35 * intensity
        adjusted["wob"] *= 1.0 + 0.22 * intensity
    elif event_type == "high_vibration":
        adjusted["bit_vibration"] += 7.5 * intensity
        adjusted["torque"] *= 1.0 + 0.24 * intensity
        adjusted["rpm"] *= 1.0 - 0.12 * intensity

    return adjusted


def _formation_layers(base_md: float) -> list[dict[str, float | str]]:
    return [
        {"name": "Soft Clay", "top": base_md, "bottom": base_md + 72.0, "color": "#c89a6d"},
        {"name": "Fine Sandstone", "top": base_md + 72.0, "bottom": base_md + 168.0, "color": "#b17e4f"},
        {"name": "Reactive Shale", "top": base_md + 168.0, "bottom": base_md + 260.0, "color": "#87705a"},
        {"name": "Interbedded Limestone", "top": base_md + 260.0, "bottom": base_md + 390.0, "color": "#c4b49a"},
        {"name": "Tight Sand", "top": base_md + 390.0, "bottom": base_md + 540.0, "color": "#9f7a53"},
    ]


def _formation_name(md: float, layers: list[dict[str, float | str]]) -> str:
    for layer in layers:
        top = float(layer["top"])
        bottom = float(layer["bottom"])
        if top <= md <= bottom:
            return str(layer["name"])
    return str(layers[-1]["name"])


def generate_mock_data(
    *,
    tenant_id_text: str | None,
    warehouse_name: str,
    well_run_name: str,
    duration_minutes: int,
    step_seconds: int,
    seed: int,
    scenario: str,
    replace: bool,
) -> dict[str, str | int]:
    duration_minutes = max(10, duration_minutes)
    step_seconds = max(1, step_seconds)
    total_seconds = duration_minutes * 60
    total_points = total_seconds // step_seconds + 1
    start_ts = datetime.now(timezone.utc) - timedelta(seconds=total_seconds)
    end_ts = start_ts + timedelta(seconds=(total_points - 1) * step_seconds)

    scenario = scenario if scenario in {"normal", "anomaly"} else "normal"
    plans = _plan_segments(total_points, scenario)
    event_windows = _build_event_windows(total_points, scenario)
    rng = random.Random(seed)
    base_md = 1500.0
    current_md = base_md
    formations = _formation_layers(base_md)
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
            elif seg == "stick_slip_mitigation":
                md_rate_mps = 0.030 + 0.004 * math.sin(idx / 45.0) + rng.gauss(0, 0.0012)
            elif seg == "circulation":
                md_rate_mps = 0.002 + rng.gauss(0, 0.0004)
            else:
                md_rate_mps = 0.0
            current_md += max(0.0, md_rate_mps) * step_seconds

            if seg == "drilling":
                signals = _drilling_signals(idx, current_md, base_md, rng)
            elif seg == "stick_slip_mitigation":
                signals = _mitigation_signals(idx, current_md, base_md, rng)
            elif seg == "circulation":
                signals = _circulation_signals(idx, rng)
            else:
                signals = _connection_signals(idx, rng)

            active_event = _event_at_idx(idx, event_windows)
            signals = _apply_event_to_signals(signals, idx, active_event)

            inclination = 6.0 + 0.016 * (current_md - base_md) + 0.45 * math.sin(idx / 170.0) + rng.gauss(0, 0.08)
            azimuth = (35.0 + 0.028 * (current_md - base_md) + 2.2 * math.sin(idx / 95.0) + rng.gauss(0, 0.4)) % 360.0
            signals["inclination"] = max(0.0, min(88.0, inclination))
            signals["azimuth"] = azimuth
            signals["flow_in"] = 535.0 if seg in {"drilling", "stick_slip_mitigation"} else 430.0 if seg == "circulation" else 24.0
            signals["flow_in"] += rng.gauss(0, 8.0)
            signals["rop"] = max(0.0, md_rate_mps * 3600.0)
            signals["bit_depth"] = current_md - (0.2 if seg == "connection" else 0.0)
            signals["hookload"] = max(20.0, 172.0 - signals["wob"] * 0.42 + rng.gauss(0, 2.5))
            signals["differential_pressure"] = max(0.0, signals["standpipe_pressure"] - 930.0 + rng.gauss(0, 18.0))
            signals["mud_motor_rpm"] = max(0.0, signals["rpm"] * 0.72 + signals["flow_in"] * 0.055 + rng.gauss(0, 1.8))

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
                        "quality_code": 1 if active_event and active_event.spec.severity == "critical" else 0,
                        "value": float(signals[channel]),
                    }
                )

        simulation_events = []
        for window in event_windows:
            simulation_events.append(
                {
                    "id": f"{scenario}-{window.spec.event_type}-{window.start_idx}",
                    "type": window.spec.event_type,
                    "title": window.spec.title,
                    "severity": window.spec.severity,
                    "start_ts": ts_series[window.start_idx].isoformat(),
                    "end_ts": ts_series[window.end_idx].isoformat(),
                    "md_start": float(md_series[window.start_idx]),
                    "md_end": float(md_series[window.end_idx]),
                    "description": window.spec.description,
                    "recommendation": window.spec.recommendation,
                    "confidence": 0.94 if window.spec.severity == "critical" else 0.88,
                }
            )

        run.details = {
            "mock_data": {
                "seed": seed,
                "scenario": scenario,
                "duration_minutes": duration_minutes,
                "step_seconds": step_seconds,
                "channels": CHANNELS,
            },
            "digital_twin": {
                "rig": "WV-260 AC automated drilling package",
                "well_profile": "build-and-hold directional section",
                "bit": {
                    "type": "PDC 12-1/4in",
                    "iadc": "M323",
                    "nozzles": "6 x 12/32",
                    "serial": f"WV-{scenario.upper()}-{seed}",
                },
                "bha": {
                    "motor": "7in 1.5deg mud motor",
                    "mwd": "near-bit vibration + inclination package",
                    "stabilizers": 3,
                },
                "mud": {
                    "density_ppg": 10.6,
                    "viscosity_cp": 38,
                    "chloride_ppm": 5200,
                },
                "operating_window": {
                    "wob_min": 62,
                    "wob_max": 105,
                    "rpm_min": 92,
                    "rpm_max": 148,
                    "pressure_min": 2600,
                    "pressure_max": 4300,
                    "vibration_max": 7.2,
                    "torque_max": 32,
                },
            },
            "geology": {
                "layers": formations
            },
            "simulation_events": simulation_events,
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
                    details={
                        "generator": "generate_replay_mock_data.py",
                        "scenario": scenario,
                        "formation": _formation_name(float(md_series[start_idx]), formations),
                        "target": {
                            "wob": "62-105 kN",
                            "rpm": "92-148 rpm",
                            "pressure": "2600-4300 psi",
                        },
                    },
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
            "scenario": scenario,
            "points": total_points,
            "metrics_inserted": len(metric_rows),
            "segments_inserted": len(plans),
            "events_inserted": len(simulation_events),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic well-run metrics for Drill Replay.")
    parser.add_argument("--tenant-id", type=str, default=None, help="Target tenant UUID. Defaults to oldest tenant.")
    parser.add_argument("--warehouse-name", type=str, default="Replay Demo Warehouse", help="Warehouse name.")
    parser.add_argument("--well-run-name", type=str, default="Replay Demo Run", help="Well run name.")
    parser.add_argument(
        "--scenario",
        choices=["normal", "anomaly", "all"],
        default="normal",
        help="Synthetic scenario to generate. 'all' creates normal and anomaly runs.",
    )
    parser.add_argument("--duration-minutes", type=int, default=120, help="Replay duration in minutes.")
    parser.add_argument("--step-seconds", type=int, default=2, help="Sampling step in seconds.")
    parser.add_argument("--seed", type=int, default=20260219, help="Random seed for deterministic data.")
    parser.add_argument(
        "--append",
        action="store_true",
        help="Do not clear existing metrics/segments when well run name already exists.",
    )
    args = parser.parse_args()

    scenarios = ["normal", "anomaly"] if args.scenario == "all" else [args.scenario]
    results = []
    for offset, scenario in enumerate(scenarios):
        suffix = "Normal Twin" if scenario == "normal" else "Anomaly Twin"
        run_name = args.well_run_name.strip() or "Replay Demo Run"
        if args.scenario == "all":
            run_name = f"{run_name} - {suffix}"
        result = generate_mock_data(
            tenant_id_text=args.tenant_id,
            warehouse_name=args.warehouse_name.strip() or "Replay Demo Warehouse",
            well_run_name=run_name,
            duration_minutes=args.duration_minutes,
            step_seconds=args.step_seconds,
            seed=args.seed + offset,
            scenario=scenario,
            replace=not args.append,
        )
        results.append(result)
    print(results if len(results) > 1 else results[0])


if __name__ == "__main__":
    main()
