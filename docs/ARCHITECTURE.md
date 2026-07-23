# Architecture

## Current State: Deterministic Pipeline

```
CLI (cli.py)
  └── pipeline.py (orchestrator)
        ├── discovery/jobspy.py      ── scrape boards
        ├── discovery/workday.py     ── scrape Workday ATS
        ├── discovery/ai_scraper.py  ── AI-powered scraping
        ├── enrichment/page_scraper.py ── detail pages
        ├── scoring/fit_scorer.py    ── LLM fit scoring
        ├── scoring/resume_tailor.py ── LLM resume tailoring
        ├── scoring/cover_writer.py  ── LLM cover letters
        └── scoring/document_converter.py ── text to PDF
```

**Data flow:** Linear chain. Each stage reads from SQLite, processes, writes back. No stage communicates with another. No stage makes decisions about what to do next.

**Control flow:** `pipeline.py` calls stage runners in fixed order: discover, enrich, score, tailor, cover, pdf. The user specifies which stages to run. There is no conditional routing, no replanning, no error recovery beyond retry.

**State:** Single SQLite table (`jobs`) shared by all stages. Thread-local connections for concurrency.

## Target State: Agent-Orchestrated Pipeline

```
CLI (cli.py)
  └── agent/orchestrator.py        ── supervisory agent
        ├── agent/planner.py       ── goal decomposition
        ├── agent/memory.py        ── episodic + semantic memory
        ├── agent/reflector.py     ── post-run analysis
        └── pipeline.py            ── existing pipeline (unchanged)
              ├── tools/discovery.py   ── wraps discovery modules
              ├── tools/enrichment.py  ── wraps enrichment modules
              ├── tools/scoring.py     ── wraps scoring modules
              ├── tools/documents.py   ── wraps document modules
              └── tools/database.py    ── wraps database queries
```

**Key architectural decisions:**

1. **The existing pipeline stays.** It works. The agent layer sits above it, calling pipeline stages as tools when needed, not replacing them.

2. **Tools are atomic capabilities, not pipeline stages.** Instead of `run_scoring()` (which processes all jobs), the agent has `score_single_job(url, resume)` and can choose which jobs to score, in what order, with what parameters.

3. **The orchestrator is the only agent that reasons.** Pipeline stages remain deterministic. The orchestrator decides what to do; the stages do it.

4. **Memory is a first-class citizen.** The system remembers past runs, learns what works, and improves over time.

5. **Reflection closes the loop.** After each pipeline run, the system analyzes results and updates its strategy.

## Component Responsibilities

### Orchestrator (the brain)
- Receives user goals ("find and apply to senior Python jobs")
- Decomposes into pipeline actions
- Monitors progress and replans when things fail
- Decides when to stop, retry, or escalate to the user
- Budgets cost and token usage

### Planner (the strategist)
- Breaks high-level goals into ordered tasks
- Estimates cost and time for each task
- Identifies dependencies between tasks
- Generates execution plans the orchestrator approves

### Memory (the experience)
- Records what strategies worked for which sites
- Tracks scoring calibration accuracy
- Stores per-site extraction success rates
- Remembers user preferences and feedback

### Reflector (the critic)
- Analyzes pipeline run results
- Identifies what went well and what didn't
- Updates memory with new insights
- Suggests strategy changes for next run

### Tools (the hands)
- Thin wrappers around existing modules
- Each tool does one thing well
- Tools are stateless and idempotent
- The orchestrator composes tools into workflows

## Data Architecture

### SQLite Tables

```
jobs              ── existing table (unchanged)
source_reliability ── existing table (unchanged)
site_memory       ── NEW: per-site strategy outcomes
run_log           ── NEW: pipeline run metadata and results
reflection_log    ── NEW: post-run analysis entries
cost_ledger       ── NEW: per-action token and cost tracking
```

### Context Window Management

The orchestrator maintains a working context that includes:
- Current goal and plan
- Relevant memory entries (top-5 per site being processed)
- Cost budget remaining
- Previous action results (last 5)
- User preferences

Context is compressed after each action to prevent window overflow.
