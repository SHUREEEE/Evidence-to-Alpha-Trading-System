# Evidence-to-Alpha Trading System 开发与部署文档

版本：v0.1.0 MVP

## 1. 架构决策

采用 Python 标准库实现薄集成服务，不 fork 完整交易引擎。原因是核心价值是证据和版本契约，而非重新实现通用量化平台。Zipline Reloaded 可作为后续可选回测适配器，NautilusTrader 或 LEAN 只在进入真实执行评估后再考虑。

## 2. 组件

- contracts：解析并验证事件、证据、映射、行情和因子权重。
- store：SQLite 事件版本和运行账本，阻止静默覆盖。
- signals：门控、衰减、配置哈希和逐条 lineage。
- study：1/3/5/20 日事件研究与相对基准收益。
- portfolio：基线、事件和 overlay 三条组合路径及约束。
- oms：T+1 订单、滑点、手续费、现金、持仓与闭合。
- validation：泄漏、证据、版本、压力和研究结论门禁。
- api：只读 HTTP 服务。
- cli：demo、run、verify、serve 四类操作入口。

## 3. 数据契约

事件唯一键为 event_id + event_version。published_at、observed_at、asof 必须是带时区 ISO-8601；published_at 不晚于 observed_at，observed_at 不晚于 asof。运行截止时间决定可见版本。

订单和成交记录 run_id、ticker、side、quantity、factor_version、signal_ids、event_refs、evidence_ids。没有事件调整的因子基线订单允许事件引用为空，但因子版本不可为空。

## 4. 核心流程

1. 读取并验证输入。
2. 将事件版本以不可变方式登记到 SQLite。
3. 按运行截止时间选择每个事件的最新可见版本。
4. 映射实体并生成带配置哈希的事件信号。
5. 计算事件研究和异常收益。
6. 生成因子基线、事件基线和 overlay 目标权重。
7. 在下一交易日生成纸面成交并进行账本闭合。
8. 运行自动验证，输出 PROMOTE / REJECT / INCONCLUSIVE。
9. 持久化 JSON、CSV、SQLite 和审计证据。

## 5. 运行与部署

本地演示：`python -m evidence_alpha demo --output-dir artifacts/demo`

测试：`python -m unittest discover -s tests -v`

服务：`python -m evidence_alpha serve --artifact-dir artifacts/demo --port 8080`

Docker：`docker compose up --build`

健康检查：`GET /health`

最新报告：`GET /api/v1/runs/latest`

## 6. 安全和发布

服务只有 GET 端点；不接受订单写入，不加载券商密钥。Docker 仅暴露 8080。真实环境部署必须另行确认镜像仓库、主机、DNS、TLS、凭据、日志和回滚负责人。

## 7. 测试策略

单元测试覆盖时间契约、版本选择、不可变存储、信号追溯、组合限制、T+1、账本闭合和端到端产物。发布前还要运行源码编译、自动 verifier、API 冒烟和文档渲染检查。

## 8. Loop 交付记录

项目使用 STATE.md、run-log 和 evidence/release-id。最后一次文件编辑后只执行 VERIFY、SEAL、CLEANUP、FINAL。自动测试属于近端验证证据，不替代独立 Verifier 和生产发布负责人批准。

