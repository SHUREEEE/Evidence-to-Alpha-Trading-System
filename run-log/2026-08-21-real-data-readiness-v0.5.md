# Run Log - v0.5.0 Real-Data Readiness Preflight

## Authorization envelope

- Goal: connect non-synthetic news, require T+1 real factors and
  corporate-action-safe prices, accumulate 30 primary and 10 OOS events, pass
  robustness, PB, and 20-session Paper gates, then merge and deploy.
- Allowed: changes in this repository, read-only inspection of News_Claws and
  the factor platform, isolated local copies, private GitHub publication, and
  local read-only deployment only after release gates pass.
- Preserved: the original News_Claws database and both external repositories
  were not modified.
- Forbidden or unavailable: news writes, broker calls, credentials, real-money
  orders, cloud infrastructure changes, and unsupported Live claims.

## Loop stage record

1. DISCOVER: inspected the v0.5 branch, current News_Claws contract, isolated
   database, real export, clean factor clone, and prior V6.5 evidence.
2. PRODUCT: retained the thin governance and integration service. Readiness is
   distinct from research promotion and Live authorization.
3. ARCHITECTURE: fixed 30 primary events, 10 OOS events, three rolling folds,
   all robustness gates, real PB evidence, and 20 Paper sessions as minimums.
4. ORCHESTRATE: separated external data acquisition from locally verifiable
   code, contracts, tests, and sealed evidence.
5. DEVELOP: added current News_Claws compatibility, token-by-environment,
   conservative timestamp conversion, mapping quarantine, caller-label
   downgrade, readiness CLI/API, artifact hashes, provenance, PB, and Paper
   checks, including a three-way PB borrow-file hash cross-check. Added an
   exact-event-version PIT news-enrichment contract with external provenance,
   effective dates, availability timestamps, and fail-closed partial state.
6. VERIFY CODE: 44/44 tests passed with warnings as errors. Coverage now
   includes strict integer versions, duplicate/unknown event references,
   placeholder and local-source rejection, PIT dates, partial enrichment,
   signal generation, event-scoped mapping, CSV round-trip, CLI wiring, and
   enrichment-file tampering. Python compilation, 37-file JSON parsing, two
   JSON Schema validations, credential scanning, and Git whitespace checks
   passed before sealing.
7. VERIFY DATA: the source and latest isolated database snapshot share SHA-256
   D1D30FC43897A8CCCC6B370A05A4926C7CC0D44F488CDFFAA82CDA5A36F9D67A.
   The snapshot has 254 non-demo events, 260 reports, zero company impacts, 48
   industry impacts, and zero report-level novelty fields. The retained
   100-event API export belongs to the earlier F16FEB1F... snapshot and remains
   explicitly historical.
8. VERIFY READINESS: the policy returned exit code 1, decision BLOCKED, 20 hard
   failures, zero usable primary events, zero OOS events, and zero verified
   Paper sessions.
9. VERIFY RUNTIME: 127.0.0.1:8080 remains v0.4.0, health is ok, and POST is
   rejected with 405. The isolated 8016 service was stopped.
10. SEAL: sanitized inventory, readiness output, hashes, schemas, examples,
    documentation, and this log are retained in the v0.5 preflight branch.
11. RELEASE: merge, tag, and v0.4 replacement are blocked until one consistent
    real-data run passes every v0.5 gate.

## Current decision

- Readiness mechanism: PASS.
- PIT news enrichment mechanism: PASS; production enrichment artifact absent.
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
