"""Tests for joborion.sources.registry — provider result caps + cost pre-flight."""

import pytest

from joborion.database import init_db, close_connection
from joborion.sources.base import ProviderResult, RawJob, store_raw_jobs
from joborion.sources.registry import (
    compute_result_caps,
    preflight_estimate,
    run_providers,
)


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "test.db"
    close_connection(str(db_path))
    c = init_db(str(db_path))
    yield c
    close_connection(str(db_path))


class FakeProvider:
    """Minimal provider that stores its jobs directly via store_raw_jobs."""

    uses_llm = False

    def __init__(self, name="fake", cfg=None, jobs=None, conn=None):
        self.name = name
        self.cfg = cfg or {}
        self.jobs = jobs or []
        self.conn = conn

    def search(self, intent):
        new, existing = store_raw_jobs(self.conn, self.jobs, provider=self.name)
        return ProviderResult(provider=self.name, found=new + existing, stored=new)


def _jobs(count: int) -> list[RawJob]:
    return [
        RawJob(title=f"Engineer {i}", company="Acme", location="Remote",
               url=f"https://x.com/{i}", source="fake")
        for i in range(count)
    ]


class TestComputeResultCaps:
    def test_uses_provider_max_results(self):
        provider = FakeProvider(cfg={"max_results": 5})
        assert compute_result_caps([provider], intent={}) == {"fake": 5}

    def test_falls_back_to_intent_cap(self):
        provider = FakeProvider(cfg={})
        assert compute_result_caps([provider], intent={"max_results": 3}) == {"fake": 3}

    def test_provider_cap_beats_intent_cap(self):
        provider = FakeProvider(cfg={"max_results": 5})
        assert compute_result_caps([provider], intent={"max_results": 3}) == {"fake": 5}

    def test_default_is_unlimited(self):
        provider = FakeProvider(cfg={})
        assert compute_result_caps([provider], intent={}) == {"fake": 0}


class TestPreflightEstimate:
    def test_free_providers_cost_zero(self):
        provider = FakeProvider(cfg={"max_results": 10})
        estimate = preflight_estimate([provider], intent={})
        assert estimate["estimated_cost_usd"] == 0.0
        assert estimate["per_provider"]["fake"]["estimated_cost_usd"] == 0.0

    def test_llm_provider_has_estimated_cost(self):
        provider = FakeProvider(cfg={"max_results": 10})
        provider.uses_llm = True
        estimate = preflight_estimate([provider], intent={})
        assert estimate["per_provider"]["fake"]["estimated_cost_usd"] > 0.0
        assert estimate["estimated_cost_usd"] > 0.0
        assert estimate["estimated_total_jobs"] == 10

    def test_uncapped_uses_default_estimate(self):
        provider = FakeProvider(cfg={})
        estimate = preflight_estimate([provider], intent={})
        assert estimate["per_provider"]["fake"]["estimated_jobs"] == 10


class TestResultCaps:
    def test_respects_result_caps(self, conn):
        provider = FakeProvider(cfg={"max_results": 2}, jobs=_jobs(5), conn=conn)
        caps = compute_result_caps([provider], intent={})
        results = run_providers({}, providers=[provider], conn=conn, caps=caps)
        assert caps["fake"] == 2
        assert results[0].trimmed == 3
        remaining = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE source_provider = 'fake'"
        ).fetchone()[0]
        assert remaining == 2

    def test_unlimited_keeps_all(self, conn):
        provider = FakeProvider(cfg={}, jobs=_jobs(5), conn=conn)
        results = run_providers({}, providers=[provider], conn=conn)
        assert results[0].trimmed == 0
        remaining = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        assert remaining == 5

    def test_trim_only_touches_this_run(self, conn):
        store_raw_jobs(
            conn,
            [RawJob(title="Old", company="Acme", location="Remote",
                    url="https://x.com/old", source="fake")],
            provider="fake",
        )
        provider = FakeProvider(cfg={"max_results": 2}, jobs=_jobs(5), conn=conn)
        results = run_providers({}, providers=[provider], conn=conn)
        assert results[0].trimmed == 3
        remaining = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE source_provider = 'fake'"
        ).fetchone()[0]
        assert remaining == 3  # 1 historical + 2 kept from this run
