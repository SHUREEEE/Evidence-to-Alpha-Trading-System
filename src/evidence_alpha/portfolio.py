from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from .models import BaselineWeight, ContractError, EventSignal, content_hash


@dataclass(frozen=True)
class PortfolioConfig:
    overlay_scale: float = 0.04
    max_overlay_per_name: float = 0.03
    turnover_cap: float = 0.12
    max_single_name_weight: float = 0.60

    @property
    def hash(self) -> str:
        return content_hash(asdict(self))


def _cap_and_normalize(weights: dict[str, float], cap: float) -> dict[str, float]:
    if cap <= 0 or cap * len(weights) < 1.0 - 1e-12:
        raise ContractError("max_single_name_weight is infeasible for the universe")
    result = {ticker: max(0.0, value) for ticker, value in weights.items()}
    total = sum(result.values())
    if total <= 0:
        raise ContractError("portfolio has no positive target weight")
    result = {ticker: value / total for ticker, value in result.items()}
    for _ in range(len(result) + 2):
        excess = sum(max(0.0, value - cap) for value in result.values())
        if excess <= 1e-12:
            break
        capped = {ticker for ticker, value in result.items() if value >= cap}
        for ticker in capped:
            result[ticker] = cap
        room = {ticker: cap - value for ticker, value in result.items() if ticker not in capped}
        room_total = sum(room.values())
        if room_total <= 0:
            raise ContractError("cannot redistribute capped portfolio weight")
        for ticker, available in room.items():
            result[ticker] += excess * available / room_total
    total = sum(result.values())
    return {ticker: value / total for ticker, value in result.items()}


def build_portfolios(
    baseline_rows: Iterable[BaselineWeight],
    signals: Iterable[EventSignal],
    config: PortfolioConfig,
) -> dict[str, object]:
    baseline_list = list(baseline_rows)
    baseline = {item.ticker: item.weight for item in baseline_list}
    if not baseline:
        raise ContractError("baseline portfolio is empty")
    factor_versions = sorted({item.factor_version for item in baseline_list})
    if len(factor_versions) != 1:
        raise ContractError("MVP run requires exactly one factor_version")

    score = {ticker: 0.0 for ticker in baseline}
    for signal in signals:
        if signal.ticker in score:
            score[signal.ticker] += signal.decayed_strength
    raw_delta = {ticker: value * config.overlay_scale for ticker, value in score.items()}
    mean_delta = sum(raw_delta.values()) / len(raw_delta)
    delta = {
        ticker: max(-config.max_overlay_per_name, min(config.max_overlay_per_name, value - mean_delta))
        for ticker, value in raw_delta.items()
    }
    turnover = sum(abs(value) for value in delta.values())
    if turnover > config.turnover_cap and turnover > 0:
        scale = config.turnover_cap / turnover
        delta = {ticker: value * scale for ticker, value in delta.items()}
    target = _cap_and_normalize(
        {ticker: baseline[ticker] + delta[ticker] for ticker in baseline},
        config.max_single_name_weight,
    )

    positive = {ticker: max(0.0, value) for ticker, value in score.items()}
    positive_total = sum(positive.values())
    event_only = (
        {ticker: value / positive_total for ticker, value in positive.items() if value > 0}
        if positive_total > 0
        else {}
    )
    actual_delta = {ticker: target[ticker] - baseline[ticker] for ticker in baseline}
    constraints = {
        "weights_sum_to_one": abs(sum(target.values()) - 1.0) <= 1e-9,
        "single_name_limit": max(target.values()) <= config.max_single_name_weight + 1e-9,
        "overlay_per_name_limit": max(abs(value) for value in actual_delta.values()) <= config.max_overlay_per_name + 1e-9,
        "turnover_limit": sum(abs(value) for value in actual_delta.values()) <= config.turnover_cap + 1e-9,
    }
    return {
        "factor_version": factor_versions[0],
        "config_hash": config.hash,
        "baseline": baseline,
        "event_only": event_only,
        "overlay": target,
        "overlay_delta": actual_delta,
        "constraints": constraints,
    }

