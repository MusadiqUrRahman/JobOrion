# Specifications

## System Interface

### User Input

The user interacts via CLI commands:

```
joborion run                          # full pipeline (existing)
joborion run discover score           # specific stages (existing)
joborion apply --limit 5              # apply to 5 jobs (existing)
joborion search "senior python"       # NEW: agent-driven search
joborion run --goal "find remote ML"  # NEW: goal-oriented run
```

### Output Contract

Every pipeline action returns a standardized result:

```
ActionResult:
  action: str           # what was attempted
  status: "ok" | "error" | "skipped" | "retry"
  details: dict         # action-specific data
  cost: float           # estimated LLM cost in USD
  duration_ms: int      # wall clock time
  error: str | None     # error message if failed
```

### Tool Interface

Every tool follows the same contract:

```
Tool:
  name: str                          # unique identifier
  description: str                   # what it does (for the LLM)
  parameters: dict                   # JSON Schema of inputs
  execute(params) -> ActionResult    # run the tool
  estimate_cost(params) -> float     # pre-flight cost estimate
  estimate_duration(params) -> int   # pre-flight time estimate (ms)
```

## Data Models

### Job Record (existing, extended)

```
jobs table:
  url                   TEXT PRIMARY KEY
  title                 TEXT
  salary                TEXT
  description           TEXT
  location              TEXT
  site                  TEXT
  strategy              TEXT          -- how it was discovered
  discovered_at         TEXT

  -- enrichment
  full_description      TEXT
  application_url       TEXT
  detail_scraped_at     TEXT
  detail_error          TEXT

  -- scoring
  fit_score             INTEGER
  score_reasoning       TEXT
  scored_at             TEXT

  -- tailoring
  tailored_resume_path  TEXT
  tailored_at           TEXT
  tailor_attempts       INTEGER

  -- cover letter
  cover_letter_path     TEXT
  cover_letter_at       TEXT
  cover_attempts        INTEGER

  -- apply
  applied_at            TEXT
  apply_status          TEXT
  apply_error           TEXT
  apply_attempts        INTEGER
  agent_id              TEXT

  -- NEW: agent metadata
  priority_score        REAL          -- orchestrator-assigned priority
  last_strategy         TEXT          -- strategy used for this job
  retry_count           INTEGER       -- how many times retried
  cost_accrued          REAL          -- total cost spent on this job
```

### Site Memory Record (NEW)

```
site_memory table:
  site_name             TEXT PRIMARY KEY
  total_attempts        INTEGER
  successful_extractions INTEGER
  successful_applications INTEGER
  avg_extraction_time_ms INTEGER
  preferred_strategy    TEXT          -- which strategy works best
  blocked_reason        TEXT          -- why it's blocked (if any)
  last_attempted_at     TEXT
  notes                 TEXT          -- free-form observations
```

### Run Log Record (NEW)

```
run_log table:
  run_id                TEXT PRIMARY KEY
  started_at            TEXT
  completed_at          TEXT
  goal                  TEXT          -- what the user wanted
  plan                  TEXT          -- JSON: the execution plan
  stages_run            TEXT          -- JSON: list of stages
  jobs_discovered       INTEGER
  jobs_enriched         INTEGER
  jobs_scored           INTEGER
  jobs_tailored         INTEGER
  jobs_covered          INTEGER
  jobs_applied          INTEGER
  total_cost            REAL
  total_duration_ms     INTEGER
  status                TEXT          -- "completed" | "partial" | "failed"
  errors                TEXT          -- JSON: list of errors
  reflection_id         TEXT          -- link to reflection entry
```

### Reflection Record (NEW)

```
reflection_log table:
  reflection_id         TEXT PRIMARY KEY
  run_id                TEXT          -- which run this reflects on
  analyzed_at           TEXT
  overall_rating        TEXT          -- "good" | "mixed" | "poor"
  what_went_well        TEXT          -- JSON: list of successes
  what_failed           TEXT          -- JSON: list of failures
  strategy_changes      TEXT          -- JSON: recommended changes
  memory_updates        TEXT          -- JSON: what was written to memory
```

## Cost Budget Contract

```
CostBudget:
  max_tokens_per_run: int       # default: 500_000
  max_cost_per_run: float       # default: 10.00
  max_cost_per_job: float       # default: 1.00
  warn_threshold_pct: int       # default: 80 (warn at 80%)
  
  enforce() -> bool             # check if budget allows action
  record(tokens, cost) -> None  # record spent tokens/cost
  remaining() -> float          # remaining budget
```

## Error Recovery Contract

Every tool must classify its errors:

```
ErrorClass:
  TRANSIENT    -- retry with backoff (rate limit, timeout, 5xx)
  PERMANENT    -- do not retry (404, expired, blocked)
  DEGRADED     -- partial result usable (missing some fields)
  USER_ACTION  -- needs human input (CAPTCHA, login, ambiguous)
```

The orchestrator uses error classification to decide:
- TRANSIENT: retry up to 3 times with exponential backoff
- PERMANENT: skip and log, do not retry
- DEGRADED: use partial result, flag for review
- USER_ACTION: pause and ask the user
