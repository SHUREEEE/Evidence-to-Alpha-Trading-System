# Project State

- Project: Evidence-to-Alpha Trading System
- Release candidate: v0.2.0
- Current phase: 08 Seal and local operations
- Task state: verified for research and Paper use
- Owner: Maker implementation complete; automated evidence sealed; independent production acceptance pending
- Scope: read-only news export, immutable event lineage, pre-V4 event overlay, multi-factor V4 handoff, three-path backtest verification, T+1 Paper OMS, attribution artifacts, read-only API
- Non-scope: news mutation, broker connectivity, live credentials, real-money execution, cloud account provisioning, economic-performance claims
- Decision: extend the thin integration service around the existing factor platform; do not fork a full trading engine
- Evidence: `evidence/v0.2.0/`
- Private remote target: `SHUREEEE/Evidence-to-Alpha-Trading-System`
- Next gate: real V3/prices and event history, rolling OOS and robustness evidence, real PB borrow feed, continuous Paper observation, independent risk validation, broker security design, and explicit live-release authorization

## Current release facts

- Verified fact: 13 automated tests pass and Python compile checks pass.
- Verified fact: integration run `INT-21959353434E657B` passed 11/11 machine gates with no hard failures.
- Verified fact: the multi-factor V4 production loader returned `validation_state=PASS` through one cvxpy path; all three external backtests returned code 0.
- Verified fact: one T+1 Paper order and one linked fill reconcile to the cent.
- Verified fact: the local read-only service responds on `http://127.0.0.1:8080`; write methods are rejected.
- Verified fact: all three Word deliverables passed structural, accessibility, table-geometry, and rendered-page visual checks.
- Verified fact: Docker configuration is present, but Docker CLI is not installed in the current environment, so the image was not built here.
- Inference: the adapters and contracts are compatible with real artifacts that satisfy the documented schemas.
- Decision: status is `READY_FOR_PAPER_RESEARCH`; research decision is `INCONCLUSIVE`; live launch is `BLOCKED`.
- Unknown: performance and robustness on sufficiently long real event, price, liquidity, and borrow datasets.
- Unknown: independent production Verifier acceptance, cloud environment, DNS/TLS, broker design, and live authorization remain absent.
