import unittest
from urllib.parse import parse_qs, urlsplit

from evidence_alpha.models import ContractError
from evidence_alpha.news_adapter import NewsAdapter


def _article(url, published, source, synthetic=True):
    return {
        "canonical_url": url,
        "published_at": published,
        "discovered_at": "2026-08-19T08:00:00Z",
        "metadata": {"synthetic_demo": synthetic},
        "source_name": source,
    }


def _evidence(evidence_id, url, source):
    return {
        "id": evidence_id,
        "canonical_url": url,
        "source_name": source,
        "created_at": "2026-08-19T08:00:00Z",
        "stance": "supports",
    }


class FixtureApi:
    def __call__(self, url, timeout):
        parsed = urlsplit(url)
        query = parse_qs(parsed.query)
        if parsed.path == "/api/v1/events":
            data = {"items": [{"id": "E1"}], "next_cursor": None}
        elif parsed.path == "/api/v1/events/E1/timeline":
            data = {"items": [{"version": 2}, {"version": 1}]}
        elif parsed.path == "/api/v1/events/E1":
            version = int(query["version"][0])
            first_url = "https://source.test/first"
            second_url = "https://source.test/second"
            articles = [
                _article(first_url, "2026-08-19T10:00:00Z", "First"),
                _article(second_url, "2026-08-19T10:05:00Z", "Second"),
            ]
            evidence = [_evidence("EV1", first_url, "First")]
            if version == 2:
                evidence.append(_evidence("EV2", second_url, "Second"))
            data = {
                "id": "E1",
                "state": "developing",
                "version": {
                    "version": version,
                    "created_at": "2026-08-19T09:00:00Z",
                    "sentiment_label": "positive",
                    "sentiment_score": 1.0,
                    "reliability": 80,
                    "novelty": 60,
                    "reliability_breakdown": {"conflict_penalty": 0},
                },
                "articles": articles,
                "claims": [{"evidence": evidence}],
                "industry_impacts": [{"industry_name": "Technology", "horizon": "medium"}],
                "company_impacts": [
                    {"company_name": "NVIDIA", "ticker": "NVDA", "horizon": "medium"}
                ],
            }
        else:
            raise AssertionError(url)
        return {"request_id": "R1", "data_version": "v1", "data": data}


class CurrentApi:
    def __init__(self, ticker="NVDA", industry="Technology"):
        self.ticker = ticker
        self.industry = industry

    def __call__(self, url, timeout):
        parsed = urlsplit(url)
        if parsed.path == "/api/v1/events":
            return {
                "items": [
                    {
                        "id": "E2",
                        "title": "Current real event",
                        "is_demo": False,
                    }
                ],
                "next_cursor": None,
            }
        if parsed.path != "/api/v1/events/E2":
            raise AssertionError(url)
        return {
            "event": {
                "id": "E2",
                "first_seen": "2026-08-19T10:02:00Z",
                "last_seen": "2026-08-19T10:03:00Z",
                "state": "active",
                "is_demo": False,
            },
            "articles": [
                {
                    "id": "A2",
                    "url": "https://sec.gov/news/real-event",
                    "published_at": "2026-08-19T10:00:00Z",
                    "source_name": "SEC",
                }
            ],
            "claims": [{"id": "C2"}],
            "evidence": [
                {
                    "id": "EV2",
                    "claim_id": "C2",
                    "article_id": "A2",
                    "fetched_at": "2026-08-19T10:04:00Z",
                }
            ],
            "verification": {
                "status": "primary_source_confirmed",
                "confidence": "high",
            },
            "industries": (
                [
                    {
                        "name": self.industry,
                        "direction": "positive",
                        "horizon": "short",
                        "confidence": "high",
                    }
                ]
                if self.industry
                else []
            ),
            "companies": [
                {
                    "name": "NVIDIA",
                    "identifiers": {"ticker": self.ticker},
                    "direction": "positive",
                    "horizon": "short",
                    "confidence": "high",
                }
            ],
            "report": {
                "version": 3,
                "generated_at": "2026-08-19T10:05:00Z",
                "data_cutoff_at": "2026-08-19T10:04:30Z",
                "content_json": {
                    "overall_tone": "positive",
                    "novelty": 0.7,
                },
            },
        }


class NewsAdapterTests(unittest.TestCase):
    def test_synthetic_data_requires_explicit_opt_in(self):
        adapter = NewsAdapter("http://news.test", get_json=FixtureApi())
        with self.assertRaises(ContractError):
            adapter.export()

    def test_every_version_is_exported_with_conservative_timestamps(self):
        adapter = NewsAdapter("http://news.test", get_json=FixtureApi())
        bundle = adapter.export(allow_synthetic=True)
        self.assertEqual([item.event_version for item in bundle.events], [1, 2])
        self.assertEqual(bundle.events[0].observed_at.isoformat(), "2026-08-19T10:00:00+00:00")
        self.assertEqual(bundle.events[1].observed_at.isoformat(), "2026-08-19T10:05:00+00:00")
        self.assertEqual(bundle.events[0].evidence_ids, ("EV1",))
        self.assertEqual(bundle.events[1].evidence_ids, ("EV1", "EV2"))
        self.assertEqual({item.ticker for item in bundle.mappings}, {"NVDA"})
        self.assertTrue(bundle.manifest["synthetic"])

    def test_current_api_exports_authenticated_shape_without_v1_envelope(self):
        bundle = NewsAdapter("http://news.test", get_json=CurrentApi()).export()

        self.assertEqual(len(bundle.events), 1)
        self.assertEqual(bundle.events[0].ref, "E2:v3")
        self.assertEqual(
            bundle.events[0].observed_at.isoformat(),
            "2026-08-19T10:05:00+00:00",
        )
        self.assertEqual(bundle.events[0].evidence_ids, ("EV2",))
        self.assertEqual({item.ticker for item in bundle.mappings}, {"NVDA"})
        self.assertFalse(bundle.manifest["synthetic"])
        self.assertEqual(bundle.manifest["api_dialects"], ["news-claws-current"])
        self.assertFalse(bundle.manifest["contract_degradations_by_event_version"])

    def test_current_api_quarantines_placeholder_tickers(self):
        bundle = NewsAdapter(
            "http://news.test", get_json=CurrentApi("DEMO-GRID")
        ).export()

        self.assertFalse(bundle.mappings)
        self.assertEqual(bundle.manifest["placeholder_mapping_refs"], ["E2:v3"])

    def test_current_api_quarantines_event_without_investable_mapping(self):
        bundle = NewsAdapter(
            "http://news.test", get_json=CurrentApi(ticker="", industry="")
        ).export()

        self.assertFalse(bundle.mappings)
        self.assertEqual(bundle.events[0].entities, ())
        self.assertEqual(bundle.events[0].sectors, ("__UNMAPPED__",))
        self.assertEqual(
            bundle.manifest["contract_degradations_by_event_version"],
            {"E2:v3": ["no_investable_company_or_industry_mapping"]},
        )

    def test_current_api_quarantines_corrupted_industry_mapping(self):
        bundle = NewsAdapter(
            "http://news.test",
            get_json=CurrentApi(ticker="", industry="\ufffd\ufffd\ufffd"),
        ).export()

        self.assertEqual(bundle.events[0].sectors, ("__UNMAPPED__",))
        self.assertEqual(
            bundle.manifest["contract_degradations_by_event_version"],
            {
                "E2:v3": [
                    "industry_mapping_contains_encoding_replacement",
                    "no_investable_company_or_industry_mapping",
                ]
            },
        )
