from __future__ import annotations

import unittest

from scripts.generate_replay_mock_data import (
    CHANNELS,
    _apply_event_to_signals,
    _build_event_windows,
    _drilling_signals,
    _event_at_idx,
    _formation_layers,
    _formation_name,
)


class ReplayMockDataTests(unittest.TestCase):
    def test_anomaly_scenario_builds_event_windows(self) -> None:
        windows = _build_event_windows(1000, "anomaly")

        self.assertEqual([window.spec.event_type for window in windows], ["pressure_surge", "stick_slip", "high_vibration"])
        self.assertIsNotNone(_event_at_idx(500, windows))
        self.assertIsNone(_event_at_idx(900, windows))

    def test_critical_event_changes_drilling_signals(self) -> None:
        windows = _build_event_windows(1000, "anomaly")
        event = windows[1]
        idx = (event.start_idx + event.end_idx) // 2
        base = {
            "standpipe_pressure": 3300.0,
            "bit_vibration": 4.0,
            "wob": 82.0,
            "rpm": 128.0,
            "torque": 20.0,
        }

        adjusted = _apply_event_to_signals(base, idx, event)

        self.assertGreater(adjusted["bit_vibration"], base["bit_vibration"])
        self.assertGreater(adjusted["torque"], base["torque"])
        self.assertLess(adjusted["rpm"], base["rpm"])

    def test_channels_include_core_and_derived_twin_fields(self) -> None:
        self.assertIn("standpipe_pressure", CHANNELS)
        self.assertIn("bit_vibration", CHANNELS)
        self.assertIn("flow_in", CHANNELS)
        self.assertIn("differential_pressure", CHANNELS)

    def test_formation_lookup_uses_depth_layers(self) -> None:
        layers = _formation_layers(1500.0)

        self.assertEqual(_formation_name(1501.0, layers), "Soft Clay")
        self.assertEqual(_formation_name(1700.0, layers), "Reactive Shale")
        self.assertEqual(_formation_name(2200.0, layers), "Tight Sand")

    def test_drilling_signal_shape_contains_replay_metrics(self) -> None:
        import random

        signals = _drilling_signals(20, 1510.0, 1500.0, random.Random(7))

        self.assertGreater(signals["standpipe_pressure"], 0)
        self.assertGreater(signals["wob"], 0)
        self.assertGreater(signals["rpm"], 0)
        self.assertGreater(signals["torque"], 0)


if __name__ == "__main__":
    unittest.main()
