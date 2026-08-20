from __future__ import annotations

from datetime import date, timedelta
from math import sin
from pathlib import Path
import csv
import json

from .pipeline import config_from_cutoff, run_pipeline


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _business_days(start: date, count: int) -> list[date]:
    result: list[date] = []
    current = start
    while len(result) < count:
        if current.weekday() < 5:
            result.append(current)
        current += timedelta(days=1)
    return result


def generate_demo_inputs(root: str | Path) -> dict[str, Path]:
    target = Path(root)
    inputs = target / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    events = [
        {"event_id": "EVT-20260112-001", "event_version": 1, "published_at": "2026-01-12T01:00:00+00:00", "observed_at": "2026-01-12T01:05:00+00:00", "event_type": "product", "direction": "positive", "confidence": 0.68, "novelty": 0.74, "conflict": False, "impact_horizon_days": 20, "entities": ["NVIDIA"], "sectors": ["Semiconductors"], "evidence_ids": ["SRC-001"], "status": "developing", "asof": "2026-01-12T01:05:00+00:00"},
        {"event_id": "EVT-20260112-001", "event_version": 2, "published_at": "2026-01-12T01:00:00+00:00", "observed_at": "2026-01-14T02:00:00+00:00", "event_type": "product", "direction": "positive", "confidence": 0.78, "novelty": 0.74, "conflict": False, "impact_horizon_days": 20, "entities": ["NVIDIA"], "sectors": ["Semiconductors"], "evidence_ids": ["SRC-001", "SRC-002"], "status": "confirmed", "asof": "2026-01-14T02:00:00+00:00"},
        {"event_id": "EVT-20260115-002", "event_version": 1, "published_at": "2026-01-15T00:30:00+00:00", "observed_at": "2026-01-15T00:45:00+00:00", "event_type": "supply_chain", "direction": "negative", "confidence": 0.62, "novelty": 0.66, "conflict": True, "impact_horizon_days": 5, "entities": ["Advanced Micro Devices"], "sectors": ["Semiconductors"], "evidence_ids": ["SRC-003", "SRC-004"], "status": "developing", "asof": "2026-01-15T00:45:00+00:00"},
        {"event_id": "EVT-20260115-002", "event_version": 2, "published_at": "2026-01-15T00:30:00+00:00", "observed_at": "2026-01-20T00:45:00+00:00", "event_type": "supply_chain", "direction": "neutral", "confidence": 0.80, "novelty": 0.66, "conflict": False, "impact_horizon_days": 5, "entities": ["Advanced Micro Devices"], "sectors": ["Semiconductors"], "evidence_ids": ["SRC-003", "SRC-004", "SRC-005"], "status": "resolved", "asof": "2026-01-20T00:45:00+00:00"},
    ]
    evidence = {"evidence": [
        {"evidence_id": "SRC-001", "source_url": "https://example.test/source/1", "captured_at": "2026-01-12T01:05:00+00:00", "source_name": "Example Wire"},
        {"evidence_id": "SRC-002", "source_url": "https://example.test/source/2", "captured_at": "2026-01-14T02:00:00+00:00", "source_name": "Company Filing"},
        {"evidence_id": "SRC-003", "source_url": "https://example.test/source/3", "captured_at": "2026-01-15T00:45:00+00:00", "source_name": "Example Wire"},
        {"evidence_id": "SRC-004", "source_url": "https://example.test/source/4", "captured_at": "2026-01-15T00:45:00+00:00", "source_name": "Supplier Update"},
        {"evidence_id": "SRC-005", "source_url": "https://example.test/source/5", "captured_at": "2026-01-20T00:45:00+00:00", "source_name": "Follow-up"},
    ]}
    _write_json(inputs / "events.json", events)
    _write_json(inputs / "evidence.json", evidence)
    with (inputs / "mappings.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["entity", "ticker", "sector", "impact_multiplier"])
        writer.writeheader()
        writer.writerows([
            {"entity": "NVIDIA", "ticker": "NVDA", "sector": "Semiconductors", "impact_multiplier": 1.0},
            {"entity": "Advanced Micro Devices", "ticker": "AMD", "sector": "Semiconductors", "impact_multiplier": 1.0},
        ])
    with (inputs / "baseline_weights.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["asof", "ticker", "weight", "factor_version"])
        writer.writeheader()
        writer.writerows([
            {"asof": "2026-01-16", "ticker": "NVDA", "weight": 0.30, "factor_version": "FACTOR-2026-01"},
            {"asof": "2026-01-16", "ticker": "AMD", "weight": 0.25, "factor_version": "FACTOR-2026-01"},
            {"asof": "2026-01-16", "ticker": "SPY", "weight": 0.45, "factor_version": "FACTOR-2026-01"},
        ])
    days = _business_days(date(2026, 1, 2), 45)
    with (inputs / "prices.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["date", "ticker", "open", "close"])
        writer.writeheader()
        for index, day in enumerate(days):
            spy = 100.0 * (1 + 0.0008 * index + 0.0015 * sin(index / 3))
            nvda = 50.0 * (1 + 0.0010 * index + 0.004 * min(max(index - 7, 0), 8) + 0.002 * sin(index / 2))
            amd = 40.0 * (1 + 0.0009 * index - 0.0025 * min(max(index - 10, 0), 4) + 0.0015 * sin(index / 2.5))
            for ticker, close in (("SPY", spy), ("NVDA", nvda), ("AMD", amd)):
                writer.writerow({"date": day.isoformat(), "ticker": ticker, "open": f"{close * (1 - 0.0007):.6f}", "close": f"{close:.6f}"})
    return {"events_path": inputs / "events.json", "evidence_path": inputs / "evidence.json", "mappings_path": inputs / "mappings.csv", "prices_path": inputs / "prices.csv", "baseline_weights_path": inputs / "baseline_weights.csv"}


def run_demo(output_dir: str | Path):
    paths = generate_demo_inputs(output_dir)
    return run_pipeline(**paths, output_dir=output_dir, config=config_from_cutoff("2026-01-16T08:00:00+00:00"))

