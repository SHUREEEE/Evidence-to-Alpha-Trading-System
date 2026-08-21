# v0.5.0 Real-Data Readiness Preflight

This directory seals the fail-closed v0.5 preflight. It is evidence of current
readiness gaps, not a production release.

- real_data_inventory.json records sanitized News_Claws, factor, price, PB, and
  Paper facts with logical paths and SHA-256 values.
- news_enrichment_summary.json records the snapshot-matched 200-event export,
  56/144 partial publication-time coverage, remaining contract gaps, and
  stopped isolated runtime without retaining raw news.
- readiness.json is the machine-readable policy result produced against the
  current sealed integration evidence.
- verification.json records code, artifact, and runtime checks.

Verified result:

- 53 automated tests passed with warnings promoted to errors.
- Python compilation, 121-file JSON parsing, three JSON Schema instance checks,
  credential scanning, and Git whitespace checks passed.
- Exact-event PIT enrichment, report cutoffs, pending-WAL rejection, read-only
  input invariants, partial-degradation retention, 200-item no-cursor paging,
  CLI wiring, and enrichment/input-file tamper detection are covered.
- The current snapshot export contains 200 events and 206 evidence records.
  Publication time is verified for 56 versions and unresolved for 144; all 200
  still lack novelty or complete investable mapping.
- Readiness returned exit code 1, decision BLOCKED, and 20 hard failures.
- The deployed 127.0.0.1:8080 service remains v0.4.0 and read-only.
- The isolated 8016 preflight service was stopped.

No database, raw news body, price row, credential, local absolute path, broker
instruction, or real-money authorization is retained here.
