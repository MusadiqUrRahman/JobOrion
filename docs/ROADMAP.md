# Roadmap

## Overview

Six phases, ordered by value delivered and dependency. Each phase produces a working system that is better than the previous one. No phase requires the next phase to be useful.

```
Phase 0: Foundation          ── installable package, tests, README
Phase 1: Memory              ── the system remembers what happens
Phase 2: Tools               ── pipeline stages become composable tools
Phase 3: Orchestrator        ── an agent decides what to do
Phase 4: Reflection          ── the system learns from outcomes
Phase 5: Full Autonomy       ── goal-driven operation with supervision
```

## Phase 0: Foundation

**Goal:** Make the project installable, tested, and documented.

**Value:** Immediate. Every subsequent phase builds on this.

**Duration:** 1-2 days

**Deliverables:**
- `pip install -e .` works, `joborion` command available
- README with setup instructions
- Unit tests for database, config, output_checker, document_converter
- CI linting with ruff

## Phase 1: Memory

**Goal:** The system remembers what happens across runs.

**Value:** High. Without memory, every run starts from scratch. With memory, the system knows which sites work, which strategies succeed, and what the user prefers.

**Duration:** 3-5 days

**Depends on:** Phase 0

**Deliverables:**
- `site_memory` table tracking per-site outcomes
- `run_log` table recording each pipeline run
- `cost_ledger` tracking token usage and costs
- Memory read/write functions used by discovery and enrichment
- Source routing that uses memory to prioritize reliable sources

## Phase 2: Tools

**Goal:** Pipeline stages become atomic, composable tools.

**Value:** High. This enables the orchestrator to call individual capabilities instead of running entire stages. The agent can score one job, tailor one resume, or enrich one page without processing everything.

**Duration:** 3-5 days

**Depends on:** Phase 0

**Deliverables:**
- Tool interface definition (name, description, parameters, execute)
- `tools/discovery.py` — individual job board scrapers as tools
- `tools/enrichment.py` — single-page enrichment as a tool
- `tools/scoring.py` — single-job scoring as a tool
- `tools/documents.py` — resume tailoring and cover letter as tools
- `tools/database.py` — query and update tools
- Cost estimation for each tool
- Error classification for each tool

## Phase 3: Orchestrator

**Goal:** An agent decides what pipeline actions to take.

**Value:** High. This is the core transformation from pipeline to agent. The orchestrator decomposes goals into actions, monitors progress, and adapts to failures.

**Duration:** 5-7 days

**Depends on:** Phase 1, Phase 2

**Deliverables:**
- `agent/orchestrator.py` — main decision loop
- `agent/planner.py` — goal decomposition into action sequences
- Context window management (compression, working memory)
- Cost budget enforcement
- Error recovery with retry and escalation
- Integration with CLI (`joborion run --goal "..."`)

## Phase 4: Reflection

**Goal:** The system analyzes its own performance and improves.

**Value:** Medium-High. Reflection turns one-time fixes into lasting improvements. The system gets better at its job over time.

**Duration:** 3-5 days

**Depends on:** Phase 1, Phase 3

**Deliverables:**
- `agent/reflector.py` — post-run analysis
- `reflection_log` table
- Scoring calibration analysis (are 7+ scores actually good?)
- Site strategy recommendations
- Cover letter quality feedback loop
- CLI command: `joborion reflect`

## Phase 5: Full Autonomy

**Goal:** Goal-driven operation with minimal human supervision.

**Value:** Medium. This is the capstone that ties everything together. The system can receive a goal, plan, execute, learn, and report.

**Duration:** 5-7 days

**Depends on:** Phase 1-4

**Deliverables:**
- `joborion run --goal "senior python remote"` — full autonomous run
- `joborion search --goal "ML engineers at FAANG"` — agent-driven search
- Periodic autonomous runs (cron-like)
- Human-in-the-loop approval gates
- Cost cap enforcement with automatic stop
- Run summary with reflection

## Dependency Graph

```
Phase 0 (Foundation)
  ├── Phase 1 (Memory)
  └── Phase 2 (Tools)
        ├── Phase 3 (Orchestrator)
        │     ├── Phase 4 (Reflection)
        │     └── Phase 5 (Full Autonomy)
        └── Phase 4 (Reflection)
```

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| LLM cost exceeds budget | High | Cost ledger + hard caps enforced in code |
| Orchestrator makes bad decisions | Medium | Start with narrow goals, add human approval gates |
| Memory becomes stale | Low | TTL on memory entries, periodic reflection |
| Context window overflow | Medium | Aggressive compression, sub-agent delegation |
| Pipeline regression | High | Existing tests + new tool-level tests |

## Success Criteria

The transformation is complete when:

1. **The system can receive a goal and execute autonomously** — "find 10 remote Python jobs paying 150k+, score them, tailor resumes, and apply to the top 5"
2. **The system learns from outcomes** — after 10 runs, it remembers which sites work and which strategies succeed
3. **The system stays within budget** — cost caps are enforced, no surprise bills
4. **The system fails gracefully** — errors are classified, retried or escalated, never silently swallowed
5. **The existing pipeline still works** — `joborion run` does exactly what it did before
