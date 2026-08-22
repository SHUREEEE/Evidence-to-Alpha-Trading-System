# Run Log - v0.5.0 Real-Data Readiness Preflight

## Authorization envelope

- Goal: connect non-synthetic news, require T+1 real factors and
  corporate-action-safe prices, accumulate 30 primary and 10 OOS events, pass
  robustness, PB, and 20-session Paper gates, then merge and deploy.
- Allowed: changes in this repository, read-only inspection of News_Claws and
  the factor platform, isolated local copies, private GitHub inspection, and
  GitHub publication or local deployment only after their separate gates pass.
- Preserved: the original News_Claws database and both external repositories
  were not modified.
- Forbidden or unavailable: news writes, broker calls, credentials, real-money
  orders, cloud infrastructure changes, and unsupported Live claims.

## Loop stage record

1. DISCOVER: inspected the v0.5 branch, current News_Claws contract, isolated
   database, real export, local factor workspace, and prior V6.5 evidence.
2. PRODUCT: retained the thin governance and integration service. Readiness is
   distinct from research promotion and Live authorization.
3. ARCHITECTURE: fixed 30 primary events, 10 OOS events, three rolling folds,
   all robustness gates, real PB evidence, and 20 Paper sessions as minimums.
4. ORCHESTRATE: separated external data acquisition from locally verifiable
   code, contracts, tests, and sealed evidence.
5. DEVELOP: added current News_Claws compatibility, token-by-environment,
   conservative timestamp conversion, mapping quarantine, caller-label
   downgrade, readiness CLI/API, artifact hashes, provenance, PB, and Paper
   checks, including verified PB source/mapping/canonical ingestion and a
   four-way PB canonical-file hash cross-check. Added an
   exact-event-version PIT news-enrichment contract with external provenance,
   effective dates, availability timestamps, and fail-closed partial state.
   Readiness now reloads CSV/Parquet factor and price files, derives coverage,
   and rejects declarations that do not match the file contents or substitute
   raw close for an explicit adjusted-price field. A deterministic
   `inspect-panel` CLI now double-fingerprints candidate inputs, rejects unsafe
   logical paths and input overwrite, and preserves unverified provenance/PIT
   and corporate-action limitations. Added an `audit-news-overlap` CLI that
   reads all non-demo reports through SQLite `mode=ro` plus verified
   `query_only`, checks required columns and `quick_check`, rejects pending WAL,
   fingerprints the snapshot before and after, applies conservative observation
   timestamps and exact OOS rounding, and emits aggregate evidence without raw
   news fields or absolute paths.
6. VERIFY CODE: 70/70 tests and 8 subtests passed with warnings as errors.
   Coverage includes strict integer versions, duplicate/unknown event
   references, placeholder and local-source rejection, PIT dates, partial
   enrichment, signal generation, event-scoped mapping, CSV round-trip,
   200-item no-cursor API paging, exact SQLite report versions, report cutoff
   enforcement, pending-WAL rejection, read-only input invariants, CLI wiring,
   enrichment/input-file tampering, false coverage declarations, raw-close
   substitution, total-return-index matching, and wide-table missing-cell
   handling, PB ingestion provenance, and source-file tampering. Python
   compilation, 128-file JSON parsing, twelve JSON Schema validations,
   credential scanning, and Git whitespace checks passed before sealing. Seven
   dedicated historical-overlap tests cover a valid 31-event cohort, the
   30-event OOS failure, late observation rejection, pending WAL, input change,
   machine-readable CLI output, raw-news non-disclosure, and database overwrite
   refusal.
7. VERIFY DATA: News_Claws uses SQLite WAL mode, so a direct main-file copy was
   rejected as incomplete. A SQLite online backup produced consistent snapshot
   SHA-256 81D179EB... with integrity_check=ok and the same logical counts as
   the source: 254 non-demo events, 260 reports, zero company impacts, 48
   industry impacts, and zero report-level novelty fields. Of 254 events, 110
   have at least one article published_at. An isolated API over the same
   snapshot exported 200 current events and 206 evidence records. A read-only
   SQLite run requested those 200 exact versions, enriched 56 publication
   times, and retained 144 unresolved versions. All 200 remain degraded because
   novelty or investable mapping is absent. The original snapshot hash was
   unchanged and the isolated 8016 service was stopped. A direct market-input
   audit found V6.5 weights through 2026-07-17, explicit adjusted prices through
   2024-12-31, and only raw-close TDX spot checks through 2026-07-17. All 200
   current real events occur later. GitHub has no usable Release or Actions
   artifact to close the gap. The all-report historical audit independently
   examined 254 non-demo events and 260 report versions. Every conservative
   observation timestamp is in 2026. Six report versions have publication dates
   inside the historical market window, but all six were observed too late;
   causal overlap is zero. Under the fixed 30% split, 31 total events are needed
   to satisfy both 30 primary and 10 OOS gates.
8. VERIFY READINESS: the policy returned exit code 1, decision BLOCKED, 23 hard
   failures, zero usable primary events, zero OOS events, and zero verified
   Paper sessions.
9. VERIFY RUNTIME: 127.0.0.1:8080 remains v0.4.0, health is ok, and POST is
   rejected with 405. The isolated 8016 service was stopped.
10. SEAL: sanitized news inventory, market-input audit, historical news overlap
    audit, readiness output, hashes, schemas, examples, documentation, and this
    log are retained in the v0.5 preflight branch.
11. RELEASE: merge, tag, and v0.4 replacement are blocked until one consistent
    real-data run passes every v0.5 gate.

## Current decision

- Readiness mechanism: PASS.
- PIT news enrichment mechanism: PASS; real publication-time artifact is
  partial (56 enriched, 144 unresolved) and lacks novelty/ticker mappings.
- News contract completeness: BLOCKED.
- Statistical sample and OOS validation: BLOCKED.
- T+1 PIT factor and corporate-action-safe prices: BLOCKED.
- PB borrow and launch evidence: BLOCKED.
- Continuous Paper: BLOCKED.
- Live authorization: NOT GRANTED.

## Next inputs

1. A production enrichment artifact with stable novelty, verified
   point-in-time company/ticker mappings, exact event versions, external
   sources, and availability-time provenance.
2. PIT weights and adjusted or total-return prices through each event return
   endpoint.
3. A real security-level PB borrow feed and matching validation artifacts.
4. Twenty gap-free Paper sessions with hashes, freshness, and reconciliation.
5. Independent risk acceptance after the policy reaches authorization review.
