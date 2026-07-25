# Plan: Add Tests for Agent Module

**Goal:** Every agent module function has test coverage, verifying orchestrator
execution, planner goal decomposition, context management, reporting, goal
parsing, and reflection analysis.

## Step 1: Define the Goal

User can run `pytest tests/test_planner.py tests/test_goal_parser.py
tests/test_context.py tests/test_reporter.py tests/test_reflector.py
tests/test_orchestrator.py -v` and see all tests pass.

## Step 2: Map the File Surface

Files to create:
- `tests/test_goal_parser.py` — GoalParser tests (query extraction, filters, actions, limits)
- `tests/test_planner.py` — Planner tests (stage detection, step building, query extraction)
- `tests/test_context.py` — ContextManager tests (add, compress, working state, token estimate)
- `tests/test_reporter.py` — RunReporter tests (formatting, duration, empty data)
- `tests/test_reflector.py` — Reflector tests (outcomes, failures, calibration, recommendations)
- `tests/test_orchestrator.py` — Orchestrator integration tests (plan, execute, budget, gates)

Files to modify: none

## Step 3: Decompose into Tasks

Task 1: Create GoalParser tests
  File: tests/test_goal_parser.py
  Tests: test_parse_basic_goal, test_extract_query, test_extract_remote_filter,
         test_extract_salary_filter, test_extract_min_score, test_extract_actions,
         test_extract_limits, test_no_match_defaults
  Depends on: nothing

Task 2: Create Planner tests
  File: tests/test_planner.py
  Tests: test_plan_default_goal, test_plan_with_query, test_plan_tailor_goal,
         test_detect_stages_order, test_build_steps_params
  Depends on: nothing

Task 3: Create ContextManager tests
  File: tests/test_context.py
  Tests: test_add_action, test_get_recent_actions, test_get_working_state,
         test_compress, test_token_estimate
  Depends on: nothing

Task 4: Create RunReporter tests
  File: tests/test_reporter.py
  Tests: test_generate_full_report, test_generate_empty_data, test_format_duration
  Depends on: nothing

Task 5: Create Reflector tests
  File: tests/test_reflector.py
  Tests: test_analyze_run_empty, test_analyze_run_with_jobs,
         test_identify_failures, test_scoring_calibration, test_recommendations,
         test_cost_analysis
  Depends on: nothing

Task 6: Create Orchestrator tests
  File: tests/test_orchestrator.py
  Tests: test_plan_dry_run, test_execute_dry_run, test_execute_budget_check,
         test_execute_tool_failure, test_execute_autonomous, test_error_rate_gate
  Depends on: Tasks 1-5 (uses all agent modules)

## Step 4: Define Verification

```bash
pytest tests/test_goal_parser.py tests/test_planner.py tests/test_context.py tests/test_reporter.py tests/test_reflector.py tests/test_orchestrator.py -v
pytest tests/ -v  # full suite still passes
ruff check tests/ src/joborion/agent/
```

## Step 5: Critical Review

1. Scope creep? — No, only agent module tests.
2. Missing tasks? — No, all 6 agent files covered.
3. Wrong order? — Tasks 1-5 are independent, can be parallelized. Task 6 depends on understanding the others.
4. Over-engineered? — No, straightforward unit tests.
5. Testable? — Yes, all modules have clear interfaces.
