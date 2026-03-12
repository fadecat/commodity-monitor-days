# 使用与运维手册（中文）

## 1. 项目目标

每天扫描大宗商品，计算最新价在历史窗口中的百分位，并根据阈值触发企业微信告警。

## 2. 目录说明

- `scripts/run_daily_monitor.py`: 主入口，支持 `core/extended` 与自动降级。
- `audit_history_windows.py`: 历史长度审计脚本，输出 5 年/10 年覆盖度结果。
- `config/monitor.toml`: 核心配置（阈值、窗口、延时、降级、精选池）。
- `config/symbols_extended.toml`: 扩展池配置（仅 `--profile extended` 生效）。
- `.github/workflows/daily-monitor.yml`: GitHub Actions 定时运行配置。
- `docs/HISTORY_WINDOW_ANALYSIS_CN.md`: 历史窗口可行性分析与落地建议。
- `reports/history_window_rollout_plan.md`: 基于最新审计结果生成的上线建议清单。

## 3. 上手流程

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts/run_daily_monitor.py --check-only --show-symbols
python scripts/run_daily_monitor.py --dry-run
python audit_history_windows.py
```

## 4. 运行模式

- `core`：默认模式，只扫精选池，稳定且快。
- `extended`：在 `core` 基础上加扩展池，覆盖更广。
- `--check-only`：只校验配置并打印执行计划，不抓行情不推送。

示例：

```powershell
python scripts/run_daily_monitor.py --profile extended --dry-run
python scripts/run_daily_monitor.py --profile extended --degrade-max-run-seconds 180 --dry-run
```

## 5. 配置说明（关键项）

- `[thresholds]`: `high_percentile` / `low_percentile` 告警阈值。
- `[windows]`: 百分位窗口，默认 `d21/d63/y1/y3/y5/y10`。
- 窗口长度不足时：该窗口结果返回 `None`，不会把不足额历史误算成长期窗口。
- `[scan]`: 抓取间隔与数据新鲜度控制。
- `[wechat]`: webhook 环境变量名与单条消息最大长度。
- `[degrade]`: 扩展池自动降级策略：
  - `enabled`: 是否启用。
  - `max_run_seconds`: 超时降级阈值。
  - `max_fail_ratio`: 失败率降级阈值。
  - `min_samples`: 启用失败率判断前的最小样本数。

## 6. 自动降级逻辑

仅在 `extended` 模式生效。

1. 先完整扫描 `core`，保证最小可用结果。
2. 扫描 `extra` 前检查阈值（运行时长/失败率）。
3. 触发阈值后停止扩展扫描，按 `core` 结果继续输出和推送。
4. 报告会显示 `extended(已降级为core)` 与降级原因。

## 7. GitHub Actions 配置

必须在仓库 Secrets 中设置：

- `WECHAT_WEBHOOK_URL`

默认定时低峰执行（北京时间 04:17）。  
建议日常跑 `core`，扩展池用于手动巡检或低峰时段。

## 8. 常见问题

- 没有推送：检查是否无告警、无当日数据、或 webhook 未配置。
- 告警过多：提高阈值或先用 `core`。
- 执行时间长：降低 `max_symbols` 或使用 `core`。
- 想评估 `y5` / `y10`：先跑 `python audit_history_windows.py`，不要直接改线上窗口。
