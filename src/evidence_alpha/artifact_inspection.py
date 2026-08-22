from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
from math import isfinite, isnan
from pathlib import Path, PurePosixPath, PureWindowsPath
import csv
import re
from typing import Any, Literal

from .models import ContractError


PanelKind = Literal["factor_weights", "adjusted_prices"]
DATE_COLUMNS = ("date", "asof", "index", "level_0", "__index_level_0__")
TICKER_PATTERN = re.compile(r"[A-Z0-9][A-Z0-9._/\-]{0,63}")


@dataclass(frozen=True)
class PanelInspection:
    coverage_start: date
    coverage_end: date
    row_count: int
    date_count: int
    ticker_count: int
    nonzero_value_count: int
    value_field: str


def inspect_input_panel(path: str | Path, kind: PanelKind) -> PanelInspection:
    source = Path(path)
    if not source.is_file():
        raise ContractError(f"input panel does not exist: {source}")
    suffix = source.suffix.casefold()
    if suffix == ".csv":
        return _inspect_csv(source, kind)
    if suffix == ".parquet":
        return _inspect_parquet(source, kind)
    raise ContractError(f"unsupported input panel type: {source.suffix}")


def build_panel_inspection_report(
    path: str | Path,
    kind: PanelKind,
    *,
    logical_path: str | None = None,
) -> dict[str, Any]:
    """Return deterministic content facts without asserting production provenance."""
    source = Path(path)
    safe_logical_path = _logical_path(logical_path or source.name)
    before_digest, before_size = _file_fingerprint(source)
    inspection = inspect_input_panel(source, kind)
    after_digest, after_size = _file_fingerprint(source)
    if before_digest != after_digest or before_size != after_size:
        raise ContractError("input panel changed during inspection")
    limitations = (
        [
            "production_provenance_not_attested",
            "point_in_time_universe_not_attested",
        ]
        if kind == "factor_weights"
        else [
            "production_provenance_not_attested",
            "corporate_actions_not_attested",
            "delistings_not_attested",
        ]
    )
    return {
        "schema_version": "1.0",
        "artifact_type": "market_input_panel_inspection",
        "panel_kind": kind,
        "artifact": {
            "logical_path": safe_logical_path,
            "sha256": after_digest,
            "size_bytes": after_size,
        },
        "content": {
            "coverage_start": inspection.coverage_start.isoformat(),
            "coverage_end": inspection.coverage_end.isoformat(),
            "row_count": inspection.row_count,
            "date_count": inspection.date_count,
            "ticker_count": inspection.ticker_count,
            "nonzero_value_count": inspection.nonzero_value_count,
            "value_field": inspection.value_field,
        },
        "limitations": limitations,
    }


def _logical_path(value: str) -> str:
    raw = str(value).strip().replace("\\", "/")
    windows_path = PureWindowsPath(raw)
    posix_path = PurePosixPath(raw)
    if (
        not raw
        or "\x00" in raw
        or windows_path.drive
        or posix_path.is_absolute()
        or ".." in posix_path.parts
        or posix_path.as_posix() == "."
    ):
        raise ContractError("logical path must be a non-empty relative path")
    return posix_path.as_posix()


def _file_fingerprint(path: Path) -> tuple[str, int]:
    digest = sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        size = path.stat().st_size
    except OSError as exc:
        raise ContractError(f"cannot fingerprint input panel ({type(exc).__name__})") from exc
    return digest.hexdigest(), size


def _coerce_date(value: Any, field_name: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip().replace("Z", "+00:00")
    if not text:
        raise ContractError(f"{field_name} must not be empty")
    try:
        return date.fromisoformat(text)
    except ValueError:
        try:
            return datetime.fromisoformat(text).date()
        except ValueError as exc:
            raise ContractError(
                f"{field_name} must be an ISO date or timestamp: {value!r}"
            ) from exc


def _date_column(columns: list[str]) -> str:
    for candidate in DATE_COLUMNS:
        if candidate in columns:
            return candidate
    raise ContractError(
        "input panel must contain an explicit date/asof/index column"
    )


def _value_field(columns: list[str], kind: PanelKind) -> str | None:
    if kind == "factor_weights":
        if "weight" in columns:
            return "weight"
        if "target_weight" in columns:
            return "target_weight"
        return None
    if "adj_close" in columns:
        return "adj_close"
    if "total_return_index" in columns:
        return "total_return_index"
    return None


def _ticker(value: Any) -> str:
    ticker = str(value or "").strip().upper()
    if not TICKER_PATTERN.fullmatch(ticker):
        raise ContractError(f"invalid ticker in input panel: {value!r}")
    return ticker


def _number(value: Any, *, kind: PanelKind, field_name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ContractError(f"{field_name} must be numeric: {value!r}") from exc
    if not isfinite(number):
        raise ContractError(f"{field_name} must be finite: {value!r}")
    if kind == "adjusted_prices" and number <= 0:
        raise ContractError(f"{field_name} must be positive: {value!r}")
    return number


def _is_missing_wide_cell(value: Any) -> bool:
    if value is None or (isinstance(value, str) and not value.strip()):
        return True
    try:
        return isnan(float(value))
    except (TypeError, ValueError):
        return False


def _build_inspection(
    *,
    dates: set[date],
    tickers: set[str],
    row_count: int,
    nonzero_value_count: int,
    value_field: str,
    kind: PanelKind,
) -> PanelInspection:
    if not dates or not tickers or row_count <= 0:
        raise ContractError("input panel must contain at least one usable value")
    if kind == "factor_weights" and nonzero_value_count <= 0:
        raise ContractError("factor weight panel must contain a non-zero weight")
    return PanelInspection(
        coverage_start=min(dates),
        coverage_end=max(dates),
        row_count=row_count,
        date_count=len(dates),
        ticker_count=len(tickers),
        nonzero_value_count=nonzero_value_count,
        value_field=value_field,
    )


def _inspect_csv(path: Path, kind: PanelKind) -> PanelInspection:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames or [])
        if len(columns) != len(set(columns)):
            raise ContractError("input panel contains duplicate columns")
        date_column = _date_column(columns)
        value_field = _value_field(columns, kind)
        long_form = "ticker" in columns and value_field is not None
        if "ticker" in columns and value_field is None:
            required = (
                "weight/target_weight"
                if kind == "factor_weights"
                else "adj_close or total_return_index"
            )
            raise ContractError(f"long-form input panel must contain {required}")
        ignored = {date_column, "factor_version", "version"}
        value_columns = [column for column in columns if column not in ignored]
        if not long_form:
            if "ticker" in value_columns:
                value_columns.remove("ticker")
            if not value_columns:
                raise ContractError("wide input panel contains no ticker columns")
            normalized = [_ticker(column) for column in value_columns]
            if len(set(normalized)) != len(normalized):
                raise ContractError("wide input panel contains duplicate ticker columns")

        dates: set[date] = set()
        tickers: set[str] = set()
        seen_pairs: set[tuple[date, str]] = set()
        row_count = 0
        nonzero_count = 0
        for row in reader:
            day = _coerce_date(row.get(date_column), date_column)
            if long_form and value_field:
                dates.add(day)
                ticker = _ticker(row.get("ticker"))
                pair = (day, ticker)
                if pair in seen_pairs:
                    raise ContractError(f"duplicate input panel row: {day} {ticker}")
                seen_pairs.add(pair)
                value = _number(row.get(value_field), kind=kind, field_name=value_field)
                tickers.add(ticker)
                row_count += 1
                nonzero_count += int(value != 0.0)
                continue
            values_on_day = 0
            for column in value_columns:
                raw = row.get(column)
                if _is_missing_wide_cell(raw):
                    continue
                ticker = _ticker(column)
                value = _number(raw, kind=kind, field_name=column)
                tickers.add(ticker)
                row_count += 1
                values_on_day += 1
                nonzero_count += int(value != 0.0)
            if values_on_day:
                if day in dates:
                    raise ContractError(f"duplicate wide input panel date: {day}")
                dates.add(day)
        return _build_inspection(
            dates=dates,
            tickers=tickers,
            row_count=row_count,
            nonzero_value_count=nonzero_count,
            value_field=value_field or "wide",
            kind=kind,
        )


def _inspect_parquet(path: Path, kind: PanelKind) -> PanelInspection:
    try:
        import numpy as np
        import pandas as pd
    except ImportError as exc:
        raise ContractError(
            "Parquet artifact inspection requires the optional integrations dependencies"
        ) from exc
    try:
        frame = pd.read_parquet(path)
    except (OSError, ValueError, ImportError) as exc:
        raise ContractError(
            f"cannot read Parquet input panel ({type(exc).__name__})"
        ) from exc
    if not isinstance(frame.index, pd.RangeIndex):
        frame = frame.reset_index()
    columns = [str(column) for column in frame.columns]
    if len(columns) != len(set(columns)):
        raise ContractError("input panel contains duplicate columns")
    frame.columns = columns
    date_column = _date_column(columns)
    if frame[date_column].isna().any():
        raise ContractError(f"{date_column} must not contain missing values")
    try:
        dates = {
            _coerce_date(value, date_column)
            for value in frame[date_column].drop_duplicates().tolist()
        }
    except (TypeError, ValueError) as exc:
        raise ContractError(f"invalid {date_column} values in input panel") from exc

    value_field = _value_field(columns, kind)
    long_form = "ticker" in columns and value_field is not None
    if "ticker" in columns and value_field is None:
        required = (
            "weight/target_weight"
            if kind == "factor_weights"
            else "adj_close or total_return_index"
        )
        raise ContractError(f"long-form input panel must contain {required}")
    if long_form and value_field:
        if frame[[date_column, "ticker"]].duplicated().any():
            raise ContractError("long-form input panel contains duplicate date/ticker rows")
        if frame["ticker"].isna().any():
            raise ContractError("ticker must not contain missing values")
        tickers = {_ticker(value) for value in frame["ticker"].drop_duplicates().tolist()}
        values = pd.to_numeric(frame[value_field], errors="coerce")
        if values.isna().any():
            raise ContractError(f"{value_field} must be numeric and non-missing")
        numbers = values.to_numpy(dtype=float)
        if not bool(np.isfinite(numbers).all()):
            raise ContractError(f"{value_field} must contain only finite values")
        if kind == "adjusted_prices" and bool((numbers <= 0).any()):
            raise ContractError(f"{value_field} must contain only positive values")
        return _build_inspection(
            dates=dates,
            tickers=tickers,
            row_count=len(frame),
            nonzero_value_count=int((numbers != 0).sum()),
            value_field=value_field,
            kind=kind,
        )

    ignored = {date_column, "factor_version", "version"}
    value_columns = [column for column in columns if column not in ignored]
    if "ticker" in value_columns:
        value_columns.remove("ticker")
    if not value_columns:
        raise ContractError("wide input panel contains no ticker columns")
    normalized = [_ticker(column) for column in value_columns]
    if len(set(normalized)) != len(normalized):
        raise ContractError("wide input panel contains duplicate ticker columns")
    numeric = frame[value_columns].apply(pd.to_numeric, errors="coerce")
    invalid = numeric.isna() & frame[value_columns].notna()
    if bool(invalid.to_numpy().any()):
        raise ContractError("wide input panel contains a non-numeric value")
    values = numeric.to_numpy(dtype=float)
    finite_or_missing = pd.isna(values) | np.isfinite(values)
    if not bool(finite_or_missing.all()):
        raise ContractError("wide input panel contains a non-finite value")
    if kind == "adjusted_prices" and bool((values[~pd.isna(values)] <= 0).any()):
        raise ContractError("adjusted prices must contain only positive values")
    usable_rows = numeric.notna().any(axis=1)
    usable_dates = frame.loc[usable_rows, date_column]
    if usable_dates.duplicated().any():
        raise ContractError("wide input panel contains duplicate dates")
    dates = {
        _coerce_date(value, date_column)
        for value in usable_dates.drop_duplicates().tolist()
    }
    usable_tickers = {
        normalized[index]
        for index, column in enumerate(value_columns)
        if numeric[column].notna().any()
    }
    usable = values[~pd.isna(values)]
    return _build_inspection(
        dates=dates,
        tickers=usable_tickers,
        row_count=int(usable.size),
        nonzero_value_count=int((usable != 0).sum()),
        value_field="wide",
        kind=kind,
    )
