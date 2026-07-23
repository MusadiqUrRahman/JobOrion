# Implementation Phases

## Phase 0: Foundation

### Step 0.1: Package Installation

**File:** `pyproject.toml` (already correct)

Verify `pip install -e .` works and `joborion` CLI command is available.

```bash
pip install -e .
joborion --version
joborion --help
```

### Step 0.2: README

**File:** `README.md` (new)

Write a minimal README with:
- What JobOrion does (one paragraph)
- Requirements (Python 3.11+, Chrome for auto-apply)
- Quick start (`pip install -e .`, `joborion init`, `joborion run`)
- Tier system explanation
- Link to docs/

### Step 0.3: Unit Tests for Output Checker

**File:** `tests/test_output_checker.py` (new)

Test the pure-logic validation functions:
- `BANNED_WORDS` list is not empty
- `LLM_LEAK_PHRASES` list is not empty
- `sanitize_text()` removes em dashes, smart quotes
- `validate_json_fields()` catches banned words
- `validate_cover_letter()` catches LLM leak phrases
- Validation modes (strict/normal/lenient) behave differently

### Step 0.4: Unit Tests for Document Converter

**File:** `tests/test_document_converter.py` (new)

Test the text parsing logic:
- `parse_resume()` extracts header and sections correctly
- `parse_resume()` handles missing fields gracefully
- `parse_resume()` handles various section header formats
- `build_html()` produces valid HTML with all sections
- Edge cases: empty input, no sections, only header

### Step 0.5: Unit Tests for Database

**File:** `tests/test_database.py` (new)

Test database operations with a temporary DB:
- `init_db()` creates all columns
- `init_db()` is idempotent (calling twice doesn't break)
- `store_jobs()` inserts correctly
- `store_jobs()` handles duplicates (IntegrityError)
- `get_jobs_by_stage()` returns correct rows
- `get_stats()` returns complete stats dict
- Thread-local connections work correctly

### Step 0.6: Unit Tests for Config

**File:** `tests/test_config.py` (new)

Test configuration loading:
- `load_profile()` raises FileNotFoundError when missing
- `load_search_config()` falls back to example config
- `load_sites_config()` returns empty dict when missing
- `get_tier()` returns correct tier based on env vars
- `ensure_dirs()` creates all required directories
- `DEFAULTS` dict has all expected keys

### Step 0.7: Linting Setup

**File:** `pyproject.toml` (add ruff config)

Verify ruff runs cleanly:
```bash
ruff check src/
ruff format src/
```

---

## Phase 1: Memory

### Step 1.1: Site Memory Table

**File:** `database.py` (add migration)

Add `site_memory` table to `init_db()`:

```sql
CREATE TABLE IF NOT EXISTS site_memory (
    site_name             TEXT PRIMARY KEY,
    total_attempts        INTEGER DEFAULT 0,
    successful_extractions INTEGER DEFAULT 0,
    successful_applications INTEGER DEFAULT 0,
    avg_extraction_time_ms INTEGER DEFAULT 0,
    preferred_strategy    TEXT,
    blocked_reason        TEXT,
    last_attempted_at     TEXT,
    notes                 TEXT
);
```

Add functions:
- `record_site_attempt(site_name, success, duration_ms)` — update counters
- `get_site_memory(site_name) -> dict` — get site's history
- `get_reliable_sites() -> list[str]` — sites with >50% success rate
- `get_blocked_sites_from_memory() -> list[str]` — sites with >3 consecutive failures

### Step 1.2: Run Log Table

**File:** `database.py` (add migration)

Add `run_log` table:

```sql
CREATE TABLE IF NOT EXISTS run_log (
    run_id                TEXT PRIMARY KEY,
    started_at            TEXT,
    completed_at          TEXT,
    goal                  TEXT,
    plan                  TEXT,
    stages_run            TEXT,
    jobs_discovered       INTEGER DEFAULT 0,
    jobs_enriched         INTEGER DEFAULT 0,
    jobs_scored           INTEGER DEFAULT 0,
    jobs_tailored         INTEGER DEFAULT 0,
    jobs_covered          INTEGER DEFAULT 0,
    jobs_applied          INTEGER DEFAULT 0,
    total_cost            REAL DEFAULT 0.0,
    total_duration_ms     INTEGER DEFAULT 0,
    status                TEXT,
    errors                TEXT,
    reflection_id         TEXT
);
```

Add functions:
- `start_run(goal) -> str` — create run entry, return run_id
- `finish_run(run_id, stats)` — update run with results
- `get_recent_runs(n) -> list[dict]` — last N runs

### Step 1.3: Cost Ledger Table

**File:** `database.py` (add migration)

Add `cost_ledger` table:

```sql
CREATE TABLE IF NOT EXISTS cost_ledger (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id                TEXT,
    action                TEXT,
    tool                  TEXT,
    tokens_in             INTEGER DEFAULT 0,
    tokens_out            INTEGER DEFAULT 0,
    cost_usd              REAL DEFAULT 0.0,
    recorded_at           TEXT
);
```

Add functions:
- `record_cost(run_id, action, tool, tokens_in, tokens_out, cost_usd)`
- `get_run_cost(run_id) -> float` — total cost for a run
- `get_total_cost() -> float` — all-time cost

### Step 1.4: Cost Budget Enforcement

**File:** `llm.py` (modify)

Add budget tracking to the LLM client:
- `set_budget(max_tokens, max_cost)` — set limits for current session
- Before each LLM call, check if budget allows
- After each LLM call, record tokens and cost
- Raise `BudgetExceeded` when limits hit

### Step 1.5: Memory-Aware Source Routing

**File:** `pipeline.py` (modify `_run_discovery_stage`)

Update discovery to use site memory:
- Before running each source, check `get_site_memory()`
- Skip sources with `blocked_reason` set
- Prioritize sources with highest success rate
- Record attempt results after each source completes

### Step 1.6: Memory Tests

**File:** `tests/test_memory.py` (new)

- `record_site_attempt` increments counters correctly
- `get_reliable_sites` filters by success rate
- `get_blocked_sites_from_memory` returns sites with 3+ failures
- `start_run` / `finish_run` lifecycle works
- `record_cost` / `get_run_cost` accounting is accurate
- Cost budget enforcement stops calls when exceeded

---

## Phase 2: Tools

### Step 2.1: Tool Interface Definition

**File:** `agent/tools.py` (new)

Define the base tool contract:

```python
class Tool:
    name: str
    description: str
    parameters: dict  # JSON Schema
    
    def execute(self, **params) -> ActionResult
    def estimate_cost(self, **params) -> float
    def estimate_duration(self, **params) -> int
```

Define `ActionResult` dataclass:
```python
@dataclass
class ActionResult:
    action: str
    status: str  # "ok" | "error" | "skipped" | "retry"
    details: dict
    cost: float
    duration_ms: int
    error: str | None
```

### Step 2.2: Discovery Tools

**File:** `tools/discovery.py` (new)

Wrap discovery modules as individual tools:

- `scrape_jobspy(search_query, location)` → list of job URLs
- `scrape_workday(employer_name)` → list of job URLs
- `scrape_ai_site(url)` → list of job URLs
- `get_search_config()` → current search parameters

Each tool:
- Calls the underlying module function
- Returns ActionResult with job count
- Records site attempt in memory
- Classifies errors (transient/permanent/degraded)

### Step 2.3: Enrichment Tools

**File:** `tools/enrichment.py` (new)

- `enrich_single_job(url)` → full description + apply URL
- `enrich_batch(urls)` → list of enriched jobs

The single-job tool is the key enabler for the orchestrator. Instead of processing all jobs, the agent can enrich only the ones it cares about.

### Step 2.4: Scoring Tools

**File:** `tools/scoring.py` (new)

- `score_single_job(url, resume_text)` → score + reasoning
- `score_batch(urls, resume_text)` → list of scores
- `get_scoring_calibration()` → recent score distribution

### Step 2.5: Document Tools

**File:** `tools/documents.py` (new)

- `tailor_resume(url, job_description, resume_text)` → tailored resume
- `write_cover_letter(url, job_description, resume_text, profile)` → cover letter
- `convert_to_pdf(text, output_path)` → PDF file path

### Step 2.6: Database Tools

**File:** `tools/database.py` (new)

- `query_jobs(stage, min_score, limit)` → list of jobs
- `get_job_detail(url)` → full job record
- `update_job(url, field, value)` → confirmation
- `get_pipeline_stats()` → current pipeline state

### Step 2.7: Tool Registry

**File:** `agent/registry.py` (new)

Central registry that:
- Lists all available tools
- Provides tool descriptions for the LLM
- Handles tool dispatch (name → execute)
- Tracks per-tool usage statistics

### Step 2.8: Tool Tests

**File:** `tests/test_tools.py` (new)

For each tool:
- Test with valid inputs
- Test with invalid inputs (error classification)
- Test cost estimation accuracy
- Test that site memory is updated
- Test that cost is recorded

---

## Phase 3: Orchestrator

### Step 3.1: Orchestrator Core

**File:** `agent/orchestrator.py` (new)

The main agent loop:

```
while not done:
    1. Read current state (what's been done, what's left)
    2. Consult memory (what works, what failed before)
    3. Decide next action (which tool, with what parameters)
    4. Check budget (can we afford this action?)
    5. Execute action (call the tool)
    6. Record result (update state, memory, cost)
    7. Evaluate progress (are we moving toward the goal?)
    8. Replan if needed (adjust strategy based on results)
```

### Step 3.2: Planner

**File:** `agent/planner.py` (new)

Decomposes goals into action sequences:

Input: `"Find 10 remote Python jobs paying 150k+, score them, tailor resumes"`

Plan:
1. Run discovery with query="python", filters=["remote", "150k+"]
2. Enrich top 20 results
3. Score enriched jobs against resume
4. Filter to score >= 7
5. Tailor resumes for top 10
6. Write cover letters for top 5
7. Generate PDFs
8. Apply to top 5

The planner estimates cost and duration for each step and presents the plan for user approval (or proceeds if in autonomous mode).

### Step 3.3: Context Manager

**File:** `agent/context.py` (new)

Manages the LLM context window:

- `add(message)` — add to working context
- `compress()` — summarize old context to save tokens
- `get_relevant_memory(site)` — fetch relevant memory entries
- `get_working_state()` — current progress summary
- `token_count()` — current context size

Strategy: After each action, keep the last 5 action results in full, compress everything else into a summary.

### Step 3.4: CLI Integration

**File:** `cli.py` (modify)

Add new commands:

```
joborion run --goal "senior python remote"    # goal-oriented run
joborion search --goal "ML at FAANG"          # agent-driven search
joborion plan --goal "10 jobs at startups"    # show plan without executing
```

### Step 3.5: Orchestrator Tests

**File:** `tests/test_orchestrator.py` (new)

- Test plan generation from goals
- Test budget enforcement stops execution
- Test error recovery retries transient failures
- Test error recovery skips permanent failures
- Test replanning when a stage fails completely
- Test context compression preserves recent actions

---

## Phase 4: Reflection

### Step 4.1: Reflection Log Table

**File:** `database.py` (add migration)

```sql
CREATE TABLE IF NOT EXISTS reflection_log (
    reflection_id         TEXT PRIMARY KEY,
    run_id                TEXT,
    analyzed_at           TEXT,
    overall_rating        TEXT,
    what_went_well        TEXT,
    what_failed           TEXT,
    strategy_changes      TEXT,
    memory_updates        TEXT
);
```

### Step 4.2: Reflector

**File:** `agent/reflector.py` (new)

After each pipeline run, analyzes results:

1. **Scoring calibration:** Do jobs scoring 7+ actually get callbacks? Compare score distribution to application success rate.
2. **Site reliability:** Which sites had successful extractions? Which failed? Update site_memory.
3. **Strategy effectiveness:** Did the chosen strategies work? What would have worked better?
4. **Cost efficiency:** Where did we spend the most? Was it worth it?
5. **Recommendations:** What should change for the next run?

### Step 4.3: Scoring Calibration

**File:** `agent/reflector.py` (add method)

Analyzes scoring accuracy:
- If we have application outcomes, correlate scores with success
- If scores cluster too tightly (all 6-8), suggest score range adjustment
- If certain sites always score high but never get callbacks, flag as unreliable

### Step 4.4: Reflection CLI

**File:** `cli.py` (add command)

```
joborion reflect                    # analyze last run
joborion reflect --run-id <id>      # analyze specific run
joborion reflect --last 5           # analyze last 5 runs
```

### Step 4.5: Reflection Tests

**File:** `tests/test_reflector.py` (new)

- Test analysis produces valid reflection record
- Test strategy changes are recommended when failures detected
- Test memory updates are correct
- Test scoring calibration with known outcomes

---

## Phase 5: Full Autonomy

### Step 5.1: Goal Parser

**File:** `agent/goal_parser.py` (new)

Converts natural language goals into structured parameters:

Input: `"Find 10 remote senior Python jobs paying 150k+, apply to the best ones"`

Output:
```json
{
  "query": "senior python",
  "filters": {
    "remote": true,
    "min_salary": 150000,
    "min_score": 7
  },
  "actions": {
    "discover": true,
    "enrich": true,
    "score": true,
    "tailor": true,
    "cover": true,
    "apply": true
  },
  "limits": {
    "max_jobs": 10,
    "max_applications": 5
  }
}
```

### Step 5.2: Autonomous Mode

**File:** `agent/orchestrator.py` (extend)

Full autonomous loop:
1. Parse goal
2. Generate plan
3. Present plan for approval (if not --yes)
4. Execute plan with monitoring
5. Replan on failures
6. Reflect on results
7. Generate summary report
8. Update memory

### Step 5.3: Human-in-the-Loop Gates

**File:** `agent/orchestrator.py` (extend)

Approval points for autonomous mode:
- Before first application submission
- When cost exceeds 50% of budget
- When error rate exceeds 30%
- When results are ambiguous (score 6.5-7.5 range)

The user can configure these gates:
```
joborion run --goal "..." --auto           # full autonomous
joborion run --goal "..." --auto --yes     # skip approvals
joborion run --goal "..." --semi           # approve before each apply
```

### Step 5.4: Run Summary Report

**File:** `agent/reporter.py` (new)

Generates a human-readable summary after each run:

```
=== JobOrion Run Report ===
Goal: Find 10 remote senior Python jobs, apply to best 5
Duration: 12m 34s | Cost: $2.47

Pipeline:
  Discovered: 47 jobs (3 sources)
  Enriched:   35 jobs (8 failed detail pages)
  Scored:     35 jobs (avg: 6.8)
  Tailored:   12 jobs (score >= 7)
  Covered:     8 jobs
  Applied:     5 jobs

Top applications:
  1. Senior Python Dev @ Stripe (score: 9) - Applied
  2. Backend Engineer @ Notion (score: 8) - Applied
  3. Sr. SWE @ Vercel (score: 8) - Applied

Lessons learned:
  - RemoteOK consistently fails extraction, consider blocking
  - Workday sites have 94% success rate, prioritize them
  - Scoring seems generous (avg 6.8), may need calibration
```

### Step 5.5: Periodic Autonomous Runs

**File:** `agent/scheduler.py` (new)

Optional cron-like capability:
- Check for new jobs daily
- Score and tailor as new jobs appear
- Apply to high-fit jobs automatically
- Send summary via email (optional)

This is the lowest priority feature — manual runs with `--goal` are more important.

### Step 5.6: Integration Tests

**File:** `tests/test_autonomous.py` (new)

End-to-end tests:
- Goal parsing produces correct parameters
- Full autonomous run completes without errors
- Cost budget is enforced
- Memory is updated after run
- Reflection is generated after run
- Human-in-the-loop gates pause correctly
