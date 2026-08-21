# 2026-08-22 SEC Event Route

## Objective

Advance the real-data production route without treating the current synthetic
News_Claws service or stale market files as production inputs.

## Loop

- Constraint: no synthetic data, no guessed SEC identity, no broker or live
  credentials, and no merge/deploy while readiness is blocked.
- Maker: add a read-only SEC EDGAR event exporter and a sealed news-bundle
  loader.
- Verifier: run the isolated SEC contract tests and the complete suite.
- Gate: SEC export requires a real contact email in User-Agent; placeholder
  domains fail closed.
- Persist: record the route, current external facts, and next inputs here.

## Verified facts

- `http://127.0.0.1:8765` currently returns the synthetic demonstration event.
- SEC submissions and official filing URLs are reachable, but no authorized
  user email is present for a production SEC User-Agent.
- Local V6.5 OOS weights end on 2026-07-17.
- The inspected adjusted-price panel ends on 2024-12-31 and lacks corporate-
  action and delisting attestations.
- The new SEC exporter creates point-in-time events from acceptance timestamps,
  official filing URLs, explicit CIK/ticker mappings, deterministic document
  direction, and prior-30-day novelty.
- `--news-export-dir` loads an immutable bundle into the existing integration
  without bypassing event, robustness, factor, price, PB, or Paper gates.
- Full regression: 73 tests passed.

## Decision

`BLOCKED`: no production event bundle was generated without a real SEC contact
identity, and market/PB/Paper inputs remain incomplete. Existing v0.4 remains
the only deployed read-only service.

## Next action

Obtain a real SEC User-Agent email, a PIT factor-weight artifact, a licensed
corporate-action-safe price artifact through every event T+1, a real PB borrow
feed, and 20 continuous Paper sessions. Then export at least 31 causal SEC
(or equivalent licensed news) events, integrate, run readiness, and only after
all gates pass begin human release authorization.
