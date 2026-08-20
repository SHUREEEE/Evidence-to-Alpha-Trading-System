# Run Log - v0.3.0 Independent Validation

## Authorization envelope

- Goal: continue the project under the attached Loop process, merge the verified release, and deploy the authorized local read-only research service.
- Allowed: changes in this repository, private GitHub publication, local package installation, and replacement of the existing service on `127.0.0.1:8080`.
- Preserved: the separate multi-factor-platform worktree and its user changes were not modified.
- Forbidden or unavailable: news writes, broker calls, real-money orders, cloud infrastructure changes, and unsupported economic-performance claims.

## Loop stage record

1. DISCOVER: re-read the task-book structure and identified the missing formal IS/OOS and chronological rolling-validation gate.
2. PRODUCT: retained the thin integration decision; the next product claim is independent research validation, not live execution.
3. ARCHITECTURE: added a standalone verifier consuming immutable visible events, event-study rows, and recorded robustness scenarios.
4. ORCHESTRATE: defined hard integrity gates separately from research-sufficiency and economic gates.
5. DEVELOP: implemented chronological partitions, rolling OOS folds, signed abnormal-return summaries, three-state decisions, CLI configuration, artifact output, and read-only API access.
6. VERIFY: compilation, diff checks, SQLite integrity, and 21/21 tests pass. ResourceWarning is promoted to an error. Added regressions for leakage, missing/unknown refs, malformed rows, non-finite scenarios, negative OOS, and insufficient samples.
7. VERIFY DOCUMENTS: rebuilt three v0.3 Word files. ZIP integrity, exact table geometry, heading hierarchy, and accessibility checks pass. Microsoft Word and Poppler were used to inspect all 15 pages; canonical LibreOffice rendering was unavailable because `soffice` is not installed.
8. DEPLOY: the first v0.3 process exited because PowerShell split an unquoted artifact path containing spaces. No listener was present. The path was quoted, the process was restarted, and the full HTTP assertion suite then passed.
9. SEAL: `evidence/v0.3.0/` records path-free hashes, decisions, API checks, document QA, deployment scope, and unresolved real-data gates.
10. CLEANUP/FINAL: only the local read-only research/Paper service is deployed. Continuous Paper and Live remain blocked.

## Verified result

- Package version: 0.3.0.
- Demo run: `RUN-25ECC87FAC46A1DE`.
- Demo decision: INCONCLUSIVE in report, audit, and independent validation.
- Integrity: zero hard failures; IS/OOS refs are disjoint; SQLite integrity is ok.
- Sample: 2 usable events, 1 IS, 1 OOS, and only 1 of 3 non-empty rolling folds.
- API: health/report/independent-validation return 200; POST returns 405; unknown route returns 404.
- Local deployment: `http://127.0.0.1:8080`, read-only, version 0.3.0.

## Decision

- Independent-validation mechanism: PASS.
- Economic promotion: INCONCLUSIVE.
- Real-data continuous Paper: BLOCKED.
- Live: BLOCKED.
- Next action: refresh non-synthetic events, factor weights, and corporate-action-safe prices through event T+1; accumulate enough real events and rerun the unchanged v0.3 gates.
