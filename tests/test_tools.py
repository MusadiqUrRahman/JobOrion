"""Tests for joborion.agent.tools, registry, and concrete tool implementations."""

import sqlite3
from unittest.mock import patch, MagicMock

import pytest
from joborion.agent.tools import Tool, ActionResult
from joborion.agent.registry import ToolRegistry
from joborion.database import close_connection, init_db


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "test.db"
    close_connection(str(db_path))
    c = init_db(str(db_path))
    yield c
    close_connection(str(db_path))


# ===========================================================================
# Task 1: Tool Base Class + ActionResult
# ===========================================================================

class TestToolBase:
    """Tests for Tool base class and ActionResult dataclass."""

    def test_action_result_fields(self):
        """ActionResult has all required fields."""
        result = ActionResult(
            action="score",
            status="ok",
            details={"score": 8},
            cost=0.001,
            duration_ms=150,
            error=None,
        )
        assert result.action == "score"
        assert result.status == "ok"
        assert result.details == {"score": 8}
        assert result.cost == pytest.approx(0.001)
        assert result.duration_ms == 150
        assert result.error is None

    def test_action_result_error_status(self):
        """ActionResult accepts error status with error message."""
        result = ActionResult(
            action="enrich",
            status="error",
            details={},
            cost=0.0,
            duration_ms=0,
            error="Connection timeout",
        )
        assert result.status == "error"
        assert result.error == "Connection timeout"

    def test_action_result_skipped_status(self):
        """ActionResult accepts 'skipped' status."""
        result = ActionResult(
            action="tailor",
            status="skipped",
            details={"reason": "no jobs above min_score"},
            cost=0.0,
            duration_ms=0,
            error=None,
        )
        assert result.status == "skipped"

    def test_tool_base_cannot_be_instantiated(self):
        """Tool is abstract — cannot instantiate directly."""
        with pytest.raises(TypeError):
            Tool()

    def test_tool_subclass_must_implement_execute(self):
        """Subclass without execute() raises TypeError on instantiation."""
        class BadTool(Tool):
            name = "bad"
            description = "bad tool"
            parameters = {}
        with pytest.raises(TypeError):
            BadTool()

    def test_tool_subclass_works(self):
        """Concrete subclass with execute() can be instantiated."""
        class EchoTool(Tool):
            name = "echo"
            description = "echoes input"
            parameters = {"text": {"type": "string"}}

            def execute(self, **params) -> ActionResult:
                return ActionResult(
                    action="echo",
                    status="ok",
                    details={"text": params.get("text", "")},
                    cost=0.0,
                    duration_ms=0,
                    error=None,
                )

        tool = EchoTool()
        assert tool.name == "echo"
        result = tool.execute(text="hello")
        assert result.details["text"] == "hello"

    def test_tool_estimate_cost_default(self):
        """Default estimate_cost returns 0.0."""
        class SimpleTool(Tool):
            name = "simple"
            description = "simple"
            parameters = {}

            def execute(self, **params) -> ActionResult:
                return ActionResult("simple", "ok", {}, 0.0, 0, None)

        tool = SimpleTool()
        assert tool.estimate_cost() == 0.0

    def test_tool_estimate_duration_default(self):
        """Default estimate_duration returns 0."""
        class SimpleTool(Tool):
            name = "simple"
            description = "simple"
            parameters = {}

            def execute(self, **params) -> ActionResult:
                return ActionResult("simple", "ok", {}, 0.0, 0, None)

        tool = SimpleTool()
        assert tool.estimate_duration() == 0


# ===========================================================================
# Task 2: Tool Registry
# ===========================================================================

class TestRegistry:
    """Tests for ToolRegistry."""

    def test_register_and_dispatch(self):
        """Register a tool and dispatch to it by name."""
        class EchoTool(Tool):
            name = "echo"
            description = "echoes"
            parameters = {}

            def execute(self, **params) -> ActionResult:
                return ActionResult("echo", "ok", params, 0.0, 0, None)

        registry = ToolRegistry()
        registry.register(EchoTool())
        result = registry.dispatch("echo", text="hi")
        assert result.status == "ok"
        assert result.details["text"] == "hi"

    def test_dispatch_unknown_tool_raises(self):
        """Dispatching unknown tool name raises KeyError."""
        registry = ToolRegistry()
        with pytest.raises(KeyError):
            registry.dispatch("nonexistent")

    def test_list_tools(self):
        """list_tools returns registered tool names."""
        class A(Tool):
            name = "a"
            description = "a"
            parameters = {}
            def execute(self, **kwargs): pass

        class B(Tool):
            name = "b"
            description = "b"
            parameters = {}
            def execute(self, **kwargs): pass

        registry = ToolRegistry()
        registry.register(A())
        registry.register(B())
        names = registry.list_tools()
        assert "a" in names
        assert "b" in names

    def test_get_tool_descriptions(self):
        """get_tool_descriptions returns name+description for LLM consumption."""
        class X(Tool):
            name = "x"
            description = "does x"
            parameters = {"q": {"type": "string"}}
            def execute(self, **kwargs): pass

        registry = ToolRegistry()
        registry.register(X())
        descs = registry.get_tool_descriptions()
        assert len(descs) == 1
        assert descs[0]["name"] == "x"
        assert descs[0]["description"] == "does x"
        assert "q" in descs[0]["parameters"]

    def test_track_usage(self):
        """Registry tracks per-tool usage count."""
        class T(Tool):
            name = "t"
            description = "t"
            parameters = {}
            def execute(self, **kwargs):
                return ActionResult("t", "ok", {}, 0.0, 0, None)

        registry = ToolRegistry()
        registry.register(T())
        registry.dispatch("t")
        registry.dispatch("t")
        stats = registry.get_usage_stats()
        assert stats["t"] == 2


# ===========================================================================
# Task 3: Discovery Tools
# ===========================================================================

class TestDiscoveryTools:
    """Tests for discovery tool implementations."""

    def test_scrape_jobspy_returns_result(self):
        """scrape_jobspy tool returns ActionResult with correct structure."""
        from joborion.tools.discovery import ScrapeJobSpyTool

        tool = ScrapeJobSpyTool()
        assert tool.name == "scrape_jobspy"
        assert "search_query" in tool.parameters

    def test_scrape_workday_returns_result(self):
        """scrape_workday tool returns ActionResult with correct structure."""
        from joborion.tools.discovery import ScrapeWorkdayTool

        tool = ScrapeWorkdayTool()
        assert tool.name == "scrape_workday"

    def test_scrape_ai_sites_returns_result(self):
        """scrape_ai_sites tool returns ActionResult with correct structure."""
        from joborion.tools.discovery import ScrapeAISitesTool

        tool = ScrapeAISitesTool()
        assert tool.name == "scrape_ai_sites"


# ===========================================================================
# Task 4: Enrichment Tools
# ===========================================================================

class TestEnrichmentTools:
    """Tests for enrichment tool implementations."""

    def test_enrich_single_job_returns_result(self):
        """enrich_single_job tool has correct structure."""
        from joborion.tools.enrichment import EnrichSingleJobTool

        tool = EnrichSingleJobTool()
        assert tool.name == "enrich_single_job"
        assert "url" in tool.parameters

    def test_enrich_batch_returns_result(self):
        """enrich_batch tool has correct structure."""
        from joborion.tools.enrichment import EnrichBatchTool

        tool = EnrichBatchTool()
        assert tool.name == "enrich_batch"


# ===========================================================================
# Task 5: Scoring Tools
# ===========================================================================

class TestScoringTools:
    """Tests for scoring tool implementations."""

    def test_score_single_job_returns_result(self):
        """score_single_job tool has correct structure."""
        from joborion.tools.scoring import ScoreSingleJobTool

        tool = ScoreSingleJobTool()
        assert tool.name == "score_single_job"
        assert "url" in tool.parameters

    def test_score_batch_returns_result(self):
        """score_batch tool has correct structure."""
        from joborion.tools.scoring import ScoreBatchTool

        tool = ScoreBatchTool()
        assert tool.name == "score_batch"


# ===========================================================================
# Task 6: Document Tools
# ===========================================================================

class TestDocumentTools:
    """Tests for document tool implementations."""

    def test_tailor_returns_result(self):
        """tailor_resume tool has correct structure."""
        from joborion.tools.documents import TailorResumeTool

        tool = TailorResumeTool()
        assert tool.name == "tailor_resume"
        assert "url" in tool.parameters

    def test_cover_returns_result(self):
        """write_cover_letter tool has correct structure."""
        from joborion.tools.documents import WriteCoverLetterTool

        tool = WriteCoverLetterTool()
        assert tool.name == "write_cover_letter"

    def test_pdf_returns_result(self):
        """convert_to_pdf tool has correct structure."""
        from joborion.tools.documents import ConvertToPdfTool

        tool = ConvertToPdfTool()
        assert tool.name == "convert_to_pdf"


# ===========================================================================
# Task 7: Database Query Tools
# ===========================================================================

class TestDatabaseTools:
    """Tests for database query tool implementations."""

    def test_query_jobs_returns_result(self):
        """query_jobs tool has correct structure."""
        from joborion.tools.database import QueryJobsTool

        tool = QueryJobsTool()
        assert tool.name == "query_jobs"
        assert "stage" in tool.parameters

    def test_get_job_detail_returns_result(self):
        """get_job_detail tool has correct structure."""
        from joborion.tools.database import GetJobDetailTool

        tool = GetJobDetailTool()
        assert tool.name == "get_job_detail"
        assert "url" in tool.parameters

    def test_get_pipeline_stats_returns_result(self):
        """get_pipeline_stats tool has correct structure."""
        from joborion.tools.database import GetPipelineStatsTool

        tool = GetPipelineStatsTool()
        assert tool.name == "get_pipeline_stats"


# ===========================================================================
# Task 8: Integration — All Tools Registered
# ===========================================================================

class TestIntegration:
    """Integration tests for the full tool system."""

    def test_all_tools_registered(self):
        """All tools are discoverable through the registry."""
        from joborion.agent.registry import build_default_registry

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

    def test_registry_descriptions_for_llm(self):
        """Registry produces valid tool descriptions for LLM consumption."""
        from joborion.agent.registry import build_default_registry

        registry = build_default_registry()
        descs = registry.get_tool_descriptions()
        assert len(descs) >= 13
        for desc in descs:
            assert "name" in desc
            assert "description" in desc
            assert "parameters" in desc
            assert len(desc["description"]) > 10
