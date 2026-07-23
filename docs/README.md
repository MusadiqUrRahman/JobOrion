# JobOrion Agentic AI Transformation

This documentation suite defines the transformation of JobOrion from a deterministic automation pipeline into a production-grade autonomous Agentic AI system.

## Principles

1. **Determinism by default, agency by necessity.** Every degree of autonomy is earned, not granted.
2. **Architecture beats framework.** Patterns outlive libraries.
3. **Harness > model.** 98% of reliability lives in the code around the LLM.
4. **Context engineering is the core discipline.** What enters the context window determines everything.
5. **Eval-driven development.** No measurement, no improvement.

## Documentation

| Document | Purpose |
|----------|---------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Current state, target state, and the gap between them |
| [SPECIFICATIONS.md](SPECIFICATIONS.md) | System contracts, interfaces, and data models |
| [ROADMAP.md](ROADMAP.md) | High-level phased transformation plan |
| [PHASES.md](PHASES.md) | Detailed implementation steps per phase |
| [AGENT_DESIGN.md](AGENT_DESIGN.md) | Agent patterns, roles, and decision-making architecture |
| [MEMORY.md](MEMORY.md) | Episodic, semantic, and working memory design |
| [PLANNING.md](PLANNING.md) | Goal decomposition, replanning, and task management |
| [REFLECTION.md](REFLECTION.md) | Self-evaluation, learning loops, and quality improvement |
| [AUTONOMOUS_WORKFLOW.md](AUTONOMOUS_WORKFLOW.md) | Autonomous operation, supervision, and safety bounds |
| [MILESTONES.md](MILESTONES.md) | Concrete milestones and success criteria |

## Autonomy Ladder

| Level | What it is | JobOrion status |
|-------|-----------|-----------------|
| L0 | Single LLM call | Scoring, tailoring, cover letters |
| L1 | Augmented LLM | + retrieval, + tools |
| L2 | Workflow | Deterministic pipeline orchestrating LLM steps |
| L3 | Orchestrator-Worker | LLM decomposes within a bounded graph |
| L4 | Autonomous Agent Loop | LLM chooses the next step until termination |

**Current state: L2.** Target state: L3 with selective L4 components.

## Design Philosophy

The existing pipeline is reliable and should not be broken. The transformation adds intelligent layers ABOVE and AROUND the existing modules, not inside them. Each module becomes a tool that an agent can call, while retaining its deterministic behavior as a fallback.

## Development Skills

All development follows actionable skill protocols stored in `skills/`. These are not documentation — they are working procedures that directly govern how code is written, debugged, and verified.

| Skill | Purpose |
|-------|---------|
| [Writing Plans](../skills/writing-plans.md) | TDD task decomposition before implementation |
| [Executing Plans](../skills/executing-plans.md) | Sequential task execution with verification |
| [Systematic Debugging](../skills/systematic-debugging.md) | Root cause investigation before fixes |
| [Verification Before Completion](../skills/verification-before-completion.md) | Evidence-based completion claims |
| [Subagent-Driven Dev](../skills/subagent-driven-development.md) | Parallel task execution with isolated context |
| [Plan Orchestrate](../skills/plan-orchestrate.md) | Budget-aware plan execution |

See [`skills/README.md`](../skills/README.md) for the full index and skill chain.
