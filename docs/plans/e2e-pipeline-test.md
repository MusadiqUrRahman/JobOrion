# Plan: End-to-End Pipeline Integration Test

**Goal:** A single test that exercises the full pipeline (search → enrich → score → tailor → letter → export) with real SQLite DB, verifying data flows correctly between every stage, with all external I/O mocked.

## Step 1: Define the Goal

User can run `pytest tests/test_pipeline_e2e.py -v` and see a test that:
- Creates a temp DB with sample jobs
- Runs each pipeline stage in sequence
- Verifies data flows: jobs inserted by search are enriched by details, scored by evaluate, tailored by tailor, etc.
- All external I/O (LLM, jobspy, Playwright, HTTP) is mocked with canned responses

## Step 2: Map the File Surface

Files to create:
- `tests/test_pipeline_e2e.py` — Full pipeline integration test

Files to modify: none

## Step 3: Decompose into Tasks

Task 1: Create test fixture with temp DB + mock config
  File: tests/test_pipeline_e2e.py
  - `tmp_path` fixture with: profile.json, resume.txt, searches.yaml
  - Patch `DB_PATH` to point to tmp_path/joborion.db
  - Patch `PROFILE_PATH`, `RESUME_PATH`, `SEARCH_CONFIG_PATH`
  - Create all required dirs via `ensure_dirs()`
  - Seed 3 sample jobs into the `jobs` table (url, title, site)
  Test: fixture loads without error
  Depends on: nothing

Task 2: Mock LLM client with canned responses
  File: tests/test_pipeline_e2e.py
  - Mock `llm.get_client()` to return a mock LLM client
  - Mock `client.chat()` to return appropriate responses per call:
    - Scoring calls → returns JSON with score/reasoning
    - Tailoring calls → returns tailored resume text
    - Cover letter calls → returns cover letter text
  - Track call count to verify correct number of LLM calls per stage
  Test: LLM mock returns correct response types
  Depends on: Task 1

Task 3: Mock jobspy discovery
  File: tests/test_pipeline_e2e.py
  - Mock `jobspy.scrape_jobs()` to return a small DataFrame with 2-3 jobs
  - Verify jobs are inserted into DB after search stage
  Test: search stage inserts jobs into DB
  Depends on: Task 1

Task 4: Write the full pipeline e2e test
  File: tests/test_pipeline_e2e.py
  - Test `test_full_pipeline_search_to_tailor`:
    1. Seed 3 jobs into DB (url, title, site, full_description)
    2. Run scoring stage → verify fit_score written to DB
    3. Run tailoring stage → verify tailored_resume_path written to DB
    4. Run cover letter stage → verify cover_letter_path written to DB
    5. Verify cost_ledger has entries
  - Test `test_pipeline_search_to_evaluate`:
    1. Mock jobspy to return 2 jobs
    2. Run search → verify 2 jobs in DB
    3. Mock enrichment to simulate detail scraping
    4. Run evaluate → verify scores written
  Test: tests/test_pipeline_e2e.py::test_full_pipeline_search_to_tailor
  Depends on: Tasks 1-3

Task 5: Test error recovery across stages
  File: tests/test_pipeline_e2e.py
  - Test `test_pipeline_continues_after_stage_error`:
    1. Mock one tool to fail (e.g., enrichment returns error)
    2. Run pipeline → verify other stages still execute
    3. Verify errors are recorded but pipeline doesn't crash
  Test: tests/test_pipeline_e2e.py::test_pipeline_continues_after_stage_error
  Depends on: Task 4

## Step 4: Define Verification

```bash
pytest tests/test_pipeline_e2e.py -v
pytest tests/ -v  # full suite still passes
ruff check tests/test_pipeline_e2e.py
```

## Step 5: Critical Review

1. Scope creep? — No. Single test file, tests data flow between stages.
2. Missing tasks? — No. Covers search→enrich→score→tailor→letter flow.
3. Wrong order? — Tasks 1-3 are setup, Task 4 is the main test, Task 5 is error case.
4. Over-engineered? — No. One test file, focused on data flow verification.
5. Testable? — Yes. All external I/O mocked, real DB for data verification.

**Key design decisions:**
- Use `run_pipeline()` from pipeline.py as the entry point (tests the real pipeline, not just tools)
- Mock at the lowest level (jobspy, LLM, Playwright) not at tool level
- Verify DB state after each stage (not just final state)
- Keep it simple: 3 sample jobs, 1 search query, minimal config
