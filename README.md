# Evidence-to-Alpha Trading System

Evidence-to-Alpha is the integration and governance layer between:

- the read-only news service at `http://127.0.0.1:8765`;
- `SHUREEEE/multi-factor-alpha-platform`;
- a point-in-time event Alpha and Paper OMS pipeline.

It exports immutable news-event versions, creates traceable event signals, overlays bounded deltas on factor weights before V4 controls, runs the factor platform's production loader and T+1 backtests, records paper orders with complete evidence lineage, and independently validates the integrated path with chronological event studies and robustness scenarios.

The deployed v0.4 release is a research and Paper integration MVP. The v0.5
branch adds a fail-closed real-data readiness policy but is not yet eligible to
replace v0.4. Neither version has a broker connection, live credentials,
real-order write path, or claim of economic efficacy.

## Quick start

Python 3.11+ is required. Core demo and read-only serving have no third-party dependencies.

```powershell
python -m pip install -e .
python -m evidence_alpha demo --output-dir artifacts/demo-v0.4
python -m evidence_alpha verify --artifact-dir artifacts/demo-v0.4
python -m evidence_alpha serve --artifact-dir artifacts/demo-v0.4 --host 127.0.0.1 --port 8080
```

Open `http://127.0.0.1:8080/health`, `http://127.0.0.1:8080/api/v1/runs/latest`, `http://127.0.0.1:8080/api/v1/runs/latest/event-study`, and `http://127.0.0.1:8080/api/v1/runs/latest/independent-validation`.

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
  --benchmark SPY `
  --data-classification real `
  --minimum-event-count 30 `
  --minimum-oos-events 10 `
  --rolling-folds 3 `
  --primary-window-days 5 `
  --run-factor-v4 `
  --run-factor-backtests `
  --output-dir artifacts/integrated-v0.4
```

`--asof` must include a timezone. The public factor repository does not contain its large V3 weights and processed prices, so point `--weights` and `--prices` at the user's real local artifacts. Synthetic news is rejected unless `--allow-synthetic-news` is explicit, and a synthetic run can never return `PROMOTE`.

Serve only the validated artifact directory:

```powershell
python -m evidence_alpha serve `
  --artifact-dir artifacts/integrated-v0.4 `
  --host 127.0.0.1 `
  --port 8080
```

The container has the same read-only default and never bootstraps demo data:

```powershell
docker compose up --build
```

Override the container artifact directory only when needed:

```powershell
$env:EVIDENCE_ALPHA_ARTIFACT_DIR='/app/artifacts/integrated-v0.4'
docker compose up --build
```

## Verification

```powershell
python -m unittest discover -s tests -v
```

The verified v0.4 integration run produced:

- run ID `INT-3294801BE2C27699`;
- 22/22 automated tests passed with `ResourceWarning` promoted to an error;
- 13/13 integration hard gates passed and `evidence-alpha verify` reported zero hard failures;
- V4 `input_mode=prod`, `validation_state=PASS`, and one cvxpy solver path;
- three external `run_backtest.py` processes passed;
- T+1 paper fills reconciled to 0.01;
- eight event-study rows and all five numeric robustness scenarios;
- decision `INCONCLUSIVE` and live launch `BLOCKED`.

The run used a three-day synthetic factor fixture and one synthetic news event with two immutable versions. Those inputs prove interface, chronology, and control-flow compatibility only; their annualized statistics and Sharpe have no economic meaning.

## Real-data preflight

The v0.2.1 preflight fixes a causality defect in stale-data handling: T+1 comparisons and Paper fills are now anchored to the integration as-of date, not the factor weight date. A fill must use the first available price date strictly after as-of; otherwise the run is `BLOCKED` and emits no orders or fills. The complete suite passes 15/15 tests, including a July-data/August-event regression.

Current local real artifacts are not fresh enough to run that loop. V3 ends on 2024-12-31; V6.5 weights and NVDA/TSM/SPY TDX prices end on 2026-07-17; the only news event is synthetic and has an August 2026 as-of. The V6.5 manifest also identifies raw-close corporate-action, survivorship, and borrow-proxy limitations. Sanitized evidence is in `evidence/v0.2.1/real_data_preflight.json`.

## Independent validation v0.3

v0.3 adds a fail-closed independent-validation stage to the core pipeline:

- chronological in-sample/out-of-sample partitions ordered by event `observed_at`;
- configurable rolling OOS folds with no cross-partition event references;
- primary-window signed abnormal-return summaries;
- factor baseline, placebo, one-day-delay, and doubled-cost comparisons;
- hard rejection for leakage, unknown event refs, malformed study rows, duplicate visible refs, and missing or non-finite scenario outputs;
- `INCONCLUSIVE` for synthetic/unknown data or insufficient chronological samples;
- `PROMOTE` only when every real-data, OOS, rolling-stability, placebo, delay, and doubled-cost gate passes.

The release passes 21/21 automated tests, including positive, negative, insufficient-sample, leakage, malformed-row, and read-only API cases. The sealed synthetic demo remains `INCONCLUSIVE`: it contains 2 usable events, only 1 OOS event, and incomplete rolling folds. This is the expected fail-closed result, not an economic claim.

## Integrated validation v0.4

v0.4 moves the independent validator into the real `integrate` orchestration path:

- converts the factor platform's adjusted-close panel into point-in-time event-study bars;
- records 1/3/5/20-day event-study rows;
- computes factor baseline, overlay, placebo, one-trading-day delay, and doubled-cost returns;
- forces a synthetic news manifest to remain `synthetic` even if a caller declares real data;
- writes `event_study.csv`, `independent_validation.json`, and standard `audit.json`;
- makes integrated artifacts compatible with `evidence-alpha verify`;
- serves both event-study and independent-validation artifacts through the read-only API.

The v0.4 synthetic integration has no integrity failures, but its five-day primary window has no usable events and the doubled-cost result does not exceed the factor baseline. Its correct research result is therefore `INCONCLUSIVE`; live launch remains separately `BLOCKED`.

## Real-data readiness v0.5

v0.5 adds compatibility with the maintained News_Claws API and a separate
release-readiness command. It verifies actual file hashes and provenance rather
than accepting a caller-provided real label. It requires:

- 30 usable primary-window events, 10 OOS events, and at least three rolling folds;
- passing baseline, placebo, one-day-delay, and doubled-cost gates;
- PIT factor weights and corporate-action-safe prices through event T+1;
- a real PB borrow feed, passing dry run, and passing launch bundle;
- 20 gap-free hashed Paper sessions with freshness and reconciliation.

Run the fail-closed policy after producing one real integration:

    python -m evidence_alpha readiness
      --artifact-dir artifacts/integrated-real
      --factor-attestation path/to/factor_attestation.json
      --price-attestation path/to/price_attestation.json
      --pb-validation path/to/pb_validation.json
      --pb-dry-run-manifest path/to/pb_dry_run_manifest.json
      --pb-launch-bundle path/to/pb_launch_bundle.json
      --paper-manifest path/to/paper/manifest.json

The current real-data inventory contains 245 non-demo News_Claws events, but
the latest 100-event API export has no direct ticker mappings and lacks novelty
for every event. Available factor and price evidence ends on 2026-07-17, before
the 2026-08-20 news observations. PB evidence and continuous Paper sessions are
absent. The sealed readiness decision is BLOCKED.

See docs/09_real_data_readiness_v0.5.md and
evidence/v0.5.0-preflight/real_data_inventory.json.

## Inputs

- versioned news events and evidence from read-only HTTP GET endpoints;
- V3 factor weights in long or wide CSV/Parquet format;
- adjusted-close prices in long or wide CSV/Parquet format;
- ticker-to-sector mappings;
- a timezone-aware as-of cutoff.

## Outputs

- `integration_report.json`, backward-compatible `integration_audit.json`, and standard `audit.json`;
- factor-only, event-only, and fused pre-V4 weights;
- V4 input cache, external backtest results, and V4 output manifest;
- `signals.json`, `orders.json`, and `fills.json` with event/version/evidence lineage; `paper_orders.json` is retained for compatibility;
- `independent_validation.json` with chronological partitions, rolling folds, window summaries, scenarios, gates, and decision;
- `event_study.csv` with event/ticker/window chronology and abnormal-return status;
- immutable news export and machine-readable gate evidence.

## Live gate

Research and Paper use are available. The rolling OOS and robustness mechanism is implemented, but Live remains blocked until fresh real V3 and corporate-action-safe price artifacts pass it with enough real events, and until a real PB borrow feed, continuous Paper operation, independent risk verification, broker-specific security design, and explicit release authorization are all complete.

Project state is tracked in [STATE.md](STATE.md). Release evidence is retained under `evidence/<release-id>/`.

