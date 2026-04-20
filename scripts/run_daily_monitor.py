from __future__ import annotations

import argparse
import os
import random
import sys
import time
from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from commodity_monitor.config import MonitorConfig, SymbolConfig, load_config, load_symbols
from commodity_monitor.core import SymbolResult, evaluate_symbol, run_scan
from commodity_monitor.email_notifier import send_email
from commodity_monitor.reporting import (
    build_email_html,
    build_report_v1,
    build_report_v2_markdown,
)
from commodity_monitor.wechat import send_in_chunks


@dataclass(frozen=True)
class ScanMeta:
    mode_label: str
    degraded: bool
    degrade_reason: str | None
    elapsed_seconds: float
    core_planned: int
    extra_planned: int
    core_scanned: int
    extra_scanned: int


@dataclass(frozen=True)
class SymbolPlan:
    core_symbols: list[SymbolConfig]
    extra_symbols: list[SymbolConfig]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Daily commodity percentile monitor")
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "config" / "monitor.toml",
        help="Config path (.toml/.yaml/.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run scan and print report without pushing to WeChat",
    )
    parser.add_argument(
        "--max-symbols",
        type=int,
        default=None,
        help="Only scan first N enabled symbols (for local debug)",
    )
    parser.add_argument(
        "--profile",
        choices=["core", "extended"],
        default="core",
        help="Symbol profile: core uses selected pool, extended appends larger pool",
    )
    parser.add_argument(
        "--extended-symbols",
        type=Path,
        default=ROOT / "config" / "symbols_extended.toml",
        help="Extra symbols file used when --profile=extended",
    )
    parser.add_argument(
        "--degrade-off",
        action="store_true",
        help="Disable runtime auto-degrade even in extended profile",
    )
    parser.add_argument(
        "--degrade-max-run-seconds",
        type=int,
        default=None,
        help="Override degrade max runtime seconds",
    )
    parser.add_argument(
        "--degrade-max-fail-ratio",
        type=float,
        default=None,
        help="Override degrade max failed ratio, range (0, 1]",
    )
    parser.add_argument(
        "--degrade-min-samples",
        type=int,
        default=None,
        help="Override degrade minimum sample count before fail-ratio check",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Validate config and print planned scan scope without fetching market data",
    )
    parser.add_argument(
        "--show-symbols",
        action="store_true",
        help="Print planned symbol list in check-only mode",
    )
    parser.add_argument(
        "--report-version",
        choices=["v1", "v2"],
        default="v2",
        help="Report rendering version, v2 is markdown-optimized for WeChat",
    )
    return parser.parse_args()


def _sleep_between_symbols(cfg: MonitorConfig) -> None:
    pause = random.uniform(cfg.delay.min_seconds, cfg.delay.max_seconds)
    time.sleep(pause)


def _enabled_symbols(items: list[SymbolConfig], max_count: int | None = None) -> list[SymbolConfig]:
    enabled = [item for item in items if item.enabled]
    if max_count is not None:
        return enabled[:max_count]
    return enabled


def _dedup_extra_symbols(
    core_symbols: list[SymbolConfig], extra_symbols: list[SymbolConfig]
) -> list[SymbolConfig]:
    seen = {(item.market, item.code) for item in core_symbols}
    out: list[SymbolConfig] = []
    for item in extra_symbols:
        key = (item.market, item.code)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _override_degrade(cfg: MonitorConfig, args: argparse.Namespace) -> MonitorConfig:
    degrade_cfg = cfg.degrade
    if args.degrade_off:
        degrade_cfg = replace(degrade_cfg, enabled=False)
    if args.degrade_max_run_seconds is not None:
        if args.degrade_max_run_seconds <= 0:
            raise ValueError("--degrade-max-run-seconds must be > 0")
        degrade_cfg = replace(degrade_cfg, max_run_seconds=args.degrade_max_run_seconds)
    if args.degrade_max_fail_ratio is not None:
        if not (0 < args.degrade_max_fail_ratio <= 1):
            raise ValueError("--degrade-max-fail-ratio must be in (0, 1]")
        degrade_cfg = replace(degrade_cfg, max_fail_ratio=args.degrade_max_fail_ratio)
    if args.degrade_min_samples is not None:
        if args.degrade_min_samples <= 0:
            raise ValueError("--degrade-min-samples must be > 0")
        degrade_cfg = replace(degrade_cfg, min_samples=args.degrade_min_samples)
    return replace(cfg, degrade=degrade_cfg)


def _build_symbol_plan(cfg: MonitorConfig, args: argparse.Namespace) -> SymbolPlan:
    core_symbols = _enabled_symbols(cfg.symbols)
    extra_symbols: list[SymbolConfig] = []
    if args.profile == "extended":
        extra_symbols = _enabled_symbols(load_symbols(args.extended_symbols))
        extra_symbols = _dedup_extra_symbols(core_symbols, extra_symbols)

    if args.max_symbols is not None:
        if args.max_symbols <= len(core_symbols):
            core_symbols = core_symbols[: args.max_symbols]
            extra_symbols = []
        else:
            remaining = args.max_symbols - len(core_symbols)
            extra_symbols = extra_symbols[:remaining]
    return SymbolPlan(core_symbols=core_symbols, extra_symbols=extra_symbols)


def _print_plan(cfg: MonitorConfig, args: argparse.Namespace, plan: SymbolPlan) -> None:
    total = len(plan.core_symbols) + len(plan.extra_symbols)
    print("=== Monitor Plan ===")
    print(f"profile={args.profile}")
    print(f"report_version={args.report_version}")
    print(f"core_symbols={len(plan.core_symbols)}")
    print(f"extra_symbols={len(plan.extra_symbols)}")
    print(f"total_symbols={total}")
    print(
        "degrade="
        f"enabled:{cfg.degrade.enabled},"
        f"max_run_seconds:{cfg.degrade.max_run_seconds},"
        f"max_fail_ratio:{cfg.degrade.max_fail_ratio},"
        f"min_samples:{cfg.degrade.min_samples}"
    )
    print(f"windows={cfg.windows}")
    print(
        "thresholds="
        f"high>={cfg.thresholds.high_percentile},"
        f"low<={cfg.thresholds.low_percentile}"
    )
    print(
        "wechat="
        f"env:{cfg.wechat.webhook_env},"
        f"max_chars:{cfg.wechat.max_message_chars},"
        f"send_when_no_alert:{cfg.wechat.send_when_no_alert}"
    )
    if args.show_symbols:
        print("\n[core symbols]")
        for item in plan.core_symbols:
            print(f"- {item.name} ({item.code}/{item.market}) enabled={item.enabled}")
        if plan.extra_symbols:
            print("\n[extra symbols]")
            for item in plan.extra_symbols:
                print(f"- {item.name} ({item.code}/{item.market}) enabled={item.enabled}")


def _safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        sys.stdout.buffer.write((text + "\n").encode(encoding, errors="replace"))


def _scan_extended_with_degrade(
    cfg: MonitorConfig,
    plan: SymbolPlan,
) -> tuple[list[SymbolResult], ScanMeta]:
    results: list[SymbolResult] = []
    start = time.monotonic()
    degrade_reason: str | None = None
    core_scanned = 0
    extra_scanned = 0

    for symbol in plan.core_symbols:
        if results:
            _sleep_between_symbols(cfg)
        results.append(evaluate_symbol(symbol, cfg))
        core_scanned += 1

    for symbol in plan.extra_symbols:
        elapsed = time.monotonic() - start
        failed = sum(1 for item in results if item.error is not None)
        scanned = len(results)
        fail_ratio = (failed / scanned) if scanned else 0.0

        if cfg.degrade.enabled and elapsed >= cfg.degrade.max_run_seconds:
            degrade_reason = (
                f"运行时长超阈值: {elapsed:.0f}s >= {cfg.degrade.max_run_seconds}s"
            )
            break
        if (
            cfg.degrade.enabled
            and scanned >= cfg.degrade.min_samples
            and fail_ratio > cfg.degrade.max_fail_ratio
        ):
            degrade_reason = (
                f"抓取失败率超阈值: {fail_ratio:.1%} > {cfg.degrade.max_fail_ratio:.1%}"
            )
            break

        if results:
            _sleep_between_symbols(cfg)
        results.append(evaluate_symbol(symbol, cfg))
        extra_scanned += 1

    elapsed = time.monotonic() - start
    degraded = degrade_reason is not None
    mode_label = "extended(已降级为core)" if degraded else "extended"
    return results, ScanMeta(
        mode_label=mode_label,
        degraded=degraded,
        degrade_reason=degrade_reason,
        elapsed_seconds=elapsed,
        core_planned=len(plan.core_symbols),
        extra_planned=len(plan.extra_symbols),
        core_scanned=core_scanned,
        extra_scanned=extra_scanned,
    )


def _run_scan_by_profile(
    cfg: MonitorConfig, args: argparse.Namespace, plan: SymbolPlan
) -> tuple[list[SymbolResult], ScanMeta]:
    if args.profile == "core":
        core_only_cfg = replace(cfg, symbols=plan.core_symbols)
        start = time.monotonic()
        results = run_scan(core_only_cfg)
        elapsed = time.monotonic() - start
        return results, ScanMeta(
            mode_label="core",
            degraded=False,
            degrade_reason=None,
            elapsed_seconds=elapsed,
            core_planned=len(plan.core_symbols),
            extra_planned=0,
            core_scanned=len(results),
            extra_scanned=0,
        )

    return _scan_extended_with_degrade(cfg, plan)


def main() -> int:
    args = parse_args()
    cfg = load_config(args.config)
    cfg = _override_degrade(cfg, args)
    plan = _build_symbol_plan(cfg, args)
    _print_plan(cfg, args, plan)

    if args.check_only:
        print("\n[check-only] configuration and plan look valid")
        return 0

    results, meta = _run_scan_by_profile(cfg, args, plan)
    if args.report_version == "v1":
        report, summary = build_report_v1(
            results,
            cfg,
            mode_label=meta.mode_label,
            degrade_reason=meta.degrade_reason,
            elapsed_seconds=meta.elapsed_seconds,
            core_planned=meta.core_planned,
            extra_planned=meta.extra_planned,
            core_scanned=meta.core_scanned,
            extra_scanned=meta.extra_scanned,
        )
    else:
        report, summary = build_report_v2_markdown(
            results=results,
            cfg=cfg,
            stale_days_threshold=5,
        )
    _safe_print(report)

    webhook = os.getenv(cfg.wechat.webhook_env, "").strip()
    should_send = summary.alert_symbols > 0 or cfg.wechat.send_when_no_alert
    today_cn = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    has_today_data = any(item.error is None and item.latest_date == today_cn for item in results)

    if args.dry_run:
        print("\n[dry-run] skip webhook push")
        return 0

    if cfg.skip_if_no_today_data and not has_today_data:
        print("\nNo symbol has today's data, skip webhook push")
        return 0

    if not should_send:
        print("\nNo alert symbols, skip webhook push by config")
        return 0

    _try_send_email(results, cfg, today_cn)

    if not webhook:
        print(
            f"\nMissing webhook env `{cfg.wechat.webhook_env}` while push is required",
            file=sys.stderr,
        )
        return 2

    sent = 0
    for _ in send_in_chunks(
        webhook_url=webhook, content=report, max_chars=cfg.wechat.max_message_chars
    ):
        sent += 1
    print(f"\nWeChat push succeeded, chunks={sent}")
    return 0


def _try_send_email(
    results: list[SymbolResult], cfg: MonitorConfig, today_cn: date
) -> None:
    try:
        html_parts, _ = build_email_html(results=results, cfg=cfg)
        send_email(f"商品极值监控日报 {today_cn.isoformat()}", html_parts)
    except Exception as exc:  # noqa: BLE001
        print(f"邮件推送失败: {exc}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
