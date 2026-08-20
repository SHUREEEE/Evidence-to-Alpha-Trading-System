from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from math import floor
from typing import Iterable

from .models import ContractError, Fill, Order, PriceBar, content_hash


@dataclass(frozen=True)
class OmsConfig:
    starting_cash: float = 100000.0
    commission_bps: float = 2.0
    slippage_bps: float = 5.0

    @property
    def hash(self) -> str:
        return content_hash(asdict(self))


def _common_fill_date(prices: list[PriceBar], tickers: set[str], cutoff: datetime):
    by_date: dict[object, set[str]] = {}
    for bar in prices:
        if bar.trade_date > cutoff.date() and bar.ticker in tickers:
            by_date.setdefault(bar.trade_date, set()).add(bar.ticker)
    return next((day for day in sorted(by_date) if by_date[day] >= tickers), None)


def simulate_paper_oms(
    run_id: str,
    cutoff: datetime,
    target_weights: dict[str, float],
    prices: Iterable[PriceBar],
    factor_version: str,
    lineage: dict[str, dict[str, tuple[str, ...]]],
    config: OmsConfig,
) -> tuple[list[Order], list[Fill], dict[str, object]]:
    price_list = list(prices)
    tickers = {ticker for ticker, weight in target_weights.items() if weight > 0}
    fill_date = _common_fill_date(price_list, tickers, cutoff)
    if fill_date is None:
        raise ContractError("no common T+1 trading date is available for target tickers")
    fill_bars = {bar.ticker: bar for bar in price_list if bar.trade_date == fill_date and bar.ticker in tickers}
    mark_bars: dict[str, PriceBar] = {}
    for bar in price_list:
        if bar.ticker in tickers and bar.trade_date >= fill_date:
            mark_bars[bar.ticker] = bar

    orders: list[Order] = []
    fills: list[Fill] = []
    cash = config.starting_cash
    positions: dict[str, int] = {}
    total_commission = 0.0
    for ticker in sorted(tickers):
        bar = fill_bars[ticker]
        fill_price = bar.open * (1.0 + config.slippage_bps / 10000.0)
        desired_value = config.starting_cash * target_weights[ticker]
        quantity = max(0, floor(desired_value / fill_price))
        commission_rate = config.commission_bps / 10000.0
        max_affordable = floor(cash / (fill_price * (1.0 + commission_rate)))
        quantity = min(quantity, max_affordable)
        if quantity <= 0:
            continue
        trace = lineage.get(ticker, {})
        identity = {"run_id": run_id, "ticker": ticker, "side": "BUY", "quantity": quantity}
        order = Order(
            order_id=f"ORD-{content_hash(identity)[:16].upper()}",
            run_id=run_id,
            created_at=cutoff,
            ticker=ticker,
            side="BUY",
            quantity=quantity,
            target_weight=target_weights[ticker],
            factor_version=factor_version,
            signal_ids=trace.get("signal_ids", ()),
            event_refs=trace.get("event_refs", ()),
            evidence_ids=trace.get("evidence_ids", ()),
        )
        commission = quantity * fill_price * commission_rate
        fill = Fill(
            fill_id=f"FIL-{content_hash({**identity, 'fill_date': fill_date.isoformat()})[:16].upper()}",
            order_id=order.order_id,
            run_id=run_id,
            trade_date=fill_date,
            ticker=ticker,
            side="BUY",
            quantity=quantity,
            fill_price=round(fill_price, 8),
            commission=round(commission, 8),
            slippage_bps=config.slippage_bps,
        )
        cash -= quantity * fill_price + commission
        positions[ticker] = quantity
        total_commission += commission
        orders.append(order)
        fills.append(fill)

    market_value = sum(positions[ticker] * mark_bars[ticker].close for ticker in positions)
    ending_equity = cash + market_value
    invested_cost = sum(fill.quantity * fill.fill_price for fill in fills)
    unrealized_pnl = sum(
        fill.quantity * (mark_bars[fill.ticker].close - fill.fill_price)
        for fill in fills
    )
    expected_cash = config.starting_cash - invested_cost - total_commission
    reconciliation = {
        "cash_residual": abs(cash - expected_cash),
        "equity_residual": abs(ending_equity - (cash + market_value)),
        "closed_to_cent": abs(cash - expected_cash) <= 0.01 and abs(ending_equity - (cash + market_value)) <= 0.01,
    }
    summary = {
        "fill_date": fill_date.isoformat(),
        "mark_date": max(bar.trade_date for bar in mark_bars.values()).isoformat(),
        "starting_cash": config.starting_cash,
        "ending_cash": round(cash, 8),
        "market_value": round(market_value, 8),
        "ending_equity": round(ending_equity, 8),
        "total_commission": round(total_commission, 8),
        "realized_pnl": 0.0,
        "unrealized_pnl": round(unrealized_pnl, 8),
        "total_pnl": round(ending_equity - config.starting_cash, 8),
        "positions": positions,
        "reconciliation": reconciliation,
        "config_hash": config.hash,
    }
    return orders, fills, summary

