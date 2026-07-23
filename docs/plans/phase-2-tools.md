# Phase 2: Tools — Implementation Plan

## Goal

The orchestrator (Phase 3) can call any pipeline stage as a tool with
standardized input/output, cost tracking, and error classification.

## File Surface

Files to create:
- `src/joborion/agent/__init__.py` — empty, makes agent a package
- `src/joborion/agent/tools.py` — Tool base class + ActionResult dataclass
- `src/joborion/agent/registry.py` — tool registry, dispatch, descriptions for LLM
- `src/joborion/tools/__init__.py` — empty, makes tools a package
- `src/joborion/tools/discovery.py` — discovery tools (3 scrapers)
- `src/joborion/tools/enrichment.py` — enrichment tools (single + batch)
- `src/joborion/tools/scoring.py` — scoring tools (single + batch)
- `src/joborion/tools/documents.py` — document tools (tailor, cover, pdf)
- `src/joborion/tools/database.py` — database query tools
- `tests/test_tools.py` — all tool tests

## Tasks

### Task 1: Create agent package + Tool base class + ActionResult
  File: src/joborion/agent/__init__.py, src/joborion/agent/tools.py
  Test: tests/test_tools.py::TestToolBase::test_action_result_fields
  Depends on: nothing

### Task 2: Create Tool Registry
  File: src/joborion/agent/registry.py
  Test: tests/test_tools.py::TestRegistry::test_register_and_dispatch
  Depends on: Task 1

### Task 3: Create tools package + discovery tools
  File: src/joborion/tools/__init__.py, src/joborion/tools/discovery.py
  Test: tests/test_tools.py::TestDiscoveryTools::test_scrape_jobspy_returns_result
  Depends on: Task 1

### Task 4: Enrichment tools
  File: src/joborion/tools/enrichment.py
  Test: tests/test_tools.py::TestEnrichmentTools::test_enrich_single_job_returns_result
  Depends on: Task 1

### Task 5: Scoring tools
  File: src/joborion/tools/scoring.py
  Test: tests/test_tools.py::TestScoringTools::test_score_single_job_returns_result
  Depends on: Task 1

### Task 6: Document tools
  File: src/joborion/tools/documents.py
  Test: tests/test_tools.py::TestDocumentTools::test_tailor_returns_result
  Depends on: Task 1

### Task 7: Database query tools
  File: src/joborion/tools/database.py
  Test: tests/test_tools.py::TestDatabaseTools::test_query_jobs_returns_result
  Depends on: Task 1

### Task 8: Register all tools + integration tests
  File: src/joborion/agent/registry.py (update), tests/test_tools.py (update)
  Test: tests/test_tools.py::TestRegistry::test_all_tools_registered
  Depends on: Tasks 2-7

## Verification

```bash
pytest tests/test_tools.py -v
pytest tests/ -v
ruff check src/
```

## Critical Review

1. Scope creep? — No, only touches agent/ and tools/ packages + tests
2. Missing tasks? — No, all 8 PHASES.md steps covered
3. Wrong order? — Tasks 1-2 are foundation, 3-7 are independent, 8 integrates
4. Over-engineered? — Simplified from PHASES.md: batch tools are convenience wrappers, single-job tools are the core
5. Testable? — Each task has exactly one test, all verifiable independently
