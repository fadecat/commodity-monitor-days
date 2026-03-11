from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DelayConfig:
    min_seconds: float
    max_seconds: float


@dataclass(frozen=True)
class ThresholdConfig:
    high_percentile: float
    low_percentile: float


@dataclass(frozen=True)
class WeChatConfig:
    webhook_env: str
    max_message_chars: int
    send_when_no_alert: bool


@dataclass(frozen=True)
class DegradeConfig:
    enabled: bool
    max_run_seconds: int
    max_fail_ratio: float
    min_samples: int


@dataclass(frozen=True)
class SymbolConfig:
    code: str
    name: str
    market: str
    enabled: bool = True


@dataclass(frozen=True)
class MonitorConfig:
    delay: DelayConfig
    thresholds: ThresholdConfig
    windows: dict[str, int]
    wechat: WeChatConfig
    degrade: DegradeConfig
    symbols: list[SymbolConfig]
    max_stale_days: int
    skip_if_no_today_data: bool


def _required_dict(raw: dict[str, Any], key: str) -> dict[str, Any]:
    value = raw.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"Missing or invalid config section: {key}")
    return value


def _load_raw_config(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    text = path.read_text(encoding="utf-8")

    if suffix == ".toml":
        data = tomllib.loads(text)
    elif suffix in {".yaml", ".yml"}:
        try:
            import yaml
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "PyYAML not installed. Use TOML config or install PyYAML."
            ) from exc
        data = yaml.safe_load(text) or {}
    elif suffix == ".json":
        data = json.loads(text)
    else:
        raise ValueError(f"Unsupported config extension: {suffix}")

    if not isinstance(data, dict):
        raise ValueError("Config root must be a mapping")
    return data


def _parse_symbols(raw_symbols: Any) -> list[SymbolConfig]:
    if not isinstance(raw_symbols, list):
        raise ValueError("symbols must be a list")

    symbols: list[SymbolConfig] = []
    for item in raw_symbols:
        if not isinstance(item, dict):
            continue
        symbols.append(
            SymbolConfig(
                code=str(item["code"]).strip().upper(),
                name=str(item.get("name", item["code"])).strip(),
                market=str(item.get("market", "domestic")).strip().lower(),
                enabled=bool(item.get("enabled", True)),
            )
        )
    return symbols


def load_symbols(path: Path) -> list[SymbolConfig]:
    content = _load_raw_config(path)
    symbols = _parse_symbols(content.get("symbols", []))
    if not symbols:
        raise ValueError(f"No valid symbols in {path}")
    return symbols


def with_extra_symbols(cfg: MonitorConfig, extra_symbols: list[SymbolConfig]) -> MonitorConfig:
    seen: set[tuple[str, str]] = set()
    merged: list[SymbolConfig] = []

    for item in [*cfg.symbols, *extra_symbols]:
        key = (item.market, item.code)
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)

    return replace(cfg, symbols=merged)


def load_config(path: Path) -> MonitorConfig:
    content = _load_raw_config(path)

    scan = _required_dict(content, "scan")
    thresholds = _required_dict(content, "thresholds")
    windows = _required_dict(content, "windows")
    wechat = _required_dict(content, "wechat")
    degrade = content.get("degrade", {})
    if degrade is None:
        degrade = {}
    if not isinstance(degrade, dict):
        raise ValueError("degrade section must be a mapping")

    delay = DelayConfig(
        min_seconds=float(scan.get("delay_min_seconds", 2.0)),
        max_seconds=float(scan.get("delay_max_seconds", 4.0)),
    )
    if delay.min_seconds < 0 or delay.max_seconds < delay.min_seconds:
        raise ValueError("Invalid delay range in scan section")

    threshold_cfg = ThresholdConfig(
        high_percentile=float(thresholds.get("high_percentile", 85)),
        low_percentile=float(thresholds.get("low_percentile", 30)),
    )
    if not (0 <= threshold_cfg.low_percentile <= 100):
        raise ValueError("low_percentile must be in [0, 100]")
    if not (0 <= threshold_cfg.high_percentile <= 100):
        raise ValueError("high_percentile must be in [0, 100]")
    if threshold_cfg.low_percentile >= threshold_cfg.high_percentile:
        raise ValueError("low_percentile must be smaller than high_percentile")

    normalized_windows = {
        str(name): int(days)
        for name, days in windows.items()
        if isinstance(name, str) and int(days) > 0
    }
    if not normalized_windows:
        raise ValueError("windows section cannot be empty")

    wechat_cfg = WeChatConfig(
        webhook_env=str(wechat.get("webhook_env", "WECHAT_WEBHOOK_URL")),
        max_message_chars=int(wechat.get("max_message_chars", 3300)),
        send_when_no_alert=bool(wechat.get("send_when_no_alert", False)),
    )
    degrade_cfg = DegradeConfig(
        enabled=bool(degrade.get("enabled", True)),
        max_run_seconds=int(degrade.get("max_run_seconds", 240)),
        max_fail_ratio=float(degrade.get("max_fail_ratio", 0.25)),
        min_samples=int(degrade.get("min_samples", 20)),
    )
    if degrade_cfg.max_run_seconds <= 0:
        raise ValueError("degrade.max_run_seconds must be > 0")
    if not (0 < degrade_cfg.max_fail_ratio <= 1):
        raise ValueError("degrade.max_fail_ratio must be in (0, 1]")
    if degrade_cfg.min_samples <= 0:
        raise ValueError("degrade.min_samples must be > 0")

    symbols = _parse_symbols(content.get("symbols", []))
    if not symbols:
        raise ValueError("No valid symbols in config")

    return MonitorConfig(
        delay=delay,
        thresholds=threshold_cfg,
        windows=normalized_windows,
        wechat=wechat_cfg,
        degrade=degrade_cfg,
        symbols=symbols,
        max_stale_days=int(scan.get("max_stale_days", 10)),
        skip_if_no_today_data=bool(scan.get("skip_if_no_today_data", True)),
    )
