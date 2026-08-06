"""Tests for Phase F4: personalization dashboard — matched jobs by provider."""

import pytest

from joborion.database import close_connection, init_db
from joborion.dashboard import generate_dashboard, group_by_provider


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "test.db"
    close_connection(str(db_path))
    c = init_db(str(db_path))
    yield c
    close_connection(str(db_path))


def _insert_job(conn, url, title="Python Dev", provider="jobspy", site="Indeed",
                score=8, apply_status=None):
    conn.execute(
        "INSERT INTO jobs (url, title, company, site, source_provider, fit_score, "
        "apply_status, is_remote, salary) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (url, title, "Acme", site, provider, score, apply_status, 1, "150k"),
    )
    conn.commit()


class TestGroupByProvider:
    def test_groups_by_provider(self):
        jobs = [
            {"source_provider": "jobspy", "site": "Indeed", "url": "1"},
            {"source_provider": "jobspy", "site": "Indeed", "url": "2"},
            {"source_provider": "adzuna", "site": "Adzuna", "url": "3"},
        ]
        groups = group_by_provider(jobs)
        assert len(groups) == 2
        by_name = {g["provider"]: g for g in groups}
        assert by_name["jobspy"]["count"] == 2
        assert by_name["adzuna"]["count"] == 1

    def test_falls_back_to_site(self):
        jobs = [{"source_provider": None, "site": "Workday", "url": "1"}]
        assert group_by_provider(jobs)[0]["provider"] == "Workday"

    def test_unknown_provider(self):
        jobs = [{"source_provider": None, "site": None, "url": "1"}]
        assert group_by_provider(jobs)[0]["provider"] == "unknown"


class TestGenerateDashboard:
    def test_writes_html_with_provider_section(self, monkeypatch, conn, tmp_path):
        _insert_job(conn, "https://a.dev/1", score=8)
        monkeypatch.setattr("joborion.dashboard.get_connection", lambda: conn)
        out = tmp_path / "dash.html"
        path = generate_dashboard(str(out))
        content = __import__("pathlib").Path(path).read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "Matched Jobs by Provider" in content
        assert "data-provider='jobspy'" in content
        assert "Python Dev" in content

    def test_excludes_expired_and_unscored(self, monkeypatch, conn, tmp_path):
        _insert_job(conn, "https://a.dev/1", score=8)
        _insert_job(conn, "https://a.dev/2", score=6, apply_status="expired")
        _insert_job(conn, "https://a.dev/3", score=None)
        monkeypatch.setattr("joborion.dashboard.get_connection", lambda: conn)
        path = generate_dashboard(str(tmp_path / "dash.html"))
        content = __import__("pathlib").Path(path).read_text(encoding="utf-8")
        start = content.index("Matched Jobs by Provider")
        end = content.index('<div id="job-count"')
        matched_section = content[start:end]
        assert "https://a.dev/1" in matched_section
        assert "https://a.dev/2" not in matched_section
        assert "https://a.dev/3" not in matched_section

    def test_escapes_job_content(self, monkeypatch, conn, tmp_path):
        _insert_job(conn, "https://a.dev/1", title="<script>alert(1)</script>", score=8)
        monkeypatch.setattr("joborion.dashboard.get_connection", lambda: conn)
        path = generate_dashboard(str(tmp_path / "dash.html"))
        content = __import__("pathlib").Path(path).read_text(encoding="utf-8")
        assert "<script>alert(1)</script>" not in content
        assert "&lt;script&gt;" in content
