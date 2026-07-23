# Phase 1: Memory

## Goal

System remembers which sites work, tracks costs per run, and logs every pipeline execution — enabling smarter decisions in later phases.

## File Surface

**Modify:**
- `src/joborion/database.py` — add site_memory, run_log, cost_ledger tables + functions
- `src/joborion/llm.py` — add budget enforcement and cost recording
- `src/joborion/pipeline.py` — add memory-aware source routing

**Create:**
- `tests/test_memory.py` — 12+ test cases

---

## Task 1: Site Memory Table

**File:** `src/joborion/database.py`

Add `site_memory` table:
```sql
site_memory (
    site            TEXT PRIMARY KEY,
    total_attempts  INTEGER DEFAULT 0,
    successful_extractions INTEGER DEFAULT 0,
    blocked_count   INTEGER DEFAULT 0,
    last_blocked_at TEXT,
    success_rate    REAL DEFAULT 1.0,
    reliability     TEXT DEFAULT 'unknown'  -- unknown, reliable, unreliable, blocked
)
```

Functions:
- `record_site_attempt(site, success, blocked)` — update stats
- `get_site_memory(site)` — get reliability data
- `get_reliable_sites()` — sites with >80% success rate
- `get_blocked_sites_from_memory()` — sites marked blocked
- `unblock_site(site)` — reset blocked status

---

## Task 2: Run Log Table

**File:** `src/joborion/database.py`

Add `run_log` table:
```sql
run_log (
    run_id      TEXT PRIMARY KEY,
    goal        TEXT,
    started_at  TEXT,
    finished_at TEXT,
    status      TEXT,
    stats       TEXT  -- JSON
)
```

Functions:
- `start_run(goal)` — create run record, return run_id
- `finish_run(run_id, stats)` — update with completion data
- `get_recent_runs(n)` — get last N runs

---

## Task 3: Cost Ledger Table

**File:** `src/joborion/database.py`

Add `cost_ledger` table:
```sql
cost_ledger (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT,
    action      TEXT,
    tool        TEXT,
    cost_usd    REAL DEFAULT 0.0,
    recorded_at TEXT
)
```

Functions:
- `record_cost(run_id, action, tool, cost_usd)` — log a cost
- `get_run_cost(run_id)` — total cost for a run
- `get_total_cost()` — all-time total

---

## Task 4: Budget Enforcement in LLM

**File:** `src/joborion/llm.py`

- Add `_budget` module variable (default $5.00)
- Add `set_budget(amount)` function
- Add `budget_remaining` property
- Check budget before each LLM call
- Raise `BudgetExceeded` if over budget
- Auto-record cost after each call

---

## Task 5: Memory-Aware Source Routing

**File:** `src/joborion/pipeline.py`

In discovery stage:
- Check site_memory before scraping each source
- Skip sites marked as blocked
- Prioritize sites with high reliability
- Record attempt results after scraping

---

## Task 6: Memory Tests

**File:** `tests/test_memory.py`

Tests:
1. `test_record_site_attempt` — records success/failure
2. `test_get_site_memory` — returns correct stats
3. `test_get_reliable_sites` — filters by success rate
4. `test_get_blocked_sites` — returns blocked sites
5. `test_unblock_site` — resets blocked status
6. `test_start_run` — creates run record
7. `test_finish_run` — updates with stats
8. `test_get_recent_runs` — returns N runs
9. `test_record_cost` — logs cost entry
10. `test_get_run_cost` — sums costs for run
11. `test_get_total_cost` — sums all costs
12. `test_cost_ledger_unique_run_ids` — run_ids are unique

---

## Verification

```bash
pytest tests/test_memory.py -v
pytest tests/ -v
ruff check src/
```

---

## Phase 1 is complete when:

- [ ] site_memory table + 5 functions work
- [ ] run_log table + 3 functions work
- [ ] cost_ledger table + 3 functions work
- [ ] Budget enforcement in llm.py works
- [ ] Memory-aware routing in pipeline.py works
- [ ] 12+ tests pass, ruff clean
