from __future__ import annotations

from datetime import date
from typing import Iterable

from .models import EventSnapshot, PriceBar


WINDOWS = (1, 3, 5, 20)


def _price_index(prices: Iterable[PriceBar]) -> dict[str, list[PriceBar]]:
    result: dict[str, list[PriceBar]] = {}
    for bar in prices:
        result.setdefault(bar.ticker, []).append(bar)
    for bars in result.values():
        bars.sort(key=lambda item: item.trade_date)
    return result


def run_event_study(
    events: Iterable[EventSnapshot],
    event_tickers: dict[str, set[str]],
    prices: Iterable[PriceBar],
    benchmark: str,
) -> list[dict[str, object]]:
    index = _price_index(prices)
    benchmark_bars = index.get(benchmark, [])
    benchmark_by_date = {bar.trade_date: bar.close for bar in benchmark_bars}
    rows: list[dict[str, object]] = []
    for event in events:
        for ticker in sorted(event_tickers.get(event.ref, set())):
            bars = index.get(ticker, [])
            start_position = next(
                (i for i, bar in enumerate(bars) if bar.trade_date > event.observed_at.date()),
                None,
            )
            if start_position is None:
                continue
            start = bars[start_position]
            for window in WINDOWS:
                end_position = start_position + window
                if end_position >= len(bars):
                    rows.append(
                        {
                            "event_ref": event.ref,
                            "ticker": ticker,
                            "window_days": window,
                            "start_date": start.trade_date.isoformat(),
                            "end_date": None,
                            "return": None,
                            "benchmark_return": None,
                            "abnormal_return": None,
                            "status": "insufficient_data",
                        }
                    )
                    continue
                end = bars[end_position]
                benchmark_start = benchmark_by_date.get(start.trade_date)
                benchmark_end = benchmark_by_date.get(end.trade_date)
                security_return = end.close / start.close - 1.0
                benchmark_return = (
                    benchmark_end / benchmark_start - 1.0
                    if benchmark_start and benchmark_end
                    else None
                )
                rows.append(
                    {
                        "event_ref": event.ref,
                        "ticker": ticker,
                        "window_days": window,
                        "start_date": start.trade_date.isoformat(),
                        "end_date": end.trade_date.isoformat(),
                        "return": security_return,
                        "benchmark_return": benchmark_return,
                        "abnormal_return": security_return - benchmark_return if benchmark_return is not None else None,
                        "status": "ok" if benchmark_return is not None else "missing_benchmark",
                    }
                )
    return rows


def portfolio_period_return(
    weights: dict[str, float],
    prices: Iterable[PriceBar],
    start_date: date,
    end_date: date,
) -> float | None:
    index = _price_index(prices)
    total = 0.0
    used_weight = 0.0
    for ticker, weight in weights.items():
        bars = index.get(ticker, [])
        start = next((bar.close for bar in bars if bar.trade_date >= start_date), None)
        end = next((bar.close for bar in reversed(bars) if bar.trade_date <= end_date), None)
        if start is None or end is None:
            continue
        total += weight * (end / start - 1.0)
        used_weight += abs(weight)
    return total if used_weight > 0 else None

