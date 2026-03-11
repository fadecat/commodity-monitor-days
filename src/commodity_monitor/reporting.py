from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import re
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
    stale_symbols: int  # v1 uses cfg.max_stale_days, v2 uses fixed stale cutoff


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "NA"
    return f"{value:.1f}%"


def _fmt_pct_short(value: float | None) -> str:
    if value is None:
        return "NA"
    return f"{value:.0f}%"


def _fmt_price(value: float) -> str:
    abs_value = abs(value)
    if abs_value >= 10000:
        # Use plain integer-style representation for large values, never scientific notation.
        return f"{value:.0f}"
    if abs_value >= 1000:
        return f"{value:.2f}".rstrip("0").rstrip(".")
    if abs_value >= 100:
        return f"{value:.3f}".rstrip("0").rstrip(".")
    if abs_value >= 1:
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _pct_hit_style(value: float | None, is_hit: bool) -> str:
    base = _fmt_pct_short(value)
    if is_hit and value is not None:
        return f"**{base}**"
    return base


def _normalize_code_root(code: str) -> str:
    code_up = code.upper()
    root = re.sub(r"\d+$", "", code_up)
    return root


# v2 板块映射
ENERGY_CHEM = {
    "CL",
    "NG",
    "OIL",
    "SC",
    "FU",
    "BU",
    "LU",
    "PG",
    "TA",
    "MA",
    "EG",
    "SA",
    "UR",
    "L",
    "PP",
    "V",
}
METALS = {
    "GC",
    "SI",
    "HG",
    "AHD",
    "CAD",
    "NID",
    "PBD",
    "SND",
    "ZSD",
    "AU",
    "AG",
    "CU",
    "AL",
    "ZN",
    "NI",
    "SN",
    "PB",
    "AO",
    "LC",
}
BLACKS = {"ZC", "JM", "J", "I", "RB", "HC", "SS", "SF"}
AGRI = {
    "C",
    "S",
    "W",
    "BO",
    "SM",
    "CT",
    "FCPO",
    "RSS",
    "M",
    "Y",
    "P",
    "RM",
    "OI",
    "A",
    "SR",
    "CF",
    "AP",
    "PK",
}


def _section_name(code_root: str) -> str:
    if code_root in ENERGY_CHEM:
        return "能源与化工"
    if code_root in METALS:
        return "有色贵金属"
    if code_root in BLACKS:
        return "黑色建材"
    if code_root in AGRI:
        return "农产品"
    return "其他"


def _section_name_for_symbol(result: SymbolResult) -> str:
    code = result.symbol.code.upper()
    # "SM" exists in both CBOT soymeal and CZCE manganese silicon.
    if code == "SM":
        return "农产品"
    if code == "SM0":
        return "黑色建材"
    return _section_name(_normalize_code_root(code))


def _is_stale(result: SymbolResult, stale_days_threshold: int) -> bool:
    return (
        result.error is None
        and result.stale_days is not None
        and result.stale_days > stale_days_threshold
    )


def _is_resonance(
    result: SymbolResult,
    expected_windows: tuple[str, str, str, str] = ("d21", "d63", "y1", "y3"),
    high_cutoff: float = 95.0,
    low_cutoff: float = 5.0,
) -> tuple[bool, str | None]:
    pct = result.window_percentiles or {}
    values = [pct.get(w) for w in expected_windows]
    if any(v is None for v in values):
        return False, None
    float_values = [float(v) for v in values if v is not None]
    if all(v >= high_cutoff for v in float_values):
        return True, "high"
    if all(v <= low_cutoff for v in float_values):
        return True, "low"
    return False, None


def _build_alert_line_v2(result: SymbolResult) -> tuple[str, str]:
    assert result.latest_price is not None
    assert result.window_percentiles is not None
    assert result.latest_date is not None

    highs = result.high_windows or []
    lows = result.low_windows or []

    if highs and not lows:
        emoji = "🔴"
        trend_desc = f"创[{', '.join(highs)}]高位"
    elif lows and not highs:
        emoji = "🟢"
        trend_desc = f"创[{', '.join(lows)}]低位"
    elif highs and lows:
        emoji = "🔴"
        trend_desc = f"高位[{', '.join(highs)}] / 低位[{', '.join(lows)}]"
    else:
        emoji = "⚪"
        trend_desc = "无告警"

    pct = result.window_percentiles
    p21 = _pct_hit_style(pct.get("d21"), "d21" in highs or "d21" in lows)
    p63 = _pct_hit_style(pct.get("d63"), "d63" in highs or "d63" in lows)
    py1 = _pct_hit_style(pct.get("y1"), "y1" in highs or "y1" in lows)
    py3 = _pct_hit_style(pct.get("y3"), "y3" in highs or "y3" in lows)

    title_line = (
        f"{emoji} **{result.symbol.name}({result.symbol.code})**: "
        f"**{_fmt_price(result.latest_price)}** | {trend_desc}"
    )
    detail_line = (
        f"> 历史分位: 21d({p21}) | 63d({p63}) | 1y({py1}) | 3y({py3})"
    )
    return title_line, detail_line


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


def build_report_v1(
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


def build_report_v2_markdown(
    results: list[SymbolResult],
    cfg: MonitorConfig,
    stale_days_threshold: int = 5,
) -> tuple[str, ReportSummary]:
    today_cn = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()

    success_items = [r for r in results if r.error is None]
    failed_items = [r for r in results if r.error is not None]
    stale_items = [r for r in success_items if _is_stale(r, stale_days_threshold)]

    # 先按阈值选告警，再剔除过期数据
    alert_raw = [r for r in success_items if (r.high_windows or r.low_windows)]
    alert_items = [r for r in alert_raw if not _is_stale(r, stale_days_threshold)]

    resonance_items: list[tuple[SymbolResult, str]] = []
    normal_items: list[SymbolResult] = []
    for item in alert_items:
        is_res, direction = _is_resonance(item)
        if is_res and direction is not None:
            resonance_items.append((item, direction))
        else:
            normal_items.append(item)

    grouped: dict[str, list[SymbolResult]] = {
        "能源与化工": [],
        "黑色建材": [],
        "有色贵金属": [],
        "农产品": [],
        "其他": [],
    }
    for item in normal_items:
        sec = _section_name_for_symbol(item)
        grouped[sec].append(item)

    high_alerts = sum(1 for r in alert_items if r.high_windows)
    low_alerts = sum(1 for r in alert_items if r.low_windows)
    summary = ReportSummary(
        scanned=len(results),
        success=len(success_items),
        failed=len(failed_items),
        high_alerts=high_alerts,
        low_alerts=low_alerts,
        alert_symbols=len(alert_items),
        stale_symbols=len(stale_items),
    )

    lines: list[str] = [
        f"**商品极值监控日报** ({today_cn})",
        f"> 监控规则: 高位区>={cfg.thresholds.high_percentile:.0f}%, 低位区<={cfg.thresholds.low_percentile:.0f}%",
        "",
    ]

    if resonance_items:
        lines.append("🔥 **【多周期极值共振】(重点关注)**")
        for item, direction in resonance_items:
            assert item.latest_price is not None
            emoji = "🔴" if direction == "high" else "🟢"
            blast = "四周期极值共振！"
            lines.append(
                f"{emoji} **{item.symbol.name}({item.symbol.code})**: "
                f"**{_fmt_price(item.latest_price)}** | {blast}"
            )
        lines.append("")

    lines.append("---------------------------")

    section_order = [
        ("能源与化工", "🛢"),
        ("黑色建材", "🏗"),
        ("有色贵金属", "👑"),
        ("农产品", "🌾"),
        ("其他", "🧩"),
    ]
    has_any_section = False
    for sec, icon in section_order:
        items = grouped[sec]
        if not items:
            continue
        has_any_section = True
        lines.append(f"{icon} **【{sec}】**")
        for item in items:
            title_line, detail_line = _build_alert_line_v2(item)
            lines.append(title_line)
            lines.append(detail_line)
            lines.append("")

    if not has_any_section and not resonance_items:
        lines.append("✅ 本次无有效告警。")
        lines.append("")

    lines.append("---------------------------")
    lines.append(
        "<font color=\"comment\">"
        f"系统信息: 扫描完成({summary.scanned}个品种), "
        f"有效告警{summary.alert_symbols}个, "
        f"高位{summary.high_alerts}个, 低位{summary.low_alerts}个, "
        f"剔除过期数据{summary.stale_symbols}个, 抓取失败{summary.failed}个。"
        "</font>"
    )
    return "\n".join(lines), summary


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
    # v2 is default for webhook and local report output; keep v1 callable via build_report_v1.
    _ = (mode_label, degrade_reason, elapsed_seconds, core_planned, extra_planned, core_scanned, extra_scanned)
    return build_report_v2_markdown(results=results, cfg=cfg, stale_days_threshold=5)
