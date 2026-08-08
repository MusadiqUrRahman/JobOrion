# Plan: Dynamic Agent Loop (ReAct-style)

## Step 1 — Goal

User can run `joborion run --goal "<goal>" --agentic` and the agent picks the
next tool on each step based on LLM observation of prior tool results — it
self-corrects on errors, adapts parameters, and stops when the goal is met or
budget/iteration limits hit. The existing deterministic `run --goal --auto`
path keeps working unchanged.

## Step 2 — File Surface

### Files to create

- `src/joborion/agent/agent_loop.py` (NEW) — `AgentLoop` class implementing the
  ReAct loop: system prompt built from the real tool registry schemas, each
  LLM turn returns a JSON decision (`tool`+`params` or `done`+`summary`),
  observations are appended to the message history, tool errors are fed back
  for self-correction, failing tools are blocked after 2 consecutive failures,
  malformed LLM responses are retried (max 2) then stopped, and the loop ends
  on `done`, iteration limit, or budget exhaustion.
- `tests/test_agent_loop.py` (NEW) — ~10 test cases (see Task 3).

### Files to modify

- `src/joborion/agent/planner.py` — fix stale tool names in `_STAGE_TOOLS`,
  `_KNOWN_TOOLS`, and `_LLM_SYSTEM_PROMPT` example to the real registry names
  (`scrape_jobspy`, `scrape_workday`, `scrape_ai_sites`, `enrich_batch`,
  `score_batch`, `write_cover_letter`, `convert_to_pdf`).
- `src/joborion/agent/orchestrator.py` — fix `_APPLY_TOOLS` stale names; extract
  the reflect+report tail of `execute_autonomous` into a private
  `_reflect_and_report(execution)` helper; add `agentic: bool = False` param and
  new `execute_agentic()` method that runs `AgentLoop` (falling back to the
  deterministic path when no LLM client is available) and reuses the shared
  reflect+report tail.
- `src/joborion/cli.py` — add `--agentic` flag to `run`; when set with `--goal`,
  call `orch.execute_agentic()` and render the report panel (same style as
  `--auto`).
- `tests/test_planner.py` — update asserted tool names to registry names.
- `tests/test_orchestrator.py` — update mock tool names; add tests for
  `execute_agentic`.
- `tests/test_search_providers_tool.py` — line 70 assert `scrape_jobspy` instead
  of `search_jobspy`.

## Step 3 — Tasks

Each task has exactly one verification test.

### [x] Task 1: Reconcile planner/orchestrator tool names with the registry

- `src/joborion/agent/planner.py`: `_STAGE_TOOLS` search stage → `scrape_jobspy`/`scrape_workday`/`scrape_ai_sites`; details → `enrich_batch`; evaluate → `score_batch`; letter → `write_cover_letter`; export → `convert_to_pdf`. Fix `_KNOWN_TOOLS` and prompt example the same way.
- `src/joborion/agent/orchestrator.py`: `_APPLY_TOOLS = {"tailor_resume", "write_cover_letter", "convert_to_pdf"}`.
- `tests/test_planner.py`, `tests/test_search_providers_tool.py:70`: update asserted names.
- Test: `pytest tests/test_planner.py tests/test_search_providers_tool.py -q`

### [x] Task 2: Add drift-guard test that planner-emitted tool names are registered

- `tests/test_planner.py`: new test — for the keyword planner's `_STAGE_TOOLS`
  tool names and `_KNOWN_TOOLS`, assert every name is in
  `build_default_registry().list_tools()`. Prevents future name drift.
- Test: `pytest tests/test_planner.py::TestPlannerToolNameSync -q`

### [x] Task 3: Create AgentLoop module

- `src/joborion/agent/agent_loop.py`:
  - `AgentLoop(goal, registry, client, max_iterations=20, max_cost=5.0, context=None)`.
  - Build system prompt from `registry.get_tool_descriptions()` (name,
    description, parameters) + output contract + rules.
  - `run() -> dict` with keys: `status` ("completed"|"partial"|"error"),
    `summary`, `actions` (list of action names), `trace` (list of
    {thought, tool, observation}), `total_cost`, `llm_calls`, `tool_calls`,
    `errors`.
  - Loop: chat → parse decision → done?/dispatch → observe. Track LLM cost via
    `client.cost_usd` delta (fallback 0 when absent). Block a tool after 2
    consecutive errors. Catch `BudgetExceeded` and return graceful "partial".
  - `_parse_decision(raw)` strips markdown fences then `json.loads`, returns
    None on failure.
- Test: covered by Task 4 tests.

### [x] Task 4: Tests for AgentLoop

- `tests/test_agent_loop.py` with a fake client (scripted chat responses):
  - happy path: agent calls `query_jobs` then declares done → status completed.
  - tool error → agent receives error observation and adapts (fake client
    switches tool next turn) → completed.
  - same tool fails twice → blocked, next turn uses another tool.
  - unknown tool name → feedback observation, loop continues.
  - malformed JSON twice → status "error".
  - iteration limit reached → status "partial".
  - budget exceeded (max_cost small, tool returns cost) → status "partial".
  - `done` with summary → summary in result.
- Test: `pytest tests/test_agent_loop.py -q`

### [x] Task 5: Wire execute_agentic() into Orchestrator

- `src/joborion/agent/orchestrator.py`:
  - Extract `_reflect_and_report(execution)` from `execute_autonomous` tail.
  - `execute_agentic()`: get LLM client via `joborion.llm.get_client()`; on any
    exception log a warning and return `self.execute_autonomous()` (determinism
    fallback). Otherwise run `AgentLoop`, then `_reflect_and_report`, return
    dict with loop trace/summary included.
- Test: `tests/test_orchestrator.py::TestOrchestratorAgentic`

### [x] Task 6: Tests for execute_agentic

- `tests/test_orchestrator.py`:
  - fake client returns `done` → result has status, report, trace, summary.
  - `get_client` raises → falls back to deterministic (result status present).
- Test: `pytest tests/test_orchestrator.py::TestOrchestratorAgentic -q`

### [x] Task 7: CLI `--agentic` flag

- `src/joborion/cli.py`: add `agentic: bool = typer.Option(False, "--agentic", ...)`
  to `run`; in the goal branch, if `agentic` call `execute_agentic()` and render
  the report panel like `--auto`.
- Test: `pytest tests/test_post_run.py::test_run_agentic_flag` (asserts
  `--agentic` in `cli_flags["run"]`) — add a small test in `tests/test_cli.py`.

### [x] Task 8: Full verification

- `pytest tests/ -q` (expect 724 existing + ~15 new → all green)
- `ruff check src/ tests/`
- Confirm `_KNOWN_TOOLS` drift-guard passes.

## Step 4 — Verification

```bash
pytest tests/ -q
ruff check src/ tests/
```

## Step 5 — Critical Review

1. **Scope creep?** No — the tool-name reconciliation is required because the
   dynamic loop dispatches real registry names; the old names would fail
   dispatch. Nothing else touched.
2. **Missing tasks?** Reflection/report sharing is included in Task 5. Budget
   semantics covered in Tasks 3/4. Fallback determinism covered in Task 5.
3. **Wrong order?** Task 1 before Task 3 so the loop dispatches canonical names;
   drift-guard (Task 2) locks it in. Tasks build sequentially.
4. **Over-engineered?** Loop uses the existing `ContextManager`, `ActionResult`,
   `ToolRegistry` — no new abstractions. Shared reflect/report helper avoids
   duplicating a 40-line block.
5. **Testable?** Every task has a specific test; `AgentLoop` takes an injectable
   fake client, no network/LLM needed in tests.
