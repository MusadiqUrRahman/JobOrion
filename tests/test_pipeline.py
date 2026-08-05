"""Tests for the pipeline search stage running source providers."""

from contextlib import contextmanager
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


@contextmanager
def _gate_patch():
    """Patch relevance-gate + DB access so discovery tests stay hermetic."""
    gate = {"processed": 0, "passed": 0, "dropped": 0, "reasons": {}}
    with patch("joborion.pipeline.apply_relevance_gate", return_value=gate) as gate_call:
        with patch("joborion.pipeline.get_connection"):
            yield gate_call


class TestSearchStage:
    def test_search_runs_all_enabled_providers(self):
        fake = _FakeProvider()
        with patch("joborion.pipeline.build_providers", return_value=[fake]):
            with patch("joborion.pipeline.get_blocked_sites_from_memory", return_value=[]):
                with patch("joborion.pipeline.record_provider_run") as record_run:
                    with patch("joborion.pipeline.record_site_attempt") as record_attempt:
                        with _gate_patch() as gate_call:
                            stats = _run_discovery_stage()

        assert fake.calls == 1
        assert stats == {"fake": "ok"}
        record_run.assert_called_once()
        record_attempt.assert_called_once()
        gate_call.assert_called_once()

    def test_search_skips_blocked_providers(self):
        fake = _FakeProvider()
        with patch("joborion.pipeline.build_providers", return_value=[fake]):
            with patch("joborion.pipeline.get_blocked_sites_from_memory", return_value=["fake"]):
                with patch("joborion.pipeline.record_provider_run"):
                    with patch("joborion.pipeline.record_site_attempt"):
                        with _gate_patch() as gate_call:
                            stats = _run_discovery_stage()
        assert fake.calls == 0
        assert stats == {}
        gate_call.assert_not_called()

    def test_search_records_errors(self):
        broken = _BrokenProvider()
        with patch("joborion.pipeline.build_providers", return_value=[broken]):
            with patch("joborion.pipeline.get_blocked_sites_from_memory", return_value=[]):
                with patch("joborion.pipeline.record_provider_run") as record_run:
                    with patch("joborion.pipeline.record_site_attempt"):
                        with _gate_patch() as gate_call:
                            stats = _run_discovery_stage()
        assert stats["broken"] == "error: boom"
        record_run.assert_called_once()
        kwargs = record_run.call_args.kwargs
        assert kwargs["errors"] == 1
        assert kwargs["error"] == "boom"
        gate_call.assert_called_once()

    def test_search_builds_intent_from_preferences(self):
        fake = _FakeProvider()
        with patch("joborion.pipeline.build_providers", return_value=[fake]):
            with patch("joborion.pipeline.get_blocked_sites_from_memory", return_value=[]):
                with patch("joborion.pipeline.record_provider_run"):
                    with patch("joborion.pipeline.record_site_attempt"):
                        with patch("joborion.pipeline.load_preferences",
                                   return_value={"arrangement": "remote"}) as load_prefs:
                            with patch("joborion.pipeline.map_arrangement",
                                       return_value={"mode": "remote", "locations": ["worldwide"]}):
                                with patch("joborion.pipeline.load_profile",
                                           return_value={
                                               "experience": {"target_role": "software engineer"},
                                               "skills_boundary": {
                                                   "programming_languages": ["python"],
                                                   "frameworks": [],
                                                   "tools": ["docker"],
                                               },
                                           }):
                                    with _gate_patch():
                                        _run_discovery_stage()
        load_prefs.assert_called_once()
        assert fake.last_intent["mode"] == "remote"
        assert fake.last_intent["locations"] == ["worldwide"]
        assert fake.last_intent["keywords"] == ["software engineer", "python", "docker"]

    def test_search_intent_ignores_missing_profile(self):
        fake = _FakeProvider()
        with patch("joborion.pipeline.build_providers", return_value=[fake]):
            with patch("joborion.pipeline.get_blocked_sites_from_memory", return_value=[]):
                with patch("joborion.pipeline.record_provider_run"):
                    with patch("joborion.pipeline.record_site_attempt"):
                        with patch("joborion.pipeline.load_preferences",
                                   return_value={"arrangement": "all"}):
                            with patch("joborion.pipeline.map_arrangement",
                                       return_value={"mode": "all", "locations": ["worldwide"]}):
                                with patch("joborion.pipeline.load_profile", side_effect=FileNotFoundError):
                                    with _gate_patch():
                                        _run_discovery_stage()
        assert fake.last_intent["keywords"] == []

    def test_records_passed_metrics_per_provider(self, tmp_path):
        from joborion.database import close_connection, init_db
        from joborion.sources.base import RawJob, store_raw_jobs

        db_path = tmp_path / "t.db"
        close_connection(str(db_path))
        conn = init_db(str(db_path))
        fake = _FakeProvider()
        store_raw_jobs(
            conn,
            [
                RawJob(
                    title="Senior Python Engineer", company="Acme", location="Remote",
                    description="Building distributed systems in Python",
                    url="https://acme.com/1", source="fake",
                )
            ],
        )
        with patch("joborion.pipeline.build_providers", return_value=[fake]):
            with patch("joborion.pipeline.get_blocked_sites_from_memory", return_value=[]):
                with patch("joborion.pipeline.record_site_attempt"):
                    with patch("joborion.pipeline.load_preferences",
                               return_value={"arrangement": "remote"}):
                        with patch("joborion.pipeline.map_arrangement",
                                   return_value={"mode": "remote", "locations": ["worldwide"],
                                                "job_types": ["all"], "keywords": ["python"]}):
                            with patch("joborion.pipeline.load_profile", return_value={}):
                                with patch("joborion.pipeline.get_connection", return_value=conn):
                                    stats = _run_discovery_stage()

        assert stats == {"fake": "ok"}
        state = conn.execute(
            "SELECT * FROM source_stats WHERE source_name = 'fake'"
        ).fetchone()
        assert state["total_runs"] == 1
        assert state["total_passed"] == 1
        assert state["consecutive_failures"] == 0
        metric = conn.execute(
            "SELECT * FROM provider_metrics WHERE provider = 'fake'"
        ).fetchone()
        assert metric["found"] == 3
        assert metric["passed"] == 1
        close_connection(str(db_path))
