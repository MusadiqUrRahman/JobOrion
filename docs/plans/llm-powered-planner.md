# Plan: LLM-Powered Planner

**Goal:** Replace keyword-matching goal decomposition with an LLM-powered planner
that understands natural language goals and produces intelligent execution plans,
with graceful fallback to the keyword planner when LLM is unavailable.

## Step 1: Define the Goal

User can run `joborion run --goal "find senior remote Python jobs at startups paying
200k+"` and the planner uses an LLM to decompose the goal into tailored tool steps
with correct parameters (query: "senior python", filters: remote=true, min_salary=200000,
min_score=8),而不是 crude regex matching.

## Step 2: Map the File Surface

Files to modify:
- `src/joborion/agent/planner.py` — Add `LLMPlanner` class; update `Planner` to try LLM first with keyword fallback
- `tests/test_planner.py` — Add LLM planner tests (mocked LLM client)

Files to create: none

## Step 3: Decompose into Tasks

Task 1: Add LLMPlanner class to planner.py
  File: src/joborion/agent/planner.py
  - New `LLMPlanner` class with `__init__(self, client)` and `plan(self, goal) -> Plan`
  - System prompt listing available tools with their names, descriptions, and parameter schemas
  - User message is the goal text
  - Parse LLM JSON response into Plan/PlanSteps
  - Validate tool names against a known tool list
  - On any failure (JSON parse error, invalid tool, LLM error), return None so caller can fallback
  Test: tests/test_planner.py::TestLLMPlanner::test_plan_valid_response
  Depends on: nothing

Task 2: Add JSON parsing and validation logic
  File: src/joborion/agent/planner.py
  - `_parse_llm_response(raw: str) -> list[dict]` — extract JSON array from LLM text
  - `_validate_steps(steps: list[dict]) -> list[PlanStep]` — check tool names, fill defaults
  - Known tool list: all 14 tools from registry
  Test: tests/test_planner.py::TestLLMPlanner::test_parse_malformed_json, test_validate_unknown_tool
  Depends on: Task 1

Task 3: Update Planner to try LLM first, fallback to keyword
  File: src/joborion/agent/planner.py
  - `Planner.__init__(self, client=None)` — accept optional LLM client
  - `Planner.plan()` tries `LLMPlanner.plan()` first; if returns None, falls back to keyword `_detect_stages` + `_build_steps`
  - If no client provided, goes straight to keyword planner (zero cost)
  Test: tests/test_planner.py::TestPlanner::test_plan_uses_llm_when_available, test_plan_fallback_on_llm_failure
  Depends on: Tasks 1-2

Task 4: Wire LLM client into Orchestrator
  File: src/joborion/agent/orchestrator.py
  - `Orchestrator.__init__` creates `Planner(client=get_client())` when LLM is available
  - Wrap in try/except so missing API key doesn't crash — falls back to keyword planner
  Test: tests/test_orchestrator.py::TestOrchestratorPlan::test_plan_with_llm_client
  Depends on: Task 3

## Step 4: Define Verification

```bash
pytest tests/test_planner.py -v
pytest tests/test_orchestrator.py -v
pytest tests/ -v  # full suite still passes
ruff check src/joborion/agent/planner.py src/joborion/agent/orchestrator.py
```

## Step 5: Critical Review

1. Scope creep? — No. Only planner.py and orchestrator.py touched.
2. Missing tasks? — No. LLM call, parsing, validation, fallback, wiring all covered.
3. Wrong order? — Tasks 1-2 are independent of each other but both needed before Task 3.
4. Over-engineered? — No. Simple: send goal to LLM, parse JSON, fallback on failure.
5. Testable? — Yes. Mock the LLM client, verify JSON parsing, verify fallback behavior.

**Design principle:** The LLM planner is additive. The keyword planner remains the
guaranteed fallback. Zero cost when LLM is unavailable. One LLM call per plan
(max ~$0.001 with Gemini Flash).
