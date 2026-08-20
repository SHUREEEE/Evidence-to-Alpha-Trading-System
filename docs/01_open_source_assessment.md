# 开源项目选型与 MVP 建议

调研日期：2026-08-20

## 结论

**决策：自己开发一个薄集成项目，不直接使用或 fork 完整交易引擎。**

原因是本项目的核心差异不在通用回测速度，而在 point-in-time 证据链、事件版本不可覆盖、事件与因子信号叠加、交易到证据的逐笔追溯，以及 PROMOTE / REJECT / INCONCLUSIVE 的研究门禁。现有项目可以复用设计、日历、绩效分析或后续执行适配能力，但直接采用会重复现有多因子平台并显著增加部署与迁移成本。

## 候选项目

| 项目 | 维护状态与许可证 | 部署复杂度 | 可复用能力 | 结论 |
|---|---|---|---|---|
| Microsoft Qlib | 活跃；MIT；2026-07-23 有代码推送；PyPI 0.9.7 | 中高；依赖较多，数据准备和模型环境复杂 | 工作流、数据集抽象、记录器、组合分析 | 不 fork；可参考实验记录与分析接口 |
| Zipline Reloaded | 活跃维护；Apache-2.0；2026-01-06 有代码推送；PyPI 3.1.1 | 中；pip/conda 可装，但数据 bundle 与交易日历有门槛 | 交易日历、事件循环、绩效跟踪 | 后续可作为可选回测适配器，不作为 MVP 内核 |
| NautilusTrader | 高活跃；LGPL-3.0；2026-08-20 有代码推送；PyPI 1.231.0 | 高；Rust 内核、Python 3.12+、执行模型复杂 | 确定性事件驱动、订单/成交/持仓模型 | 不适合当前 MVP；实盘阶段再评估 |
| QuantConnect LEAN | 高活跃；Apache-2.0；2026-08-19 有代码推送；CLI 1.0.228 | 高；Docker、.NET 10、LEAN CLI、数据约定 | 多资产回测、Paper/Live 执行、券商适配 | 功能最全但过重，不建议二次开发本项目 |
| vectorbt | 活跃；2026-08-02 有代码推送；Commons Clause 附加限制 | 低到中；pip/Docker 简单 | 向量化参数扫描、事件消融 | 许可证不是标准宽松开源，不作为基础依赖 |

## 最简单 MVP

输入：事件版本 JSON、证据 JSON、实体映射 CSV、行情 CSV、因子基线权重 CSV。

处理：as-of 版本选择、实体映射、置信度/新颖性/冲突门控、1/3/5/20 日事件研究、因子权重叠加、T+1 纸面成交、成本与持仓闭合、泄漏和压力测试。

输出：研究报告 JSON、事件研究 CSV、信号/订单/成交追溯文件、SQLite 账本、只读 HTTP API。

第一版不做新闻前端、不接券商、不使用真实凭据、不训练复杂 ML 模型、不把样例结果称为实盘有效。

## 证据来源

- https://github.com/microsoft/qlib
- https://github.com/stefan-jansen/zipline-reloaded
- https://github.com/nautechsystems/nautilus_trader
- https://github.com/QuantConnect/Lean
- https://github.com/polakowo/vectorbt
- 对应项目 README、LICENSE、GitHub 公共仓库元数据与 PyPI 元数据，访问日期均为 2026-08-20。

