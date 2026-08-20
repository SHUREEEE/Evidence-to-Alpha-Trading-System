import unittest
from datetime import datetime, timedelta, timezone

from evidence_alpha.independent_validation import (
    IndependentValidationConfig,
    run_independent_validation,
)
from evidence_alpha.models import EventSnapshot


SCENARIOS = {
    "baseline": 0.01,
    "overlay": 0.04,
    "one_day_delay": 0.02,
    "placebo": 0.005,
    "double_cost": 0.03,
}


def _sample(size=36, negative_oos=False, leak=False):
    events = []
    rows = []
    start = datetime(2025, 1, 1, 9, tzinfo=timezone.utc)
    negative_from = size - 9
    for index in range(size):
        observed = start + timedelta(days=index)
        event = EventSnapshot.from_dict(
            {
                "event_id": f"E{index:03d}",
                "event_version": 1,
                "published_at": (observed - timedelta(minutes=5)).isoformat(),
                "observed_at": observed.isoformat(),
                "event_type": "news_event",
                "direction": "positive",
                "confidence": 0.8,
                "novelty": 0.7,
                "conflict": False,
                "impact_horizon_days": 20,
                "entities": [f"T{index:03d}"],
                "sectors": [],
                "evidence_ids": [f"S{index:03d}"],
                "status": "confirmed",
                "asof": observed.isoformat(),
            }
        )
        events.append(event)
        abnormal = -0.02 if negative_oos and index >= negative_from else 0.02
        event_start = observed.date() if leak and index == 0 else (
            observed + timedelta(days=1)
        ).date()
        for window in (1, 3, 5, 20):
            rows.append(
                {
                    "event_ref": event.ref,
                    "ticker": f"T{index:03d}",
                    "window_days": window,
                    "start_date": event_start.isoformat(),
                    "end_date": (
                        observed + timedelta(days=window + 1)
                    ).date().isoformat(),
                    "return": abnormal,
                    "benchmark_return": 0.0,
                    "abnormal_return": abnormal,
                    "status": "ok",
                }
            )
    return events, rows


class IndependentValidationTests(unittest.TestCase):
    def _run(self, *, classification="real", size=36, **sample_overrides):
        events, rows = _sample(size=size, **sample_overrides)
        return run_independent_validation(
            events=events,
            event_study=rows,
            scenarios=SCENARIOS,
            config=IndependentValidationConfig(
                data_classification=classification,
                minimum_events=30,
                minimum_oos_events=8,
                rolling_folds=3,
                oos_fraction=0.25,
            ),
        )

    def test_real_positive_oos_sample_can_promote(self):
        report = self._run()
        self.assertEqual(report["decision"], "PROMOTE")
        self.assertFalse(report["hard_failures"])
        self.assertFalse(report["research_failures"])
        self.assertEqual(len(report["rolling_folds"]), 3)
        self.assertTrue(
            set(report["partitions"]["in_sample_event_refs"]).isdisjoint(
                report["partitions"]["out_of_sample_event_refs"]
            )
        )

    def test_synthetic_or_small_sample_is_inconclusive(self):
        synthetic = self._run(classification="synthetic")
        small = self._run(size=12)
        self.assertEqual(synthetic["decision"], "INCONCLUSIVE")
        self.assertIn(
            "real_data_classification", synthetic["research_failures"]
        )
        self.assertEqual(small["decision"], "INCONCLUSIVE")
        self.assertIn("event_sample_sufficient", small["research_failures"])

    def test_negative_oos_sample_is_rejected(self):
        report = self._run(negative_oos=True)
        self.assertEqual(report["decision"], "REJECT")
        self.assertIn(
            "oos_primary_window_positive", report["research_failures"]
        )

    def test_pre_observation_study_row_is_rejected(self):
        report = self._run(leak=True)
        self.assertEqual(report["decision"], "REJECT")
        self.assertIn("event_study_after_observation", report["hard_failures"])

    def test_unknown_or_missing_event_reference_is_rejected(self):
        events, rows = _sample()
        rows[0]["event_ref"] = ""
        rows[1]["event_ref"] = "UNKNOWN:v1"
        report = run_independent_validation(
            events=events,
            event_study=rows,
            scenarios=SCENARIOS,
            config=IndependentValidationConfig(
                data_classification="real",
                minimum_events=30,
                minimum_oos_events=8,
                rolling_folds=3,
                oos_fraction=0.25,
            ),
        )
        self.assertEqual(report["decision"], "REJECT")
        self.assertIn("event_study_refs_visible", report["hard_failures"])

    def test_invalid_row_or_nonfinite_scenario_is_rejected(self):
        events, rows = _sample()
        rows[0]["abnormal_return"] = float("nan")
        scenarios = {**SCENARIOS, "overlay": float("inf")}
        report = run_independent_validation(
            events=events,
            event_study=rows,
            scenarios=scenarios,
            config=IndependentValidationConfig(
                data_classification="real",
                minimum_events=30,
                minimum_oos_events=8,
                rolling_folds=3,
                oos_fraction=0.25,
            ),
        )
        self.assertEqual(report["decision"], "REJECT")
        self.assertIn("event_study_rows_valid", report["hard_failures"])
        self.assertIn("robustness_scenarios_numeric", report["hard_failures"])
