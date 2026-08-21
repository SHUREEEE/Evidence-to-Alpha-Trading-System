from __future__ import annotations

import argparse
from pathlib import Path
import json
import os
import sys

from .api import serve
from .artifact_inspection import build_panel_inspection_report
from .demo import run_demo
from .integration import config_from_asof, run_integration
from .models import ContractError
from .news_adapter import NewsAdapter, write_news_export
from .news_enrichment import apply_news_enrichment
from .news_enrichment_exporter import export_sqlite_news_enrichment
from .news_overlap import build_news_overlap_audit, write_news_overlap_audit
from .pipeline import config_from_cutoff, run_pipeline
from .readiness import evaluate_release_readiness, write_readiness_report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="evidence-alpha", description="Evidence-to-Alpha research pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="generate deterministic sample data and run the pipeline")
    demo.add_argument("--output-dir", default="artifacts/demo")
    run = sub.add_parser("run", help="run the point-in-time pipeline")
    run.add_argument("--events", required=True)
    run.add_argument("--evidence", required=True)
    run.add_argument("--mappings", required=True)
    run.add_argument("--prices", required=True)
    run.add_argument("--baseline-weights", required=True)
    run.add_argument("--cutoff", required=True, help="timezone-aware ISO-8601 timestamp")
    run.add_argument("--benchmark", default="SPY")
    run.add_argument("--minimum-event-count", type=int, default=30)
    run.add_argument(
        "--data-classification",
        choices=("unknown", "synthetic", "real"),
        default="unknown",
    )
    run.add_argument("--oos-fraction", type=float, default=0.30)
    run.add_argument("--minimum-oos-events", type=int, default=10)
    run.add_argument("--rolling-folds", type=int, default=3)
    run.add_argument(
        "--primary-window-days", type=int, choices=(1, 3, 5, 20), default=5
    )
    run.add_argument("--output-dir", required=True)
    news_export = sub.add_parser(
        "news-export", help="export immutable event versions from the read-only News Claws API"
    )
    news_export.add_argument("--news-base-url", default="http://127.0.0.1:8765")
    news_export.add_argument(
        "--news-token-env",
        default="NEWS_CLAWS_ADMIN_TOKEN",
        help="environment variable containing an optional read-only API token",
    )
    news_export.add_argument("--limit", type=int, default=100)
    news_export.add_argument(
        "--page-size",
        type=int,
        default=100,
        help="event-list page size; current no-cursor News_Claws supports up to 200",
    )
    news_export.add_argument("--allow-synthetic", action="store_true")
    news_export.add_argument(
        "--enrichment",
        help="versioned PIT enrichment JSON for published_at, novelty, and mappings",
    )
    news_export.add_argument("--output-dir", required=True)
    news_sqlite = sub.add_parser(
        "news-enrichment-sqlite",
        help="create PIT published_at enrichment from a read-only News_Claws SQLite snapshot",
    )
    news_sqlite.add_argument("--database", required=True)
    news_sqlite.add_argument("--events", required=True)
    news_sqlite.add_argument("--repository", default="SHUREEEE/News_Claws")
    news_sqlite.add_argument("--commit", required=True)
    news_sqlite.add_argument(
        "--allow-partial",
        action="store_true",
        help="explicitly retain unresolved refs that lack eligible published_at",
    )
    news_sqlite.add_argument("--output", required=True)
    integrate = sub.add_parser(
        "integrate",
        help="fuse News Claws event alpha into multi-factor weights before V4 controls",
    )
    integrate.add_argument("--news-base-url", default="http://127.0.0.1:8765")
    integrate.add_argument(
        "--news-token-env",
        default="NEWS_CLAWS_ADMIN_TOKEN",
        help="environment variable containing an optional read-only API token",
    )
    integrate.add_argument("--factor-root", required=True)
    integrate.add_argument("--weights", help="override V3 weights path, relative to factor root")
    integrate.add_argument("--sectors", help="override V3 sector-map path, relative to factor root")
    integrate.add_argument("--prices", help="override adjusted-close path, relative to factor root")
    integrate.add_argument("--asof", required=True, help="timezone-aware ISO-8601 timestamp")
    integrate.add_argument("--news-limit", type=int, default=100)
    integrate.add_argument(
        "--news-page-size",
        type=int,
        default=100,
        help="event-list page size; use 200 for current no-cursor News_Claws",
    )
    integrate.add_argument("--allow-synthetic-news", action="store_true")
    integrate.add_argument(
        "--news-enrichment",
        help="versioned PIT enrichment JSON for published_at, novelty, and mappings",
    )
    integrate.add_argument("--overlay-scale", type=float, default=0.02)
    integrate.add_argument("--max-overlay-per-name", type=float, default=0.01)
    integrate.add_argument("--overlay-turnover-cap", type=float, default=0.08)
    integrate.add_argument("--cost-bps", type=float, default=5.0)
    integrate.add_argument("--minimum-universe-overlap", type=float, default=0.50)
    integrate.add_argument("--paper-nav", type=float, default=100000.0)
    integrate.add_argument("--skip-parquet-staging", action="store_true")
    integrate.add_argument("--run-factor-v4", action="store_true")
    integrate.add_argument("--run-factor-backtests", action="store_true")
    integrate.add_argument("--output-dir", required=True)
    verify = sub.add_parser("verify", help="verify an existing artifact directory")
    verify.add_argument("--artifact-dir", default="artifacts/demo")
    inspect_panel = sub.add_parser(
        "inspect-panel",
        help="report deterministic content facts for a factor or price panel",
    )
    inspect_panel.add_argument("--input", required=True)
    inspect_panel.add_argument(
        "--kind",
        required=True,
        choices=("factor_weights", "adjusted_prices"),
    )
    inspect_panel.add_argument(
        "--logical-path", help="relative path recorded in the report"
    )
    inspect_panel.add_argument("--output")
    news_overlap = sub.add_parser(
        "audit-news-overlap",
        help="audit causal overlap between a read-only news snapshot and market coverage",
    )
    news_overlap.add_argument("--database", required=True)
    news_overlap.add_argument("--factor-coverage-start", required=True)
    news_overlap.add_argument("--adjusted-price-coverage-end", required=True)
    news_overlap.add_argument("--minimum-event-count", type=int, default=30)
    news_overlap.add_argument("--oos-fraction", type=float, default=0.30)
    news_overlap.add_argument("--minimum-oos-events", type=int, default=10)
    news_overlap.add_argument("--output", required=True)
    readiness = sub.add_parser(
        "readiness",
        help="evaluate fail-closed real-data, PB, and continuous Paper release gates",
    )
    readiness.add_argument("--artifact-dir", required=True)
    readiness.add_argument("--factor-attestation")
    readiness.add_argument("--price-attestation")
    readiness.add_argument("--pb-ingestion-manifest")
    readiness.add_argument("--pb-validation")
    readiness.add_argument("--pb-dry-run-manifest")
    readiness.add_argument("--pb-launch-bundle")
    readiness.add_argument("--paper-manifest")
    readiness.add_argument("--output")
    service = sub.add_parser("serve", help="serve artifacts through a read-only HTTP API")
    service.add_argument("--artifact-dir", default="artifacts/demo")
    service.add_argument("--host", default="127.0.0.1")
    service.add_argument("--port", type=int, default=8080)
    service.add_argument("--bootstrap-demo", action="store_true")
    integrate.add_argument('--benchmark', default='SPY')
    integrate.add_argument(
        '--data-classification',
        choices=('unknown', 'synthetic', 'real'),
        default='unknown',
    )
    integrate.add_argument('--minimum-event-count', type=int, default=30)
    integrate.add_argument('--oos-fraction', type=float, default=0.30)
    integrate.add_argument('--minimum-oos-events', type=int, default=10)
    integrate.add_argument('--rolling-folds', type=int, default=3)
    integrate.add_argument(
        '--primary-window-days',
        type=int,
        choices=(1, 3, 5, 20),
        default=5,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "demo":
        report = run_demo(args.output_dir)
        print(json.dumps({"run_id": report["run_id"], "decision": report["decision"], "output_dir": args.output_dir}, indent=2))
        return 0
    if args.command == "run":
        report = run_pipeline(
            events_path=args.events,
            evidence_path=args.evidence,
            mappings_path=args.mappings,
            prices_path=args.prices,
            baseline_weights_path=args.baseline_weights,
            output_dir=args.output_dir,
            config=config_from_cutoff(
                args.cutoff,
                benchmark=args.benchmark,
                minimum_event_count=args.minimum_event_count,
                data_classification=args.data_classification,
                oos_fraction=args.oos_fraction,
                minimum_oos_events=args.minimum_oos_events,
                rolling_folds=args.rolling_folds,
                primary_window_days=args.primary_window_days,
            ),
        )
        print(json.dumps({"run_id": report["run_id"], "decision": report["decision"]}, indent=2))
        return 0
    if args.command == "news-export":
        bundle = NewsAdapter(
            args.news_base_url, admin_token=os.getenv(args.news_token_env)
        ).export(
            limit=args.limit,
            allow_synthetic=args.allow_synthetic,
            page_size=args.page_size,
        )
        if args.enrichment:
            bundle = apply_news_enrichment(bundle, args.enrichment)
        paths = write_news_export(bundle, args.output_dir)
        print(
            json.dumps(
                {
                    "event_versions": len(bundle.events),
                    "synthetic": bundle.manifest["synthetic"],
                    "output_dir": args.output_dir,
                    "paths": {key: str(value) for key, value in paths.items()},
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "news-enrichment-sqlite":
        enrichment = export_sqlite_news_enrichment(
            database_path=args.database,
            events_path=args.events,
            output_path=args.output,
            repository=args.repository,
            commit=args.commit,
            allow_partial=args.allow_partial,
        )
        print(
            json.dumps(
                {
                    "event_versions": len(enrichment.events),
                    "pipeline_run_id": enrichment.pipeline_run_id,
                    "output": str(enrichment.path),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "integrate":
        report = run_integration(
            news_base_url=args.news_base_url,
            news_admin_token=os.getenv(args.news_token_env),
            news_enrichment_path=args.news_enrichment,
            factor_root=args.factor_root,
            weights_path=args.weights,
            sectors_path=args.sectors,
            prices_path=args.prices,
            output_dir=args.output_dir,
            news_limit=args.news_limit,
            news_page_size=args.news_page_size,
            allow_synthetic_news=args.allow_synthetic_news,
            write_parquet_staging=not args.skip_parquet_staging,
            run_factor_v4=args.run_factor_v4,
            run_factor_backtests=args.run_factor_backtests,
            config=config_from_asof(
                args.asof,
                benchmark=args.benchmark,
                data_classification=args.data_classification,
                minimum_event_count=args.minimum_event_count,
                oos_fraction=args.oos_fraction,
                minimum_oos_events=args.minimum_oos_events,
                rolling_folds=args.rolling_folds,
                primary_window_days=args.primary_window_days,
                overlay_scale=args.overlay_scale,
                max_overlay_per_name=args.max_overlay_per_name,
                overlay_turnover_cap=args.overlay_turnover_cap,
                cost_bps=args.cost_bps,
                minimum_universe_overlap=args.minimum_universe_overlap,
                paper_nav=args.paper_nav,
            ),
        )
        print(
            json.dumps(
                {
                    "run_id": report["run_id"],
                    "status": report["status"],
                    "decision": report["decision"],
                    "live_launch": report["live_launch"]["decision"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1 if report["hard_failures"] else 0
    if args.command == "inspect-panel":
        source = Path(args.input)
        output = Path(args.output) if args.output else None
        try:
            if output and source.resolve() == output.resolve():
                raise ContractError("--output must not overwrite --input")
            report = build_panel_inspection_report(
                source,
                args.kind,
                logical_path=args.logical_path,
            )
            payload = json.dumps(
                report,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            if output:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(payload, encoding="utf-8")
        except (ContractError, OSError) as exc:
            print(
                json.dumps(
                    {"decision": "REJECT", "error": str(exc)},
                    ensure_ascii=False,
                    indent=2,
                ),
                file=sys.stderr,
            )
            return 2
        print(payload)
        return 0
    if args.command == "audit-news-overlap":
        database = Path(args.database)
        output = Path(args.output)
        try:
            if database.resolve() == output.resolve():
                raise ContractError("--output must not overwrite --database")
            report = build_news_overlap_audit(
                database,
                factor_coverage_start=args.factor_coverage_start,
                adjusted_price_coverage_end=args.adjusted_price_coverage_end,
                minimum_event_count=args.minimum_event_count,
                oos_fraction=args.oos_fraction,
                minimum_oos_events=args.minimum_oos_events,
            )
            write_news_overlap_audit(report, output)
        except (ContractError, OSError) as exc:
            print(
                json.dumps(
                    {"decision": "REJECT", "error": str(exc)},
                    ensure_ascii=False,
                    indent=2,
                ),
                file=sys.stderr,
            )
            return 2
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if report["decision"] == "COHORT_CANDIDATE" else 1
    if args.command == "verify":
        source = Path(args.artifact_dir) / "audit.json"
        if not source.exists():
            print(f"missing audit artifact: {source}", file=sys.stderr)
            return 2
        audit = json.loads(source.read_text(encoding="utf-8"))
        hard_failures = [gate for gate in audit.get("gates", []) if gate.get("severity") == "hard" and not gate.get("passed")]
        print(json.dumps({"decision": audit.get("decision"), "hard_failures": hard_failures}, indent=2))
        return 1 if hard_failures else 0
    if args.command == "readiness":
        report = evaluate_release_readiness(
            artifact_dir=args.artifact_dir,
            factor_attestation_path=args.factor_attestation,
            price_attestation_path=args.price_attestation,
            pb_ingestion_manifest_path=args.pb_ingestion_manifest,
            pb_validation_path=args.pb_validation,
            pb_dry_run_manifest_path=args.pb_dry_run_manifest,
            pb_launch_bundle_path=args.pb_launch_bundle,
            paper_manifest_path=args.paper_manifest,
        )
        output = Path(args.output) if args.output else Path(args.artifact_dir) / "readiness.json"
        write_readiness_report(report, output)
        print(
            json.dumps(
                {
                    "decision": report["decision"],
                    "hard_failures": report["hard_failures"],
                    "output": str(output),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1 if report["hard_failures"] else 0
    if args.command == "serve":
        artifact_dir = Path(args.artifact_dir)
        if args.bootstrap_demo and not (artifact_dir / "report.json").exists():
            run_demo(artifact_dir)
        serve(artifact_dir, args.host, args.port)
        return 0
    return 2

