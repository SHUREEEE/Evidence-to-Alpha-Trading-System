from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
import csv
import json
from typing import Any

from .contracts import file_digests, load_baseline_weights, load_evidence, load_events, load_mappings, load_prices, select_visible_versions
from .independent_validation import (
    IndependentValidationConfig,
    run_independent_validation,
)
from .models import ContractError, content_hash, parse_datetime
from .oms import OmsConfig, simulate_paper_oms
from .portfolio import PortfolioConfig, build_portfolios
from .signals import SignalConfig, generate_signals, lineage_by_ticker
from .store import EvidenceStore
from .study import run_event_study
from .validation import validate_run


@dataclass(frozen=True)
class RunConfig:
    cutoff: datetime
    benchmark: str = "SPY"
    minimum_event_count: int = 30
    data_classification: str = "unknown"
    oos_fraction: float = 0.30
    minimum_oos_events: int = 10
    rolling_folds: int = 3
    primary_window_days: int = 5
    signal: SignalConfig = field(default_factory=SignalConfig)
    portfolio: PortfolioConfig = field(default_factory=PortfolioConfig)
    oms: OmsConfig = field(default_factory=OmsConfig)

    @property
    def hash(self) -> str:
        payload = {
            "cutoff": self.cutoff.isoformat(),
            "benchmark": self.benchmark,
            "minimum_event_count": self.minimum_event_count,
            "data_classification": self.data_classification,
            "oos_fraction": self.oos_fraction,
            "minimum_oos_events": self.minimum_oos_events,
            "rolling_folds": self.rolling_folds,
            "primary_window_days": self.primary_window_days,
            "signal": asdict(self.signal),
            "portfolio": asdict(self.portfolio),
            "oms": asdict(self.oms),
        }
        return content_hash(payload)


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _artifact_return(summary: dict[str, object]) -> float:
    return float(summary["total_pnl"]) / float(summary["starting_cash"])


def _scenario_summary(name, run_id, cutoff, weights, prices, factor_version, lineage, oms_config):
    _, _, summary = simulate_paper_oms(f"{run_id}-{name}", cutoff, weights, prices, factor_version, lineage, oms_config)
    return summary


def run_pipeline(*, events_path: str | Path, evidence_path: str | Path, mappings_path: str | Path, prices_path: str | Path, baseline_weights_path: str | Path, output_dir: str | Path, config: RunConfig) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    input_paths = {"events": Path(events_path), "evidence": Path(evidence_path), "mappings": Path(mappings_path), "prices": Path(prices_path), "baseline_weights": Path(baseline_weights_path)}
    digests = file_digests(input_paths)
    run_id = f"RUN-{content_hash({'inputs': digests, 'config': config.hash})[:16].upper()}"

    all_events = load_events(events_path)
    evidence = load_evidence(evidence_path)
    mappings = load_mappings(mappings_path)
    prices = load_prices(prices_path)
    baseline_rows = load_baseline_weights(baseline_weights_path)
    if any(row.asof > config.cutoff.date() for row in baseline_rows):
        raise ContractError("baseline weight asof must not be later than run cutoff")
    visible = select_visible_versions(all_events, config.cutoff)
    signals, unmapped = generate_signals(visible, mappings, config.cutoff, config.signal)
    portfolio = build_portfolios(baseline_rows, signals, config.portfolio)
    lineage = lineage_by_ticker(signals)
    orders, fills, oms_summary = simulate_paper_oms(run_id, config.cutoff, portfolio["overlay"], prices, str(portfolio["factor_version"]), lineage, config.oms)

    event_tickers: dict[str, set[str]] = {}
    for signal in signals:
        event_tickers.setdefault(f"{signal.event_id}:v{signal.event_version}", set()).add(signal.ticker)
    event_study = run_event_study(visible, event_tickers, prices, config.benchmark)

    baseline_summary = _scenario_summary("baseline", run_id, config.cutoff, portfolio["baseline"], prices, str(portfolio["factor_version"]), {}, config.oms)
    delayed_summary = _scenario_summary("delay", run_id, config.cutoff + timedelta(days=1), portfolio["overlay"], prices, str(portfolio["factor_version"]), lineage, config.oms)
    double_cost_config = OmsConfig(starting_cash=config.oms.starting_cash, commission_bps=config.oms.commission_bps * 2, slippage_bps=config.oms.slippage_bps * 2)
    double_cost_summary = _scenario_summary("double-cost", run_id, config.cutoff, portfolio["overlay"], prices, str(portfolio["factor_version"]), lineage, double_cost_config)
    tickers = sorted(portfolio["baseline"])
    rotated = [portfolio["overlay_delta"][ticker] for ticker in tickers]
    rotated = rotated[1:] + rotated[:1]
    placebo_weights = {ticker: portfolio["baseline"][ticker] + rotated[index] for index, ticker in enumerate(tickers)}
    placebo_summary = _scenario_summary("placebo", run_id, config.cutoff, placebo_weights, prices, str(portfolio["factor_version"]), {}, config.oms)
    scenarios = {"baseline": _artifact_return(baseline_summary), "overlay": _artifact_return(oms_summary), "one_day_delay": _artifact_return(delayed_summary), "placebo": _artifact_return(placebo_summary), "double_cost": _artifact_return(double_cost_summary)}

    independent_validation = run_independent_validation(
        events=visible,
        event_study=event_study,
        scenarios=scenarios,
        config=IndependentValidationConfig(
            data_classification=config.data_classification,
            minimum_events=config.minimum_event_count,
            oos_fraction=config.oos_fraction,
            minimum_oos_events=config.minimum_oos_events,
            rolling_folds=config.rolling_folds,
            primary_window_days=config.primary_window_days,
        ),
    )
    audit = validate_run(
        config.cutoff,
        all_events,
        visible,
        evidence,
        signals,
        orders,
        fills,
        portfolio,
        oms_summary,
        scenarios,
        independent_validation,
        unmapped,
        config.minimum_event_count,
    )
    report: dict[str, Any] = {
        "run_id": run_id,
        "release": "v0.4.0",
        "cutoff": config.cutoff.isoformat(),
        "created_at": datetime.now().astimezone().isoformat(),
        "decision": audit["decision"],
        "rationale": audit["rationale"],
        "config_hash": config.hash,
        "input_digests": digests,
        "counts": {"event_versions": len(all_events), "visible_events": len(visible), "signals": len(signals), "orders": len(orders), "fills": len(fills), "unmapped": len(unmapped)},
        "portfolio": portfolio,
        "paper_oms": oms_summary,
        "scenarios": scenarios,
        "independent_validation": independent_validation,
        "audit": audit,
        "limitations": ["The MVP uses daily bars and a deterministic paper fill model.", "The demo data is synthetic and cannot support an economic promotion claim.", "No broker, credentials, or real-money execution path is present."],
    }
    signal_payload = [item.to_dict() for item in signals]
    order_payload = [item.to_dict() for item in orders]
    fill_payload = [item.to_dict() for item in fills]
    visible_payload = [item.to_dict() for item in visible]
    _write_json(output / "report.json", report)
    _write_json(output / "audit.json", audit)
    _write_json(output / "visible_events.json", visible_payload)
    _write_json(output / "signals.json", signal_payload)
    _write_json(output / "orders.json", order_payload)
    _write_json(output / "fills.json", fill_payload)
    _write_json(output / "independent_validation.json", independent_validation)
    with (output / "event_study.csv").open("w", encoding="utf-8", newline="") as handle:
        fields = ["event_ref", "ticker", "window_days", "start_date", "end_date", "return", "benchmark_return", "abnormal_return", "status"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(event_study)
    with EvidenceStore(output / "ledger.sqlite3") as store:
        store.register_events(all_events)
        store.write_run(run_id, config.cutoff.isoformat(), str(audit["decision"]), config.hash, report, {"visible_event": visible_payload, "signal": signal_payload, "order": order_payload, "fill": fill_payload})
    return report


def config_from_cutoff(cutoff: str | datetime, **overrides: Any) -> RunConfig:
    parsed = parse_datetime(cutoff, "cutoff") if not isinstance(cutoff, datetime) else cutoff
    return RunConfig(cutoff=parsed, **overrides)
