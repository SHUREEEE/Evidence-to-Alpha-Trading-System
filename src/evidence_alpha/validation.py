from __future__ import annotations

from datetime import datetime
from typing import Iterable

from .models import EventSignal, EventSnapshot, EvidenceRecord, Fill, Order


def _gate(name: str, passed: bool, detail: str, severity: str = "hard") -> dict[str, object]:
    return {"name": name, "passed": passed, "detail": detail, "severity": severity}


def validate_run(
    cutoff: datetime,
    all_events: list[EventSnapshot],
    visible_events: list[EventSnapshot],
    evidence: dict[str, EvidenceRecord],
    signals: Iterable[EventSignal],
    orders: Iterable[Order],
    fills: Iterable[Fill],
    portfolio: dict[str, object],
    oms_summary: dict[str, object],
    scenarios: dict[str, object],
    independent_validation: dict[str, object],
    unmapped: list[dict[str, str]],
    minimum_event_count: int = 30,
) -> dict[str, object]:
    signal_list = list(signals)
    order_list = list(orders)
    fill_list = list(fills)
    expected_visible = {
        event.event_id: max(
            (
                candidate
                for candidate in all_events
                if candidate.event_id == event.event_id
                and candidate.observed_at <= cutoff
                and candidate.asof <= cutoff
            ),
            key=lambda item: (item.event_version, item.asof),
        ).event_version
        for event in visible_events
    }
    version_pass = all(expected_visible[event.event_id] == event.event_version for event in visible_events)
    missing_evidence = sorted(
        {
            evidence_id
            for event in visible_events
            for evidence_id in event.evidence_ids
            if evidence_id not in evidence
        }
    )
    signal_trace_pass = all(
        signal.config_hash
        and signal.evidence_ids
        and all(evidence_id in evidence for evidence_id in signal.evidence_ids)
        for signal in signal_list
    )
    fill_by_order = {fill.order_id: fill for fill in fill_list}
    t1_pass = all(
        order.order_id in fill_by_order
        and fill_by_order[order.order_id].trade_date > order.created_at.date()
        for order in order_list
    )
    constraints = portfolio.get("constraints", {})
    gates = [
        _gate("point_in_time_versions", version_pass, "latest visible event version selected at cutoff"),
        _gate("evidence_completeness", not missing_evidence, f"missing evidence: {missing_evidence}"),
        _gate("signal_lineage", signal_trace_pass, "signals carry evidence IDs and configuration hash"),
        _gate("paper_oms_t_plus_one", t1_pass, "all fills occur after signal cutoff date"),
        _gate("portfolio_constraints", bool(constraints) and all(constraints.values()), str(constraints)),
        _gate(
            "ledger_reconciliation",
            bool(oms_summary.get("reconciliation", {}).get("closed_to_cent")),
            str(oms_summary.get("reconciliation", {})),
        ),
        _gate(
            "stress_scenarios_present",
            all(name in scenarios for name in ("baseline", "overlay", "one_day_delay", "placebo", "double_cost")),
            "baseline, overlay, one-day delay, placebo, and doubled-cost outputs are recorded",
        ),
        _gate(
            "independent_validation_integrity",
            not independent_validation.get("hard_failures"),
            (
                "hard failures="
                f"{independent_validation.get('hard_failures', [])}"
            ),
        ),
        _gate(
            "independent_validation_research",
            independent_validation.get("decision") == "PROMOTE",
            (
                f"decision={independent_validation.get('decision')}; "
                f"research failures="
                f"{independent_validation.get('research_failures', [])}"
            ),
            severity="research",
        ),
        _gate(
            "mapping_disclosure",
            True,
            f"{len(unmapped)} unmapped entity records disclosed",
            severity="disclosure",
        ),
        _gate(
            "sample_sufficiency",
            len(visible_events) >= minimum_event_count,
            f"visible events={len(visible_events)}, required={minimum_event_count}",
            severity="research",
        ),
    ]
    hard_failures = [gate for gate in gates if gate["severity"] == "hard" and not gate["passed"]]
    if hard_failures:
        decision = "REJECT"
        rationale = "One or more integrity gates failed."
    elif independent_validation.get("decision") == "INCONCLUSIVE":
        decision = "INCONCLUSIVE"
        rationale = str(independent_validation.get("rationale"))
    elif independent_validation.get("decision") == "PROMOTE":
        decision = "PROMOTE"
        rationale = str(independent_validation.get("rationale"))
    else:
        decision = "REJECT"
        rationale = str(independent_validation.get("rationale"))
    return {
        "decision": decision,
        "rationale": rationale,
        "gates": gates,
        "missing_evidence_ids": missing_evidence,
        "unmapped": unmapped,
        "facts": [
            "All reported hard gates are computed from the current run artifacts.",
            "Paper execution is simulated and does not represent broker fills.",
        ],
        "inferences": [
            "Passing integrity gates makes the run reproducible but does not prove economic value."
        ],
        "unknowns": [
            "Real execution quality and production capacity remain unknown without broker and market-impact data."
        ],
    }
