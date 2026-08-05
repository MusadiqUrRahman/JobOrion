"""Tests for the pipeline search stage running source providers."""

from unittest.mock import patch

from joborion.sources.base import ProviderResult
from joborion.pipeline import _run_discovery_stage


class _FakeProvider:
    name = "fake"

    def __init__(self):
        self.calls = 0
        self.last_intent = None

    def search(self, intent):
        self.calls += 1
        self.last_intent = intent
        return ProviderResult(provider=self.name, found=3, stored=2)


class _BrokenProvider:
    name = "broken"

    def search(self, intent):
        return ProviderResult(provider=self.name, errors=1, error="boom")


class TestSearchStage:
    def test_search_runs_all_enabled_providers(self):
        fake = _FakeProvider()
        with patch("joborion.pipeline.build_providers", return_value=[fake]):
            with patch("joborion.pipeline.get_blocked_sites_from_memory", return_value=[]):
                with patch("joborion.pipeline.record_source_run") as record_run:
                    with patch("joborion.pipeline.record_site_attempt") as record_attempt:
                        stats = _run_discovery_stage()

        assert fake.calls == 1
        assert stats == {"fake": "ok"}
        record_run.assert_called_once()
        record_attempt.assert_called_once()

    def test_search_skips_blocked_providers(self):
        fake = _FakeProvider()
        with patch("joborion.pipeline.build_providers", return_value=[fake]):
            with patch("joborion.pipeline.get_blocked_sites_from_memory", return_value=["fake"]):
                with patch("joborion.pipeline.record_source_run"):
                    with patch("joborion.pipeline.record_site_attempt"):
                        stats = _run_discovery_stage()
        assert fake.calls == 0
        assert stats == {}

    def test_search_records_errors(self):
        broken = _BrokenProvider()
        with patch("joborion.pipeline.build_providers", return_value=[broken]):
            with patch("joborion.pipeline.get_blocked_sites_from_memory", return_value=[]):
                with patch("joborion.pipeline.record_source_run") as record_run:
                    with patch("joborion.pipeline.record_site_attempt"):
                        stats = _run_discovery_stage()
        assert stats["broken"] == "error: boom"
        record_run.assert_called_once()
        kwargs = record_run.call_args.kwargs
        assert kwargs["success"] is False
        assert kwargs["error"] == "boom"

    def test_search_builds_intent_from_preferences(self):
        fake = _FakeProvider()
        with patch("joborion.pipeline.build_providers", return_value=[fake]):
            with patch("joborion.pipeline.get_blocked_sites_from_memory", return_value=[]):
                with patch("joborion.pipeline.record_source_run"):
                    with patch("joborion.pipeline.record_site_attempt"):
                        with patch("joborion.pipeline.load_preferences",
                                   return_value={"arrangement": "remote"}) as load_prefs:
                            with patch("joborion.pipeline.map_arrangement",
                                       return_value={"mode": "remote", "locations": ["worldwide"]}):
                                _run_discovery_stage()
        load_prefs.assert_called_once()
        assert fake.last_intent == {"mode": "remote", "locations": ["worldwide"]}
