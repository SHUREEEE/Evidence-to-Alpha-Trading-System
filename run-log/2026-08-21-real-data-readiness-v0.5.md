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
   checks, including a three-way PB borrow-file hash cross-check.
6. VERIFY CODE: 33/33 tests passed with warnings as errors. Python compilation
   and Git whitespace checks passed. Malformed numbers and datetimes fail the
   input-contract gate without an unhandled exception.
7. VERIFY DATA: the isolated database has 245 non-demo events and zero company
   impacts. The latest export has 100 events, zero ticker mappings, 15
   industry-only mappings, 85 unmapped events, and missing novelty for all 100.
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
- News contract completeness: BLOCKED.
- Statistical sample and OOS validation: BLOCKED.
- T+1 PIT factor and corporate-action-safe prices: BLOCKED.
- PB borrow and launch evidence: BLOCKED.
- Continuous Paper: BLOCKED.
- Live authorization: NOT GRANTED.

## Next inputs

1. Stable novelty and verified point-in-time company/ticker mappings.
2. PIT weights and adjusted or total-return prices through each event return
   endpoint.
3. A real security-level PB borrow feed and matching validation artifacts.
4. Twenty gap-free Paper sessions with hashes, freshness, and reconciliation.
5. Independent risk acceptance after the policy reaches authorization review.
