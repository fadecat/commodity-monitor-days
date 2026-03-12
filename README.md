# commodity-monitor-days

AKShare 大宗商品日频监控项目。  
核心输出是“当前价格在历史窗口中的百分位”，并按阈值推送企业微信告警。

## 文档入口

- 使用与运维手册（推荐先看）：`docs/USAGE_CN.md`
- 历史窗口可行性分析：`docs/HISTORY_WINDOW_ANALYSIS_CN.md`
- 历史窗口上线建议（自动生成）：`reports/history_window_rollout_plan.md`
- 历史窗口策略清单（自动生成）：`reports/history_window_policy.csv`
- 监控主配置：`config/monitor.toml`
- 扩展池配置：`config/symbols_extended.toml`
- 定时任务：`.github/workflows/daily-monitor.yml`

## 快速命令

```powershell
# 1) 安装
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2) 仅预检（不抓行情、不推送）
python scripts/run_daily_monitor.py --check-only --show-symbols

# 3) 本地干跑（默认 core 精选池）
python scripts/run_daily_monitor.py --dry-run

# 4) 扩展池干跑
python scripts/run_daily_monitor.py --profile extended --dry-run

# 5) 审计历史窗口覆盖度
python audit_history_windows.py
```

## 默认策略

- 默认 profile: `core`（精选池，优先效率和稳定性）
- 阈值: 高位 `>=85%`，低位 `<=30%`
- 窗口: `d21/d63/y1/y3/y5/y10`
- 窗口校验: 历史长度不足时，该窗口分位返回 `None`，不会冒充长期窗口
- 扩展池保护: `extended` 模式触发超时/失败率阈值时自动降级为 `core`

## Extended 降级参数

- 配置位置: `config/monitor.toml` 的 `[degrade]` 段
- 超时阈值: `max_run_seconds`
- 失败率阈值: `max_fail_ratio`
- 失败率判断最小样本: `min_samples`

示例：

```toml
[degrade]
enabled = true
max_run_seconds = 240
max_fail_ratio = 0.25
min_samples = 20
```

## GitHub Actions

- 定时: 北京时间 04:17（UTC 20:17，周一至周五）
- Secret: `WECHAT_WEBHOOK_URL`
