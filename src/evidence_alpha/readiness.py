from __future__ import annotations

from datetime import date, datetime
from hashlib import sha256
from ipaddress import ip_address
from pathlib import Path
import json
import re
from typing import Any
from urllib.parse import urlparse

from .models import parse_date, parse_datetime


MINIMUM_PRIMARY_EVENTS = 30
MINIMUM_OOS_EVENTS = 10
MINIMUM_PAPER_SESSIONS = 20
REQUIRED_RESEARCH_GATES = {
    "real_data_classification",
    "event_sample_sufficient",
    "oos_sample_sufficient",
    "rolling_folds_complete",
    "oos_primary_window_positive",
    "rolling_primary_window_stable",
    "overlay_exceeds_factor_baseline",
    "overlay_exceeds_placebo",
    "overlay_exceeds_one_day_delay",
    "double_cost_exceeds_factor_baseline",
}
PLACEHOLDER_HOSTS = {
    "example.com",
    "example.org",
    "example.net",
    "localhost",
}


def _gate(name: str, passed: bool, detail: str) -> dict[str, object]:
    return {
        "name": name,
        "passed": bool(passed),
        "detail": detail,
        "severity": "hard",
    }


def _read_json(path: Path | None, label: str, errors: list[str]) -> Any:
    if path is None:
        errors.append(f"{label}: missing path")
        return None
    if not path.is_file():
        errors.append(f"{label}: file not found")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"{label}: invalid JSON ({type(exc).__name__})")
        return None


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _as_path(value: object, artifact_dir: Path) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    candidate = Path(text)
    if candidate.is_absolute():
        return candidate
    local = artifact_dir / candidate
    if local.exists():
        return local
    return Path.cwd() / candidate


def _external_url(value: object) -> bool:
    try:
        parsed = urlparse(str(value))
    except ValueError:
        return False
    host = (parsed.hostname or "").casefold().rstrip(".")
    if parsed.scheme not in {"http", "https"} or not host:
        return False
    if host in PLACEHOLDER_HOSTS or host.endswith((".invalid", ".test", ".example")):
        return False
    try:
        address = ip_address(host)
    except ValueError:
        return True
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_unspecified
    )


def _is_fixture_path(path: Path | None) -> bool:
    if path is None:
        return True
    normalized = "/".join(part.casefold() for part in path.parts)
    return any(
        marker in normalized
        for marker in ("/tests/fixtures/", "/fixture/", "/demo/", "/synthetic/")
    )


def _valid_commit(value: object) -> bool:
    return bool(re.fullmatch(r"[0-9a-fA-F]{40}", str(value or "")))


def _non_placeholder(value: object) -> bool:
    text = str(value or "").strip().casefold()
    return bool(text) and not any(
        marker in text for marker in ("example", "placeholder", "synthetic", "demo")
    )


def _date_or_none(value: object) -> date | None:
    try:
        return parse_date(str(value), "date")
    except (TypeError, ValueError):
        return None


def _datetime_date_or_none(value: object) -> date | None:
    try:
        return parse_datetime(str(value), "timestamp").date()
    except (TypeError, ValueError):
        return None


def _integer_or_none(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    text = str(value or "").strip()
    if not re.fullmatch(r"-?\d+", text):
        return None
    return int(text)


def _datetime_is_aware(value: object) -> bool:
    try:
        parse_datetime(str(value), "timestamp")
    except (TypeError, ValueError):
        return False
    return True


def _artifact_hash_matches(path: Path | None, expected: object) -> tuple[bool, str | None]:
    if path is None or not path.is_file():
        return False, None
    actual = _sha256_file(path)
    return actual.casefold() == str(expected or "").casefold(), actual


def _attested_artifact(attestation: Any) -> dict[str, Any]:
    if not isinstance(attestation, dict):
        return {}
    artifact = attestation.get("artifact")
    return artifact if isinstance(artifact, dict) else {}


def _attested_production(attestation: Any) -> dict[str, Any]:
    if not isinstance(attestation, dict):
        return {}
    production = attestation.get("production")
    return production if isinstance(production, dict) else {}


def _attested_quality(attestation: Any) -> dict[str, Any]:
    if not isinstance(attestation, dict):
        return {}
    quality = attestation.get("quality")
    return quality if isinstance(quality, dict) else {}


def evaluate_release_readiness(
    *,
    artifact_dir: str | Path,
    factor_attestation_path: str | Path | None = None,
    price_attestation_path: str | Path | None = None,
    pb_validation_path: str | Path | None = None,
    pb_dry_run_manifest_path: str | Path | None = None,
    pb_launch_bundle_path: str | Path | None = None,
    paper_manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    """Evaluate the immutable v0.5 release policy without granting live authority."""
    root = Path(artifact_dir).resolve()
    errors: list[str] = []
    report = _read_json(root / "report.json", "integration report", errors)
    validation = _read_json(
        root / "independent_validation.json", "independent validation", errors
    )
    audit = _read_json(root / "audit.json", "integration audit", errors)
    visible_events = _read_json(root / "visible_events.json", "visible events", errors)
    news_evidence = _read_json(
        root / "news_export" / "evidence.json", "news evidence", errors
    )
    factor_attestation = _read_json(
        Path(factor_attestation_path).resolve() if factor_attestation_path else None,
        "factor attestation",
        errors,
    )
    price_attestation = _read_json(
        Path(price_attestation_path).resolve() if price_attestation_path else None,
        "price attestation",
        errors,
    )
    pb_validation = _read_json(
        Path(pb_validation_path).resolve() if pb_validation_path else None,
        "PB validation",
        errors,
    )
    pb_dry_run = _read_json(
        Path(pb_dry_run_manifest_path).resolve()
        if pb_dry_run_manifest_path
        else None,
        "PB dry-run manifest",
        errors,
    )
    pb_bundle = _read_json(
        Path(pb_launch_bundle_path).resolve() if pb_launch_bundle_path else None,
        "PB launch bundle",
        errors,
    )
    paper_manifest_file = (
        Path(paper_manifest_path).resolve() if paper_manifest_path else None
    )
    paper_manifest = _read_json(paper_manifest_file, "Paper manifest", errors)

    report = report if isinstance(report, dict) else {}
    validation = validation if isinstance(validation, dict) else {}
    audit = audit if isinstance(audit, dict) else {}
    visible_events = visible_events if isinstance(visible_events, list) else []
    news_evidence = news_evidence if isinstance(news_evidence, dict) else {}
    news_manifest = report.get("news_manifest")
    news_manifest = news_manifest if isinstance(news_manifest, dict) else {}
    counts = validation.get("counts")
    counts = counts if isinstance(counts, dict) else {}
    config = validation.get("config")
    config = config if isinstance(config, dict) else {}
    research_rows = validation.get("gates")
    research_rows = research_rows if isinstance(research_rows, list) else []
    research_by_name = {
        str(item.get("name")): bool(item.get("passed"))
        for item in research_rows
        if isinstance(item, dict)
    }

    gates: list[dict[str, object]] = []
    hard_audit_rows = [
        item
        for item in audit.get("gates", [])
        if isinstance(item, dict) and item.get("severity") == "hard"
    ]
    integration_integrity = bool(
        report
        and not report.get("hard_failures")
        and hard_audit_rows
        and all(bool(item.get("passed")) for item in hard_audit_rows)
    )
    gates.append(
        _gate(
            "integration_integrity",
            integration_integrity,
            f"hard failures={report.get('hard_failures', [])}",
        )
    )

    primary_count_value = _integer_or_none(
        counts.get("usable_primary_window_events")
    )
    oos_count_value = _integer_or_none(counts.get("out_of_sample_events"))
    configured_primary = _integer_or_none(config.get("minimum_events"))
    configured_oos = _integer_or_none(config.get("minimum_oos_events"))
    configured_folds = _integer_or_none(config.get("rolling_folds"))
    primary_count = primary_count_value if primary_count_value is not None else 0
    oos_count = oos_count_value if oos_count_value is not None else 0
    if primary_count_value is None:
        errors.append("independent validation: invalid primary event count")
    if oos_count_value is None:
        errors.append("independent validation: invalid OOS event count")
    if None in (configured_primary, configured_oos, configured_folds):
        errors.append("independent validation: invalid policy thresholds")
    policy_not_weakened = bool(
        configured_primary is not None
        and configured_primary >= MINIMUM_PRIMARY_EVENTS
        and configured_oos is not None
        and configured_oos >= MINIMUM_OOS_EVENTS
        and configured_folds is not None
        and configured_folds >= 3
    )
    gates.extend(
        [
            _gate(
                "validation_policy_not_weakened",
                policy_not_weakened,
                (
                    f"configured primary={config.get('minimum_events')}, "
                    f"OOS={config.get('minimum_oos_events')}, "
                    f"folds={config.get('rolling_folds')}"
                ),
            ),
            _gate(
                "primary_event_sample",
                primary_count >= MINIMUM_PRIMARY_EVENTS,
                f"usable={primary_count}, required={MINIMUM_PRIMARY_EVENTS}",
            ),
            _gate(
                "oos_event_sample",
                oos_count >= MINIMUM_OOS_EVENTS,
                f"usable={oos_count}, required={MINIMUM_OOS_EVENTS}",
            ),
            _gate(
                "robustness_and_rolling",
                validation.get("decision") == "PROMOTE"
                and all(research_by_name.get(name, False) for name in REQUIRED_RESEARCH_GATES),
                (
                    f"decision={validation.get('decision')}, failed="
                    f"{sorted(name for name in REQUIRED_RESEARCH_GATES if not research_by_name.get(name, False))}"
                ),
            ),
        ]
    )

    source_urls = news_manifest.get("source_urls_by_event_version")
    source_urls = source_urls if isinstance(source_urls, dict) else {}
    visible_refs = [
        f"{item.get('event_id')}:v{item.get('event_version')}"
        for item in visible_events
        if isinstance(item, dict)
    ]
    url_failures = {
        ref: list(source_urls.get(ref, []))
        for ref in visible_refs
        if not source_urls.get(ref)
        or not all(_external_url(value) for value in source_urls.get(ref, []))
    }
    evidence_rows = news_evidence.get("evidence")
    evidence_rows = evidence_rows if isinstance(evidence_rows, list) else []
    evidence_by_id = {
        str(item.get("evidence_id")): item
        for item in evidence_rows
        if isinstance(item, dict)
    }
    required_evidence_ids = {
        str(evidence_id)
        for item in visible_events
        if isinstance(item, dict)
        for evidence_id in item.get("evidence_ids", [])
    }
    bad_evidence = sorted(
        evidence_id
        for evidence_id in required_evidence_ids
        if evidence_id not in evidence_by_id
        or not _external_url(evidence_by_id[evidence_id].get("source_url"))
    )
    non_synthetic_news = bool(
        news_manifest
        and news_manifest.get("synthetic") is False
        and not news_manifest.get("synthetic_event_refs")
        and not news_manifest.get("placeholder_mapping_refs")
        and not news_manifest.get("contract_degradations_by_event_version")
    )
    gates.extend(
        [
            _gate(
                "news_non_synthetic",
                non_synthetic_news,
                (
                    f"synthetic={news_manifest.get('synthetic')}, "
                    f"placeholder mappings={news_manifest.get('placeholder_mapping_refs', [])}, "
                    f"degradations={sorted(news_manifest.get('contract_degradations_by_event_version', {}))}"
                ),
            ),
            _gate(
                "news_external_provenance",
                bool(visible_refs)
                and not url_failures
                and bool(required_evidence_ids)
                and not bad_evidence,
                f"bad refs={sorted(url_failures)}, bad evidence={bad_evidence}",
            ),
        ]
    )

    factor_inputs = report.get("factor_inputs")
    factor_inputs = factor_inputs if isinstance(factor_inputs, dict) else {}
    weights_path = _as_path(factor_inputs.get("weights"), root)
    prices_path = _as_path(factor_inputs.get("prices"), root)
    production_paths = bool(
        weights_path
        and prices_path
        and weights_path.is_file()
        and prices_path.is_file()
        and not _is_fixture_path(weights_path)
        and not _is_fixture_path(prices_path)
    )
    gates.append(
        _gate(
            "production_input_paths",
            production_paths,
            "factor and price inputs must exist outside fixture/demo paths",
        )
    )

    factor_artifact = _attested_artifact(factor_attestation)
    factor_production = _attested_production(factor_attestation)
    factor_quality = _attested_quality(factor_attestation)
    factor_hash_ok, weights_hash = _artifact_hash_matches(
        weights_path, factor_artifact.get("sha256")
    )
    factor_provenance = bool(
        isinstance(factor_attestation, dict)
        and factor_attestation.get("schema_version") == "1.0"
        and factor_attestation.get("attestation_type") == "factor_weights"
        and factor_production.get("synthetic") is False
        and _non_placeholder(factor_production.get("source_repository"))
        and _valid_commit(factor_production.get("source_commit"))
        and _non_placeholder(factor_production.get("pipeline_run_id"))
        and _datetime_is_aware(factor_production.get("generated_at"))
        and factor_quality.get("point_in_time") is True
        and factor_quality.get("universe_membership_point_in_time") is True
        and factor_quality.get("unresolved_exceptions") == []
    )
    event_dates: list[date] = []
    for item in visible_events:
        if not isinstance(item, dict) or not item.get("observed_at"):
            continue
        parsed_event_date = _datetime_date_or_none(item.get("observed_at"))
        if parsed_event_date is None:
            errors.append(
                "visible events: invalid observed_at for "
                f"{item.get('event_id')}:v{item.get('event_version')}"
            )
        else:
            event_dates.append(parsed_event_date)
    comparison_rows = report.get("comparisons")
    comparison_rows = comparison_rows if isinstance(comparison_rows, dict) else {}
    return_end_dates = [
        _date_or_none(item.get("return_end_date"))
        for item in comparison_rows.values()
        if isinstance(item, dict)
    ]
    return_end_dates = [item for item in return_end_dates if item is not None]
    required_start = min(event_dates) if event_dates else None
    required_end = max(return_end_dates) if return_end_dates else None
    factor_start = _date_or_none(factor_artifact.get("coverage_start"))
    factor_end = _date_or_none(factor_artifact.get("coverage_end"))
    factor_coverage = bool(
        required_start
        and required_end
        and factor_start
        and factor_end
        and factor_start <= required_start
        and factor_end >= required_end
        and report.get("gates", {}).get("factor_asof_not_future") is True
    )
    gates.extend(
        [
            _gate(
                "factor_artifact_hash",
                factor_hash_ok,
                f"verified sha256={weights_hash or 'unavailable'}",
            ),
            _gate(
                "factor_production_provenance",
                factor_provenance,
                "requires immutable production commit/run and PIT universe with no exceptions",
            ),
            _gate(
                "factor_coverage_through_t_plus_one",
                factor_coverage,
                f"coverage={factor_start}..{factor_end}, required={required_start}..{required_end}",
            ),
        ]
    )

    price_artifact = _attested_artifact(price_attestation)
    price_production = _attested_production(price_attestation)
    price_quality = _attested_quality(price_attestation)
    adjustments = (
        price_attestation.get("adjustments", {})
        if isinstance(price_attestation, dict)
        else {}
    )
    adjustments = adjustments if isinstance(adjustments, dict) else {}
    price_hash_ok, prices_hash = _artifact_hash_matches(
        prices_path, price_artifact.get("sha256")
    )
    corporate_action_safe = bool(
        isinstance(price_attestation, dict)
        and price_attestation.get("schema_version") == "1.0"
        and price_attestation.get("attestation_type")
        == "corporate_action_safe_prices"
        and price_production.get("synthetic") is False
        and _non_placeholder(price_production.get("provider"))
        and _non_placeholder(price_production.get("dataset"))
        and _datetime_is_aware(price_production.get("retrieved_at"))
        and adjustments.get("price_field") in {"adj_close", "total_return_index"}
        and adjustments.get("splits") is True
        and adjustments.get("cash_dividends") is True
        and adjustments.get("special_dividends") is True
        and price_quality.get("delistings_represented") is True
        and price_quality.get("unresolved_exceptions") == []
    )
    price_start = _date_or_none(price_artifact.get("coverage_start"))
    price_end = _date_or_none(price_artifact.get("coverage_end"))
    price_coverage = bool(
        required_start
        and required_end
        and price_start
        and price_end
        and price_start <= required_start
        and price_end >= required_end
        and report.get("gates", {}).get("t_plus_one_prices") is True
    )
    gates.extend(
        [
            _gate(
                "price_artifact_hash",
                price_hash_ok,
                f"verified sha256={prices_hash or 'unavailable'}",
            ),
            _gate(
                "corporate_action_safe_prices",
                corporate_action_safe,
                "requires adjusted prices, split/dividend coverage, delistings, and no exceptions",
            ),
            _gate(
                "price_coverage_through_t_plus_one",
                price_coverage,
                f"coverage={price_start}..{price_end}, required={required_start}..{required_end}",
            ),
        ]
    )

    pb_validation = pb_validation if isinstance(pb_validation, dict) else {}
    pb_dry_run = pb_dry_run if isinstance(pb_dry_run, dict) else {}
    pb_bundle = pb_bundle if isinstance(pb_bundle, dict) else {}
    pb_feed_a = _as_path(pb_validation.get("borrow_feed"), root)
    pb_feed_b = _as_path(pb_dry_run.get("borrow_feed"), root)
    same_pb_feed = bool(
        pb_feed_a
        and pb_feed_b
        and pb_feed_a.resolve() == pb_feed_b.resolve()
        and pb_feed_a.is_file()
    )
    pb_feed_hash = _sha256_file(pb_feed_a) if same_pb_feed and pb_feed_a else None
    attested_pb_hashes = [
        str(pb_validation.get("borrow_feed_sha256", "")).casefold(),
        str(pb_dry_run.get("borrow_feed_sha256", "")).casefold(),
        str(pb_bundle.get("borrow_feed_sha256", "")).casefold(),
    ]
    pb_feed_hash_crosscheck = bool(
        same_pb_feed
        and pb_feed_hash
        and all(re.fullmatch(r"[0-9a-f]{64}", item) for item in attested_pb_hashes)
        and len(set(attested_pb_hashes)) == 1
        and attested_pb_hashes[0] == pb_feed_hash
    )
    required_symbols_count = _integer_or_none(
        pb_validation.get("required_symbols_count")
    )
    pb_max_age_days = _integer_or_none(pb_validation.get("max_age_days"))
    pb_validation_pass = bool(
        pb_validation.get("pass_fail") is True
        and pb_validation.get("failures") == []
        and required_symbols_count is not None
        and required_symbols_count > 0
        and pb_validation.get("missing_required_symbols") == []
        and pb_validation.get("stale_symbols") == []
        and pb_validation.get("required_zero_locate_symbols") == []
        and pb_max_age_days is not None
        and pb_max_age_days <= 1
    )
    integration_asof = _date_or_none(str(report.get("asof", ""))[:10])
    pb_asof = _date_or_none(pb_dry_run.get("asof"))
    pb_dry_run_pass = bool(
        pb_dry_run.get("workflow") == "v4_pb_live_dry_run"
        and pb_dry_run.get("status") == "PASS"
        and pb_dry_run.get("synthetic_borrow_used") is False
        and pb_dry_run.get("pipeline_exit_code") == 0
        and pb_asof == integration_asof
        and same_pb_feed
    )
    pb_bundle_pass = bool(
        pb_bundle.get("workflow") == "v4_launch_evidence_bundle"
        and pb_bundle.get("status") == "READY"
        and pb_bundle.get("synthetic_borrow_used") is False
        and pb_bundle.get("pb_dry_run_exit_code") == 0
        and pb_bundle.get("go_no_go_exit_code") == 0
        and _date_or_none(pb_bundle.get("asof")) == integration_asof
    )
    gates.extend(
        [
            _gate(
                "pb_borrow_validation",
                pb_validation_pass,
                f"reason={pb_validation.get('reason')}, required={pb_validation.get('required_symbols_count')}",
            ),
            _gate(
                "pb_real_feed_crosscheck",
                pb_feed_hash_crosscheck,
                (
                    f"same file={same_pb_feed}, "
                    f"attestations agree={len(set(attested_pb_hashes)) == 1}, "
                    f"sha256={pb_feed_hash or 'unavailable'}"
                ),
            ),
            _gate(
                "pb_gated_dry_run",
                pb_dry_run_pass,
                f"status={pb_dry_run.get('status')}, asof={pb_dry_run.get('asof')}",
            ),
            _gate(
                "pb_launch_bundle",
                pb_bundle_pass,
                f"status={pb_bundle.get('status')}",
            ),
        ]
    )

    paper_manifest = paper_manifest if isinstance(paper_manifest, dict) else {}
    expected_dates = paper_manifest.get("expected_session_dates")
    expected_dates = expected_dates if isinstance(expected_dates, list) else []
    sessions = paper_manifest.get("sessions")
    sessions = sessions if isinstance(sessions, list) else []
    parsed_expected = [_date_or_none(item) for item in expected_dates]
    expected_valid = bool(
        len(expected_dates) >= MINIMUM_PAPER_SESSIONS
        and all(parsed_expected)
        and len(set(expected_dates)) == len(expected_dates)
        and expected_dates == sorted(expected_dates)
        and (parsed_expected[-1] - parsed_expected[0]).days >= 25
        and all(item <= date.today() for item in parsed_expected if item)
    )
    session_by_date = {
        str(item.get("session_date")): item
        for item in sessions
        if isinstance(item, dict) and item.get("session_date")
    }
    session_set_complete = bool(
        expected_valid
        and set(session_by_date) == set(expected_dates)
        and len(sessions) == len(expected_dates)
        and paper_manifest.get("missing_session_dates") == []
    )
    paper_base = paper_manifest_file.parent if paper_manifest_file else root
    invalid_paper_sessions: list[str] = []
    verified_paper_hashes: dict[str, str] = {}
    if session_set_complete:
        for session_date in expected_dates:
            item = session_by_date[session_date]
            artifact_path = _as_path(item.get("artifact"), paper_base)
            hash_ok, artifact_hash = _artifact_hash_matches(
                artifact_path, item.get("sha256")
            )
            payload = _read_json(
                artifact_path, f"Paper session {session_date}", errors
            )
            payload = payload if isinstance(payload, dict) else {}
            reconciliation = payload.get("reconciliation")
            reconciliation = (
                reconciliation if isinstance(reconciliation, dict) else {}
            )
            freshness = payload.get("data_freshness")
            freshness = freshness if isinstance(freshness, dict) else {}
            unreconciled_items = _integer_or_none(
                reconciliation.get("unreconciled_items")
            )
            valid = bool(
                hash_ok
                and payload.get("session_date") == session_date
                and payload.get("mode") == "PAPER"
                and payload.get("status") == "PASS"
                and _non_placeholder(payload.get("run_id"))
                and reconciliation.get("closed_to_cent") is True
                and unreconciled_items == 0
                and freshness.get("passed") is True
                and payload.get("exceptions") == []
            )
            if not valid:
                invalid_paper_sessions.append(session_date)
            elif artifact_hash:
                verified_paper_hashes[session_date] = artifact_hash
    paper_provenance = paper_manifest.get("calendar_source")
    paper_provenance = paper_provenance if isinstance(paper_provenance, dict) else {}
    paper_contract = bool(
        paper_manifest.get("schema_version") == "1.0"
        and paper_manifest.get("mode") == "PAPER"
        and paper_manifest.get("market_calendar") in {"XNYS", "XNAS"}
        and _non_placeholder(paper_provenance.get("name"))
        and _non_placeholder(paper_provenance.get("version"))
        and _datetime_is_aware(paper_provenance.get("generated_at"))
        and paper_manifest.get("exceptions") == []
    )
    gates.extend(
        [
            _gate(
                "continuous_paper_contract",
                paper_contract,
                "requires versioned XNYS/XNAS calendar provenance and no exceptions",
            ),
            _gate(
                "continuous_paper_sessions",
                session_set_complete,
                (
                    f"observed={len(session_by_date)}, expected={len(expected_dates)}, "
                    f"required={MINIMUM_PAPER_SESSIONS}"
                ),
            ),
            _gate(
                "continuous_paper_reconciliation",
                session_set_complete and not invalid_paper_sessions,
                f"invalid sessions={invalid_paper_sessions}",
            ),
        ]
    )

    gates.append(
        _gate(
            "input_contract_valid",
            not errors,
            f"errors={errors}",
        )
    )
    failures = [str(item["name"]) for item in gates if not item["passed"]]
    decision = (
        "READY_FOR_LIVE_AUTHORIZATION_REVIEW" if not failures else "BLOCKED"
    )
    evaluated_at = datetime.now().astimezone().isoformat()
    return {
        "schema_version": "1.0",
        "policy": "evidence-alpha-real-readiness-v0.5",
        "evaluated_at": evaluated_at,
        "integration_run_id": report.get("run_id"),
        "decision": decision,
        "gates": gates,
        "hard_failures": failures,
        "input_errors": errors,
        "counts": {
            "usable_primary_window_events": primary_count,
            "out_of_sample_events": oos_count,
            "paper_sessions": len(verified_paper_hashes),
        },
        "verified_hashes": {
            "factor_weights": weights_hash,
            "prices": prices_hash,
            "pb_borrow_feed": pb_feed_hash,
            "paper_sessions": verified_paper_hashes,
        },
        "authorization": {
            "live_trading": "NOT_GRANTED",
            "broker_execution": "BLOCKED",
            "next_step": (
                "independent risk acceptance and explicit live authorization"
                if not failures
                else "clear every hard failure and rerun this policy"
            ),
        },
        "facts": [
            "A caller-provided real label is not sufficient for this policy.",
            "Every external data class is cross-checked against provenance or file hashes.",
            "Passing this policy permits an authorization review; it does not authorize trading.",
        ],
    }


def write_readiness_report(report: dict[str, Any], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return target
