from __future__ import annotations

import unittest
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from commodity_monitor.core import compute_window_percentiles, percentile_of_latest


class TestCore(unittest.TestCase):
    def test_percentile_of_latest_uses_latest_value(self) -> None:
        series = pd.Series([1, 2, 3, 4, 5])
        self.assertEqual(percentile_of_latest(series), 100.0)

    def test_compute_window_percentiles_min_points(self) -> None:
        series = pd.Series(range(1, 31))
        windows = {"d21": 21, "d63": 63}
        result = compute_window_percentiles(series, windows, min_points=20)
        self.assertEqual(result["d21"], 100.0)
        self.assertEqual(result["d63"], 100.0)

    def test_compute_window_percentiles_insufficient_data(self) -> None:
        series = pd.Series([1, 2, 3, 4, 5])
        windows = {"d21": 21}
        result = compute_window_percentiles(series, windows, min_points=20)
        self.assertIsNone(result["d21"])


if __name__ == "__main__":
    unittest.main()
