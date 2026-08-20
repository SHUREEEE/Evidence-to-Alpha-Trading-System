# 开源项目选型与三系统 MVP 建议

版本：v0.2.0

调研日期：2026-08-20

## 1. 执行结论

最终建议是“基于现有两个项目做薄集成”，不是直接引入第三套完整交易引擎，也不是重写多因子平台。

新项目负责把新闻证据转换为 point-in-time 事件 Alpha，并在 `multi-factor-alpha-platform` 的 V4 组合控制之前注入有限幅度的权重调整。多因子平台继续拥有因子、V4 风控、T+1 回测和归因；新闻系统继续拥有采集、事件聚类、证据、可信度、公司/行业影响和版本时间线。

完整链路为：

`新闻证据 -> 事件版本 -> 事件 Alpha -> 因子 + 事件预 V4 权重 -> V4 风控 -> T+1 回测/Paper OMS -> 归因反馈`

## 2. 现有两个项目的可复用性

### 2.1 multi-factor-alpha-platform

- 本轮直接检查提交：`9792ed27059b1179b39cca8fca2982fe22baf86e`。
- 最后提交时间：2026-06-21 23:50:03 +08:00。
- 许可证：MIT。
- 可直接复用：V3 权重契约、V4 组合构建器、换手惩罚、no-trade band、行业净敞口、T+1 向量回测、归因和发布门禁。
- 关键接口：`scripts/run_backtest.py`、`scripts/run_v4_pipeline.py`、`config/v4.yaml`。
- 生产输入：`results/pillar5_artifacts/v3_weights.parquet` 与 `v3_sector_map.csv`；价格面板要求 `adj_close`。
- 部署复杂度：中等。Python、pandas、pyarrow、cvxpy；大型二进制数据不在公共仓库中，需要本地恢复。
- 维护判断：项目本身是完整研究平台和 V4 工程候选，但公开状态明确为 live blocked。
- 硬门禁：`results/v4_launch_go_no_go.json` 指出真实 PB borrow feed 尚未就绪。

### 2.2 本地新闻系统 127.0.0.1:8765

- 可直接复用：事件列表、逐版本详情、时间线、claim/evidence、来源 URL、公司 ticker、行业影响、可靠性、新颖性、冲突和不确定性。
- 使用的只读端点：`GET /api/v1/events`、`GET /api/v1/events/{id}?version=N`、`GET /api/v1/events/{id}/timeline`。
- 部署复杂度：低。当前本机服务已运行，集成端不读取其 SQLite，也不调用 POST/管理写接口。
- 数据现状：只有 1 个合成事件、2 个版本，涉及 NVDA 和 TSM；不能支持经济有效性结论。
- 时间异常：服务的 `discovered_at` 和版本创建时间可能早于 `published_at`。适配器采用保守规则 `observed_at=max(相关 published_at, discovered_at, version.created_at)`。

## 3. 其他开源候选

| 项目 | 维护与许可证 | 部署复杂度 | 可复用能力 | 判断 |
|---|---|---|---|---|
| Microsoft Qlib | 活跃；MIT | 中高 | 数据集、工作流、记录器、组合分析 | 参考，不作为内核 |
| Zipline Reloaded | 活跃；Apache-2.0 | 中 | 交易日历、事件循环、绩效 | 可选回测适配器 |
| NautilusTrader | 高活跃；LGPL-3.0 | 高 | 确定性订单、成交和持仓 | 实盘评估阶段再看 |
| QuantConnect LEAN | 高活跃；Apache-2.0 | 高 | 多资产回测、Paper/Live、券商适配 | 功能过重，不引入 |
| vectorbt | 活跃；附 Commons Clause | 低到中 | 向量参数扫描、事件消融 | 许可证不适合作为基础依赖 |

这些候选的维护和许可证信息来自 2026-08-20 已记录的 GitHub、README、LICENSE 和 PyPI 调研。本轮 GitHub REST 公共 API 遭遇共享出口限流，未把失败查询当作新增证据。

## 4. 最简单可用 MVP

### 4.1 输入

- 新闻服务只读 API。
- 多因子 V3 权重 CSV/Parquet。
- V3 行业映射 CSV。
- `adj_close` 行情 CSV/Parquet。
- 带时区的研究截止时间。

### 4.2 处理

1. 按时间线逐版本读取新闻事件，保存证据 ID 和来源 URL。
2. 拒绝未来版本；对异常时间戳采用保守修正。
3. 显式门控 synthetic demo 数据，默认拒绝。
4. 把公司 ticker 映射到因子股票池并计算事件信号。
5. 生成因子基线、事件基线、因子加事件三路权重。
6. 事件 Overlay 保持净敞口不变，并受单票幅度和换手上限约束。
7. 写出多因子回测器可直接读取的 CSV，并可生成 V4 `v3_weights.parquet` 缓存。
8. 运行 V4 生产加载器、三路 T+1 回测和 Paper OMS。
9. 输出门禁、追溯、局限和 live launch 决策。

### 4.3 输出

- `integration_report.json` 和 `integration_audit.json`。
- `factor_baseline_weights.csv`、`event_only_weights.csv`、`fused_pre_v4_weights.csv`。
- `v4_input_cache/v3_weights.parquet` 和 `v3_sector_map.csv`。
- 三路多因子回测结果。
- `signals.json`、`visible_events.json`、`orders.json`、`fills.json`；兼容保留 `paper_orders.json`。
- 只读结果 API。

## 5. 已验证结果与边界

- 已验证：本地新闻服务导出 2 个事件版本，证据和来源 URL 可追溯。
- 已验证：NVDA/TSM 与兼容性因子股票池重叠率 100%。
- 已验证：预 V4 Overlay 净调整为 0，换手未超上限。
- 已验证：多因子 V4 生产加载器返回 `validation_state=PASS`，cvxpy 路径通过。
- 已验证：因子、事件、融合三路外部回测命令均返回 0。
- 已验证：Paper OMS 使用 T+1 研究成交，账本闭合到 0.01。
- 未验证：真实 V3 权重和价格大文件不在公共仓库或本机已发现目录中。
- 未验证：真实事件样本、样本外增量收益、容量和实盘成交质量。
- 决策：研究与模拟交易 MVP 可用；经济结论为 INCONCLUSIVE；实盘上线 BLOCKED。

## 6. 最终选择

选择“基于现有项目改造并新增薄集成层”。不 fork Qlib、LEAN、NautilusTrader 或 Zipline，不重写因子和新闻系统。这样部署最简单、边界最清楚，也最符合任务书要求的证据链和 Loop 门禁。
