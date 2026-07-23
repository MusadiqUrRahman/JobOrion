# Phase 4: Reflection

## Goal

User can run `joborion reflect` after a pipeline run and get a structured analysis of what worked, what failed, and what should change — with scoring calibration and actionable recommendations.

## File Surface

**Create:**
- `src/joborion/agent/reflector.py` — Reflector class that analyzes runs
- `tests/test_reflector.py` — 10+ test cases

**Modify:**
- `src/joborion/database.py` — add `reflection_log` table + store/query functions
- `src/joborion/cli.py` — add `reflect` command
- `src/joborion/agent/orchestrator.py` — auto-reflect after execute()

---

## Task 1: Reflection Log (Database)

**File:** `src/joborion/database.py`
**Test:** `tests/test_reflector.py::TestReflectionLog`

Add `reflection_log` table:
```sql
reflection_log (
    reflection_id TEXT PRIMARY KEY,
    run_id        TEXT,
    analyzed_at   TEXT,
    overall_rating TEXT,        -- "good" | "ok" | "poor"
    what_went_well TEXT,        -- JSON list
    what_failed    TEXT,        -- JSON list
    strategy_changes TEXT,     -- JSON list
    memory_updates  TEXT,      -- JSON list
    recommendations TEXT,      -- JSON list
    scoring_calibration TEXT,  -- JSON dict
    cost_analysis   TEXT       -- JSON dict
)
```

Functions:
- `store_reflection(record: dict) -> str` — insert, return reflection_id
- `get_reflection(reflection_id: str) -> dict | None`
- `get_recent_reflections(n: int = 5) -> list[dict]`
- `get_reflections_for_run(run_id: str) -> list[dict]`

---

## Task 2: Reflector Core

**File:** `src/joborion/agent/reflector.py`
**Test:** `tests/test_reflector.py::TestReflector`

Class `Reflector`:
- `__init__(self, conn)` — takes database connection
- `analyze_run(self, run_id: str) -> dict` — main entry point
- `_collect_run_data(self, run_id: str) -> dict` — gather actions, costs, stats
- `_analyze_outcomes(self, data: dict) -> dict` — compare planned vs actual
- `_identify_failures(self, data: dict) -> list[dict]` — categorize errors
- `_check_scoring_calibration(self, data: dict) -> dict` — score distribution + success correlation
- `_update_site_memory(self, data: dict) -> list[dict]` — update reliability scores
- `_generate_recommendations(self, data: dict) -> list[str]` — actionable advice
- `_build_reflection(self, run_id: str, data: dict) -> dict` — assemble final record

---

## Task 3: Scoring Calibration

**Method:** `Reflector._check_scoring_calibration()`

Analyzes:
1. Score distribution (count per score 1-10)
2. Whether scores cluster too tightly (all 6-8)
3. Score-vs-outcome correlation (if application data exists)
4. Recommendations: raise/lower thresholds, adjust scoring prompt

---

## Task 4: Reflection CLI

**File:** `src/joborion/cli.py`
**Test:** `tests/test_reflector.py::TestReflectionCLI`

Command: `joborion reflect`
- `--run-id <id>` — analyze specific run
- `--last <n>` — analyze last n runs (default: 1)
- No args — analyze most recent run

Output: Rich table with:
- Overall rating (good/ok/poor)
- What went well
- What failed
- Recommendations
- Score calibration summary

---

## Task 5: Auto-Reflect in Orchestrator

**File:** `src/joborion/agent/orchestrator.py`

After `execute()` completes:
1. Check if run_id exists
2. Create Reflector
3. Call `analyze_run(run_id)`
4. Store reflection record
5. Log summary (don't block execution on reflection failure)

---

## Task 6: Reflection Tests

**File:** `tests/test_reflector.py`

Tests:
1. `test_reflection_log_store_and_retrieve` — store + get roundtrip
2. `test_reflection_log_recent` — get_recent_reflections returns N records
3. `test_reflection_log_for_run` — filter by run_id
4. `test_reflector_analyze_produces_record` — analyze_run returns valid dict
5. `test_reflector_identifies_failures` — errors are categorized
6. `test_reflector_scoring_calibration` — score distribution computed
7. `test_reflector_recommendations_on_failure` — recommendations generated
8. `test_reflector_memory_updates` — site memory updates proposed
9. `test_reflector_handles_empty_run` — graceful on no data
10. `test_reflect_cli_help` — `joborion reflect --help` works

---

## Verification

```bash
pytest tests/test_reflector.py -v
pytest tests/ -v
ruff check src/
joborion reflect --help
```

---

## Critical Review

1. **Scope creep?** — No. Reflection is self-contained: analyze → store → recommend.
2. **Missing tasks?** — No. Database, reflector, calibration, CLI, tests covered.
3. **Wrong order?** — Sequential. DB first, then reflector, then CLI, then integration.
4. **Over-engineered?** — No. Simple dict-based analysis, no LLM calls in reflector.
5. **Testable?** — Yes. Every task has independent verification.

---

## Phase 4 is complete when:

- [ ] M4.1: Reflection log table + store/query functions work
- [ ] M4.2: Reflector analyzes runs, identifies failures, generates recommendations
- [ ] M4.3: Scoring calibration produces actionable insights
- [ ] M4.4: `joborion reflect` CLI works with all flags
- [ ] M4.5: 10+ tests pass, ruff clean
