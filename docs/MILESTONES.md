# Milestones

## Overview

Milestones are concrete checkpoints within each phase. They answer the question: "How do I know this phase is done?" Each milestone is independently verifiable.

Every phase follows the development skill chain: `writing-plans` → `executing-plans` → `verification-before-completion`. See [`skills/README.md`](../skills/README.md) for the full protocol.

## Phase 0: Foundation

**Skills used:** `writing-plans`, `executing-plans`, `verification-before-completion`

### M0.1: Installable Package
- [ ] `pip install -e .` succeeds
- [ ] `joborion --version` prints correct version
- [ ] `joborion --help` lists all commands
- [ ] No import errors on `import joborion`

### M0.2: README
- [ ] README.md exists at project root
- [ ] Setup instructions are correct and tested
- [ ] Tier system is documented
- [ ] Basic usage examples work

### M0.3: Core Tests
- [ ] `tests/test_output_checker.py` passes (10+ test cases)
- [ ] `tests/test_document_converter.py` passes (8+ test cases)
- [ ] `tests/test_database.py` passes (10+ test cases)
- [ ] `tests/test_config.py` passes (6+ test cases)

### M0.4: Linting
- [ ] `ruff check src/` passes with 0 errors
- [ ] `ruff format src/` produces no changes
- [ ] No type errors (if mypy is added later)

**Phase 0 is complete when:** All 4 milestones are checked. Total effort: 1-2 days.

---

## Phase 1: Memory

**Skills used:** `writing-plans`, `executing-plans`, `verification-before-completion`, `systematic-debugging`

### M1.1: Site Memory
- [ ] `site_memory` table exists in database
- [ ] `record_site_attempt()` works for success and failure
- [ ] `get_reliable_sites()` filters correctly (>50% success rate)
- [ ] `get_blocked_sites_from_memory()` returns sites with 3+ failures
- [ ] Existing discovery modules use site memory (at least one source)

### M1.2: Run Log
- [ ] `run_log` table exists
- [ ] `start_run()` creates entry and returns run_id
- [ ] `finish_run()` updates entry with stats
- [ ] `get_recent_runs()` returns correct entries

### M1.3: Cost Ledger
- [ ] `cost_ledger` table exists
- [ ] `record_cost()` inserts correctly
- [ ] `get_run_cost()` sums correctly
- [ ] `get_total_cost()` returns all-time total
- [ ] `llm.py` records cost after every call

### M1.4: Cost Budget Enforcement
- [ ] `llm.py` has `set_budget()` method
- [ ] `llm.py` raises `BudgetExceeded` when limit hit
- [ ] Orchestrator checks budget before expensive actions
- [ ] Budget is enforced in pipeline mode

### M1.5: Memory Tests
- [ ] `tests/test_memory.py` passes (12+ test cases)
- [ ] All site memory operations tested with real DB
- [ ] Cost ledger accounting is accurate to the cent
- [ ] Budget enforcement stops calls correctly

**Phase 1 is complete when:** All 5 milestones are checked. Total effort: 3-5 days.

---

## Phase 2: Tools

**Skills used:** `writing-plans`, `executing-plans`, `subagent-driven-development`, `plan-orchestrate`

### M2.1: Tool Interface
- [ ] `agent/tools.py` defines `Tool` base class
- [ ] `ActionResult` dataclass has all required fields
- [ ] Tool interface is documented

### M2.2: Discovery Tools
- [ ] `tools/discovery.py` wraps `scrape_jobspy()`
- [ ] `tools/discovery.py` wraps `scrape_workday()`
- [ ] `tools/discovery.py` wraps `scrape_ai_sites()`
- [ ] Each tool returns `ActionResult` with correct status
- [ ] Each tool records site attempt in memory

### M2.3: Enrichment Tools
- [ ] `tools/enrichment.py` wraps single-job enrichment
- [ ] `tools/enrichment.py` wraps batch enrichment
- [ ] Error classification works (transient/permanent/degraded)

### M2.4: Scoring Tools
- [ ] `tools/scoring.py` wraps single-job scoring
- [ ] `tools/scoring.py` wraps batch scoring
- [ ] Cost estimation is accurate

### M2.5: Document Tools
- [ ] `tools/documents.py` wraps resume tailoring
- [ ] `tools/documents.py` wraps cover letter writing
- [ ] `tools/documents.py` wraps PDF conversion

### M2.6: Database Tools
- [ ] `tools/database.py` provides query functions
- [ ] `tools/database.py` provides update functions
- [ ] `tools/database.py` provides stats function

### M2.7: Tool Registry
- [ ] `agent/registry.py` lists all tools
- [ ] Tool descriptions are correct for LLM consumption
- [ ] Tool dispatch works (name -> execute)
- [ ] Usage statistics are tracked

### M2.8: Tool Tests
- [ ] `tests/test_tools.py` passes (20+ test cases)
- [ ] Each tool tested with valid and invalid inputs
- [ ] Error classification verified
- [ ] Cost estimation tested

**Phase 2 is complete when:** All 8 milestones are checked. Total effort: 3-5 days.

---

## Phase 3: Orchestrator

**Skills used:** `writing-plans`, `plan-orchestrate`, `subagent-driven-development`, `systematic-debugging`

### M3.1: Orchestrator Core
- [ ] `agent/orchestrator.py` implements the main loop
- [ ] Loop reads state correctly from database
- [ ] Loop checks memory before decisions
- [ ] Loop records results after actions
- [ ] Loop evaluates progress after each step

### M3.2: Planner
- [ ] `agent/planner.py` parses natural language goals
- [ ] Goal parsing produces correct structured output
- [ ] Planner generates valid action sequences
- [ ] Planner estimates cost and duration
- [ ] Planner handles different plan types (discovery-only, full, targeted)

### M3.3: Context Manager
- [ ] `agent/context.py` manages context window
- [ ] Context compression preserves recent actions
- [ ] Token counting is accurate
- [ ] Memory integration works (relevant memory fetched)

### M3.4: CLI Integration
- [ ] `joborion run --goal "..."` triggers orchestrator
- [ ] `joborion search --goal "..."` works
- [ ] `joborion plan --goal "..."` shows plan without executing
- [ ] Progress is displayed in real-time

### M3.5: Orchestrator Tests
- [ ] `tests/test_orchestrator.py` passes (10+ test cases)
- [ ] Plan generation produces valid plans
- [ ] Budget enforcement stops execution
- [ ] Error recovery retries transient failures
- [ ] Error recovery skips permanent failures
- [ ] Replanning works when stages fail

**Phase 3 is complete when:** All 5 milestones are checked. Total effort: 5-7 days.

---

## Phase 4: Reflection

**Skills used:** `writing-plans`, `executing-plans`, `verification-before-completion`

### M4.1: Reflection Log
- [ ] `reflection_log` table exists
- [ ] Reflection records are stored correctly
- [ ] Reflection records reference run_id

### M4.2: Reflector
- [ ] `agent/reflector.py` analyzes run outcomes
- [ ] Reflector identifies failures and their causes
- [ ] Reflector checks scoring calibration
- [ ] Reflector generates recommendations

### M4.3: Scoring Calibration
- [ ] Score distribution analysis works
- [ ] Score-vs-outcome correlation works (when data available)
- [ ] Calibration recommendations are actionable

### M4.4: Reflection CLI
- [ ] `joborion reflect` analyzes last run
- [ ] `joborion reflect --run-id <id>` analyzes specific run
- [ ] `joborion reflect --last 5` aggregates multiple runs

### M4.5: Reflection Tests
- [ ] `tests/test_reflector.py` passes (8+ test cases)
- [ ] Analysis produces valid reflection records
- [ ] Strategy changes are recommended on failure
- [ ] Memory updates are correct

**Phase 4 is complete when:** All 5 milestones are checked. Total effort: 3-5 days.

---

## Phase 5: Full Autonomy

**Skills used:** `writing-plans`, `plan-orchestrate`, `subagent-driven-development`, `verification-before-completion`

### M5.1: Goal Parser
- [ ] `agent/goal_parser.py` parses natural language to structured goal
- [ ] Goal parsing handles various input formats
- [ ] Goal parsing handles ambiguous inputs gracefully

### M5.2: Autonomous Mode
- [ ] `joborion run --goal "..." --auto` runs without pausing
- [ ] Cost cap is enforced throughout
- [ ] Application limit is enforced
- [ ] Results are saved correctly

### M5.3: Human-in-the-Loop Gates
- [ ] Approval gate works in interactive mode
- [ ] Approval gate works in semi mode
- [ ] Gates can be configured (what triggers them)
- [ ] Gates can be skipped with `--yes`

### M5.4: Run Summary Report
- [ ] `agent/reporter.py` generates human-readable report
- [ ] Report includes pipeline stats
- [ ] Report includes top applications
- [ ] Report includes cost breakdown
- [ ] Report includes lessons learned

### M5.5: Integration Tests
- [ ] `tests/test_autonomous.py` passes (8+ test cases)
- [ ] Full autonomous run completes without errors
- [ ] Cost budget is enforced end-to-end
- [ ] Memory is updated after run
- [ ] Reflection is generated after run

### M5.6: Scheduled Runs (Optional)
- [ ] `agent/scheduler.py` implements daily scheduling
- [ ] Schedule respects weekly cost cap
- [ ] Notification works (terminal or email)

**Phase 5 is complete when:** M5.1-M5.5 are checked. M5.6 is optional. Total effort: 5-7 days.

---

## Completion Criteria

The entire transformation is complete when:

1. All 6 phases have their milestones checked
2. The system can receive a goal and execute autonomously
3. The system learns from outcomes (memory + reflection)
4. The system stays within budget
5. The existing pipeline still works exactly as before
6. Total cost of development: less than $20 in LLM tokens for the agent features themselves
7. All development followed the skill protocols in `skills/`
