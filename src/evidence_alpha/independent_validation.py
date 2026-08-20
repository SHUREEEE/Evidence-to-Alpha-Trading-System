from __future__ import annotations

from dataclasses import asdict, dataclass
from math import ceil, isfinite, sqrt
from statistics import mean, median, stdev
from typing import Any, Iterable

from .models import ContractError, EventSnapshot, content_hash, parse_date


REQUIRED_SCENARIOS = (
    "baseline",
    "overlay",
    "one_day_delay",
    "placebo",
    "double_cost",
)
SUPPORTED_WINDOWS = (1, 3, 5, 20)


@dataclass(frozen=True)
class IndependentValidationConfig:
    data_classification: str = "unknown"
    minimum_events: int = 30
    oos_fraction: float = 0.30
    minimum_oos_events: int = 10
    rolling_folds: int = 3
    primary_window_days: int = 5
    minimum_positive_fold_fraction: float = 2.0 / 3.0

    def validate(self) -> None:
        if self.data_classification not in {"unknown", "synthetic", "real"}:
            raise ContractError(
                "data_classification must be unknown, synthetic, or real"
            )
        if self.minimum_events < 2:
            raise ContractError("minimum_events must be at least 2")
        if not 0.0 < self.oos_fraction < 1.0:
            raise ContractError("oos_fraction must be in (0, 1)")
        if self.minimum_oos_events < 1:
            raise ContractError("minimum_oos_events must be positive")
        if self.minimum_oos_events >= self.minimum_events:
            raise ContractError("minimum_oos_events must be below minimum_events")
        if self.rolling_folds < 2:
            raise ContractError("rolling_folds must be at least 2")
        if self.primary_window_days not in SUPPORTED_WINDOWS:
            raise ContractError(
                f"primary_window_days must be one of {SUPPORTED_WINDOWS}"
            )
        if not 0.0 < self.minimum_positive_fold_fraction <= 1.0:
            raise ContractError(
                "minimum_positive_fold_fraction must be in (0, 1]"
            )

    @property
    def hash(self) -> str:
        return content_hash(asdict(self))


def _gate(
    name: str, passed: bool, detail: str, severity: str
) -> dict[str, object]:
    return {
        "name": name,
        "passed": bool(passed),
        "detail": detail,
        "severity": severity,
    }


def _summary(values: list[float]) -> dict[str, object]:
    if not values:
        return {
            "event_count": 0,
            "mean_signed_abnormal_return": None,
            "median_signed_abnormal_return": None,
            "positive_rate": None,
            "t_stat": None,
        }
    average = mean(values)
    dispersion = stdev(values) if len(values) >= 2 else None
    t_stat = (
        average / (dispersion / sqrt(len(values)))
        if dispersion is not None and dispersion > 0
        else None
    )
    return {
        "event_count": len(values),
        "mean_signed_abnormal_return": average,
        "median_signed_abnormal_return": median(values),
        "positive_rate": sum(value > 0 for value in values) / len(values),
        "t_stat": t_stat,
    }


def _collapse_event_values(
    rows_by_event: dict[str, list[float]], refs: Iterable[str]
) -> list[float]:
    return [
        mean(rows_by_event[ref])
        for ref in refs
        if ref in rows_by_event and rows_by_event[ref]
    ]


def _direction_multiplier(direction: str) -> float:
    if direction == "positive":
        return 1.0
    if direction == "negative":
        return -1.0
    return 0.0


def run_independent_validation(
    *,
    events: Iterable[EventSnapshot],
    event_study: Iterable[dict[str, object]],
    scenarios: dict[str, object],
    config: IndependentValidationConfig,
) -> dict[str, object]:
    config.validate()
    event_list = list(events)
    event_by_ref = {event.ref: event for event in event_list}
    duplicate_refs = len(event_by_ref) != len(event_list)
    ordered_refs = [
        event.ref
        for event in sorted(
            event_by_ref.values(),
            key=lambda item: (item.observed_at, item.event_id, item.event_version),
        )
    ]

    values_by_window: dict[int, dict[str, list[float]]] = {
        window: {} for window in SUPPORTED_WINDOWS
    }
    leakage_rows: list[dict[str, str]] = []
    unknown_event_refs: set[str] = set()
    invalid_rows: list[dict[str, object]] = []
    for row_index, row in enumerate(event_study):
        event_ref = str(row.get("event_ref", ""))
        event = event_by_ref.get(event_ref)
        if event is None:
            unknown_event_refs.add(event_ref or "<missing>")
            continue
        if row.get("status") != "ok":
            continue
        abnormal = row.get("abnormal_return")
        window = row.get("window_days")
        start_date = row.get("start_date")
        if (
            isinstance(abnormal, bool)
            or not isinstance(abnormal, (int, float))
            or not isfinite(float(abnormal))
            or isinstance(window, bool)
            or not isinstance(window, int)
            or window not in values_by_window
            or not start_date
        ):
            invalid_rows.append(
                {
                    "row_index": row_index,
                    "event_ref": event_ref,
                    "reason": "invalid numeric value, window, or start date",
                }
            )
            continue
        try:
            parsed_start = parse_date(
                str(start_date), "event_study.start_date"
            )
        except ContractError as exc:
            invalid_rows.append(
                {
                    "row_index": row_index,
                    "event_ref": event_ref,
                    "reason": str(exc),
                }
            )
            continue
        if parsed_start <= event.observed_at.date():
            leakage_rows.append(
                {
                    "event_ref": event_ref,
                    "start_date": parsed_start.isoformat(),
                    "observed_date": event.observed_at.date().isoformat(),
                }
            )
            continue
        signed_value = float(abnormal) * _direction_multiplier(event.direction)
        values_by_window[window].setdefault(event_ref, []).append(signed_value)

    primary_values = values_by_window[config.primary_window_days]
    usable_refs = [ref for ref in ordered_refs if ref in primary_values]
    usable_count = len(usable_refs)
    if usable_count >= 2:
        oos_size = max(1, ceil(usable_count * config.oos_fraction))
        split_at = usable_count - oos_size
    else:
        split_at = usable_count
    in_sample_refs = usable_refs[:split_at]
    oos_refs = usable_refs[split_at:]
    partition_disjoint = not (set(in_sample_refs) & set(oos_refs))

    window_summaries: dict[str, dict[str, object]] = {}
    for window, rows_by_event in values_by_window.items():
        window_summaries[str(window)] = {
            "all": _summary(
                _collapse_event_values(rows_by_event, usable_refs)
            ),
            "in_sample": _summary(
                _collapse_event_values(rows_by_event, in_sample_refs)
            ),
            "out_of_sample": _summary(
                _collapse_event_values(rows_by_event, oos_refs)
            ),
        }

    rolling: list[dict[str, object]] = []
    base_size, extra = divmod(len(oos_refs), config.rolling_folds)
    cursor = 0
    for index in range(config.rolling_folds):
        fold_size = base_size + (1 if index < extra else 0)
        test_refs = oos_refs[cursor : cursor + fold_size]
        train_refs = usable_refs[: split_at + cursor]
        cursor += fold_size
        metrics = _summary(
            _collapse_event_values(primary_values, test_refs)
        )
        rolling.append(
            {
                "fold": index + 1,
                "train_event_count": len(train_refs),
                "test_event_refs": test_refs,
                "test_start_observed_at": (
                    event_by_ref[test_refs[0]].observed_at.isoformat()
                    if test_refs
                    else None
                ),
                "test_end_observed_at": (
                    event_by_ref[test_refs[-1]].observed_at.isoformat()
                    if test_refs
                    else None
                ),
                "metrics": metrics,
                "status": "ok" if test_refs else "insufficient_sample",
            }
        )

    scenario_values: dict[str, float] = {}
    for name, value in scenarios.items():
        if (
            name in REQUIRED_SCENARIOS
            and not isinstance(value, bool)
            and isinstance(value, (int, float))
        ):
            numeric_value = float(value)
            if isfinite(numeric_value):
                scenario_values[name] = numeric_value
    scenarios_complete = all(
        name in scenario_values for name in REQUIRED_SCENARIOS
    )
    rolling_complete = (
        len(rolling) == config.rolling_folds
        and all(item["status"] == "ok" for item in rolling)
    )
    positive_folds = sum(
        bool(
            item["metrics"]["mean_signed_abnormal_return"] is not None
            and item["metrics"]["mean_signed_abnormal_return"] > 0
        )
        for item in rolling
        if item["status"] == "ok"
    )
    evaluated_folds = sum(item["status"] == "ok" for item in rolling)
    positive_fold_fraction = (
        positive_folds / evaluated_folds if evaluated_folds else None
    )
    oos_primary = window_summaries[str(config.primary_window_days)][
        "out_of_sample"
    ]

    hard_gates = [
        _gate(
            "unique_visible_event_refs",
            not duplicate_refs,
            f"visible rows={len(event_list)}, unique refs={len(event_by_ref)}",
            "hard",
        ),
        _gate(
            "event_study_refs_visible",
            not unknown_event_refs,
            f"unknown event refs={sorted(unknown_event_refs)}",
            "hard",
        ),
        _gate(
            "event_study_after_observation",
            not leakage_rows,
            f"pre-observation rows={leakage_rows}",
            "hard",
        ),
        _gate(
            "event_study_rows_valid",
            not invalid_rows,
            f"invalid rows={invalid_rows}",
            "hard",
        ),
        _gate(
            "chronological_partition_disjoint",
            partition_disjoint,
            (
                f"in_sample={len(in_sample_refs)}, "
                f"out_of_sample={len(oos_refs)}"
            ),
            "hard",
        ),
        _gate(
            "robustness_scenarios_numeric",
            scenarios_complete,
            f"available scenarios={sorted(scenario_values)}",
            "hard",
        ),
    ]
    overlay = scenario_values.get("overlay")
    baseline = scenario_values.get("baseline")
    placebo = scenario_values.get("placebo")
    delayed = scenario_values.get("one_day_delay")
    double_cost = scenario_values.get("double_cost")
    economic_inputs_available = all(
        value is not None
        for value in (overlay, baseline, placebo, delayed, double_cost)
    )
    research_gates = [
        _gate(
            "real_data_classification",
            config.data_classification == "real",
            f"classification={config.data_classification}",
            "research",
        ),
        _gate(
            "event_sample_sufficient",
            usable_count >= config.minimum_events,
            f"usable events={usable_count}, required={config.minimum_events}",
            "research",
        ),
        _gate(
            "oos_sample_sufficient",
            len(oos_refs) >= config.minimum_oos_events,
            (
                f"oos events={len(oos_refs)}, "
                f"required={config.minimum_oos_events}"
            ),
            "research",
        ),
        _gate(
            "rolling_folds_complete",
            rolling_complete,
            (
                f"complete folds={evaluated_folds}, "
                f"required={config.rolling_folds}"
            ),
            "research",
        ),
        _gate(
            "oos_primary_window_positive",
            bool(
                oos_primary["mean_signed_abnormal_return"] is not None
                and oos_primary["mean_signed_abnormal_return"] > 0
            ),
            (
                f"window={config.primary_window_days}, "
                f"mean={oos_primary['mean_signed_abnormal_return']}"
            ),
            "research",
        ),
        _gate(
            "rolling_primary_window_stable",
            bool(
                positive_fold_fraction is not None
                and positive_fold_fraction
                >= config.minimum_positive_fold_fraction
            ),
            (
                f"positive fold fraction={positive_fold_fraction}, "
                f"required={config.minimum_positive_fold_fraction}"
            ),
            "research",
        ),
        _gate(
            "overlay_exceeds_factor_baseline",
            bool(
                economic_inputs_available
                and overlay is not None
                and baseline is not None
                and overlay > baseline
            ),
            f"overlay={overlay}, baseline={baseline}",
            "research",
        ),
        _gate(
            "overlay_exceeds_placebo",
            bool(
                economic_inputs_available
                and overlay is not None
                and placebo is not None
                and overlay > placebo
            ),
            f"overlay={overlay}, placebo={placebo}",
            "research",
        ),
        _gate(
            "overlay_exceeds_one_day_delay",
            bool(
                economic_inputs_available
                and overlay is not None
                and delayed is not None
                and overlay > delayed
            ),
            f"overlay={overlay}, delayed={delayed}",
            "research",
        ),
        _gate(
            "double_cost_exceeds_factor_baseline",
            bool(
                economic_inputs_available
                and double_cost is not None
                and baseline is not None
                and double_cost > baseline
            ),
            f"double_cost={double_cost}, baseline={baseline}",
            "research",
        ),
    ]
    hard_failures = [
        gate["name"] for gate in hard_gates if not gate["passed"]
    ]
    research_failures = [
        gate["name"] for gate in research_gates if not gate["passed"]
    ]
    sufficiency_names = {
        "real_data_classification",
        "event_sample_sufficient",
        "oos_sample_sufficient",
        "rolling_folds_complete",
    }
    if hard_failures:
        decision = "REJECT"
        rationale = "Independent-validation integrity gates failed."
    elif any(name in sufficiency_names for name in research_failures):
        decision = "INCONCLUSIVE"
        rationale = (
            "Integrity gates passed, but real-data or chronological sample "
            "coverage is insufficient."
        )
    elif research_failures:
        decision = "REJECT"
        rationale = (
            "The event overlay did not pass all OOS, rolling, placebo, "
            "delay, and doubled-cost gates."
        )
    else:
        decision = "PROMOTE"
        rationale = (
            "Real-data OOS, rolling stability, placebo, delay, baseline, "
            "and doubled-cost gates all passed."
        )

    return {
        "decision": decision,
        "rationale": rationale,
        "config": {**asdict(config), "config_hash": config.hash},
        "counts": {
            "visible_events": len(event_list),
            "usable_primary_window_events": usable_count,
            "in_sample_events": len(in_sample_refs),
            "out_of_sample_events": len(oos_refs),
        },
        "partitions": {
            "in_sample_event_refs": in_sample_refs,
            "out_of_sample_event_refs": oos_refs,
        },
        "window_summaries": window_summaries,
        "rolling_folds": rolling,
        "scenario_returns": scenario_values,
        "gates": [*hard_gates, *research_gates],
        "hard_failures": hard_failures,
        "research_failures": research_failures,
        "leakage_rows": leakage_rows,
        "invalid_rows": invalid_rows,
        "facts": [
            "Event refs are assigned chronologically and never cross partitions.",
            "Only event-study rows strictly after event observation are evaluated.",
            "Scenario returns are consumed as recorded; this verifier does not tune parameters.",
        ],
        "inferences": [
            "Positive signed abnormal returns are evidence about event-signal direction, not broker execution quality."
        ],
        "unknowns": [
            "Capacity, real borrow, and live market impact remain unknown without production data."
        ],
    }
