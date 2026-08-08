"""Tests for joborion.report — read-only pipeline analytics."""

from datetime import datetime, timedelta, timezone

import pytest

from joborion.database import init_db, close_connection
from joborion.report import (
    build_report,
    cost_report,
    pipeline_funnel,
    provider_report,
    render_report,
    run_history,
)


def _now(days_ago: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "test.db"
    close_connection(str(db_path))
    c = init_db(str(db_path))
    yield c
    close_connection(str(db_path))


def _seed_jobs(conn):
    conn.executemany(
        "INSERT INTO jobs (url, title, full_description, fit_score, "
        "tailored_resume_path, applied_at) VALUES (?, ?, ?, ?, ?, ?)",
        [
            ("u1", "J1", "desc", 8, "/r1.pdf", _now()),
            ("u2", "J2", "desc", 7, None, None),
            ("u3", "J3", None, None, None, None),
        ],
    )
    conn.commit()


def _seed_metrics(conn):
    conn.executemany(
        "INSERT INTO provider_metrics (provider, run_id, run_started_at, found, "
        "stored, passed, scored, applied, rejected, errors, latency_ms, avg_fit) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("A", "r1", _now(1), 10, 8, 7, 5, 2, 1, 0, 500, 7.5),
            ("A", "r2", _now(2), 20, 15, 12, 10, 4, 0, 1, 300, 8.0),
            ("B", "r3", _now(1), 30, 25, 20, 15, 6, 2, 0, 900, 6.5),
            ("C", "r4", _now(60), 100, 90, 80, 70, 30, 5, 0, 100, 9.0),
        ],
    )
    conn.execute("INSERT INTO source_stats (source_name, disabled) VALUES ('B', 1)")
    conn.commit()


def _seed_cost(conn):
    conn.executemany(
        "INSERT INTO cost_ledger (run_id, action, tool, tokens_in, tokens_out, "
        "cost_usd, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            ("r1", "score", "haiku", 1000, 200, 0.5, _now(1)),
            ("r1", "score", "haiku", 800, 150, 0.3, _now(2)),
            ("r2", "plan", "sonnet", 2000, 400, 1.2, _now(1)),
            ("r9", "plan", "haiku", 500, 100, 9.0, _now(60)),
        ],
    )
    conn.commit()


def _seed_runs(conn):
    conn.executemany(
        "INSERT INTO run_log (run_id, started_at, goal, status, jobs_discovered, "
        "jobs_applied, total_cost, total_duration_ms) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("r1", _now(1), "Find Python jobs", "success", 50, 3, 0.4, 10000),
            ("r2", _now(2), "", "running", 10, 0, 0.0, 5000),
            ("r3", _now(60), "old run", "success", 99, 9, 9.9, 100),
        ],
    )
    conn.commit()


class TestPipelineFunnel:
    def test_counts_stages(self, conn):
        _seed_jobs(conn)
        funnel = pipeline_funnel(conn)
        assert funnel["discovered"] == 3
        assert funnel["enriched"] == 2
        assert funnel["scored"] == 2
        assert funnel["tailored"] == 1
        assert funnel["applied"] == 1

    def test_empty_db(self, conn):
        assert pipeline_funnel(conn) == {
            "discovered": 0, "enriched": 0, "scored": 0,
            "tailored": 0, "applied": 0,
        }


class TestProviderReport:
    def test_aggregates_within_window(self, conn):
        _seed_metrics(conn)
        rows = provider_report(conn, days=30)
        by_name = {r["provider"]: r for r in rows}
        assert by_name["A"]["runs"] == 2
        assert by_name["A"]["found"] == 30
        assert by_name["A"]["stored"] == 23
        assert by_name["A"]["passed"] == 19
        assert by_name["A"]["scored"] == 15
        assert by_name["A"]["applied"] == 6
        assert by_name["A"]["rejected"] == 1
        assert by_name["A"]["errors"] == 1
        assert by_name["A"]["avg_fit"] == 7.75
        assert by_name["A"]["avg_latency_ms"] == 400.0
        assert "C" not in by_name

    def test_ordered_by_stored_and_limited(self, conn):
        _seed_metrics(conn)
        rows = provider_report(conn, days=30, top=1)
        assert len(rows) == 1
        assert rows[0]["provider"] == "B"

    def test_disabled_flag(self, conn):
        _seed_metrics(conn)
        rows = {r["provider"]: r for r in provider_report(conn)}
        assert rows["B"]["disabled"] is True
        assert rows["A"]["disabled"] is False


def _seed_legacy(conn):
    conn.executemany(
        "INSERT INTO source_stats (source_name, total_runs, failed_runs, "
        "total_passed, avg_fit, disabled) VALUES (?, ?, ?, ?, ?, ?)",
        [
            ("jobspy", 3, 1, 5, 7.0, 0),
            ("workday", 3, 0, 200, 8.5, 0),
            ("smartextract", 3, 3, 0, None, 1),
        ],
    )
    conn.executemany(
        "INSERT INTO jobs (url, title, strategy) VALUES (?, ?, ?)",
        [
            ("j1", "J1", "workday_api"),
            ("j2", "J2", "workday_api"),
            ("j3", "J3", "jobspy"),
            ("j4", "J4", "provider"),
        ],
    )
    conn.commit()


class TestProviderReportLegacy:
    def test_falls_back_to_source_stats_and_jobs(self, conn):
        _seed_legacy(conn)
        rows = provider_report(conn, days=30)
        by_name = {r["provider"]: r for r in rows}
        assert set(by_name) == {"jobspy", "workday", "smartextract"}
        assert by_name["workday"]["runs"] == 3
        assert by_name["workday"]["found"] == 2
        assert by_name["workday"]["stored"] == 2
        assert by_name["workday"]["passed"] == 200
        assert by_name["workday"]["avg_fit"] == 8.5
        assert by_name["workday"]["disabled"] is False
        assert by_name["jobspy"]["found"] == 1
        assert by_name["smartextract"]["found"] == 0
        assert by_name["smartextract"]["errors"] == 3
        assert by_name["smartextract"]["disabled"] is True

    def test_legacy_ordered_by_stored(self, conn):
        _seed_legacy(conn)
        rows = provider_report(conn, days=30)
        assert [r["provider"] for r in rows] == ["workday", "jobspy", "smartextract"]

    def test_legacy_respects_top_limit(self, conn):
        _seed_legacy(conn)
        rows = provider_report(conn, days=30, top=1)
        assert len(rows) == 1
        assert rows[0]["provider"] == "workday"

    def test_no_phantom_provider_for_unmapped_strategy(self, conn):
        conn.execute(
            "INSERT INTO source_stats (source_name, total_runs) VALUES ('jobspy', 1)"
        )
        conn.execute("INSERT INTO jobs (url, title, strategy) VALUES ('j5', 'J5', 'provider')")
        conn.commit()
        rows = provider_report(conn, days=30)
        assert len(rows) == 1
        assert rows[0]["provider"] == "jobspy"
        assert rows[0]["found"] == 0

    def test_modern_metrics_win_over_legacy(self, conn):
        _seed_legacy(conn)
        _seed_metrics(conn)
        rows = {r["provider"]: r for r in provider_report(conn, days=30)}
        assert "A" in rows
        assert rows["A"]["runs"] == 2
        assert "workday" not in rows


class TestCostReport:
    def test_totals_within_window(self, conn):
        _seed_cost(conn)
        cost = cost_report(conn, days=30)
        assert cost["calls"] == 3
        assert cost["total_cost_usd"] == 2.0
        assert [t["tool"] for t in cost["by_tool"]] == ["sonnet", "haiku"]
        assert cost["by_tool"][1]["cost_usd"] == 0.8

    def test_empty_db(self, conn):
        cost = cost_report(conn, days=30)
        assert cost["calls"] == 0
        assert cost["total_cost_usd"] == 0.0
        assert cost["by_tool"] == []


class TestRunHistory:
    def test_newest_first_within_window(self, conn):
        _seed_runs(conn)
        runs = run_history(conn, days=30)
        assert [r["run_id"] for r in runs] == ["r1", "r2"]
        assert runs[0]["goal"] == "Find Python jobs"
        assert runs[0]["jobs_discovered"] == 50
        assert runs[0]["jobs_applied"] == 3
        assert runs[0]["total_cost"] == 0.4

    def test_limit(self, conn):
        _seed_runs(conn)
        runs = run_history(conn, days=30, top=1)
        assert len(runs) == 1
        assert runs[0]["run_id"] == "r1"


class TestBuildReport:
    def test_composes_sections(self, conn):
        _seed_jobs(conn)
        _seed_metrics(conn)
        _seed_cost(conn)
        _seed_runs(conn)
        report = build_report(conn, days=30, top=10)
        assert report["window_days"] == 30
        assert report["funnel"]["discovered"] == 3
        assert {p["provider"] for p in report["providers"]} == {"A", "B"}
        assert report["cost"]["calls"] == 3
        assert report["recent_runs"][0]["run_id"] == "r1"

    def test_empty_db(self, conn):
        report = build_report(conn, days=30)
        assert report["funnel"]["discovered"] == 0
        assert report["providers"] == []
        assert report["cost"]["calls"] == 0
        assert report["recent_runs"] == []

    def test_render_empty_is_graceful(self, conn):
        text = render_report(build_report(conn, days=30))
        assert "JobOrion Report" in text
        assert "(no provider data in window)" in text
        assert "(no LLM cost data in window)" in text
        assert "(no runs in window)" in text

    def test_render_seeded(self, conn):
        _seed_metrics(conn)
        _seed_runs(conn)
        text = render_report(build_report(conn, days=30))
        assert "Pipeline funnel:" in text
        assert "Providers:" in text
        assert "disabled" in text
        assert "Recent runs:" in text
        assert "Find Python jobs" in text


class TestCLIReport:
    def test_report_help_shows_flags(self, cli_flags):
        from joborion.cli import app
        from typer.testing import CliRunner

        result = CliRunner().invoke(app, ["report", "--help"])
        assert result.exit_code == 0
        assert "--days" in cli_flags["report"]
        assert "--top" in cli_flags["report"]
        assert "--json" in cli_flags["report"]

    def test_report_runs_on_empty_db(self, conn, monkeypatch, cli_flags):
        from joborion.cli import app
        from typer.testing import CliRunner

        monkeypatch.setattr("joborion.database.get_connection", lambda db_path=None: conn)
        result = CliRunner().invoke(app, ["report"])
        assert result.exit_code == 0
        assert "JobOrion Report" in result.output

    def test_report_json(self, conn, monkeypatch):
        import json

        from joborion.cli import app
        from typer.testing import CliRunner

        monkeypatch.setattr("joborion.database.get_connection", lambda db_path=None: conn)
        result = CliRunner().invoke(app, ["report", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["funnel"]["discovered"] == 0
