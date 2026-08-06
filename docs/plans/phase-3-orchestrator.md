# Phase 3: Orchestrator

## Goal

User can run `joborion plan "Find 10 remote Python jobs"` to see an execution plan, and `joborion run --goal "..."` to execute a goal-driven pipeline with budget tracking.

## File Surface

**Create:**
- `src/joborion/agent/planner.py` — Planner class
- `src/joborion/agent/context.py` — ContextManager class
- `src/joborion/agent/orchestrator.py` — Orchestrator class
- `tests/test_orchestrator.py` — 12+ test cases

**Modify:**
- `src/joborion/cli.py` — add `plan` command, add `--goal` flag to `run`

---

## Task 1: PlanStep and Plan

**File:** `src/joborion/agent/planner.py`

Dataclasses:
- `PlanStep` — tool, params, description, cost_estimate, duration_estimate_ms, depends_on
- `Plan` — goal, steps (list), total_cost (property), total_duration_ms (property)

---

## Task 2: Planner

**File:** `src/joborion/agent/planner.py`

Class `Planner`:
- `plan(goal: str) -> Plan` — generate execution plan from natural language

Logic:
- Detect pipeline stages from goal keywords
- Map stages to tools with parameters
- Order steps by dependencies
- Estimate cost and duration per step

Stage detection:
- "find", "search", "jobs" → search
- "detail", "description", "enrich" → details
- "score", "rating", "fit" → evaluate
- "tailor", "resume" → tailor
- "cover", "letter" → letter
- "pdf", "convert" → export

---

## Task 3: ContextManager

**File:** `src/joborion/agent/context.py`

Class `ContextManager`:
- `add_action(result)` — record action result
- `get_recent_actions(n)` — get last N actions
- `get_working_state()` — summary of progress
- `compress(keep_recent)` — summarize old actions
- `token_estimate()` — rough token count

---

## Task 4: Orchestrator

**File:** `src/joborion/agent/orchestrator.py`

Class `Orchestrator`:
- `__init__(goal, max_cost, max_calls, registry)`
- `plan() -> Plan` — generate plan
- `execute(dry_run) -> dict` — run plan
- `_check_budget()` — raise if over budget
- `_record_result(result)` — store in context + cost ledger

---

## Task 5: CLI Integration

**File:** `src/joborion/cli.py`

New command: `joborion plan`
- `goal` argument (required)
- `--dry-run` flag
- `--max-cost` flag

Extended: `joborion run`
- `--goal` flag — triggers orchestrator mode

---

## Task 6: Orchestrator Tests

**File:** `tests/test_orchestrator.py`

Tests:
1. `test_plan_step_fields` — PlanStep has all fields
2. `test_plan_step_optional_fields` — defaults work
3. `test_parse_goal_query` — extracts query
4. `test_plan_includes_all_stages` — full goal produces all stages
5. `test_plan_has_cost_estimates` — every step has cost
6. `test_plan_total_cost` — total is computed
7. `test_plan_total_duration` — duration is computed
8. `test_plan_steps_ordered_by_deps` — dependency order correct
9. `test_plan_search_only` — search-only goal
10. `test_add_action` — context records actions
11. `test_get_recent_actions` — returns N actions
12. `test_get_working_state` — returns progress summary
13. `test_orchestrator_creates` — can instantiate
14. `test_orchestrator_has_budget` — respects budget
15. `test_orchestrator_plan_mode` — generates plan
16. `test_orchestrator_budget_check` — raises on exceed
17. `test_orchestrator_tracks_cost` — accumulates cost
18. `test_orchestrator_execute_dry_run` — returns plan
19. `test_orchestrator_error_recovery` — marks failed steps
20. `test_plan_command_exists` — CLI has plan command
21. `test_run_accepts_goal` — CLI accepts --goal

---

## Verification

```bash
pytest tests/test_orchestrator.py -v
pytest tests/ -v
ruff check src/
joborion plan --help
joborion run --help  # shows --goal
```

---

## Phase 3 is complete when:

- [x] Planner parses goals into ordered steps
- [x] ContextManager tracks and compresses actions
- [x] Orchestrator executes plans with budget enforcement
- [x] CLI has `plan` command and `--goal` flag
- [x] Pipeline stages renamed: Search, Details, Evaluate, Tailor, Letter, Export
- [x] 21+ tests pass, ruff clean
