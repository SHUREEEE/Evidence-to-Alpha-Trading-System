from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from math import isfinite, isnan
from pathlib import Path
import csv
from typing import Any

from .models import ContractError


def _parse_date(value: Any, field_name: str = "date") -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).date()
    except ValueError as exc:
        raise ContractError(f"{field_name} must be an ISO date or timestamp: {value!r}") from exc


@dataclass
class WeightPanel:
    weights: dict[date, dict[str, float]]
    source_path: Path

    @property
    def dates(self) -> list[date]:
        return sorted(self.weights)

    @property
    def tickers(self) -> set[str]:
        return {ticker for row in self.weights.values() for ticker in row}

    def on_or_before(self, asof: date) -> tuple[date, dict[str, float]]:
        selected = [value for value in self.dates if value <= asof]
        if not selected:
            raise ContractError(f"no factor weights are available on or before {asof}")
        day = selected[-1]
        return day, dict(self.weights[day])


@dataclass
class PricePanel:
    adj_close: dict[date, dict[str, float]]
    source_path: Path

    @property
    def dates(self) -> list[date]:
        return sorted(self.adj_close)

    @property
    def tickers(self) -> set[str]:
        return {ticker for row in self.adj_close.values() for ticker in row}


@dataclass
class FactorInputs:
    weights: WeightPanel
    prices: PricePanel
    sectors: dict[str, str]
    paths: dict[str, Path]


class MultiFactorAdapter:
    """Adapter for the public multi-factor-alpha-platform input contracts."""

    def __init__(
        self,
        factor_root: str | Path,
        *,
        weights_path: str | Path | None = None,
        sectors_path: str | Path | None = None,
        prices_path: str | Path | None = None,
    ) -> None:
        self.factor_root = Path(factor_root).resolve()
        self.weights_path = self._resolve(
            weights_path, "results/pillar5_artifacts/v3_weights.parquet"
        )
        self.sectors_path = self._resolve(
            sectors_path, "results/pillar5_artifacts/v3_sector_map.csv"
        )
        self.prices_path = self._resolve(prices_path, "data/processed/prices.parquet")

    def _resolve(self, supplied: str | Path | None, default: str) -> Path:
        if supplied is None:
            return self.factor_root / default
        path = Path(supplied)
        return path.resolve() if path.is_absolute() else (self.factor_root / path).resolve()

    def load(self) -> FactorInputs:
        required = {
            "weights": self.weights_path,
            "sectors": self.sectors_path,
            "prices": self.prices_path,
        }
        missing = [f"{name}={path}" for name, path in required.items() if not path.exists()]
        if missing:
            raise ContractError("missing multi-factor input artifact(s): " + "; ".join(missing))
        weights = load_weight_panel(self.weights_path)
        prices = load_price_panel(self.prices_path)
        sectors = load_sector_map(self.sectors_path)
        return FactorInputs(weights=weights, prices=prices, sectors=sectors, paths=required)


def _read_rows(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.casefold()
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    if suffix == ".parquet":
        try:
            import pandas as pd
        except ImportError as exc:
            raise ContractError(
                "Parquet integration requires the optional 'integrations' dependencies"
            ) from exc
        frame = pd.read_parquet(path)
        if not isinstance(frame.index, pd.RangeIndex):
            frame = frame.reset_index()
        return frame.to_dict(orient="records")
    raise ContractError(f"unsupported multi-factor artifact type: {path.suffix}")


def _date_column(rows: list[dict[str, Any]]) -> str:
    if not rows:
        raise ContractError("input panel must not be empty")
    keys = list(rows[0])
    for candidate in ("date", "asof", "index", "level_0"):
        if candidate in keys:
            return candidate
    return keys[0]


def load_weight_panel(path: str | Path) -> WeightPanel:
    source = Path(path)
    rows = _read_rows(source)
    date_column = _date_column(rows)
    long_form = "ticker" in rows[0] and (
        "weight" in rows[0] or "target_weight" in rows[0]
    )
    weights: dict[date, dict[str, float]] = {}
    if long_form:
        value_column = "weight" if "weight" in rows[0] else "target_weight"
        for row in rows:
            day = _parse_date(row.get(date_column), date_column)
            ticker = str(row.get("ticker", "")).strip().upper()
            if not ticker:
                raise ContractError("weight row is missing ticker")
            value = float(row.get(value_column, 0.0))
            _store_value(weights, day, ticker, value, "weight")
    else:
        ignored = {date_column, "factor_version", "version"}
        for row in rows:
            day = _parse_date(row.get(date_column), date_column)
            for ticker, raw in row.items():
                if ticker in ignored or _is_missing_wide_cell(raw):
                    continue
                _store_value(weights, day, str(ticker).strip().upper(), float(raw), "weight")
    if not weights:
        raise ContractError("factor weight panel is empty")
    return WeightPanel(weights=weights, source_path=source)


def load_price_panel(path: str | Path) -> PricePanel:
    source = Path(path)
    rows = _read_rows(source)
    date_column = _date_column(rows)
    long_form = "ticker" in rows[0] and "adj_close" in rows[0]
    prices: dict[date, dict[str, float]] = {}
    if long_form:
        for row in rows:
            day = _parse_date(row.get(date_column), date_column)
            ticker = str(row.get("ticker", "")).strip().upper()
            value = float(row.get("adj_close", 0.0))
            if value <= 0:
                raise ContractError(f"adj_close must be positive: {day} {ticker}")
            _store_value(prices, day, ticker, value, "adj_close")
    else:
        for row in rows:
            day = _parse_date(row.get(date_column), date_column)
            for ticker, raw in row.items():
                if ticker == date_column or _is_missing_wide_cell(raw):
                    continue
                value = float(raw)
                if value <= 0:
                    raise ContractError(f"adj_close must be positive: {day} {ticker}")
                _store_value(prices, day, str(ticker).strip().upper(), value, "adj_close")
    if not prices:
        raise ContractError("adjusted-close price panel is empty")
    return PricePanel(adj_close=prices, source_path=source)


def _is_missing_wide_cell(value: Any) -> bool:
    if value is None or (isinstance(value, str) and not value.strip()):
        return True
    try:
        return isnan(float(value))
    except (TypeError, ValueError):
        return False


def _store_value(
    panel: dict[date, dict[str, float]], day: date, ticker: str, value: float, field: str
) -> None:
    if not ticker or not isfinite(value):
        raise ContractError(f"{field} ticker and finite value are required")
    row = panel.setdefault(day, {})
    if ticker in row:
        raise ContractError(f"duplicate {field} row: {day} {ticker}")
    row[ticker] = value


def load_sector_map(path: str | Path) -> dict[str, str]:
    source = Path(path)
    if source.suffix.casefold() != ".csv":
        raise ContractError("V3 sector map must be a CSV file")
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ContractError("sector map must not be empty")
    symbol_column = "symbol" if "symbol" in rows[0] else "ticker" if "ticker" in rows[0] else list(rows[0])[0]
    sector_column = "sector" if "sector" in rows[0] else list(rows[0])[-1]
    result = {
        str(row.get(symbol_column, "")).strip().upper(): str(row.get(sector_column, "Unknown")).strip() or "Unknown"
        for row in rows
        if str(row.get(symbol_column, "")).strip()
    }
    if not result:
        raise ContractError("sector map contains no symbols")
    return result


def write_weight_panel_csv(
    panel: dict[date, dict[str, float]], path: str | Path, *, through: date | None = None
) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["date", "ticker", "weight"])
        writer.writeheader()
        for day in sorted(panel):
            if through is not None and day > through:
                continue
            for ticker, weight in sorted(panel[day].items()):
                writer.writerow({"date": day.isoformat(), "ticker": ticker, "weight": f"{weight:.12g}"})
    return target


def write_v4_staging_cache(
    panel: dict[date, dict[str, float]], sectors: dict[str, str], output_dir: str | Path
) -> dict[str, Path]:
    try:
        import pandas as pd
    except ImportError as exc:
        raise ContractError(
            "V4 Parquet staging requires the optional 'integrations' dependencies"
        ) from exc
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    weights_path = output / "v3_weights.parquet"
    sectors_path = output / "v3_sector_map.csv"
    frame = pd.DataFrame.from_dict(panel, orient="index").fillna(0.0).sort_index().sort_index(axis=1)
    frame.index = pd.DatetimeIndex(frame.index, name="date")
    try:
        frame.to_parquet(weights_path)
    except (ImportError, ValueError) as exc:
        raise ContractError(
            "V4 Parquet staging requires a working parquet engine such as pyarrow"
        ) from exc
    with sectors_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["symbol", "sector"])
        writer.writeheader()
        for ticker in sorted(frame.columns):
            writer.writerow({"symbol": ticker, "sector": sectors.get(ticker, "Unknown")})
    return {"weights": weights_path, "sectors": sectors_path}
