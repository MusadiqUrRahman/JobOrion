# Reporting Analytics

## Goal

A read-only `joborion report` command that aggregates the pipeline's existing
telemetry — pipeline funnel, provider intelligence, cost history, and recent
runs — into one deterministic terminal report. No LLM calls, no network, no
schema changes: it closes the feedback loop by surfacing what the tool already
records.

## Facts Established

- Tables already exist and are written by the pipeline:
  - `jobs` (stage columns: `full_description`, `fit_score`,
    `tailored_resume_path`, `applied_at`) → funnel
  - `provider_metrics` (per-run `found/stored/passed/scored/applied/rejected/
    errors/latency_ms/avg_fit`, ISO `run_started_at`) → provider intelligence
  - `cost_ledger` (`cost_usd`, `tool`, `action`, `recorded_at`) → cost history
  - `run_log` (`started_at`, `goal`, `status`, `jobs_discovered`,
    `jobs_applied`, `total_cost`, `total_duration_ms`) → run history
  - `source_stats` (`disabled`) → surfaced via
    `joborion.sourcing.learning.provider_states`
- `get_stats(conn)` (database.py:471) already computes funnel-ish counts but is
  per-snapshot; the report needs a time-windowed, composed view instead.
- Existing report/render patterns to reuse: `RunReporter` (plain text) and
  `dashboard.py` (pure query functions returning dicts + rich console render).
  CLI commands use `print_screen_header`, `_bootstrap()`, `get_connection()`.
- `tests/conftest.py` has the `cli_flags` fixture (introspects
  `OptionInfo.param_decls`) — new CLI flags must be asserted via that pattern,
  not on `--help` rendered text.
- ISO timestamp filtering via `recorded_at >= datetime('now', '-N days')`
  works lexicographically for the stored ISO strings.

## File Surface

Files to create:
- `src/joborion/report.py` — pure query functions + `build_report` + `render_report`
- `docs/plans/reporting-analytics.md` — this plan

Files to modify:
- `src/joborion/cli.py` — add `report` command after `reflect`
- `tests/test_report.py` — new tests (create)

## Tasks

Task 1: Build the report module
  File: `src/joborion/report.py`
  Pure functions (each takes `conn`, uses parameterized queries, no LLM/network):
  - `pipeline_funnel(conn) -> dict` — counts: discovered (total), enriched
    (full_description), scored (fit_score), tailored (tailored_resume_path),
    applied (applied_at)
  - `provider_report(conn, days, top) -> list[dict]` — aggregate
    `provider_metrics` rows where `run_started_at >= datetime('now','-N days')`,
    grouped by provider: runs, found, stored, passed, scored, applied,
    rejected, errors, avg_fit, avg latency; ordered by stored desc, limit `top`;
    each entry tagged `disabled` from `source_stats`
  - `cost_report(conn, days) -> dict` — total cost + call count in window,
    plus top cost by `tool` (limit 5)
  - `run_history(conn, days, top) -> list[dict]` — recent `run_log` rows in
    window, newest first: started_at, goal, status, jobs_discovered,
    jobs_applied, total_cost
  - `build_report(conn, days=30, top=10) -> dict` — composes the above; also
    a `generated_at` timestamp
  - `render_report(report: dict) -> str` — plain-text sections (funnel table,
    provider table, cost table, recent runs); graceful "no data yet" on empty
    DB (no crash, zeros/None rendered as `-`)
  Verify: `uv run pytest tests/test_report.py` green
  Depends on: nothing
  Status: [x] Done — module + tests pass

Task 2: Add the CLI command
  File: `src/joborion/cli.py`
  `@app.command() def report(days: int = 30, top: int = 10, json: bool = False)`
  — after `reflect`; `_bootstrap()`; prints via `render_report` or dumps JSON
  (`--json`). No LLM calls; deterministic.
  Verify: `joborion report` and `joborion report --json` run against an empty
  DB without error; cli_flags test green
  Depends on: Task 1
  Status: [x] Done — flags asserted via cli_flags; empty-DB and --json CLI
          tests pass

Task 3: Tests
  File: `tests/test_report.py` (new)
  - tmp_path DB fixture (same pattern as test_dashboard/test_adzuna)
  - funnel counts from seeded `jobs` rows (each stage represented)
  - provider aggregation math (2 runs, 2 providers → merged rows, ordering,
    top-N limit, avg_fit, disabled flag)
  - cost totals + by-tool breakdown
  - run_history ordering and window filtering
  - empty DB → `build_report` returns zeros/`[]`; `render_report` contains
    "no data" and doesn't raise
  - CLI: `cli_flags["report"]` contains `--days`, `--top`, `--json`; invoke
    with empty DB → exit_code 0
  Verify: `uv run pytest tests/test_report.py` green
  Depends on: Task 2
  Status: [x] Done — 16 tests (funnel, provider agg/limit/disabled, cost,
          run history, empty DB, render, CLI)

Task 4: Verification + commit
  Verify: `uv run ruff check src tests` clean; full `uv run pytest -q` green
  (expect 667 + ~7 new = 674); live `uv run joborion report` against the real
  local DB shows sections
  Commit: `feat: add joborion report analytics command (reporting analytics)`
  Status: [x] Done — ruff clean; full suite 683 passed (667 + 16 new); live
          run shows funnel + recent runs (providers empty in the local DB —
          historical runs predate provider_metrics; rows populate on future
          search runs, see pipeline.py:182)

## Verification

```bash
uv run ruff check src tests
uv run pytest -q
uv run pytest tests/test_report.py
uv run joborion report --days 30 --top 10
uv run joborion report --json
```

Status: [x] DONE — ruff clean; full suite 683 passed; live `report` and
`--json` render against the real local DB.

## Critical Review

1. Scope creep? Read-only aggregation of existing tables only; no schema or
   write path. `--json` is one flag, no file output, no HTML.
2. Missing tasks? No need to touch dashboard/digest/reflector — the report
   reads the same tables independently.
3. Wrong order? Tasks are sequential (module → CLI → tests).
4. Over-engineered? Reuses the RunReporter/dashboard style; no new deps.
5. Testable? All query functions are network-free; DB tests use tmp_path;
   CLI asserted via the existing cli_flags fixture.
