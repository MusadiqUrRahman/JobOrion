"""Integration tests for all tool execute() methods.

Uses a real SQLite DB with seeded job data and mocked external dependencies
(LLM, Playwright, web scraping). Validates that tools correctly interact
with the database and return proper ActionResult structures.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from joborion.agent.registry import build_default_registry, ToolRegistry
from joborion.database import close_connection, init_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    """Create a temporary database with seeded jobs and patch DB_PATH."""
    db_path = tmp_path / "test.db"
    close_connection(str(db_path))
    conn = init_db(str(db_path))
    conn.execute(
        """INSERT INTO jobs (url, title, site, location, description, full_description, fit_score, discovered_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "https://example.com/job/1",
            "Senior Python Engineer",
            "example.com",
            "Remote",
            "Looking for a Python dev",
            "We need a senior Python engineer with 5+ years experience. Skills: Python, FastAPI, PostgreSQL, Docker.",
            8,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.execute(
        """INSERT INTO jobs (url, title, site, location, description, discovered_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            "https://example.com/job/2",
            "Junior Backend Dev",
            "example.com",
            "NYC",
            "Entry level backend position",
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()

    import joborion.database as db_mod
    import joborion.tools.database as tool_db_mod
    orig_db_path = db_mod.DB_PATH
    db_mod.DB_PATH = str(db_path)
    tool_db_mod.DB_PATH = str(db_path)
    yield conn
    db_mod.DB_PATH = orig_db_path
    tool_db_mod.DB_PATH = orig_db_path
    close_connection(str(db_path))


# ---------------------------------------------------------------------------
# Discovery Tools
# ---------------------------------------------------------------------------

class TestScrapeJobSpyTool:
    def test_execute_missing_query_returns_ok(self, db):
        from joborion.tools.discovery import ScrapeJobSpyTool
        tool = ScrapeJobSpyTool()
        result = tool.execute(search_query="")
        assert result.status == "ok"

    def test_execute_network_error(self, db, mocker):
        mocker.patch("joborion.discovery.jobspy.search_jobs", side_effect=Exception("network down"))
        from joborion.tools.discovery import ScrapeJobSpyTool
        tool = ScrapeJobSpyTool()
        result = tool.execute(search_query="python engineer")
        assert result.status == "error"
        assert "network down" in result.error


class TestScrapeWorkdayTool:
    def test_execute_timeout_error(self, db, mocker):
        mocker.patch("joborion.discovery.workday.scrape_workday", side_effect=Exception("timeout"))
        from joborion.tools.discovery import ScrapeWorkdayTool
        tool = ScrapeWorkdayTool()
        result = tool.execute(search_query="engineer")
        assert result.status == "error"
        assert "timeout" in result.error


class TestScrapeAISitesTool:
    def test_execute_connection_error(self, db, mocker):
        mocker.patch("joborion.discovery.ai_scraper.scrape_ai_sites", side_effect=Exception("connection refused"))
        from joborion.tools.discovery import ScrapeAISitesTool
        tool = ScrapeAISitesTool()
        result = tool.execute()
        assert result.status == "error"
        assert "connection refused" in result.error


# ---------------------------------------------------------------------------
# Enrichment Tools
# ---------------------------------------------------------------------------

class TestEnrichSingleJobTool:
    def test_execute_missing_url(self, db):
        from joborion.tools.enrichment import EnrichSingleJobTool
        tool = EnrichSingleJobTool()
        result = tool.execute(url="")
        assert result.status == "error"
        assert "url is required" in result.error

    def test_execute_job_not_found(self, db):
        from joborion.tools.enrichment import EnrichSingleJobTool
        tool = EnrichSingleJobTool()
        result = tool.execute(url="https://nonexistent.com/job/999")
        assert result.status == "error"
        assert "not found" in result.error

    def test_execute_enriches_specific_url(self, db, mocker):
        mock_scrape = mocker.patch("joborion.enrichment.page_scraper.scrape_site_batch")
        mock_scrape.return_value = {"ok": 1, "partial": 0, "error": 0}
        from joborion.tools.enrichment import EnrichSingleJobTool
        tool = EnrichSingleJobTool()
        result = tool.execute(url="https://example.com/job/1")
        assert result.status == "ok"
        assert result.details["ok"] == 1
        mock_scrape.assert_called_once()
        call_args = mock_scrape.call_args
        assert call_args[0][1] == "example.com"
        assert len(call_args[0][2]) == 1


class TestEnrichBatchTool:
    def test_execute_calls_batch(self, db, mocker):
        mock_enrich = mocker.patch("joborion.enrichment.page_scraper.enrich_jobs")
        mock_enrich.return_value = {"ok": 5, "partial": 1, "error": 0}
        from joborion.tools.enrichment import EnrichBatchTool
        tool = EnrichBatchTool()
        result = tool.execute(limit=10, workers=2)
        assert result.status == "ok"
        assert result.details["ok"] == 5
        mock_enrich.assert_called_once_with(limit=10, workers=2)


# ---------------------------------------------------------------------------
# Scoring Tools
# ---------------------------------------------------------------------------

class TestScoreSingleJobTool:
    def test_execute_missing_url(self, db):
        from joborion.tools.scoring import ScoreSingleJobTool
        tool = ScoreSingleJobTool()
        result = tool.execute(url="")
        assert result.status == "error"
        assert "url is required" in result.error

    def test_execute_job_not_found(self, db):
        from joborion.tools.scoring import ScoreSingleJobTool
        tool = ScoreSingleJobTool()
        result = tool.execute(url="https://nonexistent.com/job/999")
        assert result.status == "error"
        assert "not found" in result.error

    def test_execute_scores_specific_url(self, db, mocker):
        mocker.patch("joborion.scoring.fit_scorer.score_job",
                      return_value={"score": 7, "keywords": "python,fastapi", "reasoning": "Strong match"})
        mocker.patch("joborion.config.RESUME_PATH")
        from joborion.tools.scoring import ScoreSingleJobTool
        tool = ScoreSingleJobTool()
        result = tool.execute(url="https://example.com/job/1")
        assert result.status == "ok"
        assert result.details["score"] == 7
        assert result.details["keywords"] == "python,fastapi"

        row = db.execute("SELECT fit_score, score_reasoning FROM jobs WHERE url = ?",
                         ("https://example.com/job/1",)).fetchone()
        assert row[0] == 7
        assert "python,fastapi" in row[1]

    def test_execute_llm_returns_zero_score(self, db, mocker):
        mocker.patch("joborion.scoring.fit_scorer.score_job",
                      return_value={"score": 0, "keywords": "", "reasoning": "LLM error: timeout"})
        mocker.patch("joborion.config.RESUME_PATH")
        from joborion.tools.scoring import ScoreSingleJobTool
        tool = ScoreSingleJobTool()
        result = tool.execute(url="https://example.com/job/1")
        assert result.status == "ok"
        assert result.details["score"] == 0


class TestScoreBatchTool:
    def test_execute_calls_batch(self, db, mocker):
        mock_score = mocker.patch("joborion.scoring.fit_scorer.score_jobs")
        mock_score.return_value = {"scored": 3, "errors": 0, "elapsed": 1.2}
        from joborion.tools.scoring import ScoreBatchTool
        tool = ScoreBatchTool()
        result = tool.execute(limit=5, rescore=True)
        assert result.status == "ok"
        assert result.details["scored"] == 3
        mock_score.assert_called_once_with(limit=5, rescore=True)


# ---------------------------------------------------------------------------
# Document Tools
# ---------------------------------------------------------------------------

class TestTailorResumeTool:
    def test_execute_calls_tailor(self, db, mocker):
        mock_tailor = mocker.patch("joborion.scoring.resume_tailor.tailor_resumes")
        mock_tailor.return_value = {"approved": 2, "failed": 0, "errors": 0}
        from joborion.tools.documents import TailorResumeTool
        tool = TailorResumeTool()
        result = tool.execute(url="https://example.com/job/1", min_score=7)
        assert result.status == "ok"
        assert result.details["approved"] == 2
        mock_tailor.assert_called_once_with(min_score=7, limit=1)


class TestWriteCoverLetterTool:
    def test_execute_calls_writer(self, db, mocker):
        mock_writer = mocker.patch("joborion.scoring.cover_writer.write_cover_letters")
        mock_writer.return_value = {"generated": 1, "errors": 0}
        from joborion.tools.documents import WriteCoverLetterTool
        tool = WriteCoverLetterTool()
        result = tool.execute(url="https://example.com/job/1", min_score=8)
        assert result.status == "ok"
        assert result.details["generated"] == 1
        mock_writer.assert_called_once_with(min_score=8, limit=1)


class TestConvertToPdfTool:
    def test_execute_missing_path(self, db):
        from joborion.tools.documents import ConvertToPdfTool
        tool = ConvertToPdfTool()
        result = tool.execute(text_path="")
        assert result.status == "error"
        assert "text_path is required" in result.error

    def test_execute_file_not_found(self, db):
        from joborion.tools.documents import ConvertToPdfTool
        tool = ConvertToPdfTool()
        result = tool.execute(text_path="/nonexistent/path.txt")
        assert result.status == "error"

    def test_execute_converts_file(self, db, mocker, tmp_path):
        fake_pdf = tmp_path / "output.pdf"
        mock_convert = mocker.patch("joborion.scoring.document_converter.convert_to_pdf")
        mock_convert.return_value = fake_pdf
        from joborion.tools.documents import ConvertToPdfTool
        tool = ConvertToPdfTool()
        result = tool.execute(text_path=str(tmp_path / "resume.txt"))
        assert result.status == "ok"
        assert result.details["output"] == str(fake_pdf)
        mock_convert.assert_called_once()


# ---------------------------------------------------------------------------
# Database Tools
# ---------------------------------------------------------------------------

class TestQueryJobsTool:
    def test_execute_discovered_stage(self, db):
        from joborion.tools.database import QueryJobsTool
        tool = QueryJobsTool()
        result = tool.execute(stage="discovered")
        assert result.status == "ok"
        assert result.details["count"] == 2

    def test_execute_with_min_score(self, db):
        from joborion.tools.database import QueryJobsTool
        tool = QueryJobsTool()
        result = tool.execute(stage="scored", min_score=7)
        assert result.status == "ok"
        assert result.details["count"] == 1

    def test_execute_limit(self, db):
        from joborion.tools.database import QueryJobsTool
        tool = QueryJobsTool()
        result = tool.execute(stage="discovered", limit=1)
        assert result.status == "ok"
        assert result.details["count"] == 1


class TestGetJobDetailTool:
    def test_execute_missing_url(self, db):
        from joborion.tools.database import GetJobDetailTool
        tool = GetJobDetailTool()
        result = tool.execute(url="")
        assert result.status == "error"
        assert "url is required" in result.error

    def test_execute_found(self, db):
        from joborion.tools.database import GetJobDetailTool
        tool = GetJobDetailTool()
        result = tool.execute(url="https://example.com/job/1")
        assert result.status == "ok"
        assert result.details["title"] == "Senior Python Engineer"
        assert result.details["fit_score"] == 8

    def test_execute_not_found(self, db):
        from joborion.tools.database import GetJobDetailTool
        tool = GetJobDetailTool()
        result = tool.execute(url="https://nonexistent.com/job/999")
        assert result.status == "ok"
        assert result.details["found"] is False


class TestGetPipelineStatsTool:
    def test_execute_returns_stats(self, db):
        from joborion.tools.database import GetPipelineStatsTool
        tool = GetPipelineStatsTool()
        result = tool.execute()
        assert result.status == "ok"
        assert result.details["total"] == 2
        assert result.details["scored"] == 1


# ---------------------------------------------------------------------------
# Registry Integration
# ---------------------------------------------------------------------------

class TestRegistryIntegration:
    def test_all_tools_registered(self):
        registry = build_default_registry()
        names = registry.list_tools()
        expected = [
            "scrape_jobspy", "scrape_workday", "scrape_ai_sites",
            "enrich_single_job", "enrich_batch",
            "score_single_job", "score_batch",
            "tailor_resume", "write_cover_letter", "convert_to_pdf",
            "query_jobs", "get_job_detail", "get_pipeline_stats",
        ]
        for name in expected:
            assert name in names, f"Missing tool: {name}"

    def test_dispatch_tracks_usage(self):
        registry = ToolRegistry()
        from joborion.tools.database import GetPipelineStatsTool
        registry.register(GetPipelineStatsTool())
        registry.dispatch("get_pipeline_stats")
        registry.dispatch("get_pipeline_stats")
        stats = registry.get_usage_stats()
        assert stats["get_pipeline_stats"] == 2

    def test_tool_descriptions_valid(self):
        registry = build_default_registry()
        descs = registry.get_tool_descriptions()
        assert len(descs) == 14
        for desc in descs:
            assert "name" in desc
            assert "description" in desc
            assert "parameters" in desc
            assert isinstance(desc["parameters"], dict)
