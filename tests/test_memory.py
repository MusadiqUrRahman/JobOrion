"""Tests for joborion.memory — site_memory, run_log, cost_ledger, budget enforcement."""

import os
import sqlite3
from unittest.mock import patch, MagicMock

import pytest
from joborion.database import (
    get_connection,
    close_connection,
    init_db,
    # Site memory
    record_site_attempt,
    get_site_memory,
    get_reliable_sites,
    get_blocked_sites_from_memory,
    unblock_site,
    # Run log
    start_run,
    finish_run,
    get_recent_runs,
    # Cost ledger
    record_cost,
    get_run_cost,
    get_total_cost,
)
from joborion.llm import LLMClient, BudgetExceeded


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary database and return its path."""
    db_path = tmp_path / "test.db"
    close_connection(str(db_path))
    yield db_path
    close_connection(str(db_path))


@pytest.fixture
def conn(tmp_db):
    """Initialize a fresh database and return the connection."""
    c = init_db(str(tmp_db))
    yield c
    close_connection(str(tmp_db))


# ===========================================================================
# Site Memory Tests
# ===========================================================================

class TestSiteMemory:
    """Tests for site_memory table and functions."""

    def test_record_site_attempt_success(self, conn):
        """Successful attempt increments counters correctly."""
        record_site_attempt("RemoteOK", success=True, duration_ms=1500, conn=conn)
        mem = get_site_memory("RemoteOK", conn=conn)

        assert mem is not None
        assert mem["site_name"] == "RemoteOK"
        assert mem["total_attempts"] == 1
        assert mem["successful_extractions"] == 1
        assert mem["avg_extraction_time_ms"] == 1500
        assert mem["last_attempted_at"] is not None

    def test_record_site_attempt_failure(self, conn):
        """Failed attempt increments total but not successful."""
        record_site_attempt("Dice", success=False, conn=conn)
        mem = get_site_memory("Dice", conn=conn)

        assert mem is not None
        assert mem["total_attempts"] == 1
        assert mem["successful_extractions"] == 0

    def test_record_site_attempt_multiple(self, conn):
        """Multiple attempts update averages correctly."""
        record_site_attempt("Indeed", success=True, duration_ms=1000, conn=conn)
        record_site_attempt("Indeed", success=True, duration_ms=2000, conn=conn)
        record_site_attempt("Indeed", success=False, duration_ms=500, conn=conn)

        mem = get_site_memory("Indeed", conn=conn)
        assert mem["total_attempts"] == 3
        assert mem["successful_extractions"] == 2
        # Average: (1000 + 2000 + 500) / 3 = 1166
        assert mem["avg_extraction_time_ms"] == 1166

    def test_record_site_attempt_strategy(self, conn):
        """Strategy is recorded on first attempt."""
        record_site_attempt("LinkedIn", success=True, strategy="api", conn=conn)
        mem = get_site_memory("LinkedIn", conn=conn)
        assert mem["preferred_strategy"] == "api"

    def test_get_site_memory_not_found(self, conn):
        """Returns None for unknown site."""
        assert get_site_memory("Unknown", conn=conn) is None

    def test_get_reliable_sites(self, conn):
        """Returns sites with >50% success rate."""
        # RemoteOK: 3/4 = 75% success
        for _ in range(3):
            record_site_attempt("RemoteOK", success=True, conn=conn)
        record_site_attempt("RemoteOK", success=False, conn=conn)

        # Dice: 1/4 = 25% success
        for _ in range(3):
            record_site_attempt("Dice", success=False, conn=conn)
        record_site_attempt("Dice", success=True, conn=conn)

        reliable = get_reliable_sites(conn=conn)
        assert "RemoteOK" in reliable
        assert "Dice" not in reliable

    def test_get_reliable_sites_min_attempts(self, conn):
        """Sites with <2 attempts are excluded."""
        record_site_attempt("NewSite", success=True, conn=conn)
        reliable = get_reliable_sites(conn=conn)
        assert "NewSite" not in reliable

    def test_get_blocked_sites(self, conn):
        """Returns sites with blocked_reason set."""
        # Manually set blocked_reason
        conn.execute(
            "INSERT INTO site_memory (site_name, blocked_reason) VALUES (?, ?)",
            ("BadSite", "3+ consecutive failures"),
        )
        conn.commit()

        blocked = get_blocked_sites_from_memory(conn=conn)
        assert "BadSite" in blocked

    def test_get_blocked_sites_none_blocked(self, conn):
        """Returns empty list when no sites are blocked."""
        record_site_attempt("GoodSite", success=True, conn=conn)
        blocked = get_blocked_sites_from_memory(conn=conn)
        assert blocked == []

    def test_unblock_site(self, conn):
        """Removes blocked_reason from a site."""
        conn.execute(
            "INSERT INTO site_memory (site_name, blocked_reason) VALUES (?, ?)",
            ("BlockedSite", "3+ consecutive failures"),
        )
        conn.commit()

        result = unblock_site("BlockedSite", conn=conn)
        assert result is True

        mem = get_site_memory("BlockedSite", conn=conn)
        assert mem["blocked_reason"] is None

    def test_unblock_site_not_blocked(self, conn):
        """Returns False for site that isn't blocked."""
        record_site_attempt("ActiveSite", success=True, conn=conn)
        result = unblock_site("ActiveSite", conn=conn)
        assert result is False

    def test_unblock_site_not_found(self, conn):
        """Returns False for unknown site."""
        result = unblock_site("GhostSite", conn=conn)
        assert result is False

    def test_site_memory_idempotent(self, conn):
        """Calling init_db twice doesn't break site_memory."""
        init_db(str(conn.execute("PRAGMA database_list").fetchone()[2]))
        record_site_attempt("Test", success=True, conn=conn)
        mem = get_site_memory("Test", conn=conn)
        assert mem is not None


# ===========================================================================
# Run Log Tests
# ===========================================================================

class TestRunLog:
    """Tests for run_log table and functions."""

    def test_start_run(self, conn):
        """Creates a run entry and returns a run_id."""
        run_id = start_run(goal="find remote jobs", conn=conn)
        assert run_id is not None
        assert len(run_id) > 0

        runs = get_recent_runs(n=1, conn=conn)
        assert len(runs) == 1
        assert runs[0]["run_id"] == run_id
        assert runs[0]["goal"] == "find remote jobs"
        assert runs[0]["status"] == "running"

    def test_finish_run(self, conn):
        """Updates run entry with completion data."""
        run_id = start_run(goal="test", conn=conn)

        finish_run(run_id, stats={
            "stages_run": "discover,enrich,score",
            "jobs_discovered": 50,
            "jobs_enriched": 35,
            "jobs_scored": 35,
            "total_cost": 1.23,
            "total_duration_ms": 45000,
            "status": "completed",
        }, conn=conn)

        runs = get_recent_runs(n=1, conn=conn)
        assert runs[0]["status"] == "completed"
        assert runs[0]["jobs_discovered"] == 50
        assert runs[0]["jobs_enriched"] == 35
        assert runs[0]["total_cost"] == 1.23
        assert runs[0]["completed_at"] is not None

    def test_finish_run_default_status(self, conn):
        """Defaults status to 'completed' when not provided."""
        run_id = start_run(goal="test", conn=conn)
        finish_run(run_id, conn=conn)

        runs = get_recent_runs(n=1, conn=conn)
        assert runs[0]["status"] == "completed"

    def test_get_recent_runs(self, conn):
        """Returns runs in reverse chronological order."""
        id1 = start_run(goal="first", conn=conn)
        id2 = start_run(goal="second", conn=conn)
        id3 = start_run(goal="third", conn=conn)

        runs = get_recent_runs(n=2, conn=conn)
        assert len(runs) == 2
        assert runs[0]["run_id"] == id3
        assert runs[1]["run_id"] == id2

    def test_get_recent_runs_empty(self, conn):
        """Returns empty list when no runs exist."""
        runs = get_recent_runs(conn=conn)
        assert runs == []

    def test_multiple_runs(self, conn):
        """Multiple runs are tracked independently."""
        id1 = start_run(goal="scoring", conn=conn)
        finish_run(id1, stats={"total_cost": 0.50}, conn=conn)

        id2 = start_run(goal="tailoring", conn=conn)
        finish_run(id2, stats={"total_cost": 1.00}, conn=conn)

        runs = get_recent_runs(conn=conn)
        assert len(runs) == 2
        # Most recent first
        assert runs[0]["goal"] == "tailoring"
        assert runs[1]["goal"] == "scoring"


# ===========================================================================
# Cost Ledger Tests
# ===========================================================================

class TestCostLedger:
    """Tests for cost_ledger table and functions."""

    def test_record_cost(self, conn):
        """Records a cost entry correctly."""
        run_id = start_run(goal="test", conn=conn)
        record_cost(run_id, action="score", tool="gemini-2.0-flash",
                    tokens_in=500, tokens_out=100, cost_usd=0.001, conn=conn)

        cost = get_run_cost(run_id, conn=conn)
        assert cost == pytest.approx(0.001)

    def test_record_cost_multiple(self, conn):
        """Multiple costs are summed correctly."""
        run_id = start_run(goal="test", conn=conn)
        record_cost(run_id, action="score", tool="gemini", cost_usd=0.10, conn=conn)
        record_cost(run_id, action="tailor", tool="gemini", cost_usd=0.25, conn=conn)
        record_cost(run_id, action="cover", tool="gemini", cost_usd=0.15, conn=conn)

        cost = get_run_cost(run_id, conn=conn)
        assert cost == pytest.approx(0.50)

    def test_get_run_cost_empty(self, conn):
        """Returns 0.0 for run with no costs."""
        run_id = start_run(goal="test", conn=conn)
        cost = get_run_cost(run_id, conn=conn)
        assert cost == 0.0

    def test_get_run_cost_unknown_run(self, conn):
        """Returns 0.0 for unknown run_id."""
        cost = get_run_cost("nonexistent", conn=conn)
        assert cost == 0.0

    def test_get_total_cost(self, conn):
        """Sums costs across all runs."""
        id1 = start_run(goal="run1", conn=conn)
        record_cost(id1, action="score", tool="gemini", cost_usd=0.10, conn=conn)

        id2 = start_run(goal="run2", conn=conn)
        record_cost(id2, action="tailor", tool="gemini", cost_usd=0.20, conn=conn)

        total = get_total_cost(conn=conn)
        assert total == pytest.approx(0.30)

    def test_get_total_cost_empty(self, conn):
        """Returns 0.0 when no costs recorded."""
        assert get_total_cost(conn=conn) == 0.0

    def test_cost_ledger_has_timestamp(self, conn):
        """Each cost entry has a recorded_at timestamp."""
        run_id = start_run(goal="test", conn=conn)
        record_cost(run_id, action="test", tool="model", cost_usd=0.01, conn=conn)

        row = conn.execute(
            "SELECT recorded_at FROM cost_ledger WHERE run_id = ?", (run_id,)
        ).fetchone()
        assert row is not None
        assert row[0] is not None

    def test_cost_per_run_isolation(self, conn):
        """Costs from different runs don't mix."""
        id1 = start_run(goal="run1", conn=conn)
        record_cost(id1, action="a", tool="m", cost_usd=1.0, conn=conn)

        id2 = start_run(goal="run2", conn=conn)
        record_cost(id2, action="b", tool="m", cost_usd=2.0, conn=conn)

        assert get_run_cost(id1, conn=conn) == pytest.approx(1.0)
        assert get_run_cost(id2, conn=conn) == pytest.approx(2.0)


# ===========================================================================
# Budget Enforcement Tests (LLMClient)
# ===========================================================================

class TestBudgetEnforcement:
    """Tests for LLMClient budget enforcement."""

    def test_set_budget(self):
        """set_budget updates limits correctly."""
        client = LLMClient("http://localhost", "test-model", "key")
        client.set_budget(max_calls=10, max_cost=2.50, run_id="test_run")

        assert client._max_calls_per_run == 10
        assert client._max_cost_usd == 2.50
        assert client._current_run_id == "test_run"
        client.close()

    def test_budget_remaining(self):
        """budget_remaining returns correct value."""
        client = LLMClient("http://localhost", "test-model", "key")
        client.set_budget(max_cost=5.0)
        client._cost_usd = 1.5

        assert client.budget_remaining == pytest.approx(3.5)
        client.close()

    def test_budget_remaining_floor(self):
        """budget_remaining never goes below 0."""
        client = LLMClient("http://localhost", "test-model", "key")
        client.set_budget(max_cost=1.0)
        client._cost_usd = 2.0

        assert client.budget_remaining == 0.0
        client.close()

    def test_cost_usd_property(self):
        """cost_usd property returns accumulated cost."""
        client = LLMClient("http://localhost", "test-model", "key")
        client._cost_usd = 3.14

        assert client.cost_usd == pytest.approx(3.14)
        client.close()

    def test_reset_budget(self):
        """reset_budget clears call count and cost."""
        client = LLMClient("http://localhost", "test-model", "key")
        client._call_count = 5
        client._cost_usd = 2.5
        client.reset_budget()

        assert client._call_count == 0
        assert client._cost_usd == 0.0
        client.close()

    def test_budget_exceeded_on_cost(self):
        """BudgetExceeded raised when cost budget exceeded."""
        client = LLMClient("http://localhost", "test-model", "key")
        client.set_budget(max_cost=0.0)
        client._cost_usd = 0.01  # Already over budget

        with pytest.raises(BudgetExceeded, match="cost budget"):
            client.chat([{"role": "user", "content": "test"}])
        client.close()

    def test_budget_exceeded_on_calls(self):
        """BudgetExceeded raised when call budget exceeded."""
        client = LLMClient("http://localhost", "test-model", "key")
        client.set_budget(max_calls=0)

        with pytest.raises(BudgetExceeded, match="call budget"):
            client.chat([{"role": "user", "content": "test"}])
        client.close()

    def test_budget_from_env(self):
        """Budget reads defaults from environment variables."""
        with patch.dict(os.environ, {"LLM_MAX_CALLS": "25", "LLM_MAX_COST": "10.0"}):
            client = LLMClient("http://localhost", "test-model", "key")
            assert client._max_calls_per_run == 25
            assert client._max_cost_usd == 10.0
            client.close()

    def test_record_cost_integration(self, conn, tmp_db):
        """_record_cost integrates with cost_ledger when run_id is set."""
        run_id = start_run(goal="test", conn=conn)
        client = LLMClient("http://localhost", "test-model", "key")
        client.set_budget(run_id=run_id)

        # Patch record_cost to use the test connection
        from joborion import database as db_mod
        original_record_cost = db_mod.record_cost
        def patched_record_cost(*args, **kwargs):
            kwargs["conn"] = conn
            return original_record_cost(*args, **kwargs)

        with patch.object(db_mod, "record_cost", side_effect=patched_record_cost):
            client._record_cost(action="test_chat", tokens_in=100, tokens_out=50)

        cost = get_run_cost(run_id, conn=conn)
        assert cost > 0
        assert client.cost_usd > 0
        client.close()
