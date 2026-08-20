import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from evidence_alpha.contracts import load_events, select_visible_versions
from evidence_alpha.models import ContractError, EventSnapshot


def event(version=1, observed="2026-01-02T01:00:00+00:00", asof=None):
    return EventSnapshot.from_dict({
        "event_id": "E1", "event_version": version,
        "published_at": "2026-01-02T00:00:00+00:00", "observed_at": observed,
        "event_type": "policy", "direction": "positive", "confidence": 0.8,
        "novelty": 0.7, "conflict": False, "impact_horizon_days": 5,
        "entities": ["A"], "evidence_ids": ["SRC"], "status": "confirmed",
        "asof": asof or observed,
    })


class ContractTests(unittest.TestCase):
    def test_observed_before_published_is_rejected(self):
        with self.assertRaises(ContractError):
            event(observed="2026-01-01T23:00:00+00:00")

    def test_future_version_is_not_visible(self):
        cutoff = datetime(2026, 1, 3, tzinfo=timezone.utc)
        visible = select_visible_versions([event(1), event(2, observed="2026-01-04T01:00:00+00:00")], cutoff)
        self.assertEqual([item.event_version for item in visible], [1])

    def test_duplicate_version_with_different_content_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.json"
            first = event(1).to_dict()
            second = dict(first, confidence=0.1)
            path.write_text(json.dumps([first, second]), encoding="utf-8")
            with self.assertRaises(ContractError):
                load_events(path)

