# Project State

- Project: Evidence-to-Alpha Trading System
- Release candidate: v0.3.0
- Current phase: 06 Verify - independent chronological validation
- Task state: v0.3 implementation and synthetic verification complete; real-data continuous Paper blocked
- Owner: Maker implementation complete; automated evidence sealed; independent production acceptance pending
- Scope: read-only news export, immutable event lineage, pre-V4 event overlay, multi-factor V4 handoff, three-path backtest verification, T+1 Paper OMS, chronological IS/OOS and rolling validation, attribution artifacts, read-only API
- Non-scope: news mutation, broker connectivity, live credentials, real-money execution, cloud account provisioning, economic-performance claims
- Decision: extend the thin integration service around the existing factor platform; do not fork a full trading engine
- Evidence: `evidence/v0.2.0/`, `evidence/v0.2.1/`, and `evidence/v0.3.0/`
- Private remote target: `SHUREEEE/Evidence-to-Alpha-Trading-System`
- Next gate: non-synthetic news plus factor weights and corporate-action-safe prices through event T+1, with enough events to pass the implemented rolling OOS and robustness gates; then real PB borrow, continuous Paper observation, independent risk validation, broker security design, and explicit live-release authorization

## Current release facts

- Verified fact: 21 automated tests pass with ResourceWarning promoted to an error.
- Verified fact: v0.3 writes `independent_validation.json` and exposes it through the read-only API.
- Verified fact: chronological IS/OOS partitions are disjoint; rolling folds, primary-window summaries, placebo, one-day delay, and doubled-cost gates are recorded.
- Verified fact: unknown/missing event refs, pre-observation rows, malformed successful rows, duplicate visible refs, and missing/non-finite scenarios fail closed as REJECT.
- Verified fact: synthetic or insufficient samples fail closed as INCONCLUSIVE and cannot produce PROMOTE.
- Verified fact: demo run `RUN-25ECC87FAC46A1DE` has 2 usable events, 1 OOS event, incomplete rolling folds, zero hard failures, and decision INCONCLUSIVE.
- Baseline fact: the v0.2.1 suite passed 15 tests after adding sparse-panel and stale-data causality regressions.
- Verified fact: Paper comparison and fill dates are anchored to integration as-of; no post-as-of price means `BLOCKED`, zero orders, and zero fills.
- Verified fact: V3 ends on 2024-12-31; V6.5 weights and NVDA/TSM/SPY TDX prices end on 2026-07-17.
- Verified fact: the current news event is synthetic with an August 2026 as-of, so no causally valid real integration can run.
- Verified fact: V6.5 documents raw-close corporate-action, survivorship, and borrow-proxy limitations.
- Decision: continuous Paper and live launch remain `BLOCKED` until the real-data preflight hard failures are cleared.
- Baseline fact: the sealed v0.2.0 integration passed 13 automated tests and its original compile checks.
- Verified fact: integration run `INT-21959353434E657B` passed 11/11 machine gates with no hard failures.
- Verified fact: the multi-factor V4 production loader returned `validation_state=PASS` through one cvxpy path; all three external backtests returned code 0.
- Verified fact: one T+1 Paper order and one linked fill reconcile to the cent.
- Verified fact: the local read-only service reports v0.3.0, serves the independent-validation endpoint, rejects POST with 405, and returns 404 for unknown routes.
- Verified fact: all three Word deliverables passed structural, accessibility, table-geometry, and rendered-page visual checks.
- Verified fact: Docker configuration is present, but Docker CLI is not installed in the current environment, so the image was not built here.
- Inference: the adapters and contracts are compatible with real artifacts that satisfy the documented schemas.
- Decision: status is `READY_FOR_PAPER_RESEARCH`; research decision is `INCONCLUSIVE`; live launch is `BLOCKED`.
- Unknown: performance and robustness on sufficiently long real event, price, liquidity, and borrow datasets; implemented gates do not replace those missing observations.
- Unknown: independent production Verifier acceptance, cloud environment, DNS/TLS, broker design, and live authorization remain absent.
