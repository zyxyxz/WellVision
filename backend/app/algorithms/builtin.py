from __future__ import annotations

from datetime import datetime, timezone
import math
from statistics import mean, median, pstdev
from typing import Sequence

import numpy as np

from app.algorithms.base import AlgorithmResult, AlgorithmSpec
from app.schemas.analysis import AlgorithmInfo, AlgorithmParam, SeriesPoint


def moving_average(points: Sequence[SeriesPoint], params: dict) -> AlgorithmResult:
    window = int(params.get("window", 10))
    window = max(2, min(window, 500))
    result: list[SeriesPoint] = []
    buf: list[float] = []
    for point in points:
        buf.append(point.value)
        if len(buf) > window:
            buf.pop(0)
        result.append(SeriesPoint(ts=point.ts, value=mean(buf)))
    return AlgorithmResult(
        result_series=result,
        metrics={"window": window, "count": len(result)},
    )


def rolling_std(points: Sequence[SeriesPoint], params: dict) -> AlgorithmResult:
    window = int(params.get("window", 20))
    window = max(2, min(window, 500))
    result: list[SeriesPoint] = []
    buf: list[float] = []
    for point in points:
        buf.append(point.value)
        if len(buf) > window:
            buf.pop(0)
        if len(buf) < 2:
            result.append(SeriesPoint(ts=point.ts, value=0.0))
        else:
            result.append(SeriesPoint(ts=point.ts, value=pstdev(buf)))
    avg_std = mean([p.value for p in result]) if result else 0.0
    return AlgorithmResult(
        result_series=result,
        metrics={"window": window, "avg_std": avg_std},
    )


def exponential_moving_average(points: Sequence[SeriesPoint], params: dict) -> AlgorithmResult:
    alpha = float(params.get("alpha", 0.2))
    alpha = max(0.01, min(alpha, 0.99))
    result: list[SeriesPoint] = []
    ema: float | None = None
    for point in points:
        ema = point.value if ema is None else alpha * point.value + (1 - alpha) * ema
        result.append(SeriesPoint(ts=point.ts, value=ema))
    return AlgorithmResult(
        result_series=result,
        metrics={"alpha": alpha, "count": len(result)},
    )


def rate_of_change(points: Sequence[SeriesPoint], params: dict) -> AlgorithmResult:
    result: list[SeriesPoint] = []
    if len(points) < 2:
        return AlgorithmResult(result_series=result, metrics={"avg_rate": 0.0, "max_rate": 0.0})
    for prev, cur in zip(points, points[1:]):
        dt = (cur.ts - prev.ts).total_seconds()
        if dt <= 0:
            continue
        rate = (cur.value - prev.value) / dt
        result.append(SeriesPoint(ts=cur.ts, value=rate))
    avg_rate = mean([p.value for p in result]) if result else 0.0
    max_rate = max([p.value for p in result], default=0.0)
    return AlgorithmResult(
        result_series=result,
        metrics={"avg_rate": avg_rate, "max_rate": max_rate, "count": len(result)},
    )


def median_filter(points: Sequence[SeriesPoint], params: dict) -> AlgorithmResult:
    window = int(params.get("window", 7))
    window = max(3, min(window, 301))
    result: list[SeriesPoint] = []
    buf: list[float] = []
    for point in points:
        buf.append(point.value)
        if len(buf) > window:
            buf.pop(0)
        result.append(SeriesPoint(ts=point.ts, value=median(buf)))
    return AlgorithmResult(
        result_series=result,
        metrics={"window": window, "count": len(result)},
    )


def linear_trend(points: Sequence[SeriesPoint], params: dict) -> AlgorithmResult:
    if len(points) < 2:
        return AlgorithmResult(result_series=list(points), metrics={"slope": 0.0, "intercept": 0.0, "r2": 0.0})
    xs = [(p.ts - points[0].ts).total_seconds() for p in points]
    ys = [p.value for p in points]
    x_mean = mean(xs)
    y_mean = mean(ys)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    denominator = sum((x - x_mean) ** 2 for x in xs) or 1e-9
    slope = numerator / denominator
    intercept = y_mean - slope * x_mean
    result_series = [SeriesPoint(ts=p.ts, value=slope * x + intercept) for p, x in zip(points, xs)]
    ss_tot = sum((y - y_mean) ** 2 for y in ys) or 1e-9
    ss_res = sum((y - (slope * x + intercept)) ** 2 for y, x in zip(ys, xs))
    r2 = max(0.0, 1.0 - ss_res / ss_tot)
    return AlgorithmResult(
        result_series=result_series,
        metrics={"slope": slope, "intercept": intercept, "r2": r2},
    )


def rolling_range(points: Sequence[SeriesPoint], params: dict) -> AlgorithmResult:
    window = int(params.get("window", 20))
    window = max(2, min(window, 500))
    result: list[SeriesPoint] = []
    buf: list[float] = []
    for point in points:
        buf.append(point.value)
        if len(buf) > window:
            buf.pop(0)
        result.append(SeriesPoint(ts=point.ts, value=max(buf) - min(buf)))
    avg_range = mean([p.value for p in result]) if result else 0.0
    return AlgorithmResult(
        result_series=result,
        metrics={"window": window, "avg_range": avg_range},
    )


def cusum_shift(points: Sequence[SeriesPoint], params: dict) -> AlgorithmResult:
    threshold = float(params.get("threshold", 5.0))
    drift = float(params.get("drift", 0.0))
    if len(points) < 2:
        return AlgorithmResult(result_series=list(points), metrics={"shifts": 0, "threshold": threshold})
    mu = mean([p.value for p in points])
    pos_cusum = 0.0
    neg_cusum = 0.0
    shifts = 0
    result: list[SeriesPoint] = []
    for p in points:
        pos_cusum = max(0.0, pos_cusum + (p.value - mu) - drift)
        neg_cusum = min(0.0, neg_cusum + (p.value - mu) + drift)
        if pos_cusum > threshold or abs(neg_cusum) > threshold:
            shifts += 1
            pos_cusum = 0.0
            neg_cusum = 0.0
        result.append(SeriesPoint(ts=p.ts, value=pos_cusum + abs(neg_cusum)))
    return AlgorithmResult(
        result_series=result,
        metrics={"shifts": shifts, "threshold": threshold, "drift": drift},
    )


def spike_mad(points: Sequence[SeriesPoint], params: dict) -> AlgorithmResult:
    window = int(params.get("window", 25))
    threshold = float(params.get("threshold", 6.0))
    window = max(5, min(window, 501))
    result: list[SeriesPoint] = []
    buf: list[float] = []
    for point in points:
        buf.append(point.value)
        if len(buf) > window:
            buf.pop(0)
        med = median(buf)
        mad = median([abs(x - med) for x in buf]) or 1e-9
        z = abs((point.value - med) / mad)
        if z >= threshold:
            result.append(SeriesPoint(ts=point.ts, value=point.value))
    return AlgorithmResult(
        result_series=result,
        metrics={"window": window, "threshold": threshold, "anomalies": len(result)},
    )


def zscore_anomaly(points: Sequence[SeriesPoint], params: dict) -> AlgorithmResult:
    threshold = float(params.get("threshold", 3.0))
    values = [p.value for p in points]
    if len(values) < 3:
        return AlgorithmResult(result_series=[], metrics={"anomalies": 0, "threshold": threshold})
    mu = mean(values)
    sigma = pstdev(values) or 1e-9

    anomalies: list[SeriesPoint] = []
    for point in points:
        z = abs((point.value - mu) / sigma)
        if z >= threshold:
            anomalies.append(point)
    return AlgorithmResult(
        result_series=anomalies,
        metrics={"anomalies": len(anomalies), "threshold": threshold, "mean": mu, "std": sigma},
    )


def _bucket_series(points: Sequence[SeriesPoint], bucket_seconds: int) -> dict[int, float]:
    bucket_seconds = max(1, int(bucket_seconds))
    buckets: dict[int, list[float]] = {}
    for point in points:
        bucket = int(point.ts.timestamp() // bucket_seconds)
        buckets.setdefault(bucket, []).append(point.value)
    return {bucket: mean(values) for bucket, values in buckets.items() if values}


def _align_series(
    primary: Sequence[SeriesPoint], secondary: Sequence[SeriesPoint], bucket_seconds: int
) -> list[tuple[datetime, float, float]]:
    bucket_seconds = max(1, int(bucket_seconds))
    primary_buckets = _bucket_series(primary, bucket_seconds)
    secondary_buckets = _bucket_series(secondary, bucket_seconds)
    keys = sorted(set(primary_buckets) & set(secondary_buckets))
    aligned: list[tuple[datetime, float, float]] = []
    for key in keys:
        ts = datetime.fromtimestamp(key * bucket_seconds, tz=timezone.utc)
        aligned.append((ts, primary_buckets[key], secondary_buckets[key]))
    return aligned


def _pearson_corr(xs: Sequence[float], ys: Sequence[float]) -> float:
    if len(xs) < 2 or len(xs) != len(ys):
        return 0.0
    x_mean = mean(xs)
    y_mean = mean(ys)
    num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    den_x = sum((x - x_mean) ** 2 for x in xs)
    den_y = sum((y - y_mean) ** 2 for y in ys)
    denom = math.sqrt(den_x * den_y) or 1e-9
    return num / denom


def correlation_coupling(points: Sequence[SeriesPoint], params: dict) -> AlgorithmResult:
    secondary = params.get("_secondary_series") or []
    if not secondary:
        return AlgorithmResult(result_series=[], metrics={"correlation": 0.0, "count": 0})
    bucket_seconds = int(params.get("align_seconds", 30))
    window = int(params.get("window", 30))
    window = max(3, min(window, 500))

    aligned = _align_series(points, secondary, bucket_seconds)
    if len(aligned) < 3:
        return AlgorithmResult(result_series=[], metrics={"correlation": 0.0, "count": len(aligned)})

    xs = [a for _, a, _ in aligned]
    ys = [b for _, _, b in aligned]
    corr = _pearson_corr(xs, ys)

    x_mean = mean(xs)
    y_mean = mean(ys)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    denominator = sum((x - x_mean) ** 2 for x in xs) or 1e-9
    slope = numerator / denominator
    intercept = y_mean - slope * x_mean
    ss_tot = sum((y - y_mean) ** 2 for y in ys) or 1e-9
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
    r2 = max(0.0, 1.0 - ss_res / ss_tot)

    result_series: list[SeriesPoint] = []
    if window >= 3 and len(aligned) >= window:
        for idx in range(window - 1, len(aligned)):
            segment = aligned[idx - window + 1 : idx + 1]
            segment_x = [a for _, a, _ in segment]
            segment_y = [b for _, _, b in segment]
            value = _pearson_corr(segment_x, segment_y)
            result_series.append(SeriesPoint(ts=aligned[idx][0], value=value))

    return AlgorithmResult(
        result_series=result_series,
        metrics={
            "correlation": corr,
            "r2": r2,
            "slope": slope,
            "intercept": intercept,
            "count": len(aligned),
            "window": window,
        },
    )


def stick_slip_detection(points: Sequence[SeriesPoint], params: dict) -> AlgorithmResult:
    secondary = params.get("_secondary_series") or []
    if not secondary:
        return AlgorithmResult(result_series=[], metrics={"events": 0, "count": 0})
    bucket_seconds = int(params.get("align_seconds", 20))
    window = int(params.get("window", 12))
    rpm_drop_ratio = float(params.get("rpm_drop_ratio", 0.8))
    torque_spike_ratio = float(params.get("torque_spike_ratio", 1.2))

    window = max(4, min(window, 200))
    rpm_drop_ratio = max(0.2, min(rpm_drop_ratio, 0.99))
    torque_spike_ratio = max(1.05, min(torque_spike_ratio, 5.0))

    aligned = _align_series(points, secondary, bucket_seconds)
    if len(aligned) < 4:
        return AlgorithmResult(result_series=[], metrics={"events": 0, "count": len(aligned)})

    rpm_buf: list[float] = []
    torque_buf: list[float] = []
    result_series: list[SeriesPoint] = []
    events = 0
    index_values: list[float] = []

    for ts, rpm, torque in aligned:
        rpm_buf.append(rpm)
        torque_buf.append(torque)
        if len(rpm_buf) > window:
            rpm_buf.pop(0)
            torque_buf.pop(0)
        base_rpm = mean(rpm_buf) if rpm_buf else 0.0
        base_torque = mean(torque_buf) if torque_buf else 0.0
        slip_index = 0.0
        if base_rpm > 0 and base_torque > 0:
            rpm_ratio = rpm / base_rpm
            torque_ratio = torque / base_torque
            slip_index = max(0.0, torque_ratio - torque_spike_ratio) + max(0.0, rpm_drop_ratio - rpm_ratio)
            if rpm_ratio < rpm_drop_ratio and torque_ratio > torque_spike_ratio:
                events += 1
        result_series.append(SeriesPoint(ts=ts, value=slip_index))
        index_values.append(slip_index)

    avg_index = mean(index_values) if index_values else 0.0
    max_index = max(index_values, default=0.0)
    event_ratio = events / len(aligned) if aligned else 0.0
    return AlgorithmResult(
        result_series=result_series,
        metrics={
            "events": events,
            "event_ratio": event_ratio,
            "avg_index": avg_index,
            "max_index": max_index,
            "count": len(aligned),
        },
    )


def fft_spectrum(points: Sequence[SeriesPoint], params: dict) -> AlgorithmResult:
    if len(points) < 8:
        return AlgorithmResult(result_series=[], metrics={"points": len(points)})

    max_points = int(params.get("max_points", 1024))
    min_freq = float(params.get("min_frequency_hz", 0.0))
    max_freq = float(params.get("max_frequency_hz", 0.0))
    detrend = bool(params.get("detrend", True))

    values = np.array([p.value for p in points], dtype=float)
    times = np.array([p.ts.timestamp() for p in points], dtype=float)
    order = np.argsort(times)
    values = values[order]
    times = times[order]

    if len(values) > max_points > 0:
        step = int(math.ceil(len(values) / max_points))
        values = values[::step]
        times = times[::step]

    dt = np.diff(times)
    dt = dt[dt > 0]
    median_dt = float(np.median(dt)) if dt.size else 1.0
    if median_dt <= 0:
        median_dt = 1.0
    sample_rate = 1.0 / median_dt

    if detrend:
        values = values - np.mean(values)

    n = len(values)
    fft_vals = np.fft.rfft(values)
    freqs = np.fft.rfftfreq(n, d=median_dt)
    amps = np.abs(fft_vals) / max(1, n)

    mask = freqs >= max(0.0, min_freq)
    if max_freq and max_freq > 0:
        mask = mask & (freqs <= max_freq)
    freqs = freqs[mask]
    amps = amps[mask]

    if len(freqs) == 0:
        return AlgorithmResult(
            result_series=[],
            metrics={"points": len(values), "sample_rate_hz": sample_rate},
            result_points=[],
            x_axis="frequency",
        )

    dominant_idx = int(np.argmax(amps))
    dominant_freq = float(freqs[dominant_idx])
    dominant_amp = float(amps[dominant_idx])
    result_points = [{"x": float(f), "y": float(a)} for f, a in zip(freqs, amps)]

    return AlgorithmResult(
        result_series=[],
        metrics={
            "points": len(values),
            "sample_rate_hz": sample_rate,
            "dominant_frequency_hz": dominant_freq,
            "dominant_amplitude": dominant_amp,
        },
        result_points=result_points,
        x_axis="frequency",
    )


def _haar_energy(values: np.ndarray, levels: int) -> float:
    energy = 0.0
    approx = values.astype(float)
    for _ in range(max(1, levels)):
        if len(approx) < 2:
            break
        if len(approx) % 2 == 1:
            approx = approx[:-1]
        even = approx[0::2]
        odd = approx[1::2]
        detail = (even - odd) / math.sqrt(2.0)
        approx = (even + odd) / math.sqrt(2.0)
        energy += float(np.sum(detail**2))
    return energy


def wavelet_energy(points: Sequence[SeriesPoint], params: dict) -> AlgorithmResult:
    window = int(params.get("window", 64))
    levels = int(params.get("levels", 2))
    window = max(8, min(window, 2048))
    levels = max(1, min(levels, 6))

    values = np.array([p.value for p in points], dtype=float)
    if len(values) < window:
        return AlgorithmResult(
            result_series=[],
            metrics={"window": window, "levels": levels, "count": len(values)},
        )

    energies: list[float] = []
    result_series: list[SeriesPoint] = []
    for idx in range(window, len(values) + 1):
        segment = values[idx - window : idx]
        energy = _haar_energy(segment, levels)
        energies.append(energy)
        result_series.append(SeriesPoint(ts=points[idx - 1].ts, value=energy))

    avg_energy = float(np.mean(energies)) if energies else 0.0
    max_energy = float(np.max(energies)) if energies else 0.0
    return AlgorithmResult(
        result_series=result_series,
        metrics={
            "window": window,
            "levels": levels,
            "avg_energy": avg_energy,
            "max_energy": max_energy,
            "count": len(result_series),
        },
    )


ALGORITHMS: dict[str, AlgorithmSpec] = {
    "moving_average": AlgorithmSpec(
        info=AlgorithmInfo(
            id="moving_average",
            name="移动平均 / Moving Average",
            description="用滚动均值平滑序列 / Smooths the series using a rolling mean window.",
            params=[
                AlgorithmParam(
                    key="window",
                    label="Window",
                    default=20,
                    min=2,
                    max=500,
                    step=1,
                    description="Rolling window size for the moving average.",
                )
            ],
        ),
        fn=moving_average,
    ),
    "zscore_anomaly": AlgorithmSpec(
        info=AlgorithmInfo(
            id="zscore_anomaly",
            name="Z 分数异常 / Z-Score Anomaly",
            description="标记 z-score 超过阈值的点 / Flags points whose z-score exceeds a threshold.",
            params=[
                AlgorithmParam(
                    key="threshold",
                    label="Threshold",
                    default=3.0,
                    min=1.0,
                    max=10.0,
                    step=0.5,
                    description="Absolute z-score threshold for anomaly detection.",
                )
            ],
        ),
        fn=zscore_anomaly,
    ),
    "rolling_std": AlgorithmSpec(
        info=AlgorithmInfo(
            id="rolling_std",
            name="滚动标准差 / Rolling Std",
            description="滚动标准差用于衡量振动/不稳定强度 / Rolling standard deviation to capture vibration/instability intensity.",
            params=[
                AlgorithmParam(
                    key="window",
                    label="Window",
                    default=20,
                    min=2,
                    max=500,
                    step=1,
                    description="Rolling window size for std calculation.",
                )
            ],
        ),
        fn=rolling_std,
    ),
    "ema": AlgorithmSpec(
        info=AlgorithmInfo(
            id="ema",
            name="指数滑动平均 / Exponential Moving Average",
            description="对噪声参数进行指数平滑 / Exponential smoothing for noisy drilling parameters.",
            params=[
                AlgorithmParam(
                    key="alpha",
                    label="Alpha",
                    default=0.2,
                    min=0.01,
                    max=0.99,
                    step=0.01,
                    description="Smoothing factor (0-1).",
                )
            ],
        ),
        fn=exponential_moving_average,
    ),
    "rate_of_change": AlgorithmSpec(
        info=AlgorithmInfo(
            id="rate_of_change",
            name="变化率 / Rate of Change",
            description="一阶变化率，突出扭矩/压力的快速变化 / First derivative to highlight rapid changes in torque/pressure.",
            params=[],
        ),
        fn=rate_of_change,
    ),
    "median_filter": AlgorithmSpec(
        info=AlgorithmInfo(
            id="median_filter",
            name="中值滤波 / Median Filter",
            description="中值平滑，去除尖峰和异常点 / Median smoothing to remove spikes and outliers.",
            params=[
                AlgorithmParam(
                    key="window",
                    label="Window",
                    default=7,
                    min=3,
                    max=301,
                    step=2,
                    description="Odd window size for median smoothing.",
                )
            ],
        ),
        fn=median_filter,
    ),
    "linear_trend": AlgorithmSpec(
        info=AlgorithmInfo(
            id="linear_trend",
            name="线性趋势 / Linear Trend",
            description="对序列拟合线性趋势线 / Fit a linear trend line to the series.",
            params=[],
        ),
        fn=linear_trend,
    ),
    "rolling_range": AlgorithmSpec(
        info=AlgorithmInfo(
            id="rolling_range",
            name="滚动极差 / Rolling Range",
            description="滚动极差（max-min）衡量波动 / Rolling range (max-min) to capture variability.",
            params=[
                AlgorithmParam(
                    key="window",
                    label="Window",
                    default=20,
                    min=2,
                    max=500,
                    step=1,
                    description="Rolling window size for range.",
                )
            ],
        ),
        fn=rolling_range,
    ),
    "cusum_shift": AlgorithmSpec(
        info=AlgorithmInfo(
            id="cusum_shift",
            name="CUSUM 变点检测 / CUSUM Shift",
            description="CUSUM 均值变点检测 / CUSUM change detection for mean shifts.",
            params=[
                AlgorithmParam(
                    key="threshold",
                    label="Threshold",
                    default=5.0,
                    min=0.5,
                    max=50.0,
                    step=0.5,
                    description="CUSUM threshold for shift detection.",
                ),
                AlgorithmParam(
                    key="drift",
                    label="Drift",
                    default=0.0,
                    min=0.0,
                    max=10.0,
                    step=0.1,
                    description="Drift term to reduce false positives.",
                ),
            ],
        ),
        fn=cusum_shift,
    ),
    "spike_mad": AlgorithmSpec(
        info=AlgorithmInfo(
            id="spike_mad",
            name="MAD 尖峰检测 / MAD Spike Detector",
            description="基于 MAD 的尖峰检测 / Detect spikes using Median Absolute Deviation (MAD).",
            params=[
                AlgorithmParam(
                    key="window",
                    label="Window",
                    default=25,
                    min=5,
                    max=501,
                    step=2,
                    description="Odd window size for MAD.",
                ),
                AlgorithmParam(
                    key="threshold",
                    label="Threshold",
                    default=6.0,
                    min=1.0,
                    max=20.0,
                    step=0.5,
                    description="MAD threshold for spike detection.",
                ),
            ],
        ),
        fn=spike_mad,
    ),
    "stick_slip": AlgorithmSpec(
        info=AlgorithmInfo(
            id="stick_slip",
            name="粘滑识别 / Stick-Slip Detection",
            description="基于 RPM 与扭矩识别粘滑 / Detect stick-slip using primary RPM and secondary torque fields.",
            params=[
                AlgorithmParam(
                    key="secondary_field",
                    label="Torque Field",
                    type="field",
                    default="torque",
                    description="Secondary field (torque) used alongside RPM.",
                ),
                AlgorithmParam(
                    key="window",
                    label="Baseline Window (points)",
                    default=12,
                    min=4,
                    max=200,
                    step=1,
                    description="Window size for baseline RPM/torque.",
                ),
                AlgorithmParam(
                    key="rpm_drop_ratio",
                    label="RPM Drop Ratio",
                    default=0.8,
                    min=0.2,
                    max=0.99,
                    step=0.05,
                    description="RPM ratio below baseline to flag stick.",
                ),
                AlgorithmParam(
                    key="torque_spike_ratio",
                    label="Torque Spike Ratio",
                    default=1.2,
                    min=1.05,
                    max=5.0,
                    step=0.05,
                    description="Torque ratio above baseline to flag slip.",
                ),
                AlgorithmParam(
                    key="align_seconds",
                    label="Align Seconds",
                    default=20,
                    min=1,
                    max=3600,
                    step=1,
                    description="Time bucket for aligning RPM/torque.",
                ),
            ],
        ),
        fn=stick_slip_detection,
    ),
    "correlation_coupling": AlgorithmSpec(
        info=AlgorithmInfo(
            id="correlation_coupling",
            name="相关性/耦合 / Correlation / Coupling",
            description="主/次字段相关性分析（如压力/流量） / Correlation analysis between primary and secondary fields.",
            params=[
                AlgorithmParam(
                    key="secondary_field",
                    label="Secondary Field",
                    type="field",
                    default="flow_rate",
                    description="Secondary field for coupling analysis.",
                ),
                AlgorithmParam(
                    key="window",
                    label="Rolling Window (points)",
                    default=30,
                    min=3,
                    max=500,
                    step=1,
                    description="Rolling window size for correlation.",
                ),
                AlgorithmParam(
                    key="align_seconds",
                    label="Align Seconds",
                    default=30,
                    min=1,
                    max=3600,
                    step=1,
                    description="Time bucket for aligning two series.",
                ),
            ],
        ),
        fn=correlation_coupling,
    ),
    "fft_spectrum": AlgorithmSpec(
        info=AlgorithmInfo(
            id="fft_spectrum",
            name="FFT 频谱 / FFT Spectrum",
            description="FFT 频域分析（振动频谱） / Frequency spectrum using FFT.",
            params=[
                AlgorithmParam(
                    key="max_points",
                    label="Max Points",
                    default=1024,
                    min=64,
                    max=4096,
                    step=64,
                    description="Limit points for FFT computation.",
                ),
                AlgorithmParam(
                    key="min_frequency_hz",
                    label="Min Frequency (Hz)",
                    default=0.0,
                    min=0.0,
                    max=2000.0,
                    step=0.1,
                    description="Minimum frequency to display.",
                ),
                AlgorithmParam(
                    key="max_frequency_hz",
                    label="Max Frequency (Hz)",
                    default=0.0,
                    min=0.0,
                    max=2000.0,
                    step=0.1,
                    description="Maximum frequency (0 = no limit).",
                ),
                AlgorithmParam(
                    key="detrend",
                    label="Detrend",
                    type="boolean",
                    default=True,
                    description="Remove mean before FFT.",
                ),
            ],
        ),
        fn=fft_spectrum,
    ),
    "wavelet_energy": AlgorithmSpec(
        info=AlgorithmInfo(
            id="wavelet_energy",
            name="小波能量 / Wavelet Energy",
            description="小波（Haar）能量随时间变化 / Wavelet (Haar) energy over sliding windows.",
            params=[
                AlgorithmParam(
                    key="window",
                    label="Window (points)",
                    default=64,
                    min=8,
                    max=2048,
                    step=8,
                    description="Sliding window for wavelet energy.",
                ),
                AlgorithmParam(
                    key="levels",
                    label="Wavelet Levels",
                    default=2,
                    min=1,
                    max=6,
                    step=1,
                    description="Number of decomposition levels.",
                ),
            ],
        ),
        fn=wavelet_energy,
    ),
}
