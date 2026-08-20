# v0.3.0 Release Evidence

This directory is the sanitized release-evidence package for chronological independent validation. It excludes local absolute paths, service logs, generated input fixtures, and raw market data.

The release adds:

`point-in-time events -> chronological IS/OOS -> rolling OOS folds -> placebo/delay/doubled-cost gates -> PROMOTE/REJECT/INCONCLUSIVE`

The package proves implementation behavior, reproducibility, fail-closed decisions, document integrity, and local read-only deployment. It does not prove economic efficacy. The sealed demo uses two synthetic events, so its decision is `INCONCLUSIVE` and Live remains `BLOCKED`.

Use `verification.json` for the release checklist and `independent_validation.json` for the sanitized machine-readable validation result.
