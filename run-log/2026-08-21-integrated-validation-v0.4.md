# Run Log - v0.4.0 Integrated Validation

## Authorization envelope

- Goal: continue under the attached Loop process, merge the verified release, and deploy the authorized local read-only research service.
- Allowed: changes in this repository, private GitHub publication, local process replacement on `127.0.0.1:8080`, and read-only integration with the two existing systems.
- Preserved: the separate multi-factor repository and its user changes were not modified.
- Forbidden or unavailable: news writes, broker calls, real-money orders, cloud infrastructure changes, and unsupported economic-performance claims.

## Loop stage record

1. DISCOVER: retained the thin integration decision and identified that event study, five scenario returns, and independent validation had to come from one integrate run.
2. PRODUCT: froze the claim at local research/Paper readiness; no Live claim was permitted.
3. ARCHITECTURE: connected read-only news, pre-V4 event overlay, V4 controls, three-path backtests, Paper OMS, event study, independent validation, standard audit, and read-only API.
4. ORCHESTRATE: separated 13 hard integration gates from research sufficiency and economic gates.
5. DEVELOP: added integrated event study, five numeric scenarios, conservative classification, standard `audit.json`, compatibility audit, CLI parameters, API access, and fail-closed regressions.
6. VERIFY CODE: compile and diff checks pass. `22/22` tests pass with `ResourceWarning` promoted to an error. Standard artifact verification returns `INCONCLUSIVE` with zero hard failures.
7. VERIFY INTEGRATION: run `INT-3294801BE2C27699` passes 13/13 hard gates; V4 loader and three external backtests pass; eight event-study rows and five finite scenarios are present.
8. VERIFY DOCUMENTS: accessibility is high=0, medium=0, low=0; exact table geometry and heading hierarchy pass. Word/Poppler rendered 15 pages and every page was inspected. LibreOffice was unavailable because `soffice` is not installed.
9. DEPLOY: confirmed PID 72344 was the v0.3 read-only service, stopped it, and started v0.4 PID 71332 against `artifacts/integrated-v0.4`. Full HTTP assertions pass.
10. SEAL: `evidence/v0.4.0/` records sanitized artifacts, hashes, decisions, API checks, document QA, deployment scope, and unresolved gates.
11. CLEANUP/FINAL: the replacement read-only service remains intentionally active; no preview service or extra command session remains. GitHub merge, tag, release, and final consistency checks complete the terminal gate.

## Operator note

The first manual verifier invocation used a positional artifact directory and correctly returned CLI usage error 2. It was immediately rerun with `--artifact-dir` and returned exit 0 with no hard failures. This was an invocation correction, not a product failure.

## Verified result

- Package version: 0.4.0.
- Integration run: `INT-3294801BE2C27699`.
- Status: `READY_FOR_PAPER_RESEARCH`.
- Research decision: `INCONCLUSIVE`.
- Live decision: `BLOCKED`.
- API: root/health/report/event-study/independent-validation return 200; POST returns 405; unknown route returns 404.
- Local deployment: `http://127.0.0.1:8080`, read-only, version 0.4.0.

## Decision

- Three-system integration mechanism: PASS.
- Independent validation integrity: PASS.
- Economic promotion: INCONCLUSIVE.
- Real-data continuous Paper: BLOCKED.
- Live: BLOCKED.
