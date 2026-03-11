from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from .config import MonitorConfig
from .core import SymbolResult


@dataclass(frozen=True)
class ReportSummary:
    scanned: int
    success: int
    failed: int
    high_alerts: int
    low_alerts: int
    alert_symbols: int
    stale_symbols: int


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "NA"
    return f"{value:.1f}%"


def _build_symbol_line(result: SymbolResult, window_order: list[str]) -> str:
    assert result.window_percentiles is not None
    assert result.latest_date is not None
    assert result.latest_price is not None

    tags: list[str] = []
    if result.high_windows:
        tags.append(f"高位[{','.join(result.high_windows)}]")
    if result.low_windows:
        tags.append(f"低位[{','.join(result.low_windows)}]")
    tag_text = " | ".join(tags) if tags else "无告警"

    pct_text = " ".join(
        f"{label}:{_fmt_pct(result.window_percentiles.get(label))}" for label in window_order
    )
    return (
        f"- {result.symbol.name}({result.symbol.code}/{result.symbol.market}) "
        f"最新={result.latest_price:.4g} 日期={result.latest_date} "
        f"{tag_text} | {pct_text}"
    )


def build_report(
    results: list[SymbolResult],
    cfg: MonitorConfig,
    mode_label: str = "core",
    degrade_reason: str | None = None,
    elapsed_seconds: float | None = None,
    core_planned: int | None = None,
    extra_planned: int | None = None,
    core_scanned: int | None = None,
    extra_scanned: int | None = None,
) -> tuple[str, ReportSummary]:
    now_cn = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S")
    window_order = list(cfg.windows.keys())

    success_items = [r for r in results if r.error is None]
    failed_items = [r for r in results if r.error is not None]
    alert_items = [r for r in success_items if (r.high_windows or r.low_windows)]

    high_alerts = sum(1 for r in success_items if r.high_windows)
    low_alerts = sum(1 for r in success_items if r.low_windows)
    stale_symbols = sum(
        1
        for r in success_items
        if r.stale_days is not None and r.stale_days > cfg.max_stale_days
    )
    summary = ReportSummary(
        scanned=len(results),
        success=len(success_items),
        failed=len(failed_items),
        high_alerts=high_alerts,
        low_alerts=low_alerts,
        alert_symbols=len(alert_items),
        stale_symbols=stale_symbols,
    )

    lines: list[str] = [
        f"## 商品日频监控告警（{now_cn}）",
        f"运行模式: {mode_label}",
        (
            f"降级策略: enabled={cfg.degrade.enabled} "
            f"max_run={cfg.degrade.max_run_seconds}s "
            f"max_fail_ratio={cfg.degrade.max_fail_ratio:.0%} "
            f"min_samples={cfg.degrade.min_samples}"
        ),
        f"阈值: 高位>={cfg.thresholds.high_percentile:.0f}% 低位<={cfg.thresholds.low_percentile:.0f}%",
        f"窗口: {', '.join(f'{k}={v}d' for k, v in cfg.windows.items())}",
        "",
    ]
    if degrade_reason:
        lines.append(f"降级原因: {degrade_reason}")
    if elapsed_seconds is not None:
        lines.append(f"运行时长: {elapsed_seconds:.1f}s")
    if core_planned is not None and extra_planned is not None:
        lines.append(f"计划扫描: core={core_planned} extra={extra_planned}")
    if core_scanned is not None and extra_scanned is not None:
        lines.append(f"实际扫描: core={core_scanned} extra={extra_scanned}")
    lines.append("")

    if alert_items:
        lines.append("### 触发告警品种")
        for item in alert_items:
            lines.append(_build_symbol_line(item, window_order))
    else:
        lines.append("### 触发告警品种")
        lines.append("- 本次无品种触发阈值。")

    lines.extend(
        [
            "",
            "### 扫描统计",
            (
                f"- 扫描总数={summary.scanned} 成功={summary.success} 失败={summary.failed} "
                f"告警品种={summary.alert_symbols} 高位={summary.high_alerts} "
                f"低位={summary.low_alerts} 过旧数据={summary.stale_symbols}"
            ),
        ]
    )

    if failed_items:
        lines.append("- 失败明细(最多10条):")
        for item in failed_items[:10]:
            lines.append(f"  - {item.symbol.name}({item.symbol.code}): {item.error}")

    return "\n".join(lines), summary
