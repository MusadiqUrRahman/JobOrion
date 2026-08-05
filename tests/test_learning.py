"""Tests for joborion.sourcing.learning — source metrics, auto-disable, ordering."""

import pytest

from joborion.database import close_connection, init_db
from joborion.sourcing.learning import (
    auto_disable,
    is_provider_disabled,
    provider_states,
    record_provider_run,
    reliability_ordering,
)


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "test.db"
    close_connection(str(db_path))
    c = init_db(str(db_path))
    yield c
    close_connection(str(db_path))


class _P:
    def __init__(self, name):
        self.name = name


class TestRecordProviderRun:
    def test_records_metrics(self, conn):
        record_provider_run(
            conn, "adzuna",
            found=5, stored=4, passed=3, errors=0, latency_ms=1200,
            avg_fit=7.5, run_id="r1",
        )
        rows = conn.execute("SELECT * FROM provider_metrics WHERE provider = 'adzuna'").fetchall()
        assert len(rows) == 1
        row = rows[0]
        assert row["found"] == 5
        assert row["stored"] == 4
        assert row["passed"] == 3
        assert row["errors"] == 0
        assert row["latency_ms"] == 1200
        assert row["avg_fit"] == 7.5
        assert row["run_id"] == "r1"

    def test_accumulates_state_across_runs(self, conn):
        record_provider_run(conn, "jobspy", found=10, passed=8, avg_fit=7.0)
        record_provider_run(conn, "jobspy", found=6, passed=4, avg_fit=9.0)
        state = provider_states(conn)[0]
        assert state["total_runs"] == 2
        assert state["total_jobs"] == 16
        assert state["total_passed"] == 12
        assert state["avg_jobs_per_run"] == 8.0
        assert state["avg_fit"] == 8.0

    def test_records_failure_latency_and_error(self, conn):
        record_provider_run(conn, "bayt", errors=1, error="rate limited", latency_ms=900)
        rows = conn.execute("SELECT * FROM provider_metrics WHERE provider = 'bayt'").fetchall()
        assert rows[0]["errors"] == 1
        assert rows[0]["latency_ms"] == 900
        state = provider_states(conn)[0]
        assert state["failed_runs"] == 1
        assert state["last_error"] == "rate limited"


class TestAutoDisable:
    def test_auto_disable_after_failures(self, conn):
        for _ in range(3):
            record_provider_run(conn, "bayt", errors=1)
        state = provider_states(conn)[0]
        assert state["consecutive_failures"] == 3
        assert state["disabled"] == 1
        assert state["disabled_at"]
        assert is_provider_disabled(conn, "bayt")

    def test_below_threshold_stays_enabled(self, conn):
        for _ in range(2):
            record_provider_run(conn, "bayt", errors=1)
        state = provider_states(conn)[0]
        assert state["consecutive_failures"] == 2
        assert state["disabled"] == 0
        assert not is_provider_disabled(conn, "bayt")

    def test_success_resets_and_reenables(self, conn):
        for _ in range(3):
            record_provider_run(conn, "bayt", errors=1)
        record_provider_run(conn, "bayt", found=2)
        state = provider_states(conn)[0]
        assert state["consecutive_failures"] == 0
        assert state["disabled"] == 0
        assert state["disabled_at"] is None
        assert not is_provider_disabled(conn, "bayt")

    def test_custom_threshold(self, conn):
        record_provider_run(conn, "remote_boards", errors=1, disable_threshold=1)
        assert is_provider_disabled(conn, "remote_boards")

    def test_sweeper_marks_disabled(self, conn):
        conn.execute(
            "INSERT INTO source_stats (source_name, consecutive_failures, disabled) "
            "VALUES ('workday', 4, 0)"
        )
        conn.commit()
        disabled = auto_disable(conn, threshold=3)
        assert "workday" in disabled
        assert is_provider_disabled(conn, "workday")


class TestReliabilityOrdering:
    def test_orders_reliable_first(self, conn):
        for _ in range(3):
            record_provider_run(conn, "jobspy", found=10)
        for _ in range(3):
            record_provider_run(conn, "adzuna", found=3)
        record_provider_run(conn, "workday", found=4)
        record_provider_run(conn, "workday", errors=1)
        for _ in range(3):
            record_provider_run(conn, "bayt", errors=1)

        order = [p.name for p in reliability_ordering(conn, [_P("bayt"), _P("jobspy"), _P("workday"), _P("adzuna")])]
        assert order[0] == "jobspy"
        assert order[1] == "adzuna"
        assert order[2] == "workday"
        assert order[-1] == "bayt"

    def test_unknown_providers_keep_relative_order(self, conn):
        order = [p.name for p in reliability_ordering(conn, [_P("b"), _P("a"), _P("c")])]
        assert order == ["b", "a", "c"]

    def test_handles_unreadable_db(self, conn):
        conn.execute("DROP TABLE source_stats")
        conn.commit()
        order = [p.name for p in reliability_ordering(conn, [_P("x"), _P("y")])]
        assert order == ["x", "y"]
