# Real Data Readiness v0.5

## Decision

The v0.5 implementation is a fail-closed release-readiness layer. The current
decision is BLOCKED. It is not a Live release candidate and it must not replace
the deployed v0.4 read-only service.

Passing v0.5 can only produce READY_FOR_LIVE_AUTHORIZATION_REVIEW. It never
grants Live trading, broker execution, credentials, or real-money authority.

## Scope

v0.5 connects the maintained News_Claws API shape to the existing
Evidence-to-Alpha integration, supports a separately versioned PIT news
enrichment artifact, and adds immutable checks for:

- non-synthetic news with complete external evidence and no contract degradation;
- exact event-version enrichment with a matching SHA-256, immutable source
  commit, pipeline run, methodology, availability timestamp, and verified
  SQLite-snapshot and event-export input hashes;
- at least 30 usable primary-window events and 10 chronological OOS events;
- at least three rolling folds plus placebo, delay, baseline, and doubled-cost gates;
- point-in-time factor weights with a matching file hash, content-derived
  coverage, and production provenance;
- corporate-action-safe prices with an explicit adjusted-price field and
  content-derived coverage through the required event T+1 return endpoint;
- one real-source PB ingestion manifest that verifies the source, mapping, and
  canonical files and covers the integration as-of;
- one real PB borrow feed shared by validation and the gated V4 dry run, with
  the same SHA-256 declared by ingestion, validation, dry run, and launch bundle;
- a passing PB launch evidence bundle;
- at least 20 gap-free Paper sessions with file hashes, data freshness, and
  cent-level reconciliation.

The thresholds are fixed minimums. Runtime configuration may be stricter but
cannot weaken 30 primary events, 10 OOS events, three folds, or 20 Paper
sessions.

## Current Real Data Inventory

News_Claws uses SQLite WAL mode, so copying only the main database file is not
a consistent logical snapshot. The current isolated snapshot was produced with
the SQLite online backup API and has SHA-256
81D179EB62A1E79469B39F0EE27375E575FA6699CDB3D339663FD0DCCF009F77.
Its integrity check is ok, and its logical counts match the live read-only
source. The source main file has SHA-256 D1D30FC4... and its WAL has SHA-256
7A960CEB.... The source database was not modified.

| Item | Current fact |
|---|---:|
| Non-demo event clusters | 254 |
| Articles | 260 |
| Claims | 260 |
| Evidence records | 267 |
| Reports | 260 |
| Reports with top-level novelty | 0 |
| Events with at least one published article time | 110 |
| Company impacts | 0 |
| Industry impacts | 48 |
| Banking/financial-services impacts | 23 |
| Pharma/life-sciences impacts | 15 |

The previously sealed 100-event API export was produced from the earlier
F16FEB1F... snapshot and remains historical evidence. A new isolated service
over the 81D179EB... snapshot exported the current API maximum of 200 events
using an explicit page size of 200. The maintained API has no cursor, so 54
older database events remain outside this API export.

| Current snapshot-matched export | Count |
|---|---:|
| Event versions | 200 |
| Evidence records | 206 |
| Direct ticker mappings | 0 |
| Industry-only events | 28 |
| Unmapped events | 172 |
| Events missing novelty | 200 |
| Events with real published_at | 56 |
| Events falling back to first_seen | 144 |

The isolated service used a separate SQLite online-backup working copy with
demo, scheduler, notifications, search, and TrendRadar disabled. It was
stopped after export. The sealed source snapshot retained SHA-256
81D179EB62A1E79469B39F0EE27375E575FA6699CDB3D339663FD0DCCF009F77.
Industry-only events are not equivalent to verified company/ticker mappings.

The SQLite enrichment path does not invent these missing values. It opens a
checkpointed database with SQLite `mode=ro` and `query_only`, requires one
exact report for each requested event version, and only accepts an article
whose `first_seen_at` is not later than the report `data_cutoff_at`. It
records both input file hashes and rejects a non-empty WAL or any input change
during extraction.

The current artifact uses pipeline run
`NEWS-SQLITE-C51F01179B111F4F43AB` and SHA-256
`CC8827736796B322A6D9925693499F075E87027F9F385B30AADF1A9CB262584C`.
Its explicit `eligible_published_at_only` selection requested 200 exact
versions, enriched 56, and retained 144 unresolved. Applying it changed no
event timestamp because the current API already exposed the same 56 real
publication times. It adds auditable provenance; it does not resolve novelty
or company/ticker mapping. All 200 event versions therefore remain degraded.

## Historical Causal Overlap Audit

The API cannot expose 54 older events because it has a 200-item maximum and no
cursor. The `audit-news-overlap` command therefore inspects the checkpointed
snapshot directly without mutating News_Claws. It:

- opens SQLite with `mode=ro` and enables and verifies `query_only`;
- requires the exact report, event, event-article, and article timing columns;
- requires `quick_check=ok` and rejects a non-empty WAL;
- fingerprints the database before and after the query;
- reads only event keys and timing fields internally; and
- emits no event IDs, titles, bodies, URLs, or absolute paths.

The causal timestamp is the maximum of the earliest linked publication time
or event first-seen fallback, event first seen, event last seen, report
generation time, and report data cutoff. This deliberately prevents an old
article publication date from backdating a report first observed in 2026.
T+1 also requires the event date to be earlier than the adjusted-price coverage
end date.

Against factor coverage starting 2022-09-26 and explicit `adj_close` coverage
ending 2024-12-31, the audit found:

| Historical overlap fact | Count |
|---|---:|
| Non-demo events | 254 |
| Non-demo report versions | 260 |
| Causally observed overlap events | 0 |
| Causally observed overlap versions | 0 |
| Publication-date-only overlap versions | 6 |
| Publication overlap observed too late | 6 |
| Chronological OOS events | 0 |

The decision is `INSUFFICIENT_CAUSAL_OVERLAP`. At 30% OOS, 30 total events
produce only 9 OOS events; 31 is the smallest total that satisfies both the
30-event and 10-OOS gates. The sanitized artifact is
`evidence/v0.5.0-preflight/historical_news_overlap_audit.json` and its contract
is `schemas/historical_news_overlap_audit.schema.json`.

The sealed machine-readable inventory is stored at
evidence/v0.5.0-preflight/real_data_inventory.json. It contains only logical
paths, counts, hashes, coverage dates, gate states, and required next inputs.

## Factor and Price State

The clean verification clone of SHUREEEE/multi-factor-alpha-platform is on main
at commit 9792ed27059b1179b39cca8fca2982fe22baf86e.

The latest separately observed V6.5 research artifact is associated with commit
365e53e5e85cfa2ee2f530403f3d934cd38b8ca3 and ends on 2026-07-17. Its large
Parquet outputs are not present in the clean verification clone. The sealed
v0.2.1 evidence records raw-close adjustment limits, current-constituent
survivorship bias, and proxy borrow cost.

A direct read-only audit of the local research artifacts produced the following
content-derived inventory:

| Artifact | Rows | Tickers | Coverage | Contract fact |
|---|---:|---:|---|---|
| V6.5 weights | 2,114,370 | 2,214 | 2022-09-26 to 2026-07-17 | `weight`; not Git-tracked; no PIT-universe attestation |
| Historical prices | 1,371,595 | 516 | 2014-01-02 to 2024-12-31 | explicit `adj_close`; no delisting attestation |
| TDX SPY/NVDA/TSM spot checks | n/a | 3 | through 2026-07-17 | raw close; not corporate-action safe |

The current 200 real events were published from 2026-08-06 through 2026-08-20,
so all 200 start after the latest V6.5 weight and TDX price date. The V6.5
manifest is tracked at commit b3230157f36e8f09d08b0f09a2180f2a88cb1ddb,
but the weight and price binaries are not tracked and the manifest does not bind
their hashes to a production pipeline run. GitHub has no Release and the latest
research Actions run has no artifacts. The secondary private research
repository has no branches.

The required T+1 date is 2026-08-21 or later. The available inputs cannot clear
causality, PIT-universe, coverage, corporate-action, or Paper freshness gates.
The sanitized audit is `evidence/v0.5.0-preflight/market_input_audit.json`.

## Readiness Inputs

The integration may carry one optional upstream news-enrichment artifact. Its
hash, production provenance, source selection, and input artifact hashes are
reloaded and cross-checked by readiness; all contract-degraded event
references must be empty. The readiness command also
accepts the integration artifact directory plus seven independent evidence
files:

1. Factor attestation with the exact factor-file SHA-256, coverage dates,
   immutable source commit and pipeline run, and PIT universe assertions.
2. Price attestation with the exact price-file SHA-256, coverage dates,
   licensed provider provenance, splits, cash and special dividends,
   delistings, and no unresolved exceptions.
3. PB ingestion manifest with a real-source attestation, timezone-aware receive
   time, positive row/symbol counts, date coverage through the integration
   as-of, and verified source, mapping, and canonical-file SHA-256 values.
4. PB validation output for a non-empty required symbol set and the exact
   borrow-feed SHA-256.
5. PB V4 gated dry-run manifest referencing the same borrow-feed path and hash.
6. PB launch bundle from the same integration as-of and the same feed hash.
7. Continuous Paper manifest referencing at least 20 hashed session artifacts.

Attestation dates are not authoritative by themselves. Readiness reloads CSV
or Parquet contents, rejects missing/duplicate/non-finite rows, requires a
non-zero factor panel and an explicit positive `adj_close` or
`total_return_index` field, and requires
declared coverage to exactly match the content-derived minimum and maximum.

Before authoring an attestation, inspect each candidate file:

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

The command fingerprints the file before and after content inspection, rejects
a file that changes during the scan, refuses to overwrite its input, and emits
only a relative logical path. Its JSON contains the observed hash, size,
coverage, row/date/ticker counts, non-zero count, and value field. It explicitly
does not attest production provenance, a PIT universe, corporate actions, or
delistings, so it cannot clear readiness by itself.

Schemas are under schemas, including
`schemas/news_enrichment.schema.json` and
`schemas/panel_inspection.schema.json`, and
`schemas/pb_ingestion_manifest.schema.json`. Non-authoritative examples are under
`examples/readiness`. Examples document shape only; example paths and
placeholder values cannot pass runtime hash and provenance checks.

## Operator Command

First apply a production enrichment artifact during the read-only export or
integration:

    python -m evidence_alpha news-enrichment-sqlite
      --database path/to/checkpointed-analysis.db
      --events path/to/events.json
      --commit NEWS_CLAWS_FULL_COMMIT
      --allow-partial
      --output path/to/news_enrichment.json

    python -m evidence_alpha news-export
      --news-base-url http://127.0.0.1:8765
      --limit 200
      --page-size 200
      --enrichment path/to/news_enrichment.json
      --output-dir artifacts/news-real

    python -m evidence_alpha integrate
      --news-base-url http://127.0.0.1:8765
      --news-limit 200
      --news-page-size 200
      --news-enrichment path/to/news_enrichment.json
      ...

Then run the policy only after producing one causally valid real integration:

    python -m evidence_alpha readiness
      --artifact-dir artifacts/integrated-real
      --factor-attestation path/to/factor_attestation.json
      --price-attestation path/to/price_attestation.json
      --pb-ingestion-manifest path/to/pb_ingestion_manifest.json
      --pb-validation path/to/pb_validation.json
      --pb-dry-run-manifest path/to/pb_dry_run_manifest.json
      --pb-launch-bundle path/to/pb_launch_bundle.json
      --paper-manifest path/to/paper/manifest.json
      --output path/to/readiness.json

The command writes JSON on both success and failure. It returns exit code 1
while any hard gate fails and 0 only when the decision is
READY_FOR_LIVE_AUTHORIZATION_REVIEW.

The read-only artifact API exposes the sealed result at:

    GET /api/v1/runs/latest/readiness

## Loop Stage Record

1. DISCOVER: inspected the current branch, maintained News_Claws API contract,
   isolated real database, clean factor clone, and sealed V6.5 evidence.
2. PRODUCT: retained the thin integration and governance service. No duplicate
   trading UI, broker write path, or unsupported Live claim was added.
3. ARCHITECTURE: separated research promotion, release readiness, and explicit
   Live authorization. File hashes and provenance cross-check caller labels.
4. ORCHESTRATE: fixed the minimum evidence set and kept external projects
   read-only.
5. DEVELOP: added current News_Claws compatibility, token-by-environment,
   explicit 200-item no-cursor paging, contract degradation tracking, strict
   read-only SQLite PIT news enrichment, input hashes, readiness CLI/API,
   deterministic `inspect-panel` reports, content-derived factor/price audits,
   historical causal-overlap auditing without raw-news retention, PB ingestion
   provenance with four-way canonical hash agreement,
   attestations, and Paper evidence contracts.
6. VERIFY: 70 tests and 8 subtests pass with warnings as errors. Coverage includes exact
   event references, duplicate and unknown references, strict integer versions,
   placeholder ticker and local URL rejection, effective dates, availability
   chronology, report cutoff enforcement, pending-WAL rejection, read-only
   database invariants, partial-selection coverage, CLI wiring, input and
   enrichment-file tamper detection, false coverage declarations, and raw-close
   substitution. Python compilation, 128-file JSON parsing, twelve JSON Schema
   instance checks, credential scanning, and Git whitespace checks pass.
7. VERIFY DATA: a snapshot-matched 200-event API export and 56-event partial
   publication-time enrichment were produced. Zero direct ticker mappings and
   zero usable novelty values remain; no complete event signal was created.
   The all-report historical audit found zero causally observed overlaps and
   rejected six publication-only overlaps observed in 2026. The market-input
   audit found zero current events with valid T+1 coverage.
8. SEAL: the real inventory, market-input audit, historical overlap audit, and
   current BLOCKED readiness report with 23 hard failures are retained as
   preflight evidence. They do not become a production release.
9. RELEASE: merge, tag, and 8080 replacement remain conditional on every hard
   gate passing in one consistent real-data run.

## Required Work Before Release

1. Extend the real, versioned publication-time artifact with stable novelty
   and verified point-in-time company-to-ticker mappings from an auditable
   production pipeline. The 56-event timestamp artifact is partial and cannot
   create investable signals by itself.
2. Export enough causally distinct events to produce 30 usable primary-window
   observations and 10 chronological OOS observations. With the fixed 30% OOS
   fraction, this requires at least 31 total usable events, not 30 publication
   dates.
3. Generate PIT factor weights and corporate-action-safe prices through every
   selected event return endpoint, including at least T+1.
4. Rerun the unchanged rolling, baseline, placebo, delay, and doubled-cost
   validation gates.
5. Supply a real security-level PB borrow feed, verify its ingestion source and
   mapping, and pass the four-way ingestion, validation, dry-run, and
   launch-bundle hash cross-checks.
6. Accumulate 20 exchange-calendar Paper sessions with no gaps, stale data,
   unresolved exceptions, or reconciliation differences.
7. Obtain independent risk acceptance and explicit Live authorization after
   readiness reports READY_FOR_LIVE_AUTHORIZATION_REVIEW.

Until all seven steps are evidenced, the correct operational state is research
and read-only inspection only.
