# Evidence-to-Alpha Trading System

Evidence-to-Alpha is the integration and governance layer between:

- the read-only news service at `http://127.0.0.1:8765`;
- `SHUREEEE/multi-factor-alpha-platform`;
- a point-in-time event Alpha and Paper OMS pipeline.

It exports immutable news-event versions, creates traceable event signals, overlays bounded deltas on factor weights before V4 controls, runs the factor platform's production loader and T+1 backtests, and records paper orders with complete evidence lineage.

The current release is a research and Paper integration MVP. It deliberately has no broker connection, live credentials, real-order write path, or claim of economic efficacy.

## Quick start

Python 3.11+ is required. Core demo and read-only serving have no third-party dependencies.

```powershell
python -m pip install -e .
python -m evidence_alpha demo --output-dir artifacts/demo
python -m evidence_alpha verify --artifact-dir artifacts/demo
python -m evidence_alpha serve --artifact-dir artifacts/demo --host 127.0.0.1 --port 8080
```

Open `http://127.0.0.1:8080/health` and `http://127.0.0.1:8080/api/v1/runs/latest`.

## Three-system integration

Install the optional CSV/Parquet integration dependencies:

```powershell
python -m pip install -e ".[integrations]"
```

Export news versions without writing to the news service:

```powershell
python -m evidence_alpha news-export `
  --news-base-url http://127.0.0.1:8765 `
  --output-dir artifacts/news
```

Run the complete integration with real factor artifacts:

```powershell
python -m evidence_alpha integrate `
  --news-base-url http://127.0.0.1:8765 `
  --factor-root C:\path\to\multi-factor-alpha-platform `
  --weights path\to\v3_weights.parquet `
  --sectors results\pillar5_artifacts\v3_sector_map.csv `
  --prices path\to\prices.parquet `
  --asof 2026-08-20T16:00:00+08:00 `
  --run-factor-v4 `
  --run-factor-backtests `
  --output-dir artifacts/integrated-live-v0.2
```

`--asof` must include a timezone. The public factor repository does not contain its large V3 weights and processed prices, so point `--weights` and `--prices` at the user's real local artifacts. Synthetic news is rejected unless `--allow-synthetic-news` is explicit, and a synthetic run can never return `PROMOTE`.

Serve only the validated artifact directory:

```powershell
python -m evidence_alpha serve `
  --artifact-dir artifacts/integrated-live-v0.2 `
  --host 127.0.0.1 `
  --port 8080
```

The container has the same read-only default and never bootstraps demo data:

```powershell
docker compose up --build
```

Override the container artifact directory only when needed:

```powershell
$env:EVIDENCE_ALPHA_ARTIFACT_DIR='/app/artifacts/integrated-live-v0.2'
docker compose up --build
```

## Verification

```powershell
python -m unittest discover -s tests -v
```

The verified v0.2 integration run produced:

- run ID `INT-21959353434E657B`;
- 13/13 automated tests passed;
- 11/11 integration gates passed;
- V4 `input_mode=prod`, `validation_state=PASS`, and one cvxpy solver path;
- three external `run_backtest.py` processes with return code 0;
- T+1 paper fills reconciled to 0.01;
- decision `INCONCLUSIVE` and live launch `BLOCKED`.

The run used a two-day synthetic factor fixture and one synthetic news event with two immutable versions. Those inputs prove interface and control-flow compatibility only; their annualized statistics and Sharpe have no economic meaning.

## Inputs

- versioned news events and evidence from read-only HTTP GET endpoints;
- V3 factor weights in long or wide CSV/Parquet format;
- adjusted-close prices in long or wide CSV/Parquet format;
- ticker-to-sector mappings;
- a timezone-aware as-of cutoff.

## Outputs

- `integration_report.json` and `integration_audit.json`;
- factor-only, event-only, and fused pre-V4 weights;
- V4 input cache, external backtest results, and V4 output manifest;
- `signals.json`, `orders.json`, and `fills.json` with event/version/evidence lineage; `paper_orders.json` is retained for compatibility;
- immutable news export and machine-readable gate evidence.

## Live gate

Research and Paper use are available. Live remains blocked until real V3 and price artifacts, enough real event samples, rolling OOS and robustness evidence, a real PB borrow feed, continuous Paper operation, independent risk verification, broker-specific security design, and explicit release authorization are all complete.

Project state is tracked in [STATE.md](STATE.md). Release evidence is retained under `evidence/<release-id>/`.

