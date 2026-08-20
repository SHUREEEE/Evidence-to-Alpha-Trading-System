# v0.3 独立样本外与滚动验证

版本：v0.3.0

日期：2026-08-21

状态：机制已实现并通过合成数据验证；真实数据结论仍为 INCONCLUSIVE

## 1. 目标

本阶段补齐任务书要求的样本内/样本外、按时间滚动、placebo、延迟一天和成本翻倍验证。验证器不调参，只消费当前运行已经生成的事件研究和场景收益，并输出 PROMOTE、REJECT 或 INCONCLUSIVE。

## 2. 时间与分区规则

- 事件按 `observed_at`、event ID 和 version 稳定排序。
- 主窗口可配置为 1、3、5 或 20 日，默认 5 日。
- 尾部按 `oos_fraction` 划为 OOS；同一 event ref 不得跨分区。
- OOS 再按时间顺序拆成可配置滚动折叠；空折叠记为样本不足。
- 只有严格晚于事件观察日期的事件研究行可进入验证。

## 3. 失败关闭

以下情况直接 REJECT：

- 可见事件引用重复；
- 事件研究引用未知或缺失；
- 研究起始日不晚于事件观察日；
- 状态为 ok 的研究行含非法窗口、日期、布尔值、NaN 或 Infinity；
- IS/OOS 交叉；
- 基线、融合、延迟、placebo、成本翻倍场景缺失或不是有限数值。

以下情况输出 INCONCLUSIVE：

- 数据分类为 unknown 或 synthetic；
- 主窗口可用事件不足；
- OOS 事件不足；
- 滚动折叠不完整。

只有真实数据、样本覆盖、OOS 正收益、滚动稳定性，以及融合相对基线/placebo/延迟和成本翻倍相对基线全部通过，才允许 PROMOTE。

## 4. 产物与接口

- `independent_validation.json`：配置哈希、计数、IS/OOS event refs、窗口摘要、滚动折叠、场景收益、门禁、事实/推断/未知和决策。
- `report.json`：嵌入同一独立验证对象。
- `GET /api/v1/runs/latest/independent-validation`：只读返回独立验证产物。
- 所有 POST 仍返回 405。

## 5. 验证结果

- Python 编译检查通过。
- `git diff --check` 通过。
- 21/21 unittest 通过，ResourceWarning 按错误级别处理后仍通过。
- SQLite `PRAGMA integrity_check` 返回 ok。
- 演示 run ID：`RUN-25ECC87FAC46A1DE`。
- 演示结论：INCONCLUSIVE；hard failures 为 0。
- 演示覆盖：2 个主窗口事件、1 个 IS、1 个 OOS、3 个滚动折叠中仅 1 个非空。

## 6. 边界与下一门禁

当前新闻是 synthetic，真实 V3 只到 2024-12-31，V6.5 和 TDX 价格只到 2026-07-17，早于 2026 年 8 月事件。原始收盘价、幸存者偏差和 borrow proxy 风险也未解除。因此本阶段只证明验证机制和失败关闭行为，不证明经济有效性、容量或实盘成交质量。

下一步是刷新非合成事件、因子权重和公司行动安全价格至事件 T+1，并积累足够的真实事件样本后原样重跑本验证器。实盘仍需真实 PB borrow、连续 Paper、独立风险验证、券商安全设计和明确发布授权。
