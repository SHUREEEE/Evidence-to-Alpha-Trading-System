# Run Log - v0.2.1 Real-Data Preflight

## Authorization envelope

- Goal: continue the integrated trading-system build with the first real-data compatibility check and continuous Paper preparation.
- Allowed: read-only inspection of the supplied news service, factor repository, V3/V6.5 artifacts, and TDX daily files; changes and private GitHub publication only in this repository.
- Preserved: the factor-platform worktree was inspected read-only and its existing modified and untracked files were not changed.
- Forbidden or unavailable: news writes, broker calls, real-money orders, unsupported performance claims, and cloud changes without a supplied target.

## Loop stage record

1. DISCOVER: re-read the current integration boundaries and inspected the real V3, V6.5, TDX, and news-service coverage.
2. PRODUCT: retained the thin integration approach; continuous Paper remains the next product gate, not live execution.
3. ARCHITECTURE: found a causality defect where stale factor dates could select a pre-event paper fill.
4. ORCHESTRATE: separated the execution anchor from the factor weight date and added an explicit post-as-of fill gate.
5. DEVELOP: sparse wide panels now accept empty/NaN cells while still rejecting infinity and duplicates; T+1 comparisons and Paper OMS now anchor on integration as-of.
6. VERIFY: Python compilation, diff checks, and 15/15 automated tests pass. The stale-data regression produces BLOCKED, zero orders, and zero fills.
7. SEAL: `evidence/v0.2.1/real_data_preflight.json` records sanitized facts and SHA-256 hashes without local absolute paths or raw price rows.
8. CLEANUP/FINAL: continuous Paper and live remain blocked; the read-only artifact API is the only deployment surface.

## Verified data facts

- News: one event and two versions; the sample is synthetic and normal export fails closed.
- V3: effective weights run from 2014-04-01 to 2024-12-31 across 516 names; NVDA is present and TSM is absent.
- V6.5: 298,890 weight rows across 2,214 names from 2026-01-02 to 2026-07-17; NVDA and TSM are present.
- TDX: NVDA, TSM, and SPY daily files all end on 2026-07-17.
- Event as-of: the latest synthetic version is 2026-08-19T01:08:00Z, after all V6.5 and TDX coverage.
- Price basis: V6.5 uses raw close with returns above 35 percent masked; dividends and smaller corporate actions remain unadjusted.

## Decision

- Real integration: BLOCKED.
- Continuous Paper: BLOCKED.
- Live: BLOCKED.
- Reason: no non-synthetic event, no factor or price coverage through the event, no price strictly after as-of, unsafe corporate-action basis, and proxy-only borrow assumptions.
- Next action: refresh real news, factor weights, and corporate-action-safe prices through event T+1, then rerun the fail-closed integration.

## Local deployment verification

- `http://127.0.0.1:8080/health` returns `status=ok`, `version=0.2.1`, and `artifact_ready=true`.
- The latest read endpoint serves sealed synthetic research run `INT-21959353434E657B`.
- POST to the latest-run endpoint returns HTTP 405.
- The service exposes historical research artifacts only; it does not clear any real-data, continuous Paper, or live gate.
