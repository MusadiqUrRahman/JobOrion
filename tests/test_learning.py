"""Tests for joborion.sourcing.learning — source metrics, auto-disable, ordering."""

import pytest

from joborion.database import close_connection, init_db
from joborion.sourcing.learning import (
    auto_disable,
    feedback_title_terms,
    is_provider_disabled,
    note_company_run,
    provider_states,
    prune_zero_yield_companies,
    pruned_companies,
    reconcile_company_yields,
    record_feedback,
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


class TestCompanyYield:
    def test_note_records_runs(self, conn):
        note_company_run(conn, "ats_boards", "stripe")
        note_company_run(conn, "ats_boards", "stripe")
        row = conn.execute(
            "SELECT * FROM company_yield WHERE provider='ats_boards' AND company='stripe'"
        ).fetchone()
        assert row["total_runs"] == 2

    def test_passes_reset_consecutive_zero(self, conn):
        note_company_run(conn, "ats_boards", "stripe")
        reconcile_company_yields(conn, {"ats_boards": {"stripe": {"found": 5, "passed": 0}}})
        note_company_run(conn, "ats_boards", "stripe")
        reconcile_company_yields(conn, {"ats_boards": {"stripe": {"found": 5, "passed": 2}}})
        row = conn.execute(
            "SELECT * FROM company_yield WHERE provider='ats_boards' AND company='stripe'"
        ).fetchone()
        assert row["consecutive_zero"] == 0
        assert row["last_pass_count"] == 2

    def test_zero_pass_advances_counter(self, conn):
        note_company_run(conn, "ats_boards", "deadbeat")
        reconcile_company_yields(conn, {"ats_boards": {"deadbeat": {"found": 3, "passed": 0}}})
        row = conn.execute(
            "SELECT * FROM company_yield WHERE provider='ats_boards' AND company='deadbeat'"
        ).fetchone()
        assert row["consecutive_zero"] == 1

    def test_prunes_zero_yield_companies(self, conn):
        for _ in range(2):
            note_company_run(conn, "ats_boards", "deadbeat")
            reconcile_company_yields(conn, {"ats_boards": {"deadbeat": {"found": 2, "passed": 0}}})
        note_company_run(conn, "ats_boards", "goodco")
        reconcile_company_yields(conn, {"ats_boards": {"goodco": {"found": 4, "passed": 3}}})

        pruned = prune_zero_yield_companies(conn)
        assert pruned == ["ats_boards:deadbeat"]
        assert "deadbeat" in pruned_companies(conn, "ats_boards")
        assert "goodco" not in pruned_companies(conn, "ats_boards")

    def test_zero_found_company_advances_via_reconcile(self, conn):
        note_company_run(conn, "workday", "acme", found=0)
        reconcile_company_yields(conn, {}, noted=[("workday", "acme")])
        row = conn.execute(
            "SELECT * FROM company_yield WHERE provider='workday' AND company='acme'"
        ).fetchone()
        assert row["consecutive_zero"] == 1

    def test_zero_found_company_pruned_after_two_runs(self, conn):
        for _ in range(2):
            note_company_run(conn, "workday", "acme", found=0)
            reconcile_company_yields(conn, {}, noted=[("workday", "acme")])
        assert "workday:acme" in prune_zero_yield_companies(conn)

    def test_below_threshold_not_pruned(self, conn):
        note_company_run(conn, "workday", "acme", found=0)
        reconcile_company_yields(conn, {}, noted=[("workday", "acme")])
        assert prune_zero_yield_companies(conn) == []


class TestFeedback:
    def _seed_job(self, conn, url, title, company="Acme"):
        conn.execute(
            "INSERT INTO jobs (url, title, company) VALUES (?, ?, ?)",
            (url, title, company),
        )
        conn.commit()

    def test_record_feedback_upserts(self, conn):
        self._seed_job(conn, "https://a/1", "Senior Python Engineer")
        record_feedback(conn, "https://a/1", "like")
        record_feedback(conn, "https://a/1", "like")
        rows = conn.execute(
            "SELECT * FROM user_feedback WHERE job_url='https://a/1'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["sentiment"] == "like"
        job = conn.execute(
            "SELECT user_feedback FROM jobs WHERE url='https://a/1'"
        ).fetchone()
        assert job["user_feedback"] == "like"

    def test_rejects_invalid_sentiment(self, conn):
        self._seed_job(conn, "https://a/1", "Python Engineer")
        with pytest.raises(ValueError):
            record_feedback(conn, "https://a/1", "meh")

    def test_feedback_weights_title_terms(self, conn):
        self._seed_job(conn, "https://a/1", "Senior Python Engineer")
        self._seed_job(conn, "https://a/2", "Senior Java Developer")
        record_feedback(conn, "https://a/1", "like")
        record_feedback(conn, "https://a/2", "dislike")

        weights = feedback_title_terms(conn)
        assert weights["python"] == 1
        assert weights["engineer"] == 1
        assert weights["java"] == -1
        assert weights["developer"] == -1
        assert weights["senior"] == 0  # liked once, disliked once -> net 0

    def test_unknown_job_records_without_title(self, conn):
        record_feedback(conn, "https://unknown/1", "like")
        row = conn.execute(
            "SELECT * FROM user_feedback WHERE job_url='https://unknown/1'"
        ).fetchone()
        assert row is not None
        assert row["job_title"] is None
        assert feedback_title_terms(conn) == {}
