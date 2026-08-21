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
  commit, pipeline run, methodology, and availability timestamp;
- at least 30 usable primary-window events and 10 chronological OOS events;
- at least three rolling folds plus placebo, delay, baseline, and doubled-cost gates;
- point-in-time factor weights with a matching file hash and production provenance;
- corporate-action-safe prices through the required event T+1 return endpoint;
- one real PB borrow feed shared by validation and the gated V4 dry run, with
  the same SHA-256 declared by validation, dry run, and launch bundle;
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
F16FEB1F... snapshot. It is retained as historical preflight evidence and is
explicitly marked as not matching the current database snapshot. That export
contains 104 evidence records, zero direct ticker mappings, 15 industry-only
mappings, 85 unmapped events, and missing novelty for all 100 events. It does
not claim to be a current full-database export. Industry-only events are not
equivalent to verified company/ticker mappings.

The new enrichment path does not invent these missing values. It accepts only
an external production artifact that names exact event versions, records when
each value became available, rejects local/example URLs and placeholder
tickers, enforces effective-dated mappings, and moves event `observed_at`
forward to prevent lookahead. Partial enrichment remains degraded.

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

The exported real news is observed on 2026-08-20, so the required T+1 date is
2026-08-21 or later. The available 2026-07-17 cutoff cannot clear causality,
coverage, corporate-action, or Paper freshness gates.

## Readiness Inputs

The integration may carry one optional upstream news-enrichment artifact. Its
hash and production provenance are reloaded and cross-checked by readiness;
all unresolved event references must be empty. The readiness command also
accepts the integration artifact directory plus six independent evidence
files:

1. Factor attestation with the exact factor-file SHA-256, coverage dates,
   immutable source commit and pipeline run, and PIT universe assertions.
2. Price attestation with the exact price-file SHA-256, coverage dates,
   licensed provider provenance, splits, cash and special dividends,
   delistings, and no unresolved exceptions.
3. PB validation output for a non-empty required symbol set and the exact
   borrow-feed SHA-256.
4. PB V4 gated dry-run manifest referencing the same borrow-feed path and hash.
5. PB launch bundle from the same integration as-of and the same feed hash.
6. Continuous Paper manifest referencing at least 20 hashed session artifacts.

Schemas are under schemas, including
`schemas/news_enrichment.schema.json`. Non-authoritative examples are under
`examples/readiness`. Examples document shape only; example paths and
placeholder values cannot pass runtime hash and provenance checks.

## Operator Command

First apply a production enrichment artifact during the read-only export or
integration:

    python -m evidence_alpha news-export
      --news-base-url http://127.0.0.1:8765
      --enrichment path/to/news_enrichment.json
      --output-dir artifacts/news-real

    python -m evidence_alpha integrate
      --news-base-url http://127.0.0.1:8765
      --news-enrichment path/to/news_enrichment.json
      ...

Then run the policy only after producing one causally valid real integration:

    python -m evidence_alpha readiness
      --artifact-dir artifacts/integrated-real
      --factor-attestation path/to/factor_attestation.json
      --price-attestation path/to/price_attestation.json
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
   contract degradation tracking, strict PIT news enrichment, readiness
   CLI/API, attestations, and Paper evidence contracts.
6. VERIFY: 44 tests pass with warnings as errors. Coverage includes exact
   event references, duplicate and unknown references, strict integer versions,
   placeholder ticker and local URL rejection, effective dates, availability
   chronology, partial-degradation retention, CLI wiring, signal generation,
   and enrichment-file tamper detection.
7. SEAL: the real inventory and current BLOCKED readiness report are retained
   as preflight evidence. They do not become a production release.
8. RELEASE: merge, tag, and 8080 replacement remain conditional on every hard
   gate passing in one consistent real-data run.

## Required Work Before Release

1. Produce a real, versioned enrichment artifact containing stable novelty and
   verified point-in-time company-to-ticker mappings from an auditable
   production pipeline. The implemented mechanism is not evidence by itself.
2. Export enough causally distinct events to produce 30 usable primary-window
   observations and 10 chronological OOS observations.
3. Generate PIT factor weights and corporate-action-safe prices through every
   selected event return endpoint, including at least T+1.
4. Rerun the unchanged rolling, baseline, placebo, delay, and doubled-cost
   validation gates.
5. Supply a real security-level PB borrow feed and pass validation, dry run, and
   launch-bundle cross-checks.
6. Accumulate 20 exchange-calendar Paper sessions with no gaps, stale data,
   unresolved exceptions, or reconciliation differences.
7. Obtain independent risk acceptance and explicit Live authorization after
   readiness reports READY_FOR_LIVE_AUTHORIZATION_REVIEW.

Until all seven steps are evidenced, the correct operational state is research
and read-only inspection only.
