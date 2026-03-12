from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from commodity_monitor.config import MonitorConfig, SymbolConfig, load_config, load_symbols
from commodity_monitor.core import fetch_history

TRADING_DAY_WINDOWS: dict[str, int] = {
    "d21": 21,
    "d63": 63,
    "y1": 252,
    "y3": 756,
    "y5": 1260,
    "y10": 2520,
}


@dataclass(frozen=True)
class SymbolScope:
    symbol: SymbolConfig
    profile_scope: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit historical data depth for configured commodity symbols"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "config" / "monitor.toml",
        help="Primary monitor config",
    )
    parser.add_argument(
        "--extended-symbols",
        type=Path,
        default=ROOT / "config" / "symbols_extended.toml",
        help="Extended symbol config",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "reports" / "history_window_audit.csv",
        help="Detailed per-symbol CSV output",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=ROOT / "reports" / "history_window_summary.csv",
        help="Grouped summary CSV output",
    )
    parser.add_argument(
        "--plan-output",
        type=Path,
        default=ROOT / "reports" / "history_window_rollout_plan.md",
        help="Human-readable rollout plan in Markdown",
    )
    parser.add_argument(
        "--policy-output",
        type=Path,
        default=ROOT / "reports" / "history_window_policy.csv",
        help="Machine-readable per-symbol window policy CSV",
    )
    return parser.parse_args()


def _load_scopes(cfg: MonitorConfig, extended_path: Path) -> list[SymbolScope]:
    core_symbols = [item for item in cfg.symbols if item.enabled]
    extended_symbols = [item for item in load_symbols(extended_path) if item.enabled]

    scopes: dict[tuple[str, str], SymbolScope] = {}
    for item in core_symbols:
        scopes[(item.market, item.code)] = SymbolScope(symbol=item, profile_scope="core")
    for item in extended_symbols:
        key = (item.market, item.code)
        if key in scopes:
            scopes[key] = SymbolScope(symbol=item, profile_scope="core+extended")
            continue
        scopes[key] = SymbolScope(symbol=item, profile_scope="extended")
    return list(scopes.values())


def _support_flags(rows: int) -> dict[str, bool]:
    return {
        f"supports_{label}": rows >= days for label, days in TRADING_DAY_WINDOWS.items()
    }


def _recommendation(rows: int, stale_days: int) -> str:
    if stale_days > 10:
        return "exclude_or_review_stale"
    if rows >= TRADING_DAY_WINDOWS["y10"]:
        return "use_10y"
    if rows >= TRADING_DAY_WINDOWS["y5"]:
        return "use_5y"
    if rows >= TRADING_DAY_WINDOWS["y3"]:
        return "use_listing_since_or_3y"
    return "use_listing_since_only"


def _bucket(rows: int, stale_days: int) -> str:
    if stale_days > 10:
        return "stale"
    if rows >= TRADING_DAY_WINDOWS["y10"]:
        return "10y_ready"
    if rows >= TRADING_DAY_WINDOWS["y5"]:
        return "5y_ready"
    if rows >= TRADING_DAY_WINDOWS["y3"]:
        return "3y_ready"
    return "under_3y"


def _write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _format_symbol_list(rows: list[dict[str, object]]) -> list[str]:
    if not rows:
        return ["- 无"]
    return [
        (
            f"- `{row['code']}` {row['name']} | {row['market']} | rows={row['rows']} | "
            f"first={row['first_date']} | last={row['last_date']}"
        )
        for row in rows
    ]


def _build_rollout_plan(as_of: str, detail_rows: list[dict[str, object]]) -> str:
    def select(profile_scope: str, recommendation: str) -> list[dict[str, object]]:
        return [
            row
            for row in detail_rows
            if row["profile_scope"] == profile_scope and row["recommended_window"] == recommendation
        ]

    def title_count(profile_scope: str, recommendation: str) -> int:
        return len(select(profile_scope, recommendation))

    lines: list[str] = [
        "# 历史窗口上线建议",
        "",
        f"- 审计日期: `{as_of}`",
        f"- 样本范围: `core={sum(1 for row in detail_rows if row['profile_scope'] == 'core')}` "
        f"`extended={sum(1 for row in detail_rows if row['profile_scope'] == 'extended')}`",
        "",
        "## 结论",
        "",
        f"- `core` 可直接上 `10y`: {title_count('core', 'use_10y')} 个",
        f"- `core` 可直接上 `5y`: {title_count('core', 'use_5y')} 个",
        f"- `core` 只能用上市以来或 `3y`: {title_count('core', 'use_listing_since_or_3y') + title_count('core', 'use_listing_since_only')} 个",
        f"- `core` 建议剔除/复核: {title_count('core', 'exclude_or_review_stale')} 个",
        f"- `extended` 可直接上 `10y`: {title_count('extended', 'use_10y')} 个",
        f"- `extended` 可直接上 `5y`: {title_count('extended', 'use_5y')} 个",
        f"- `extended` 只能用上市以来或 `3y`: {title_count('extended', 'use_listing_since_or_3y') + title_count('extended', 'use_listing_since_only')} 个",
        f"- `extended` 建议剔除/复核: {title_count('extended', 'exclude_or_review_stale')} 个",
        "",
        "## Core",
        "",
        "### 直接上 10 年",
        *_format_symbol_list(select("core", "use_10y")),
        "",
        "### 直接上 5 年",
        *_format_symbol_list(select("core", "use_5y")),
        "",
        "### 仅适合上市以来或 3 年",
        *_format_symbol_list(
            select("core", "use_listing_since_or_3y") + select("core", "use_listing_since_only")
        ),
        "",
        "### 建议剔除或复核",
        *_format_symbol_list(select("core", "exclude_or_review_stale")),
        "",
        "## Extended",
        "",
        "### 直接上 10 年",
        *_format_symbol_list(select("extended", "use_10y")),
        "",
        "### 直接上 5 年",
        *_format_symbol_list(select("extended", "use_5y")),
        "",
        "### 仅适合上市以来或 3 年",
        *_format_symbol_list(
            select("extended", "use_listing_since_or_3y")
            + select("extended", "use_listing_since_only")
        ),
        "",
        "### 建议剔除或复核",
        *_format_symbol_list(select("extended", "exclude_or_review_stale")),
        "",
        "## 上线建议",
        "",
        "- 第一阶段: 保持默认 `d21/d63/y1/y3`，先让运行逻辑稳定执行严格窗口校验。",
        "- 第二阶段: 仅对 `recommended_window=use_5y` 或 `use_10y` 的品种开放更长窗口。",
        "- 第三阶段: 对新品种单独展示“上市以来百分位”，不要混入统一 `5y/10y` 口径。",
        "- 停更或长期无新数据的品种，应先业务确认是否继续保留。",
    ]
    return "\n".join(lines) + "\n"


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _build_policy_rows(detail_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    policy_rows: list[dict[str, object]] = []
    for row in detail_rows:
        recommendation = str(row["recommended_window"])
        policy_rows.append(
            {
                "as_of": row["as_of"],
                "profile_scope": row["profile_scope"],
                "market": row["market"],
                "code": row["code"],
                "name": row["name"],
                "recommended_window": recommendation,
                "should_exclude": recommendation == "exclude_or_review_stale",
                "supports_y5": row["supports_y5"],
                "supports_y10": row["supports_y10"],
                "history_bucket": row["history_bucket"],
                "rows": row["rows"],
                "first_date": row["first_date"],
                "last_date": row["last_date"],
            }
        )
    policy_rows.sort(
        key=lambda item: (
            str(item["profile_scope"]),
            str(item["recommended_window"]),
            str(item["market"]),
            str(item["code"]),
        )
    )
    return policy_rows


def main() -> int:
    args = parse_args()
    cfg = load_config(args.config)
    scopes = _load_scopes(cfg, args.extended_symbols)
    as_of = date.today().isoformat()

    detail_rows: list[dict[str, object]] = []
    print(f"Auditing {len(scopes)} enabled symbols as of {as_of}")

    for index, scope in enumerate(scopes, start=1):
        symbol = scope.symbol
        history = fetch_history(symbol)
        rows = len(history)
        first_date = history.iloc[0]["date"].date()
        last_date = history.iloc[-1]["date"].date()
        stale_days = (date.today() - last_date).days

        detail_row: dict[str, object] = {
            "as_of": as_of,
            "profile_scope": scope.profile_scope,
            "market": symbol.market,
            "code": symbol.code,
            "name": symbol.name,
            "rows": rows,
            "first_date": first_date.isoformat(),
            "last_date": last_date.isoformat(),
            "stale_days": stale_days,
            "history_bucket": _bucket(rows, stale_days),
            "recommended_window": _recommendation(rows, stale_days),
        }
        detail_row.update(_support_flags(rows))
        detail_rows.append(detail_row)
        print(
            f"[{index}/{len(scopes)}] {symbol.market}/{symbol.code}"
            f" rows={rows} first={first_date} last={last_date}"
            f" bucket={detail_row['history_bucket']}"
        )

    fieldnames = [
        "as_of",
        "profile_scope",
        "market",
        "code",
        "name",
        "rows",
        "first_date",
        "last_date",
        "stale_days",
        "history_bucket",
        "recommended_window",
        "supports_d21",
        "supports_d63",
        "supports_y1",
        "supports_y3",
        "supports_y5",
        "supports_y10",
    ]
    detail_rows.sort(
        key=lambda item: (
            str(item["profile_scope"]),
            str(item["market"]),
            int(item["stale_days"]),
            -int(item["rows"]),
            str(item["code"]),
        )
    )
    _write_csv(args.output, detail_rows, fieldnames)

    grouped_counts: Counter[tuple[str, str, str]] = Counter()
    grouped_support: Counter[tuple[str, str, str]] = Counter()
    for row in detail_rows:
        group_keys = [
            ("all", str(row["profile_scope"]), str(row["market"])),
            (str(row["history_bucket"]), str(row["profile_scope"]), str(row["market"])),
            (str(row["recommended_window"]), str(row["profile_scope"]), str(row["market"])),
        ]
        for key in group_keys:
            grouped_counts[key] += 1
        for label in ("supports_y3", "supports_y5", "supports_y10"):
            if bool(row[label]):
                grouped_support[(label, str(row["profile_scope"]), str(row["market"]))] += 1

    summary_rows: list[dict[str, object]] = []
    for (metric, profile_scope, market), count in sorted(grouped_counts.items()):
        summary_rows.append(
            {
                "as_of": as_of,
                "metric": metric,
                "profile_scope": profile_scope,
                "market": market,
                "count": count,
            }
        )
    for (metric, profile_scope, market), count in sorted(grouped_support.items()):
        summary_rows.append(
            {
                "as_of": as_of,
                "metric": metric,
                "profile_scope": profile_scope,
                "market": market,
                "count": count,
            }
        )
    _write_csv(
        args.summary_output,
        summary_rows,
        ["as_of", "metric", "profile_scope", "market", "count"],
    )
    _write_text(args.plan_output, _build_rollout_plan(as_of, detail_rows))
    _write_csv(
        args.policy_output,
        _build_policy_rows(detail_rows),
        [
            "as_of",
            "profile_scope",
            "market",
            "code",
            "name",
            "recommended_window",
            "should_exclude",
            "supports_y5",
            "supports_y10",
            "history_bucket",
            "rows",
            "first_date",
            "last_date",
        ],
    )

    print(f"Wrote detail report to {args.output}")
    print(f"Wrote summary report to {args.summary_output}")
    print(f"Wrote rollout plan to {args.plan_output}")
    print(f"Wrote policy file to {args.policy_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
