"""Tool registry — central dispatch and discovery for all JobOrion tools.

The registry knows all available tools, provides their descriptions for LLM
consumption, handles dispatch (name → execute), and tracks usage statistics.
"""

from __future__ import annotations

import logging

from joborion.agent.tools import Tool, ActionResult

log = logging.getLogger(__name__)


class ToolRegistry:
    """Central registry for all available tools.

    Handles registration, dispatch, description generation, and usage tracking.
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self._usage: dict[str, int] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool instance.

        Args:
            tool: A Tool subclass instance with a unique name.

        Raises:
            ValueError: If a tool with the same name is already registered.
        """
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' already registered")
        self._tools[tool.name] = tool
        self._usage[tool.name] = 0

    def dispatch(self, name: str, **params) -> ActionResult:
        """Execute a tool by name with the given parameters.

        Args:
            name: The registered tool name.
            **params: Parameters to pass to the tool's execute() method.

        Returns:
            ActionResult from the tool execution.

        Raises:
            KeyError: If no tool is registered with the given name.
        """
        if name not in self._tools:
            raise KeyError(f"Unknown tool: '{name}'")

        self._usage[name] = self._usage.get(name, 0) + 1
        tool = self._tools[name]
        return tool.execute(**params)

    def list_tools(self) -> list[str]:
        """Return sorted list of registered tool names."""
        return sorted(self._tools.keys())

    def get_tool_descriptions(self) -> list[dict]:
        """Return tool descriptions formatted for LLM consumption.

        Returns:
            List of dicts with keys: name, description, parameters.
        """
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            }
            for tool in self._tools.values()
        ]

    def get_usage_stats(self) -> dict[str, int]:
        """Return per-tool usage counts."""
        return dict(self._usage)

    def get_tool(self, name: str) -> Tool | None:
        """Get a tool instance by name, or None if not found."""
        return self._tools.get(name)


def build_default_registry() -> ToolRegistry:
    """Build a registry with all default JobOrion tools registered.

    Returns:
        ToolRegistry with all discovery, enrichment, scoring, document,
        and database tools registered.
    """
    registry = ToolRegistry()

    # Discovery tools
    from joborion.tools.discovery import ScrapeJobSpyTool, ScrapeWorkdayTool, ScrapeAISitesTool
    registry.register(ScrapeJobSpyTool())
    registry.register(ScrapeWorkdayTool())
    registry.register(ScrapeAISitesTool())

    # Enrichment tools
    from joborion.tools.enrichment import EnrichSingleJobTool, EnrichBatchTool
    registry.register(EnrichSingleJobTool())
    registry.register(EnrichBatchTool())

    # Scoring tools
    from joborion.tools.scoring import ScoreSingleJobTool, ScoreBatchTool
    registry.register(ScoreSingleJobTool())
    registry.register(ScoreBatchTool())

    # Document tools
    from joborion.tools.documents import TailorResumeTool, WriteCoverLetterTool, ConvertToPdfTool
    registry.register(TailorResumeTool())
    registry.register(WriteCoverLetterTool())
    registry.register(ConvertToPdfTool())

    # Database tools
    from joborion.tools.database import QueryJobsTool, GetJobDetailTool, GetPipelineStatsTool
    registry.register(QueryJobsTool())
    registry.register(GetJobDetailTool())
    registry.register(GetPipelineStatsTool())

    return registry
