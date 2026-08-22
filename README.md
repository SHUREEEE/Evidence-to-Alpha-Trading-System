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
  --enrichment C:\path\to\news_enrichment.json `
  --output-dir artifacts/news
```

`--enrichment` is optional. When supplied, it must identify exact event
versions and carry non-synthetic repository, commit, pipeline-run, methodology,
availability-time, and external-source provenance. Partial enrichment remains
degraded; it cannot clear readiness until every visible event has no unresolved
contract degradation. The contract is
`schemas/news_enrichment.schema.json`.

For an official, non-synthetic event source, the project can export SEC EDGAR
filings into the same immutable bundle format. The SEC User-Agent must contain
a real contact email; placeholder domains are rejected. Official filings are
not a substitute for a licensed market-data or PB feed, and the bundle still
has to pass all event, price, factor, and Paper gates.

```powershell
python -m evidence_alpha sec-edgar-export `
  --cik NVDA=0001045810 `
  --cik AMD=0000002488 `
  --user-agent "Evidence-to-Alpha research@your-real-domain.example" `
  --start-date 2022-09-26 `
  --end-date 2024-11-30 `
  --forms 8-K 10-Q 10-K `
  --max-events 100 `
  --output-dir artifacts/news-sec
```

Replace the example contact address with an authorized real address before
executing. Integrate a sealed bundle without contacting its source:

```powershell
python -m evidence_alpha integrate `
  --news-export-dir artifacts/news-sec `
  --factor-root C:\path\to\multi-factor-alpha-platform `
  --weights C:\path\to\pit\weights.parquet `
  --prices C:\path\to\corporate-action-safe\prices.parquet `
  --asof 2024-11-30T16:00:00+00:00 `
  --data-classification real `
  --minimum-event-count 30 `
  --minimum-oos-events 10 `
  --rolling-folds 3 `
  --output-dir artifacts/integrated-real
```

Run the complete integration with real factor artifacts:

```powershell
python -m evidence_alpha integrate `
  --news-base-url http://127.0.0.1:8765 `
  --news-enrichment C:\path\to\news_enrichment.json `
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

v0.5 adds compatibility with the maintained News_Claws API, an exact-version
PIT news-enrichment contract, and a separate release-readiness command. It
verifies actual file hashes, recomputes CSV/Parquet coverage and value-field
semantics, and checks provenance rather than accepting a caller-provided real
label. It requires:

- non-synthetic external news provenance with no unresolved novelty,
  publication-time, or investable-mapping degradation;
- 30 usable primary-window events, 10 OOS events, and at least three rolling folds;
- passing baseline, placebo, one-day-delay, and doubled-cost gates;
- PIT factor weights and corporate-action-safe prices through event T+1;
- a real PB borrow feed with a verified real-source ingestion manifest and one
  canonical SHA-256 shared by ingestion, validation, dry run, and launch bundle;
- 20 gap-free hashed Paper sessions with freshness and reconciliation.

Inspect candidate market files before authoring attestations:

    python -m evidence_alpha inspect-panel
      --input path/to/weights.parquet
      --kind factor_weights
      --logical-path production/weights.parquet
      --output artifacts/input-inspection/weights.json

    python -m evidence_alpha inspect-panel
      --input path/to/prices.parquet
      --kind adjusted_prices
      --logical-path production/prices.parquet
      --output artifacts/input-inspection/prices.json

The reports contain content-derived hashes, coverage, counts, and value fields.
They never assert production provenance, PIT universe, corporate actions, or delistings.

Run the fail-closed policy after producing one real integration:

    python -m evidence_alpha readiness
      --artifact-dir artifacts/integrated-real
      --factor-attestation path/to/factor_attestation.json
      --price-attestation path/to/price_attestation.json
      --pb-ingestion-manifest path/to/pb_ingestion_manifest.json
      --pb-validation path/to/pb_validation.json
      --pb-dry-run-manifest path/to/pb_dry_run_manifest.json
      --pb-launch-bundle path/to/pb_launch_bundle.json
      --paper-manifest path/to/paper/manifest.json

The latest read-only database snapshot contains 254 non-demo News_Claws events,
260 reports, zero company impacts, and no top-level novelty field in any
report. A snapshot-matched, isolated API export now contains 200 events and 206
evidence records. It has zero direct ticker mappings, 28 industry-only events,
172 unmapped events, and missing novelty for all 200 events.

The read-only SQLite enrichment command records the snapshot and input-event
SHA-256 values, requires exact report versions, enforces report cutoffs, and
rejects pending WAL data. The sealed partial run resolved real
`published_at` for 56 of 200 event versions and explicitly retained 144
unresolved versions. All 200 remain contract-degraded because novelty or
investable company/ticker mapping is absent. The mechanism is covered by the
73-test suite, including false coverage declarations, raw-close substitution,
input tampering, and read-only database invariants.

A separate historical-overlap audit now inspects every non-demo report in the
checkpointed snapshot, including the 54 events hidden by the API's 200-item
no-cursor limit. It uses the conservative point-in-time rule
`observed_at=max(published_at-or-first_seen, first_seen, last_seen,
report.generated_at, report.data_cutoff_at)` and never emits event IDs, titles,
bodies, URLs, or absolute paths. Against factor coverage starting 2022-09-26
and explicit `adj_close` coverage ending 2024-12-31, it found zero causally
observed events. Six report versions have publication dates inside the market
window, but all six were only observed in 2026 and are rejected as look-ahead.
With a 30% chronological OOS split, the 30-event and 10-OOS gates require at
least 31 total usable events.

Run the same fail-closed audit on a checkpointed snapshot:

    python -m evidence_alpha audit-news-overlap
      --database path/to/analysis.db
      --factor-coverage-start 2022-09-26
      --adjusted-price-coverage-end 2024-12-31
      --minimum-event-count 30
      --oos-fraction 0.30
      --minimum-oos-events 10
      --output path/to/historical_news_overlap_audit.json

The audited V6.5 weight panel contains 2,114,370 rows across 2,214 tickers and
ends on 2026-07-17. The newer TDX feed also ends on 2026-07-17 but is raw close;
the only inspected panel with an explicit `adj_close` field ends on 2024-12-31.
All 200 current real events are later than those inputs. PB evidence and
continuous Paper sessions are absent. The sealed readiness report has 23 hard
failures, including the missing PB ingestion provenance gate, and remains
BLOCKED.

Generate an auditable publication-time artifact from a checkpointed snapshot:

    python -m evidence_alpha news-enrichment-sqlite
      --database path/to/analysis.db
      --events path/to/events.json
      --commit NEWS_CLAWS_FULL_COMMIT
      --allow-partial
      --output path/to/news_enrichment.json

Use `--page-size 200` for the maintained News_Claws API, which permits 200
items but does not expose a cursor. The legacy-compatible default remains 100.

See docs/09_real_data_readiness_v0.5.md and
evidence/v0.5.0-preflight/real_data_inventory.json. The direct market-input
audit is retained in evidence/v0.5.0-preflight/market_input_audit.json, and the
sanitized historical overlap result is retained in
evidence/v0.5.0-preflight/historical_news_overlap_audit.json under
schemas/historical_news_overlap_audit.schema.json.

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

