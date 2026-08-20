# Evidence-to-Alpha Trading System 开发与部署文档

版本：v0.2.0

## 1. 架构

本项目是两个现有系统之间的薄集成层：

`News Claws API -> NewsAdapter -> immutable EventSnapshot -> EventSignal -> pre-V4 Weight Overlay -> multi-factor V4 -> T+1 backtest/Paper OMS -> read-only artifacts API`

事件信号在 V4 风控之前进入组合。V4 风控仍由多因子平台拥有，避免在本项目重复实现 turnover penalty、no-trade band、sector net cap 和优化器。

## 2. 代码模块

| 模块 | 路径 | 责任 |
|---|---|---|
| 新闻适配 | `src/evidence_alpha/news_adapter.py` | GET、逐版本转换、时间与 synthetic 门禁、证据导出 |
| 多因子适配 | `src/evidence_alpha/multifactor_adapter.py` | CSV/Parquet、宽/长表、行业映射、V4 cache |
| 集成编排 | `src/evidence_alpha/integration.py` | 股票池重叠、三路组合、预 V4 融合、外部验证、Paper OMS |
| 核心契约 | `contracts.py`、`models.py` | 事件、证据、价格、权重的类型与校验 |
| 信号 | `signals.py` | 门控、时间衰减、lineage |
| 研究管线 | `pipeline.py`、`study.py` | 独立事件研究和原始 MVP |
| 只读 API | `api.py` | artifact 服务、POST 405 |
| CLI | `cli.py` | demo、run、news-export、integrate、verify、serve |

## 3. 新闻 API 契约

使用端点：

- `GET /api/v1/events?limit=N&cursor=...`
- `GET /api/v1/events/{event_id}/timeline`
- `GET /api/v1/events/{event_id}?version=N`

响应 envelope 为 `request_id + data_version + data`。只接受 v1。每个 timeline version 单独请求详情，claim evidence 转换为内部 EvidenceRecord。

时间策略：

- `published_at` 为相关证据文章最早发布时间。
- `observed_at` 为相关发布时间、发现时间和版本创建时间的最大值。
- `asof=observed_at`。
- 所有时间必须带时区。

## 4. 多因子契约

### 4.1 权重

支持：

- 长表：`date,ticker,weight`。
- 宽表：`date,<ticker1>,<ticker2>...`。
- CSV 或 Parquet。

### 4.2 行情

支持：

- 长表：`date,ticker,adj_close`。
- 宽表：date index + ticker columns。
- CSV 或 Parquet。

### 4.3 V4 staging

写出：

- `v4_input_cache/v3_weights.parquet`
- `v4_input_cache/v3_sector_map.csv`

然后调用：

`python scripts/run_v4_pipeline.py --asof YYYY-MM-DD --config config/v4.yaml --output <dir> --inputs-prod --v3-cache-dir <cache>`

## 5. 融合算法

1. 将每个可见事件信号按 ticker 聚合。
2. `raw_delta = event_score * overlay_scale`。
3. 横截面去均值，使 delta 净和为 0。
4. 应用单票绝对上限。
5. 重新分配残差并保持净和为 0。
6. 若 gross delta 超过 turnover cap，整体缩放。
7. `fused_pre_v4 = factor_baseline + delta`。
8. 交给 V4 构建器处理行业、换手、no-trade band 和优化约束。

默认参数：overlay scale 0.02、单票 0.01、总调整换手 0.08、成本 5 bps。

## 6. CLI

### 6.1 安装

核心：`python -m pip install -e .`

Parquet/V4：`python -m pip install -e .[integrations]`

### 6.2 新闻导出

`python -m evidence_alpha news-export --news-base-url http://127.0.0.1:8765 --output-dir artifacts/news`

当前 demo 数据必须显式增加 `--allow-synthetic`。

### 6.3 完整集成

`python -m evidence_alpha integrate --news-base-url http://127.0.0.1:8765 --factor-root <multi-factor-root> --asof <timezone-aware-timestamp> --output-dir artifacts/integrated --run-factor-v4 --run-factor-backtests`

公共 GitHub 仓库不包含大型 V3/price 二进制文件时，使用 `--weights`、`--sectors` 和 `--prices` 指定本地路径。

### 6.4 服务

`python -m evidence_alpha serve --artifact-dir artifacts/integrated --host 127.0.0.1 --port 8080`

## 7. 输出

| 文件 | 内容 |
|---|---|
| `integration_report.json` | 状态、决策、三路比较、门禁、外部验证、live block |
| `integration_audit.json` | 机器可读门禁 |
| `signals.json` | signal/event/evidence/config lineage |
| `orders.json` / `fills.json` | T+1 订单、成交、费用和证据链；兼容保留 `paper_orders.json` |
| 三路 weights CSV | 多因子回测输入 |
| `v4_input_cache` | V4 生产加载输入 |
| `factor_backtests` | 三路多因子回测输出 |
| `v4_output` | V4 cache 与运行清单 |

## 8. 测试

运行：`python -m unittest discover -s tests -v`

当前 12 项测试覆盖：

- observed time 早于 published time 的失败关闭。
- 未来事件版本不可见。
- 相同 event/version 内容冲突。
- synthetic 默认拒绝。
- 逐版本保守时间戳和 evidence lineage。
- 宽权重、长行情和重复行失败。
- 预 V4 零净敞口和换手。
- 三路集成、T+1 Paper OMS 和 live block。
- 原始 pipeline、portfolio 和 OMS 回归。

## 9. 本轮端到端证据

- News：`http://127.0.0.1:8765`，1 事件/2 版本，synthetic。
- Multi-factor commit：`9792ed27059b1179b39cca8fca2982fe22baf86e`。
- V4：`input_mode=prod`、`validation_state=PASS`、`solver_path_counts.cvxpy=1`。
- 三路回测：return code 全部为 0。
- 集成门禁：11/11 通过。
- 研究决策：INCONCLUSIVE。
- Live launch：BLOCKED，`borrow_feed_present=false`。

合成两日夹具产生的年化、Sharpe 和换手数字没有统计意义，只证明接口和流程，不证明经济有效性。

## 10. 部署

### 10.1 本地

直接启动只读服务，artifact directory 指向已验证集成产物。服务不写入新闻系统或因子平台。

### 10.2 Docker

`docker compose up --build`

通过 compose 的 artifact directory 参数选择 `demo` 或 `integrated` 目录。容器只暴露 8080 和只读 HTTP API。

### 10.3 外部环境

外部上线仍需要目标主机/云账号、DNS、TLS、镜像仓库、日志、备份、回滚负责人和网络策略。当前未提供这些资源，因此本轮完成本地部署，不声称互联网生产上线。

## 11. 安全和发布门禁

- 新闻端仅 GET；未知 data version 失败。
- 无 broker/PB 凭据读取。
- 无真实订单端点。
- synthetic 不得 PROMOTE。
- PB borrow feed 缺失时 live BLOCKED。
- 真实 V3 数据、OOS、容量和独立验证完成前不得使用“有效实盘系统”表述。
- Git push、远程合并、云发布和实盘权限仍需单独授权与目标信息。
