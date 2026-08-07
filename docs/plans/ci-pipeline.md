# CI Pipeline

## Goal

A GitHub Actions workflow runs `ruff check src tests` and the full pytest
suite on every push/PR to `main`, and both pass — so lint and test
regressions are caught automatically instead of manually.

## File Surface

Files to create:
- `.github/workflows/ci.yml` — lint + test job(s), uv-based
- `docs/plans/ci-pipeline.md` — this plan

Files to modify:
- `tests/test_document_converter.py` — remove unused `import pytest`
- `tests/test_eligibility.py` — remove unused `import pytest`
- `tests/test_memory.py` — remove unused `import sqlite3`, `MagicMock`, `get_connection` (2 spots), unused `id1`
- `tests/test_output_checker.py` — remove unused `import pytest`
- `tests/test_tools.py` — remove unused `import sqlite3`, `patch`, `MagicMock`
- `pyproject.toml` — declare `[tool.ruff.lint] select = ["E4", "E7", "E9", "F"], preview = false`
  (repo never declared a rule set; latest ruff enables preview rules by default → 330 errors, must pin stable defaults);
  add `pytest-mock` to dev extras (11 tests use the `mocker` fixture, was missing)
- `uv.lock` — committed for reproducible CI installs

These 9 F401 fixes are required for the lint gate to pass (pre-existing
baseline debt, now enforced by CI).

## Tasks

Task 1: Remove the 9 unused imports flagged by ruff
  File: tests/{test_document_converter,test_eligibility,test_memory,test_output_checker,test_tools}.py
  Verify: `python -m ruff check src tests` reports 0 errors
  Depends on: nothing
  Status: [x] Done — ruff clean on global (0.15.22) AND uv (0.16.0) after
          also pinning the lint rule set (Task 4)

Task 2: Create `.github/workflows/ci.yml`
  File: .github/workflows/ci.yml
  Workflow: `ci` on push + pull_request to main; ubuntu-latest;
  python 3.12 via `astral-sh/setup-uv`; install `uv sync --extra dev`;
  run `uv run ruff check src tests` then `uv run pytest -q`;
  concurrency group per ref; job timeout 30m.
  Verify: YAML parses (python yaml.safe_load); no local run possible
  Depends on: nothing (task 1 optional dependency, fix either order)
  Status: [x] Done

Task 3: Confirm workflow commands pass in a clean env
  Verify: `uv run ruff check src tests` → 0 errors; `uv run pytest -q`
  → all green locally via uv (replaces global-interpreter caveat)
  Depends on: Task 1, Task 2, Task 4, Task 5
  Status: [x] Done — 666 passed, ruff clean, under `uv run`

Task 4: Pin ruff rule set in pyproject.toml
  File: pyproject.toml — `[tool.ruff.lint] select = ["E4","E7","E9","F"], preview = false`
  Why: latest ruff enables preview rules by default; without a declared
  rule set the gate is non-deterministic across ruff versions
  Verify: `ruff check src tests` clean on both 0.15.22 and 0.16.0
  Status: [x] Done

Task 5: Add pytest-mock to dev extras
  File: pyproject.toml — `dev = ["pytest>=7.0", "pytest-mock>=3.0", "ruff>=0.1"]`
  Why: 11 tests use the `mocker` fixture; it was missing from dev extras
  Verify: `uv run pytest -q` → 666 passed, 0 errors
  Status: [x] Done

## Verification

```bash
python -m ruff check src tests        # 0 errors
uv run pytest -q                      # full suite green (666 tests)
python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"
```

Manual: push to origin/main and confirm the Actions run goes green on GitHub.
Status: [x] DONE — `ci` workflow green on `main` (a48787a) after the
environment-coupling fixes above; lint + tests both pass on the runner.

## Critical Review

1. Scope creep? Fixing 9 F401s is in-scope (required for the lint gate). No
   test logic changes.
2. Missing tasks? Single provider-python job is enough; a version matrix
   (3.11–3.13) is future work and risks the git JobSpy dependency.
3. Wrong order? Tasks are parallel-safe; verification last.
4. Over-engineered? No caching of uv/cache, no matrix, no nightly — minimal.
5. Testable? Task 1 and Task 3 verify locally; Task 2 verified by YAML parse
   + the manual push check.

## CI Run Fixes (from first red run on GitHub Actions)

First `ci` run failed 8 tests that passed on Windows but not on the runner:

- **6 CLI help tests** (test_autonomous x3, test_scheduler x2, test_notifier x1):
  asserted on rich-rendered `--help` text. On GH Actions, typer sets
  `force_terminal=True` (`GITHUB_ACTIONS` env, typer/rich_utils.py:78-81) and
  the option cells are truncated in the captured output. Fixed by asserting
  on registered option declarations instead (deterministic across envs):
  new `tests/conftest.py` `cli_flags` fixture introspects
  `OptionInfo.param_decls` per command; tests keep the `--help` invoke +
  `exit_code == 0` check.
- **`TestScoreSingleJobTool::test_execute_job_not_found`**: `ScoreSingleJobTool`
  read `RESUME_PATH` (absent on runner) before checking the job existed, so
  the error was `FileNotFoundError` not "job not found". Fixed the tool to
  look up the job in the DB first (`src/joborion/tools/scoring.py`).
- **`TestScoringE2E::test_score_single_job`**: patched
  `fit_scorer.RESUME_PATH` but the tool reads `config.RESUME_PATH`; on the
  runner no `~/.joborion/resume.txt` exists. Added the missing patch to
  `tests/test_pipeline_e2e.py`.

