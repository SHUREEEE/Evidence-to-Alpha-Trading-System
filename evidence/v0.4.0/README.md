# v0.4.0 Release Evidence

This directory is the sanitized release-evidence package for the integrated three-system validation. It excludes absolute local paths, service logs, raw market data, generated Parquet files, and the full integration report whose artifact map contains workstation paths.

The sealed path is:

`read-only news -> immutable event lineage -> factor/event/fused paths -> multi-factor V4 -> T+1 Paper -> event study -> independent validation -> standard audit`

Use `verification.json` for the release checklist, `audit.json` for the standard decision contract, `integration_audit.json` for backward compatibility, `independent_validation.json` for chronological and robustness gates, and `event_study.csv` for the eight event-window rows.

The evidence proves implementation behavior, reproducibility, failure closure, document quality, and local read-only deployment. It does not prove economic efficacy. News remains synthetic, the five-day primary window has no usable events, doubled-cost overlay does not beat baseline, and Live remains `BLOCKED`.
