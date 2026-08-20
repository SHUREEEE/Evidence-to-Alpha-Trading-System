# Evidence-to-Alpha Trading System

Evidence-to-Alpha is a point-in-time research and paper-trading pipeline. It converts versioned news events into traceable event signals, overlays those signals on an existing factor portfolio, and records deterministic paper orders, fills, positions, costs, and research evidence.

The MVP deliberately does not connect to a broker, ingest live credentials, or claim production trading efficacy.

## Quick start

Python 3.11+ is required. The runtime has no third-party dependencies.

```powershell
python -m pip install -e .
python -m evidence_alpha demo --output-dir artifacts/demo
python -m evidence_alpha serve --artifact-dir artifacts/demo --port 8080
```

Open `http://127.0.0.1:8080/health` and `http://127.0.0.1:8080/api/v1/runs/latest`.

Run the test suite:

```powershell
python -m unittest discover -s tests -v
```

## Inputs

- `events.json`: immutable event versions with published, observed, and as-of timestamps.
- `evidence.json`: evidence source records referenced by event versions.
- `mappings.csv`: entity-to-ticker mappings with sector and impact multiplier.
- `prices.csv`: daily open and close prices, including the configured benchmark.
- `baseline_weights.csv`: factor portfolio weights and factor version.

## Outputs

- `report.json`: decision, comparisons, reconciliation, and gate results.
- `signals.json`: event signal lineage and configuration hashes.
- `orders.json` / `fills.json`: paper execution records.
- `event_study.csv`: 1/3/5/20-day abnormal returns where enough data exists.
- `ledger.sqlite3`: immutable event versions and run artifacts.
- `audit.json`: automated verifier evidence.

## Governance

Project state is tracked in [STATE.md](STATE.md). Release evidence is retained under `evidence/<release-id>/`. Git merge, remote deployment, credentials, and production release remain separate authorization gates.

