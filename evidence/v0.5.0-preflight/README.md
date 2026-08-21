# v0.5.0 Real-Data Readiness Preflight

This directory seals the fail-closed v0.5 preflight. It is evidence of current
readiness gaps, not a production release.

- real_data_inventory.json records sanitized News_Claws, factor, price, PB, and
  Paper facts with logical paths and SHA-256 values.
- readiness.json is the machine-readable policy result produced against the
  current sealed integration evidence.
- verification.json records code, artifact, and runtime checks.

Verified result:

- 44 automated tests passed with warnings promoted to errors.
- Python compilation, 37-file JSON parsing, two JSON Schema validations,
  credential scanning, and Git whitespace checks passed.
- Exact-event PIT enrichment, partial-degradation retention, event-scoped
  mappings, CLI wiring, and file-tamper detection are covered.
- Readiness returned exit code 1, decision BLOCKED, and 20 hard failures.
- The deployed 127.0.0.1:8080 service remains v0.4.0 and read-only.
- The isolated 8016 preflight service was stopped.

No database, raw news body, price row, credential, local absolute path, broker
instruction, or real-money authorization is retained here.
