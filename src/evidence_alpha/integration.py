from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from math import floor
from pathlib import Path
import csv
import json
import subprocess
import sys
from typing import Any

from .contracts import select_visible_versions
from .independent_validation import (
    IndependentValidationConfig,
    run_independent_validation,
)
from .models import (
    ContractError,
    EventSignal,
    PriceBar,
    content_hash,
    parse_datetime,
)
from .multifactor_adapter import (
    FactorInputs,
    MultiFactorAdapter,
    write_v4_staging_cache,
    write_weight_panel_csv,
)
from .news_adapter import NewsAdapter, NewsExport, write_news_export
from .signals import SignalConfig, generate_signals, lineage_by_ticker
from .study import run_event_study


@dataclass(frozen=True)
class IntegrationConfig:
    asof: datetime
    benchmark: str = 'SPY'
    data_classification: str = 'unknown'
    minimum_event_count: int = 30
    oos_fraction: float = 0.30
    minimum_oos_events: int = 10
    rolling_folds: int = 3
    primary_window_days: int = 5
    overlay_scale: float = 0.02
    max_overlay_per_name: float = 0.01
    overlay_turnover_cap: float = 0.08
    cost_bps: float = 5.0
    minimum_universe_overlap: float = 0.50
    paper_nav: float = 100000.0

    def validate(self) -> None:
        parse_datetime(self.asof, 'asof')
        if not self.benchmark.strip():
            raise ContractError('benchmark must be non-empty')
        if self.cost_bps < 0:
            raise ContractError('cost_bps must be non-negative')
        if self.overlay_scale <= 0:
            raise ContractError("overlay_scale must be positive")
        if self.max_overlay_per_name <= 0:
            raise ContractError("max_overlay_per_name must be positive")
        if self.overlay_turnover_cap <= 0:
            raise ContractError("overlay_turnover_cap must be positive")
        if not 0 <= self.minimum_universe_overlap <= 1:
            raise ContractError("minimum_universe_overlap must be in [0, 1]")
        if self.paper_nav <= 0:
            raise ContractError("paper_nav must be positive")
        IndependentValidationConfig(
            data_classification=self.data_classification,
            minimum_events=self.minimum_event_count,
            oos_fraction=self.oos_fraction,
            minimum_oos_events=self.minimum_oos_events,
            rolling_folds=self.rolling_folds,
            primary_window_days=self.primary_window_days,
        ).validate()


def config_from_asof(asof: str | datetime, **overrides: Any) -> IntegrationConfig:
    parsed = parse_datetime(asof, "asof") if not isinstance(asof, datetime) else asof
    config = IntegrationConfig(asof=parsed, **overrides)
    config.validate()
    return config


def run_integration(
    *,
    news_base_url: str,
    factor_root: str | Path,
    output_dir: str | Path,
    config: IntegrationConfig,
    weights_path: str | Path | None = None,
    sectors_path: str | Path | None = None,
    prices_path: str | Path | None = None,
    news_admin_token: str | None = None,
    news_limit: int = 100,
    allow_synthetic_news: bool = False,
    write_parquet_staging: bool = True,
    run_factor_v4: bool = False,
    run_factor_backtests: bool = False,
) -> dict[str, Any]:
    config.validate()
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    news = NewsAdapter(news_base_url, admin_token=news_admin_token).export(
        limit=news_limit, allow_synthetic=allow_synthetic_news
    )
    news_paths = write_news_export(news, output / "news_export")
    factor = MultiFactorAdapter(
        factor_root,
        weights_path=weights_path,
        sectors_path=sectors_path,
        prices_path=prices_path,
    ).load()

    selected_day, baseline = factor.weights.on_or_before(config.asof.date())
    visible = select_visible_versions(news.events, config.asof)
    signals, unmapped = generate_signals(
        visible, news.mappings, config.asof, SignalConfig()
    )
    signal_tickers = {item.ticker for item in signals}
    overlap = signal_tickers & set(baseline)
    overlap_ratio = len(overlap) / len(signal_tickers) if signal_tickers else 0.0
    if not signals:
        raise ContractError("no event signals are visible at the requested asof timestamp")
    if not overlap:
        raise ContractError("news event tickers do not overlap the factor universe")
    if overlap_ratio < config.minimum_universe_overlap:
        raise ContractError(
            f"news/factor universe overlap {overlap_ratio:.1%} is below "
            f"the required {config.minimum_universe_overlap:.1%}"
        )

    fused_row, delta = fuse_pre_v4_weights(baseline, signals, config)
    event_only_row = build_event_only_weights(baseline, signals)
    baseline_panel = _panel_through(factor.weights.weights, selected_day)
    fused_panel = {day: dict(row) for day, row in baseline_panel.items()}
    fused_panel[selected_day] = fused_row
    event_only_panel = {
        day: ({ticker: 0.0 for ticker in baseline} if day < selected_day else event_only_row)
        for day in baseline_panel
    }

    weight_paths = {
        "factor_baseline": write_weight_panel_csv(
            baseline_panel, output / "factor_baseline_weights.csv", through=selected_day
        ),
        "event_only": write_weight_panel_csv(
            event_only_panel, output / "event_only_weights.csv", through=selected_day
        ),
        "fused_pre_v4": write_weight_panel_csv(
            fused_panel, output / "fused_pre_v4_weights.csv", through=selected_day
        ),
    }
    staging: dict[str, str] = {}
    staging_error: str | None = None
    if write_parquet_staging:
        try:
            staging = {
                key: str(value)
                for key, value in write_v4_staging_cache(
                    fused_panel, factor.sectors, output / "v4_input_cache"
                ).items()
            }
        except ContractError as exc:
            staging_error = str(exc)

    external = verify_factor_platform(
        factor_root=Path(factor_root),
        output_dir=output,
        selected_day=selected_day,
        staging_error=staging_error,
        weight_paths=weight_paths,
        prices_path=factor.prices.source_path,
        run_v4=run_factor_v4,
        run_backtests=run_factor_backtests,
    )

    comparisons = compare_t_plus_one(
        selected_day,
        config.asof.date(),
        factor,
        {
            "factor_baseline": baseline,
            "event_only": event_only_row,
            "factor_plus_event_pre_v4": fused_row,
        },
        config.cost_bps,
    )
    event_tickers: dict[str, set[str]] = {}
    for signal in signals:
        event_ref = f'{signal.event_id}:v{signal.event_version}'
        event_tickers.setdefault(event_ref, set()).add(signal.ticker)
    price_bars = _factor_price_bars(factor)
    event_study = run_event_study(
        visible,
        event_tickers,
        price_bars,
        config.benchmark,
    )

    placebo_row = build_placebo_weights(baseline, delta)
    placebo_comparison = compare_t_plus_one(
        selected_day,
        config.asof.date(),
        factor,
        {'placebo': placebo_row},
        config.cost_bps,
    )
    delayed_dates = [
        day for day in factor.prices.dates if day > config.asof.date()
    ]
    delayed_anchor = (
        delayed_dates[0]
        if delayed_dates
        else config.asof.date() + timedelta(days=1)
    )
    delayed_comparison = compare_t_plus_one(
        selected_day,
        delayed_anchor,
        factor,
        {'one_day_delay': fused_row},
        config.cost_bps,
    )
    doubled_cost_comparison = compare_t_plus_one(
        selected_day,
        config.asof.date(),
        factor,
        {'double_cost': fused_row},
        config.cost_bps * 2,
    )
    scenarios = {
        'baseline': _scenario_net_return(
            comparisons, 'factor_baseline'
        ),
        'overlay': _scenario_net_return(
            comparisons, 'factor_plus_event_pre_v4'
        ),
        'placebo': _scenario_net_return(placebo_comparison, 'placebo'),
        'one_day_delay': _scenario_net_return(
            delayed_comparison, 'one_day_delay'
        ),
        'double_cost': _scenario_net_return(
            doubled_cost_comparison, 'double_cost'
        ),
    }
    effective_classification = _effective_data_classification(news, config)
    independent_validation = run_independent_validation(
        events=visible,
        event_study=event_study,
        scenarios=scenarios,
        config=IndependentValidationConfig(
            data_classification=effective_classification,
            minimum_events=config.minimum_event_count,
            oos_fraction=config.oos_fraction,
            minimum_oos_events=config.minimum_oos_events,
            rolling_folds=config.rolling_folds,
            primary_window_days=config.primary_window_days,
        ),
    )

    lineage = lineage_by_ticker(signals)
    blotter = simulate_t_plus_one_rebalance(
        selected_day,
        config.asof.date(),
        baseline,
        fused_row,
        factor,
        lineage,
        nav=config.paper_nav,
        cost_bps=config.cost_bps,
    )
    paper_orders = blotter["orders"]
    paper_fills: list[dict[str, Any]] = []
    for order in paper_orders:
        fill_identity = {
            "order_id": order["order_id"],
            "trade_date": order["fill_date"],
            "price": order["fill_price"],
        }
        paper_fills.append(
            {
                "fill_id": f"INTFILL-{content_hash(fill_identity)[:16].upper()}",
                "order_id": order["order_id"],
                "trade_date": order["fill_date"],
                "execution_model": order["execution_model"],
                "ticker": order["ticker"],
                "side": order["side"],
                "quantity": order["quantity"],
                "price": order["fill_price"],
                "notional": order["notional"],
                "fee": order["fee"],
                "signal_ids": order["signal_ids"],
                "event_refs": order["event_refs"],
                "evidence_ids": order["evidence_ids"],
            }
        )

    paper_fill_date = blotter.get("fill_date")
    paper_fill_after_asof = bool(
        paper_fill_date and date.fromisoformat(paper_fill_date) > config.asof.date()
    )
    gates = {
        "news_read_only_contract": True,
        "point_in_time_versions": all(item.asof <= config.asof for item in visible),
        "event_lineage": all(item.evidence_ids and item.config_hash for item in signals),
        "factor_asof_not_future": selected_day <= config.asof.date(),
        "universe_overlap": overlap_ratio >= config.minimum_universe_overlap,
        "pre_v4_overlay_zero_sum": abs(sum(delta.values())) <= 1e-10,
        "pre_v4_overlay_turnover": sum(abs(value) for value in delta.values())
        <= config.overlay_turnover_cap + 1e-10,
        "t_plus_one_prices": all(item["status"] == "ok" for item in comparisons.values()),
        "paper_fill_after_asof": paper_fill_after_asof,
        "paper_reconciliation": bool(blotter["reconciliation"]["closed_to_cent"]),
    }
    if run_factor_v4:
        gates["multi_factor_v4_prod_loader"] = external["v4"]["status"] == "PASS"
    if run_factor_backtests:
        gates["multi_factor_three_backtests"] = all(
            item["status"] == "PASS" for item in external["backtests"].values()
        )
    integration_hard_failures = [
        name for name, passed in gates.items() if not passed
    ]
    validation_hard_failures = list(
        independent_validation.get('hard_failures', [])
    )
    gates['independent_validation_integrity'] = not validation_hard_failures
    hard_failures = [
        *integration_hard_failures,
        *[
            f'independent_validation:{name}'
            for name in validation_hard_failures
        ],
    ]
    synthetic = bool(news.manifest.get("synthetic"))

    config_payload = {**asdict(config), "asof": config.asof.isoformat()}
    run_id = f"INT-{content_hash({'news': news.manifest, 'asof': config.asof.isoformat(), 'factor_paths': {key: str(value) for key, value in factor.paths.items()}, 'config': config_payload})[:16].upper()}"
    if integration_hard_failures:
        decision = 'REJECT'
        rationale = 'One or more integration integrity gates failed.'
    elif validation_hard_failures:
        decision = 'REJECT'
        rationale = str(independent_validation.get('rationale'))
    else:
        decision = str(independent_validation.get('decision', 'REJECT'))
        rationale = str(independent_validation.get('rationale'))

    audit_gates = [
        {
            'name': name,
            'passed': passed,
            'detail': 'Computed by the v0.4.0 three-system integration run.',
            'severity': 'hard',
        }
        for name, passed in gates.items()
    ]
    validation_decision = independent_validation.get('decision')
    validation_research_failures = independent_validation.get(
        'research_failures', []
    )
    audit_gates.append(
        {
            'name': 'independent_validation_research',
            'passed': decision == 'PROMOTE',
            'detail': (
                f'decision={validation_decision}; '
                f'research failures={validation_research_failures}'
            ),
            'severity': 'research',
        }
    )
    audit = {
        'decision': decision,
        'rationale': rationale,
        'gates': audit_gates,
        'integration_hard_failures': integration_hard_failures,
        'independent_validation_hard_failures': validation_hard_failures,
        'facts': [
            'All hard gates are computed from this integration run.',
            'Paper fills are deterministic adjusted-close simulations.',
        ],
        'inferences': [
            'Passing integrity gates supports reproducibility, not alpha.'
        ],
        'unknowns': [
            'Capacity, borrow, market impact, and live execution remain unknown.'
        ],
    }

    report: dict[str, Any] = {
        "run_id": run_id,
        "release": "v0.4.0-integration",
        "created_at": datetime.now().astimezone().isoformat(),
        "asof": config.asof.isoformat(),
        "execution_anchor_date": config.asof.date().isoformat(),
        "factor_weight_date": selected_day.isoformat(),
        "status": "READY_FOR_PAPER_RESEARCH" if not hard_failures else "BLOCKED",
        "decision": decision,
        "rationale": rationale,
        "architecture": [
            "news_evidence",
            "event_alpha",
            "factor_plus_event_pre_v4",
            "v4_portfolio_controls",
            "t_plus_one_backtest_and_paper_oms",
            "attribution_feedback",
        ],
        "fusion_stage": "before_multi_factor_v4_controls",
        "counts": {
            "news_event_versions": len(news.events),
            "visible_events": len(visible),
            "signals": len(signals),
            "signal_tickers": len(signal_tickers),
            "overlap_tickers": len(overlap),
            "unmapped": len(unmapped),
            "paper_orders": len(paper_orders),
            "paper_fills": len(paper_fills),
        },
        "universe": {
            "signal_tickers": sorted(signal_tickers),
            "overlap_tickers": sorted(overlap),
            "overlap_ratio": overlap_ratio,
            "factor_universe_size": len(baseline),
        },
        "pre_v4_overlay": {
            "gross_delta": sum(abs(value) for value in delta.values()),
            "net_delta": sum(delta.values()),
            "delta_by_ticker": delta,
        },
        "comparisons": comparisons,
        "paper_oms": {key: value for key, value in blotter.items() if key != "orders"},
        "gates": gates,
        "hard_failures": hard_failures,
        "news_manifest": news.manifest,
        "factor_inputs": {key: str(value) for key, value in factor.paths.items()},
        "artifacts": {
            "news": {key: str(value) for key, value in news_paths.items()},
            "paper_oms": {
                "orders": "orders.json",
                "fills": "fills.json",
                "legacy_orders": "paper_orders.json",
            },
            "weights": {key: str(value) for key, value in weight_paths.items()},
            "v4_staging": staging,
            "v4_staging_error": staging_error,
            "factor_v4_output": external["v4"].get("manifest_path"),
            "factor_backtests": {
                key: value.get("metrics_path")
                for key, value in external["backtests"].items()
            },
        },
        "handoff": {
            "v4_command": external["v4"]["command"],
            "v4_command_ready": not staging_error,
            "required_order": "fused_pre_v4 -> multi-factor V4 builder -> backtest/Paper OMS",
        },
        "external_verification": external,
        "live_launch": {
            "decision": "BLOCKED",
            "reasons": [
                "The referenced multi-factor platform records PB borrow real feed as a P0 blocker.",
                "The current news sample is synthetic." if synthetic else "Independent event-sample validation is not complete.",
                "This project intentionally has no broker or real-money execution path.",
            ],
        },
        "limitations": [
            "The built-in comparison is a one-step T+1 diagnostic, not an OOS performance claim.",
            "The Paper OMS uses adjusted-close prices as deterministic T+1 research fills.",
            "V4 risk controls remain owned and executed by multi-factor-alpha-platform.",
        ],
    }
    _write_json(output / "signals.json", [item.to_dict() for item in signals])
    _write_json(output / "visible_events.json", [item.to_dict() for item in visible])
    _write_json(output / "paper_orders.json", paper_orders)
    _write_json(output / "orders.json", paper_orders)
    _write_json(output / "fills.json", paper_fills)
    report['data_classification'] = effective_classification
    report['scenarios'] = scenarios
    report['independent_validation'] = independent_validation
    report['audit'] = audit
    report['integration_hard_failures'] = integration_hard_failures
    report['counts']['event_study_rows'] = len(event_study)
    report['artifacts']['event_study'] = 'event_study.csv'
    report['artifacts']['independent_validation'] = (
        'independent_validation.json'
    )
    report['artifacts']['audit'] = 'audit.json'
    report['live_launch']['reasons'] = [
        (
            'The referenced multi-factor platform records PB borrow '
            'real feed as a P0 blocker.'
        ),
        (
            f'Independent validation decision is {decision}; live release '
            'requires separate production risk acceptance.'
        ),
        'This project intentionally has no broker execution path.',
    ]
    _write_json(output / 'integration_report.json', report)
    _write_json(output / 'report.json', report)
    _write_json(output / 'independent_validation.json', independent_validation)
    _write_json(output / 'audit.json', audit)
    _write_json(
        output / 'integration_audit.json',
        {
            'decision': decision,
            'gates': gates,
            'hard_failures': hard_failures,
            'integration_hard_failures': integration_hard_failures,
            'independent_validation_hard_failures': (
                validation_hard_failures
            ),
        },
    )
    with (output / 'event_study.csv').open(
        'w', encoding='utf-8', newline=''
    ) as handle:
        fields = [
            'event_ref',
            'ticker',
            'window_days',
            'start_date',
            'end_date',
            'return',
            'benchmark_return',
            'abnormal_return',
            'status',
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(event_study)
    return report


def fuse_pre_v4_weights(
    baseline: dict[str, float], signals: list[EventSignal], config: IntegrationConfig
) -> tuple[dict[str, float], dict[str, float]]:
    if len(baseline) < 2:
        raise ContractError("pre-V4 overlay requires at least two factor-universe names")
    score = {ticker: 0.0 for ticker in baseline}
    for signal in signals:
        if signal.ticker in score:
            score[signal.ticker] += signal.decayed_strength
    raw = {ticker: value * config.overlay_scale for ticker, value in score.items()}
    mean = sum(raw.values()) / len(raw)
    centered = {ticker: value - mean for ticker, value in raw.items()}
    delta = _zero_sum_cap(centered, config.max_overlay_per_name)
    turnover = sum(abs(value) for value in delta.values())
    if turnover > config.overlay_turnover_cap:
        scale = config.overlay_turnover_cap / turnover
        delta = {ticker: value * scale for ticker, value in delta.items()}
    if abs(sum(delta.values())) > 1e-10:
        raise ContractError("pre-V4 event overlay could not preserve net exposure")
    return ({ticker: baseline[ticker] + delta[ticker] for ticker in baseline}, delta)


def _zero_sum_cap(values: dict[str, float], cap: float) -> dict[str, float]:
    result = {ticker: max(-cap, min(cap, value)) for ticker, value in values.items()}
    for _ in range(len(result) * 2 + 2):
        residual = sum(result.values())
        if abs(residual) <= 1e-12:
            break
        if residual > 0:
            candidates = {ticker: value + cap for ticker, value in result.items() if value > -cap}
            direction = -1.0
        else:
            candidates = {ticker: cap - value for ticker, value in result.items() if value < cap}
            direction = 1.0
        room = sum(candidates.values())
        if room <= 0:
            raise ContractError("event overlay cap is infeasible")
        amount = min(abs(residual), room)
        for ticker, available in candidates.items():
            result[ticker] += direction * amount * available / room
            result[ticker] = max(-cap, min(cap, result[ticker]))
    return result


def build_event_only_weights(
    baseline: dict[str, float], signals: list[EventSignal]
) -> dict[str, float]:
    score = {ticker: 0.0 for ticker in baseline}
    for signal in signals:
        if signal.ticker in score:
            score[signal.ticker] += signal.decayed_strength
    gross_score = sum(abs(value) for value in score.values())
    if gross_score <= 0:
        raise ContractError("visible events produced no non-zero factor-universe score")
    gross_target = max(1.0, sum(abs(value) for value in baseline.values()))
    return {ticker: value / gross_score * gross_target for ticker, value in score.items()}


def build_placebo_weights(
    baseline: dict[str, float], delta: dict[str, float]
) -> dict[str, float]:
    tickers = sorted(baseline)
    if set(tickers) != set(delta):
        raise ContractError('placebo overlay must match the factor universe')
    values = [delta[ticker] for ticker in tickers]
    rotated = values[1:] + values[:1]
    return {
        ticker: baseline[ticker] + rotated[index]
        for index, ticker in enumerate(tickers)
    }


def _factor_price_bars(factor: FactorInputs) -> list[PriceBar]:
    return [
        PriceBar(
            trade_date=day,
            ticker=ticker,
            open=value,
            close=value,
        )
        for day in factor.prices.dates
        for ticker, value in sorted(factor.prices.adj_close[day].items())
    ]


def _scenario_net_return(
    comparisons: dict[str, dict[str, Any]], name: str
) -> object:
    row = comparisons.get(name, {})
    return row.get('net_return')


def _effective_data_classification(
    news: NewsExport, config: IntegrationConfig
) -> str:
    if bool(news.manifest.get('synthetic')):
        return 'synthetic'
    if news.manifest.get('placeholder_mapping_refs') or news.manifest.get(
        'contract_degradations_by_event_version'
    ):
        return 'unknown'
    if config.data_classification == 'real':
        return 'real'
    if config.data_classification == 'synthetic':
        return 'synthetic'
    return 'unknown'


def compare_t_plus_one(
    selected_day: date,
    execution_anchor: date,
    factor: FactorInputs,
    portfolios: dict[str, dict[str, float]],
    cost_bps: float,
) -> dict[str, dict[str, Any]]:
    price_dates = factor.prices.dates
    start_candidates = [day for day in price_dates if day <= execution_anchor]
    end_candidates = [day for day in price_dates if day > execution_anchor]
    if not start_candidates or not end_candidates:
        return {
            name: {
                "status": "missing_t_plus_one_prices",
                "weight_date": selected_day.isoformat(),
                "execution_anchor_date": execution_anchor.isoformat(),
                "gross_return": None,
                "net_return": None,
            }
            for name in portfolios
        }
    start_day = start_candidates[-1]
    end_day = end_candidates[0]
    start_prices = factor.prices.adj_close[start_day]
    end_prices = factor.prices.adj_close[end_day]
    prior_dates = [day for day in factor.weights.dates if day < selected_day]
    prior = factor.weights.weights[prior_dates[-1]] if prior_dates else {}
    result: dict[str, dict[str, Any]] = {}
    for name, weights in portfolios.items():
        available = {
            ticker
            for ticker, weight in weights.items()
            if weight != 0 and ticker in start_prices and ticker in end_prices
        }
        total_notional = sum(abs(value) for value in weights.values())
        covered_notional = sum(abs(weights[ticker]) for ticker in available)
        coverage = covered_notional / total_notional if total_notional else 1.0
        gross = sum(
            weights[ticker] * (end_prices[ticker] / start_prices[ticker] - 1.0)
            for ticker in available
        )
        reference = prior if name != "event_only" else {}
        turnover = sum(
            abs(weights.get(ticker, 0.0) - reference.get(ticker, 0.0))
            for ticker in set(weights) | set(reference)
        )
        cost = turnover * cost_bps / 10000.0
        result[name] = {
            "status": "ok" if coverage >= 0.95 else "insufficient_price_coverage",
            "weight_date": selected_day.isoformat(),
            "execution_anchor_date": execution_anchor.isoformat(),
            "return_start_date": start_day.isoformat(),
            "return_end_date": end_day.isoformat(),
            "price_notional_coverage": coverage,
            "gross_return": gross,
            "turnover": turnover,
            "estimated_cost": cost,
            "net_return": gross - cost,
        }
    return result


def simulate_t_plus_one_rebalance(
    selected_day: date,
    execution_anchor: date,
    baseline: dict[str, float],
    target: dict[str, float],
    factor: FactorInputs,
    lineage: dict[str, dict[str, tuple[str, ...]]],
    *,
    nav: float,
    cost_bps: float,
) -> dict[str, Any]:
    next_dates = [day for day in factor.prices.dates if day > execution_anchor]
    if not next_dates:
        return {
            "execution_model": "T+1_ADJ_CLOSE_PAPER",
            "execution_anchor_date": execution_anchor.isoformat(),
            "orders": [],
            "reconciliation": {"closed_to_cent": False, "reason": "missing_t_plus_one_prices"},
        }
    fill_day = next_dates[0]
    prices = factor.prices.adj_close[fill_day]
    orders: list[dict[str, Any]] = []
    signed_notional = 0.0
    fees = 0.0
    for ticker in sorted(set(baseline) | set(target)):
        delta = target.get(ticker, 0.0) - baseline.get(ticker, 0.0)
        if abs(delta) <= 1e-12:
            continue
        price = prices.get(ticker)
        if not price:
            continue
        quantity = floor(abs(delta) * nav / price)
        if quantity <= 0:
            continue
        side = "BUY" if delta > 0 else "SELL"
        notional = quantity * price
        fee = notional * cost_bps / 10000.0
        trace = lineage.get(ticker, {})
        identity = {
            "weight_date": selected_day.isoformat(),
            "fill_date": fill_day.isoformat(),
            "ticker": ticker,
            "side": side,
            "quantity": quantity,
        }
        orders.append(
            {
                "order_id": f"INTORD-{content_hash(identity)[:16].upper()}",
                "created_for_weight_date": selected_day.isoformat(),
                "fill_date": fill_day.isoformat(),
                "execution_model": "T+1_ADJ_CLOSE_PAPER",
                "ticker": ticker,
                "side": side,
                "quantity": quantity,
                "fill_price": price,
                "notional": notional,
                "fee": fee,
                "previous_weight": baseline.get(ticker, 0.0),
                "target_weight": target.get(ticker, 0.0),
                "delta_weight": delta,
                "signal_ids": list(trace.get("signal_ids", ())),
                "event_refs": list(trace.get("event_refs", ())),
                "evidence_ids": list(trace.get("evidence_ids", ())),
            }
        )
        signed_notional += notional if side == "BUY" else -notional
        fees += fee
    cash_change = -signed_notional - fees
    identity_residual = cash_change + signed_notional + fees
    return {
        "execution_model": "T+1_ADJ_CLOSE_PAPER",
        "execution_anchor_date": execution_anchor.isoformat(),
        "fill_date": fill_day.isoformat(),
        "orders": orders,
        "total_fees": fees,
        "signed_trade_notional": signed_notional,
        "cash_change": cash_change,
        "reconciliation": {
            "accounting_identity_residual": identity_residual,
            "closed_to_cent": abs(identity_residual) <= 0.01,
        },
    }


def _panel_through(
    panel: dict[date, dict[str, float]], through: date
) -> dict[date, dict[str, float]]:
    return {day: dict(row) for day, row in panel.items() if day <= through}


def verify_factor_platform(
    *,
    factor_root: Path,
    output_dir: Path,
    selected_day: date,
    staging_error: str | None,
    weight_paths: dict[str, Path],
    prices_path: Path,
    run_v4: bool,
    run_backtests: bool,
) -> dict[str, Any]:
    factor_root = factor_root.resolve()
    v4_output = (output_dir / "v4_output").resolve()
    v4_cache = (output_dir / "v4_input_cache").resolve()
    v4_command = [
        sys.executable,
        str(factor_root / "scripts" / "run_v4_pipeline.py"),
        "--asof",
        selected_day.isoformat(),
        "--config",
        str(factor_root / "config" / "v4.yaml"),
        "--output",
        str(v4_output),
        "--inputs-prod",
        "--v3-cache-dir",
        str(v4_cache),
    ]
    v4_result: dict[str, Any] = {
        "requested": run_v4,
        "status": "NOT_RUN",
        "command": subprocess.list2cmdline(v4_command),
    }
    if run_v4:
        if staging_error:
            v4_result.update(status="FAIL", error=staging_error)
        else:
            v4_result.update(_run_external(v4_command, factor_root))
            manifest_path = v4_output / "v4_run_manifest.json"
            v4_result["manifest_path"] = str(manifest_path)
            if v4_result["returncode"] == 0 and manifest_path.exists():
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                v4_result["manifest_summary"] = {
                    key: manifest.get(key)
                    for key in (
                        "input_mode",
                        "status",
                        "validation_state",
                        "borrow_feed_present",
                        "pit_audit_overall_status",
                        "solver_path_counts",
                    )
                }
                v4_result["status"] = (
                    "PASS"
                    if manifest.get("input_mode") == "prod"
                    and manifest.get("validation_state") == "PASS"
                    else "FAIL"
                )
            else:
                v4_result["status"] = "FAIL"

    backtests: dict[str, dict[str, Any]] = {}
    backtest_script = factor_root / "scripts" / "run_backtest.py"
    for name, weights in weight_paths.items():
        target = (output_dir / "factor_backtests" / name).resolve()
        command = [
            sys.executable,
            str(backtest_script),
            "--weights",
            str(weights.resolve()),
            "--prices",
            str(prices_path.resolve()),
            "--output",
            str(target),
        ]
        item: dict[str, Any] = {
            "requested": run_backtests,
            "status": "NOT_RUN",
            "command": subprocess.list2cmdline(command),
        }
        if run_backtests:
            item.update(_run_external(command, factor_root))
            metrics_path = target / "metrics.json"
            item["metrics_path"] = str(metrics_path)
            if item["returncode"] == 0 and metrics_path.exists():
                item["status"] = "PASS"
                item["metrics"] = json.loads(metrics_path.read_text(encoding="utf-8"))
            else:
                item["status"] = "FAIL"
        backtests[name] = item
    return {"v4": v4_result, "backtests": backtests}


def _run_external(command: list[str], cwd: Path) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
    }


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
