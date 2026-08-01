"""Tests for apply runner failure suggestions + rejection persistence."""

import pytest

from joborion.apply.runner import (
    _failure_suggestion,
    _is_permanent_failure,
    mark_result,
)
from joborion.database import close_connection, init_db


class TestFailureSuggestion:
    def test_known_reason_returns_actionable_advice(self):
        suggestion = _failure_suggestion("not_eligible_location")
        assert suggestion
        assert "sponsorship" in suggestion.lower() or "local" in suggestion.lower()

    def test_prefixed_reason_strips_prefix(self):
        suggestion = _failure_suggestion("RESULT:FAILED:expired")
        assert suggestion
        assert "expired" in suggestion.lower()

    def test_unknown_reason_returns_none(self):
        assert _failure_suggestion("mystery_reason") is None

    def test_applied_is_not_permanent(self):
        assert _is_permanent_failure("applied") is False

    def test_permanent_reason_classified(self):
        assert _is_permanent_failure("not_eligible_location") is True
        assert _is_permanent_failure("expired") is True

    def test_permanent_prefix_classified(self):
        assert _is_permanent_failure("blocked_by_waf_embargo") is True
        assert _is_permanent_failure("cloudflare_ban") is True


@pytest.fixture
def conn(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    close_connection(str(db_path))
    c = init_db(str(db_path))
    c.execute("""
        INSERT INTO jobs (title, url, location, site)
        VALUES ('Engineer', 'https://example.com/job', 'Remote', 'indeed')
    """)
    c.commit()
    import joborion.apply.runner as runner
    monkeypatch.setattr(runner, "get_connection", lambda: c)
    yield c
    close_connection(str(db_path))


class TestMarkResult:
    def test_failed_write_rejection_columns(self, conn):
        mark_result("https://example.com/job", "failed", "not_eligible_location",
                    permanent=True)
        row = conn.execute(
            "SELECT apply_status, rejection_reason, rejection_suggestion "
            "FROM jobs WHERE url = ?", ("https://example.com/job",)
        ).fetchone()
        assert row[0] == "failed"
        assert row[1] == "not_eligible_location"
        assert "sponsorship" in (row[2] or "").lower()

    def test_applied_clears_rejection_columns(self, conn):
        mark_result("https://example.com/job", "failed", "expired", permanent=True)
        mark_result("https://example.com/job", "applied")
        row = conn.execute(
            "SELECT apply_status, rejection_reason, rejection_suggestion "
            "FROM jobs WHERE url = ?", ("https://example.com/job",)
        ).fetchone()
        assert row[0] == "applied"
        assert row[1] is None
        assert row[2] is None
