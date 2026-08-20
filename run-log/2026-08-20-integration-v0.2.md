# Run Log - v0.2.0 Integration

## Authorization envelope

- Goal: integrate Evidence-to-Alpha with the supplied multi-factor repository and local news service, produce final Word documentation, deploy locally, and publish the project to a private GitHub repository.
- Allowed: local reads and writes in this project, public/private GitHub reads, read-only news GET calls, local Paper deployment, private repository creation, Git commit/push, pull-request merge, and release tag.
- Forbidden or unavailable: news POST calls, broker credentials, real-money orders, cloud deployment without a supplied host/account, DNS/TLS changes, and any representation that synthetic evidence proves tradable alpha.
- Authorized private target: `SHUREEEE/Evidence-to-Alpha-Trading-System`.

## Loop stage record

1. DISCOVER: separated the task-book requirements from the Loop governance instructions; inspected the news API and both existing factor-platform repositories.
2. PRODUCT: selected a thin integration and governance layer; no duplicate research front end and no broker path.
3. ARCHITECTURE: fixed the order as news evidence -> event Alpha -> factor plus event pre-V4 -> V4 controls -> T+1 backtest/Paper OMS -> attribution feedback.
4. ORCHESTRATE: implemented adapters, integration CLI, verification fixtures, documents, release evidence, and read-only serving.
5. DEVELOP: added immutable news-version export, CSV/Parquet factor adapters, bounded zero-sum overlay, V4/backtest execution, standard orders/fills, compatibility fallback, and Docker read-only defaults.
6. VERIFY: 13/13 tests, compile checks, 11/11 integration gates, three external backtests, V4 production-loader validation, Paper reconciliation, API smoke tests, DOCX structure/accessibility/table geometry, full-page rendering, and `git diff --check` passed.
7. SEAL: v0.2.0 evidence contains sanitized machine-readable facts; final documents and source are prepared for the authorized private GitHub repository, merged release, and tag.
8. CLEANUP/FINAL: temporary patch files and QA-only render copies are excluded or removed; local service remains available for user inspection.

## Evidence classes

- Fact: local news GET integration exported two immutable versions of one synthetic event without invoking a write endpoint.
- Fact: multi-factor commit `9792ed27059b1179b39cca8fca2982fe22baf86e` was inspected; the V4 production loader and three backtest processes returned success.
- Fact: integration run `INT-21959353434E657B` passed 11/11 gates and produced one linked order/fill pair with cent-level reconciliation.
- Fact: the public factor repository does not contain the large real V3 weights and processed-price artifacts required for economic evaluation.
- Inference: the integration boundary is compatible with real artifacts that satisfy the documented contracts.
- Unknown: real-data OOS performance, PB borrow availability, continuous Paper behavior, independent risk acceptance, and broker/cloud release design.
- Decision: research/Paper is ready; `PROMOTE` and live launch remain blocked.

## Release constraints

- The two-day synthetic factor fixture and synthetic news event prove interface and control-flow compatibility only.
- Annualized returns, Sharpe, and turnover from that fixture have no statistical or economic meaning.
- A GitHub merge or tag seals source history; it does not authorize cloud deployment or real-money trading.
