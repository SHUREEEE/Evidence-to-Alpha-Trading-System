from __future__ import annotations

import argparse
from pathlib import Path
import json
import sys

from .api import serve
from .demo import run_demo
from .pipeline import config_from_cutoff, run_pipeline


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
    run.add_argument("--output-dir", required=True)
    verify = sub.add_parser("verify", help="verify an existing artifact directory")
    verify.add_argument("--artifact-dir", default="artifacts/demo")
    service = sub.add_parser("serve", help="serve artifacts through a read-only HTTP API")
    service.add_argument("--artifact-dir", default="artifacts/demo")
    service.add_argument("--host", default="127.0.0.1")
    service.add_argument("--port", type=int, default=8080)
    service.add_argument("--bootstrap-demo", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "demo":
        report = run_demo(args.output_dir)
        print(json.dumps({"run_id": report["run_id"], "decision": report["decision"], "output_dir": args.output_dir}, indent=2))
        return 0
    if args.command == "run":
        report = run_pipeline(events_path=args.events, evidence_path=args.evidence, mappings_path=args.mappings, prices_path=args.prices, baseline_weights_path=args.baseline_weights, output_dir=args.output_dir, config=config_from_cutoff(args.cutoff, benchmark=args.benchmark, minimum_event_count=args.minimum_event_count))
        print(json.dumps({"run_id": report["run_id"], "decision": report["decision"]}, indent=2))
        return 0
    if args.command == "verify":
        source = Path(args.artifact_dir) / "audit.json"
        if not source.exists():
            print(f"missing audit artifact: {source}", file=sys.stderr)
            return 2
        audit = json.loads(source.read_text(encoding="utf-8"))
        hard_failures = [gate for gate in audit.get("gates", []) if gate.get("severity") == "hard" and not gate.get("passed")]
        print(json.dumps({"decision": audit.get("decision"), "hard_failures": hard_failures}, indent=2))
        return 1 if hard_failures else 0
    if args.command == "serve":
        artifact_dir = Path(args.artifact_dir)
        if args.bootstrap_demo and not (artifact_dir / "report.json").exists():
            run_demo(artifact_dir)
        serve(artifact_dir, args.host, args.port)
        return 0
    return 2

