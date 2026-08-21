from __future__ import annotations

import argparse
from pathlib import Path
import json
import os
import sys

from .api import serve
from .demo import run_demo
from .integration import config_from_asof, run_integration
from .news_adapter import NewsAdapter, write_news_export
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
    news_export.add_argument("--allow-synthetic", action="store_true")
    news_export.add_argument("--output-dir", required=True)
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
    integrate.add_argument("--allow-synthetic-news", action="store_true")
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
    readiness = sub.add_parser(
        "readiness",
        help="evaluate fail-closed real-data, PB, and continuous Paper release gates",
    )
    readiness.add_argument("--artifact-dir", required=True)
    readiness.add_argument("--factor-attestation")
    readiness.add_argument("--price-attestation")
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
            limit=args.limit, allow_synthetic=args.allow_synthetic
        )
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
    if args.command == "integrate":
        report = run_integration(
            news_base_url=args.news_base_url,
            news_admin_token=os.getenv(args.news_token_env),
            factor_root=args.factor_root,
            weights_path=args.weights,
            sectors_path=args.sectors,
            prices_path=args.prices,
            output_dir=args.output_dir,
            news_limit=args.news_limit,
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

