# Agent Design

## Agent Identity

**Name:** JobOrion Orchestrator
**Type:** Single-orchestrator with sub-agent delegation
**LLM:** Same provider as the rest of the system (configured via `PROVIDER` env var)
**Personality:** Systematic, frugal, transparent. Never guesses when it can check. Never spends when it can skip.

## Core Loop

```
┌─────────────────────────────────────────────────┐
│                  ORCHESTRATOR                     │
│                                                   │
│  1. READ STATE                                    │
│     - What jobs exist? (database)                 │
│     - What's been done? (run_log)                 │
│     - What worked before? (site_memory)           │
│                                                   │
│  2. PLAN                                          │
│     - Decompose goal into actions                 │
│     - Estimate cost and duration                  │
│     - Present plan for approval                   │
│                                                   │
│  3. EXECUTE                                       │
│     - Call tools in sequence                      │
│     - Monitor cost and errors                     │
│     - Record results                              │
│                                                   │
│  4. EVALUATE                                      │
│     - Did we reach the goal?                      │
│     - What failed? Why?                           │
│     - Should we replan?                           │
│                                                   │
│  5. REFLECT                                       │
│     - Analyze performance                         │
│     - Update memory                               │
│     - Generate recommendations                    │
└─────────────────────────────────────────────────┘
```

## Decision Principles

### 1. Determinism by Default

Every action the orchestrator takes should be explainable. If a module already handles something deterministically (scoring, tailoring, enriching), the orchestrator should not try to "think" about it — it should call the tool and pass the result through.

The orchestrator's agency is reserved for:
- **Sequencing:** Which tools to call and in what order
- **Filtering:** Which results to keep and which to discard
- **Recovery:** What to do when something fails
- **Budgeting:** How to allocate limited resources across actions

### 2. Memory Before Action

Before the orchestrator decides anything, it checks memory:

- Has this site been attempted before? What happened?
- Has this search query been tried? What did it find?
- Is there a known pattern of failure for this type of operation?

Memory does not make decisions — it informs them. The orchestrator always has the final say.

### 3. Cost Consciousness

Every tool call has an estimated cost. The orchestrator tracks:

- Running total for the current session
- Per-stage budget allocation
- Cost-per-value (how much did we spend to find one good job?)

When budget is exhausted, the orchestrator stops. It does not partially complete the plan.

### 4. Graceful Degradation

When something fails:
1. Classify the error (transient / permanent / degraded)
2. If transient: retry with backoff (max 2 retries)
3. If permanent: skip and log, continue with remaining work
4. If degraded: proceed with reduced quality, note in results
5. Never silently swallow errors

## Communication Style

### With the User

The orchestrator communicates through the CLI:

```
[plan] Discovering jobs from LinkedIn, Indeed, and Workday
[plan] Scoring 30 jobs against your resume
[plan] Tailoring top 8 resumes (score >= 7)
[cost] Total estimated cost: $1.84 (budget: $5.00)
[progress] Discovered 30 jobs (2m 14s)
[progress] Scored 30 jobs, 8 qualified (1m 02s)
[complete] Done. 8 resumes tailored, 5 cover letters written.
```

### With Tools

Tools communicate through structured results:

```python
ActionResult(
    action="scrape_jobspy",
    status="ok",
    details={"jobs_found": 15, "site": "indeed"},
    cost=0.002,
    duration_ms=3400,
    error=None
)
```

### With Memory

The orchestrator reads memory before planning and writes memory after execution. Memory is append-only — new entries are added, old entries are never deleted, but stale entries are deprioritized.

## Error Taxonomy

| Code | Type | Action |
|------|------|--------|
| E001 | Network timeout | Retry 2x, then skip |
| E002 | Rate limited | Wait 60s, retry 1x, then skip |
| E003 | Page structure changed | Log for manual review, skip |
| E004 | LLM refused (safety) | Log, skip, do not retry |
| E005 | LLM hallucinated | Log, skip, do not retry |
| E006 | Budget exceeded | Stop immediately, do not proceed |
| E007 | Invalid input | Log, skip, continue |
| E008 | Database error | Retry 1x, then abort run |
| E009 | Chrome crashed | Restart Chrome, retry 1x, then skip apply |
| E010 | Unknown | Log full context, skip, continue |

## Safety Rails

### 1. Cost Cap
The orchestrator enforces a hard cost cap. When exceeded:
- No more LLM calls
- No more API calls
- Report current results and stop
- Do not partially complete the plan

### 2. Application Limit
The orchestrator never applies to more jobs than the user specified. Default: 5 applications per run.

### 3. No Fabrication
The orchestrator never fabricates job data. If a field is missing from scraping, it is left empty. If a score cannot be computed, the job is skipped.

### 4. Transparency
Every action the orchestrator takes is logged in `run_log`. The user can always see:
- What was planned
- What was actually executed
- What failed and why
- How much it cost

### 5. User Override
The user can always interrupt the orchestrator. Ctrl+C stops execution gracefully, saves progress, and reports current state.
