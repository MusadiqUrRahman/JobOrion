# Memory

## Overview

Memory is the system's ability to remember what happens across runs. Without memory, every run starts from scratch. With memory, the system knows which sites work, which strategies succeed, and what the user prefers.

Memory is not intelligence. It is experience.

## Memory Types

### 1. Site Memory

Tracks the reliability of each job source.

**What it remembers:**
- How many times a source was attempted
- How many times it succeeded / failed
- The preferred strategy (direct scrape vs AI extraction)
- Whether the source is blocked and why

**Where it lives:** `site_memory` table in `joborion.db`

**How it is used:**
- Before discovery, check `get_reliable_sites()` to prioritize known-good sources
- Before discovery, check `get_blocked_sites_from_memory()` to skip known-bad sources
- After discovery, `record_site_attempt()` updates the counters
- The orchestrator uses this to decide which sources to try first

**How it updates:**
- After every discovery attempt (success or failure)
- After reflection analysis (blocking or unblocking decisions)

### 2. Run Log

Records what happened in each pipeline run.

**What it remembers:**
- The goal (what the user wanted)
- The plan (what the system intended to do)
- What stages were run
- How many jobs were processed at each stage
- Total cost and duration
- Status (completed, failed, partial)
- Any errors encountered

**Where it lives:** `run_log` table in `joborion.db`

**How it is used:**
- The orchestrator reads recent runs to understand what has been done
- The reflector analyzes runs to identify patterns
- The user can review run history via CLI

**How it updates:**
- `start_run()` creates the entry at the beginning of each run
- `finish_run()` updates it at the end

### 3. Cost Ledger

Tracks token usage and cost for every action.

**What it remembers:**
- Which action consumed tokens
- How many tokens (in and out)
- The cost in USD
- Which run it belonged to

**Where it lives:** `cost_ledger` table in `joborion.db`

**How it is used:**
- Budget enforcement: check `get_run_cost()` before expensive actions
- Cost analysis: identify where the most money is spent
- ROI calculation: cost per job discovered, cost per application

**How it updates:**
- After every LLM call in `llm.py`
- After every tool call in the orchestrator

### 4. Scoring Calibration (Phase 4)

Tracks whether scoring predictions match outcomes.

**What it remembers:**
- The score assigned to each job
- Whether the job was applied to
- Whether the application got a response (if known)

**Where it lives:** Derived from `jobs_applied` + `applications` tables

**How it is used:**
- The reflector analyzes score-vs-outcome correlation
- If scores are consistently high but outcomes are poor, the scoring prompt needs adjustment
- If certain sites produce unreliable data, they get flagged

### 5. User Preferences (Phase 5)

Infers and stores user preferences over time.

**What it remembers:**
- Preferred job sources (which sites the user trusts)
- Preferred document style (resume format, cover letter tone)
- Salary expectations (learned from filter adjustments)
- Location preferences (learned from search queries)

**Where it lives:** `user_preferences` table (Phase 5)

**How it is used:**
- The planner uses preferences to generate better initial plans
- The orchestrator uses preferences to filter results

## Memory Lifecycle

```
CREATE          READ            UPDATE          EXPIRE
  |               |               |               |
  v               v               v               v
Write entry  ->  Query entry  ->  Update entry  ->  Deprioritize
(after action)   (before plan)   (after outcome)   (after 30 days)
```

**Creation:** Every action writes a memory entry. Discovery writes site attempts. Scoring writes score results. Application writes submission records.

**Read:** Before planning, the orchestrator reads relevant memory. Before discovery, it reads site memory. Before scoring, it reads calibration data.

**Update:** After outcomes are known, memory entries are updated. If a site succeeds, its success counter increments. If a scoring prediction was wrong, calibration data is updated.

**Expiry:** Memory entries are never deleted. But after 30 days, they are deprioritized. A site that worked 30 days ago is less relevant than one that worked yesterday.

## Memory vs Context

Memory and context serve different purposes:

| Aspect | Context | Memory |
|--------|---------|--------|
| Scope | Current session only | All sessions |
| Lifetime | Resets each run | Persists |
| Size | Limited by context window | Limited by disk |
| Content | Raw action results | Summarized outcomes |
| Purpose | Inform immediate decisions | Inform long-term strategy |

The orchestrator uses context for "what just happened" and memory for "what usually happens."
