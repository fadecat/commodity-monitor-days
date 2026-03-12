from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from commodity_monitor.config import (
    DegradeConfig,
    DelayConfig,
    MonitorConfig,
    SymbolConfig,
    ThresholdConfig,
    WeChatConfig,
)
from commodity_monitor.core import SymbolResult
from commodity_monitor.reporting import build_report_v2_markdown


def _make_cfg() -> MonitorConfig:
    return MonitorConfig(
        delay=DelayConfig(min_seconds=0.0, max_seconds=0.0),
        thresholds=ThresholdConfig(high_percentile=85.0, low_percentile=30.0),
        windows={"d21": 21, "d63": 63, "y1": 252, "y3": 756, "y5": 1260, "y10": 2520},
        wechat=WeChatConfig(
            webhook_env="WECHAT_WEBHOOK_URL",
            max_message_chars=2048,
            send_when_no_alert=False,
        ),
        degrade=DegradeConfig(enabled=True, max_run_seconds=240, max_fail_ratio=0.25, min_samples=20),
        symbols=[],
        max_stale_days=10,
        skip_if_no_today_data=True,
    )


class TestReporting(unittest.TestCase):
    def test_report_v2_displays_dynamic_windows(self) -> None:
        cfg = _make_cfg()
        result = SymbolResult(
            symbol=SymbolConfig(code="CL", name="NYMEX原油", market="foreign"),
            latest_date=date(2026, 3, 12),
            latest_price=88.12,
            window_percentiles={
                "d21": 90.0,
                "d63": 91.0,
                "y1": 95.0,
                "y3": 88.0,
                "y5": None,
                "y10": None,
            },
            high_windows=["y1"],
            low_windows=[],
            stale_days=0,
            error=None,
        )

        report, summary = build_report_v2_markdown([result], cfg)

        self.assertIn("> 历史分位: 21d(90%) | 63d(91%) | 1y(**95%**) | 3y(88%) | 5y(NA) | 10y(NA)", report)
        self.assertEqual(summary.alert_symbols, 1)

    def test_report_v2_resonance_uses_configured_window_count(self) -> None:
        cfg = _make_cfg()
        result = SymbolResult(
            symbol=SymbolConfig(code="GC", name="COMEX黄金", market="foreign"),
            latest_date=date(2026, 3, 12),
            latest_price=3000.0,
            window_percentiles={
                "d21": 99.0,
                "d63": 99.0,
                "y1": 99.0,
                "y3": 99.0,
                "y5": 99.0,
                "y10": 99.0,
            },
            high_windows=["d21", "d63", "y1", "y3", "y5", "y10"],
            low_windows=[],
            stale_days=0,
            error=None,
        )

        report, summary = build_report_v2_markdown([result], cfg)

        self.assertIn("6周期极值共振！", report)
        self.assertEqual(summary.alert_symbols, 1)


if __name__ == "__main__":
    unittest.main()
