# Evidence-to-Alpha Trading System 产品需求文档

版本：v0.2.0

状态：研究与 Paper MVP 已实现；真实数据和实盘门禁未解除

## 1. 产品目标

系统在严格使用当时可得新闻证据的条件下，把新闻事件转换为可回测事件 Alpha，并与现有多因子组合融合，形成可复现的研究、风险控制、T+1 回测、Paper OMS 和归因反馈闭环。

产品不以单次高 Sharpe 为目标。核心研究问题是：事件信号在扣除成本并通过泄漏、样本外和独立验证后，是否给因子基线带来稳定增量信息。

允许三种研究决策：PROMOTE、REJECT、INCONCLUSIVE。

## 2. 用户和场景

- 量化研究员：选择 as-of 时间，运行三路比较和事件研究。
- 组合研究员：查看预 V4 事件调整、换手和股票池重叠。
- 风险/验证人员：核对 point-in-time、证据、V4、T+1 和账本门禁。
- 研究负责人：从 Paper 订单追溯到 signal、event version、evidence 和 source URL。
- 运维人员：启动只读结果服务，检查健康和最新报告。

## 3. 系统边界

| 系统 | 所有权 | 本项目交互 |
|---|---|---|
| 新闻系统 | 采集、事件、证据、可靠性、影响分析 | 只读 HTTP GET，逐版本导出 |
| Evidence-to-Alpha | 事件契约、信号、融合、追溯、Paper OMS、门禁 | 本项目核心 |
| 多因子平台 | 因子、V3 权重、V4 风控、T+1 回测、归因 | 文件契约和可选子进程验证 |
| 券商/PB | borrow、真实订单和成交 | MVP 不连接，保持阻断 |

## 4. 功能需求

### FR-001 新闻只读接入

系统必须只调用已批准的 GET 端点，不得修改新闻源、事件、审核、告警或数据库。

### FR-002 逐版本导出

系统必须读取时间线中的每个 event version，并通过 `?version=N` 获取对应 claims、evidence 和 impacts；不得用当前版本覆盖历史版本。

### FR-003 时间契约

`published_at`、`observed_at`、`asof` 必须带时区且满足 `published_at <= observed_at <= asof`。时间异常采用保守最大值，不得提前事件可见性。

### FR-004 合成数据门禁

发现 `synthetic_demo` 或 synthetic license 时默认失败。只有显式参数可以进入研究，且该运行不得输出 PROMOTE。

### FR-005 证据追溯

每条事件信号必须包含 event ID、version、evidence ID、source URL 和信号配置哈希。证据缺失或跨版本内容冲突时失败关闭。

### FR-006 多因子输入

支持长表或宽表 CSV/Parquet 权重；支持长表或宽表 `adj_close` 行情；支持 `symbol/ticker + sector` 行业映射。

### FR-007 as-of 和股票池

只能使用不晚于研究截止时间的最新权重日期。事件 ticker 与因子股票池重叠率低于配置门槛时失败。

### FR-008 事件信号

方向、可靠性、新颖性、冲突、影响倍数和时间衰减共同决定信号。映射失败必须披露。

### FR-009 三路组合

独立输出因子基线、事件基线和因子加事件组合。不得只报告融合结果。

### FR-010 预 V4 融合

事件调整必须在多因子 V4 控制之前注入。调整必须保持因子组合净敞口不变，受单票调整和总换手限制。

### FR-011 V4 交接

输出 `v3_weights.parquet` 与 `v3_sector_map.csv`，可由 `run_v4_pipeline.py --inputs-prod --v3-cache-dir` 直接读取。

### FR-012 外部回测

三路权重必须可由 `scripts/run_backtest.py` 读取并完成 T+1 回测。输出命令、return code 和 metrics 路径。

### FR-013 Paper OMS

从基线到融合目标生成 T+1 研究订单，记录 side、quantity、fill price、fee、signal IDs、event refs 和 evidence IDs，并完成会计恒等式闭合。

### FR-014 研究门禁

必须检查 point-in-time、lineage、股票池重叠、零净敞口、换手、价格覆盖、V4 加载、三路回测和 OMS 闭合。

### FR-015 研究决策

硬门禁失败为 REJECT；门禁通过但样本不足、synthetic 或 OOS 不足为 INCONCLUSIVE；只有真实样本和独立验证通过后才允许 PROMOTE。

### FR-016 只读服务

提供健康、最新报告、信号、订单/成交和事件研究端点。所有 POST 返回 405。

### FR-017 可复现产物

记录 run ID、输入路径/摘要、配置、外部命令、外部清单、门禁、局限和生成时间。

### FR-018 实盘阻断

没有 PB borrow feed、真实事件样本、OOS 稳定性、独立风险验证和发布授权时，live launch 必须为 BLOCKED。

## 5. 非功能需求

- 安全：无券商凭据、无真实订单写路径、新闻侧只读。
- 确定性：相同输入和配置产生相同 signal/order/run ID。
- 兼容性：核心使用标准库；Parquet/V4 功能作为 pandas/pyarrow 可选依赖。
- 可测试：单元测试覆盖失败关闭、时间异常、版本、融合和外部契约。
- 可审计：事实、推断、未知和决策分开；任何合成指标均带限制。
- 可运维：健康检查、Docker 配置、可配置 artifact directory。

## 6. 主要工作流

### 6.1 研究运行

1. 检查新闻服务和因子输入。
2. 导出事件所有版本。
3. 按 as-of 选择可见版本。
4. 生成信号和三路权重。
5. 生成 V4 缓存并运行 V4。
6. 运行三路 T+1 回测和 Paper OMS。
7. 输出报告和只读 API。

### 6.2 失败工作流

- synthetic 未授权：立即失败。
- 证据缺失或版本冲突：立即失败。
- 股票池无重叠：立即失败。
- Parquet 引擎缺失：保留 CSV，V4 staging 标记不可用；若请求 V4 则失败。
- PB feed 缺失：研究可继续，live launch 保持 BLOCKED。

## 7. 验收标准

1. 本地新闻系统真实 GET 联调成功，2 个版本均导出。
2. 未来版本不进入历史 as-of。
3. 合成数据默认被拒绝。
4. 每条事件订单可追溯到证据和来源 URL。
5. 预 V4 delta 净和为 0，换手不超 0.08。
6. 三路 CSV 被多因子回测器接受。
7. V4 生产加载器 `input_mode=prod` 且 `validation_state=PASS`。
8. Paper OMS 在 T+1 成交并闭合到 0.01。
9. 自动测试全绿，发布证据完整。
10. 当前 synthetic/夹具运行结论为 INCONCLUSIVE，live launch 为 BLOCKED。

## 8. MVP 后路线

- Phase 2：接入真实 V3 权重、价格和至少 100 个真实事件版本。
- Phase 3：滚动 OOS、placebo、延迟、成本翻倍和事件消融。
- Phase 4：将 V4 后权重和归因回写为只读研究结果。
- Phase 5：完成 PB borrow feed、独立风险验证和 Paper 运行期。
- Phase 6：单独审批券商连接和实盘发布。
