"""Tool base class and ActionResult dataclass for the JobOrion agent system.

Every pipeline stage becomes a Tool that the orchestrator can call.
Tools have standardized input/output, cost tracking, and error classification.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ActionResult:
    """Standardized result from every tool execution.

    Attributes:
        action: What action was performed (tool name).
        status: One of "ok", "error", "skipped", "retry".
        details: Action-specific output data.
        cost: Estimated USD cost of this action.
        duration_ms: Wall-clock time in milliseconds.
        error: Error message if status is "error" or "retry".
    """
    action: str
    status: str
    details: dict
    cost: float
    duration_ms: int
    error: str | None = None


class Tool(ABC):
    """Base class for all JobOrion tools.

    Subclasses must define:
        name: str            — unique tool identifier
        description: str     — human/LLM-readable description
        parameters: dict     — JSON Schema for input parameters

    Subclasses must implement:
        execute(**params) -> ActionResult
    """

    name: str
    description: str
    parameters: dict  # JSON Schema format

    @abstractmethod
    def execute(self, **params) -> ActionResult:
        """Execute the tool with the given parameters."""

    def estimate_cost(self, **params) -> float:
        """Estimate USD cost before execution. Override for non-zero estimates."""
        return 0.0

    def estimate_duration(self, **params) -> int:
        """Estimate duration in ms before execution. Override for non-zero estimates."""
        return 0
