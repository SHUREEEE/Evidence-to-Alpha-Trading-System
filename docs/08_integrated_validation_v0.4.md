# v0.4 三系统集成验证

版本：v0.4.0

日期：2026-08-21

状态：集成机制与本地只读研究服务通过验证；经济结论 INCONCLUSIVE；Live BLOCKED

## 1. 本轮目标

把新闻证据服务、Evidence-to-Alpha 和 multi-factor-alpha-platform 串成可重复研究链，并把独立验证接入真实的 `integrate` 路径。集成仍是薄编排层，不复制新闻前端、因子库、V4 风控或券商执行能力。

## 2. 集成链路

`只读新闻证据 -> point-in-time 事件版本 -> 事件信号 -> 因子基线/事件覆盖/融合三路权重 -> V4 组合控制 -> T+1 回测与 Paper OMS -> 事件研究 -> 独立验证 -> 只读 API`

- 新闻端只使用 GET，并逐版本保存 claim、evidence、source URL 和时间线。
- 事件调整在 V4 前注入；换手、单票限制、净敞口和 V4 仍由多因子平台负责。
- 订单和成交只使用确定性的 T+1 adjusted-close Paper 模型，没有券商写入路径。
- 独立验证消费已生成的事件研究与五个场景，不在验证阶段调参。

## 3. 机器验证结果

- 集成 run ID：`INT-3294801BE2C27699`；状态：`READY_FOR_PAPER_RESEARCH`。
- 标准审计 13/13 集成硬门禁通过，`hard_failures=[]`。
- multi-factor V4 production loader 和三个外部回测全部通过。
- 事件研究有 8 行，覆盖 NVDA/TSM 的 1/3/5/20 交易日窗口。
- baseline、overlay、placebo、one-day delay、double cost 五个场景均为有限数值。
- 标准 `verify` 命令返回 0 个硬失败；22/22 自动化测试通过，`ResourceWarning` 按错误处理后仍为零。

## 4. 独立验证结论

结论必须保持 `INCONCLUSIVE`，不能提升为 PROMOTE：

- 新闻 manifest 明确为 synthetic，保守分类覆盖任何 real 声明。
- 当前只有 1 个可见事件，5 日主窗口没有可用样本，IS/OOS 和滚动折叠因此不足。
- overlay 收益高于 baseline、placebo 和 one-day delay，但 doubled-cost 收益低于 baseline。
- 真实权重与价格相对 2026 年 8 月事件仍过期。
- 公司行动、幸存者偏差、容量、真实 borrow 和市场冲击尚未解决。

这些结果证明接口、时间契约、失败关闭和复现机制有效，不证明经济 Alpha。

## 5. 文档与服务验证

- 三份 Word 文档通过 ZIP、表格几何、标题层级和无障碍检查。
- Word 隐藏导出与 Poppler 生成 15 页 PNG；4 页选型、5 页 PRD、6 页开发文档已逐页检查，无裁切、重叠、缺字、破表或页眉页脚错位。
- 当前环境未安装 LibreOffice；已使用文档技能允许的 Word/Poppler 路径完成视觉验收。
- 本地只读服务运行在 `http://127.0.0.1:8080`，版本 0.4.0。
- health、report、event-study、independent-validation 均返回 200；POST 返回 405；未知路由返回 404。

## 6. 发布边界

本轮“部署上线”仅指经授权的本机只读研究/Paper artifact 服务和私有 GitHub 发布。没有云环境、DNS/TLS、券商连接、真实订单写入或实盘授权。Live 必须保持 `BLOCKED`。

下一门禁是接入非合成新闻、更新到事件 T+1 的真实权重和公司行动安全价格，积累至少 30 个主窗口事件和 10 个 OOS 事件，并原样通过滚动、placebo、延迟和成本翻倍门禁；之后仍需真实 PB borrow、连续 Paper、独立风险验证和明确发布授权。
