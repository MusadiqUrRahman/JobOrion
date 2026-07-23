# Phase 5: Full Autonomy

## Goal

User can run `joborion run --goal "Find 10 remote Python jobs" --auto` and get a fully autonomous pipeline that parses the goal, plans, executes, reflects, and generates a summary report — with optional human approval gates.

## File Surface

**Create:**
- `src/joborion/agent/goal_parser.py` — GoalParser class
- `src/joborion/agent/reporter.py` — RunReporter class
- `tests/test_autonomous.py` — 10+ test cases

**Modify:**
- `src/joborion/agent/orchestrator.py` — add autonomous mode, gates, reflect integration
- `src/joborion/cli.py` — add `--auto`, `--semi`, `--yes` flags to run command

---

## Task 1: Goal Parser

**File:** `src/joborion/agent/goal_parser.py`
**Test:** `tests/test_autonomous.py::TestGoalParser`

Class `GoalParser`:
- `parse(goal: str) -> dict` — main entry point

Output structure:
```python
{
    "query": str,           # search terms extracted from goal
    "filters": {
        "remote": bool,
        "min_salary": int | None,
        "min_score": int,
    },
    "actions": {
        "search": bool,
        "details": bool,
        "evaluate": bool,
        "tailor": bool,
        "letter": bool,
        "export": bool,
    },
    "limits": {
        "max_jobs": int | None,
        "max_applications": int | None,
    },
}
```

Parser logic:
- Extract tech keywords for query (python, react, senior, etc.)
- Detect "remote" from goal text
- Detect salary from "$150k", "150000", "150k+" patterns
- Detect min_score from "best", "top", "high" → 8; "good" → 7; default → 7
- Detect "apply" keyword → enable all actions including apply-related ones
- Detect limits from "10 jobs", "5 applications" patterns
- Default all actions to True

---

## Task 2: Autonomous Mode

**File:** `src/joborion/agent/orchestrator.py`
**Test:** `tests/test_autonomous.py::TestAutonomousMode`

Extend `Orchestrator`:
- `execute_autonomous(goal: str, auto: bool = True, yes: bool = False) -> dict`
- Parse goal → generate plan → present for approval → execute → reflect → report
- On failure: replan with reduced scope
- Store reflection after completion
- Generate run report

New params on `__init__`:
- `auto: bool = False` — enable autonomous mode
- `yes: bool = False` — skip approval gates
- `semi: bool = False` — approve before each apply

---

## Task 3: Human-in-the-Loop Gates

**Method:** `Orchestrator._check_gate()`

Gate triggers:
1. Before first application submission (always, unless --yes)
2. When cost exceeds 50% of budget (always, unless --yes)
3. When error rate exceeds 30% (always, unless --yes)

Gate modes:
- `auto` + `yes`: skip all gates
- `auto` without `yes`: pause at each gate, prompt user
- `semi`: pause before each application

Gate implementation:
- Check condition
- If gate triggered and not skipped: print warning, wait for user input (y/n)
- If user says n: skip that action
- If user says y: proceed

---

## Task 4: Run Summary Report

**File:** `src/joborion/agent/reporter.py`
**Test:** `tests/test_autonomous.py::TestReporter`

Class `RunReporter`:
- `generate(run_data: dict) -> str` — produce formatted report string

Report sections:
1. Header: Goal, Duration, Cost
2. Pipeline stats: discovered, enriched, scored, tailored, covered, applied
3. Top applications: top 5 jobs with scores
4. Cost breakdown: by stage/tool
5. Lessons learned: from reflection (if available)

---

## Task 5: CLI Integration

**File:** `src/joborion/cli.py`

Extend `run` command:
- `--auto` flag: enable autonomous mode
- `--semi` flag: approve before each application
- `--yes` flag: skip all approvals

When `--auto` is passed with `--goal`:
1. Bootstrap
2. Create Orchestrator with auto=True
3. Call execute_autonomous()
4. Print report

---

## Task 6: Integration Tests

**File:** `tests/test_autonomous.py`

Tests:
1. `test_goal_parser_basic` — parses "Find Python jobs" correctly
2. `test_goal_parser_with_salary` — extracts salary threshold
3. `test_goal_parser_with_remote` — detects remote flag
4. `test_goal_parser_with_limits` — extracts max_jobs, max_applications
5. `test_goal_parser_defaults` — sensible defaults for all fields
6. `test_autonomous_mode_creates` — Orchestrator with auto=True works
7. `test_autonomous_execute_dry_run` — dry run returns plan
8. `test_reporter_generates_report` — report output is non-empty
9. `test_reporter_includes_stats` — report has pipeline stats
10. `test_cli_auto_flag` — `joborion run --help` shows --auto flag

---

## Verification

```bash
pytest tests/test_autonomous.py -v
pytest tests/ -v
ruff check src/
joborion run --help  # shows --auto, --semi, --yes flags
```

---

## Critical Review

1. **Scope creep?** — No. Goal parser, gates, reporter are self-contained.
2. **Missing tasks?** — No. All milestones covered.
3. **Wrong order?** — Sequential. Parser first, then orchestrator, then reporter, then CLI, then tests.
4. **Over-engineered?** — No. Simple keyword parsing, no LLM calls in parser.
5. **Testable?** — Yes. Every task has independent verification.

---

## Phase 5 is complete when:

- [ ] M5.1: Goal parser works with various input formats
- [ ] M5.2: Autonomous mode runs full loop
- [ ] M5.3: Human-in-the-loop gates pause correctly
- [ ] M5.4: Run summary report is generated
- [ ] M5.5: 10+ tests pass, ruff clean
