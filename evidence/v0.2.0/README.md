# v0.2.0 Release Evidence

This directory is the sanitized release-evidence package for the three-system research and Paper integration. It intentionally excludes generated artifact directories and local absolute paths.

The verified integration order is:

`news evidence -> event Alpha -> factor plus event pre-V4 -> V4 controls -> T+1 backtest/Paper OMS -> attribution feedback`

The package establishes interface compatibility, point-in-time lineage, control gates, and deterministic Paper reconciliation. It does not establish economic efficacy. The input fixture contains one synthetic news event with two immutable versions and two days of synthetic factor data, so the release decision remains `INCONCLUSIVE` and live launch remains `BLOCKED`.

Use `verification.json` for the release checklist, `integration_audit.json` for machine gates, and `integration_summary.json` for the path-free run summary.
