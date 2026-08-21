# v0.5.0 Real-Data Readiness Preflight

This directory seals the fail-closed v0.5 preflight. It is evidence of current
readiness gaps, not a production release.

- real_data_inventory.json records sanitized News_Claws, factor, price, PB, and
  Paper facts with logical paths and SHA-256 values.
- news_enrichment_summary.json records the snapshot-matched 200-event export,
  56/144 partial publication-time coverage, remaining contract gaps, and
  stopped isolated runtime without retaining raw news.
- market_input_audit.json records content-derived factor and price coverage,
  TDX raw-close limitations, Git-tracking boundaries, GitHub artifact inventory,
  and the zero-event T+1 result without retaining market-data rows.
- historical_news_overlap_audit.json records the all-report conservative
  observation-time audit, exact sample/OOS threshold math, and zero causal
  overlap without retaining raw news or local absolute paths.
- readiness.json is the machine-readable policy result produced against the
  current sealed integration evidence.
- verification.json records code, artifact, and runtime checks.

Verified result:

- 70 automated tests and 8 subtests passed with warnings promoted to errors.
- Python compilation, 128-file JSON parsing, twelve JSON Schema instance checks,
  credential scanning, and Git whitespace checks passed.
- Exact-event PIT enrichment, report cutoffs, pending-WAL rejection, read-only
  input invariants, partial-degradation retention, 200-item no-cursor paging,
  CLI wiring, and enrichment/input-file tamper detection are covered.
- The deterministic `inspect-panel` CLI reproduces both real Parquet audits,
  emits path-safe content facts, and retains unverified provenance limitations.
- The `audit-news-overlap` CLI verifies read-only/query-only SQLite access,
  schema columns, quick_check, a checkpointed WAL state, and input immutability.
  It audited 254 non-demo events and 260 report versions, found zero causal
  overlaps, and rejected all six publication-window versions that were only
  observed in 2026. The exact 30% OOS threshold requires 31 total events.
- The PB gate requires a real-source ingestion manifest, verified source and
  mapping hashes, and four-way canonical-feed hash agreement; no such real
  production evidence is currently present.
- The current snapshot export contains 200 events and 206 evidence records.
  Publication time is verified for 56 versions and unresolved for 144; all 200
  still lack novelty or complete investable mapping.
- The audited V6.5 weights end on 2026-07-17, the explicit adjusted-price panel
  ends on 2024-12-31, and the newer TDX raw-close feed also ends on 2026-07-17.
  All 200 current real events occur after those inputs; GitHub has no usable
  release or Actions artifact to close the gap.
- Readiness returned exit code 1, decision BLOCKED, and 23 hard failures,
  including independently recomputed factor and price artifact contents.
- The deployed 127.0.0.1:8080 service remains v0.4.0 and read-only.
- The isolated 8016 preflight service was stopped.

No database, raw news body, price row, credential, local absolute path, broker
instruction, or real-money authorization is retained here.
