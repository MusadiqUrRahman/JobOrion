# Post-Run Reporting Hook

## Goal

Automate delivery of existing reporting after a pipeline run: `joborion run
--notify` / `--report` and `joborion daemon --notify` / `--report` finish each
run by emailing the digest and/or printing the analytics report — so a
scheduled run delivers insight without a manual `notify`/`report`/`status`.

## Facts Established

- `run_pipeline` (pipeline.py:575) is the single execution entry used by both
  the `run` command (cli.py:461) and the daemon job `_job` (cli.py:504-506).
- The CLI already has `notify` (cli.py:530) — builds the digest from
  `get_stats` + `get_total_cost` via `digest_from_stats`/`build_digest` and
  sends with `send_digest`. `send_digest` is best-effort: returns False and
  skips when SMTP is unconfigured — safe to reuse for automation.
- `report` (cli.py) renders `build_report`/`render_report` from
  `joborion.report` (newly landed). Both digest and report are read-only.
- `_run_scheduled(stages, interval, at)` (cli.py:494) is called by both
  `run --schedule` and `daemon`; the daemon `_job` closure is where a
  post-run hook must go to cover scheduled runs.
- `--notify`/`--report` must be asserted via the `cli_flags` fixture (no
  rich `--help` text assertions).
- Automation sends must never fail the run: missing SMTP → warn and continue.

## File Surface

Files to modify:
- `src/joborion/cli.py` — new `_post_run_output` helper; `--notify`/`--report`
  flags on `run` and `daemon`; thread through `_run_scheduled`
- `docs/plans/post-run-reporting.md` — this plan

Files to create:
- `tests/test_post_run.py` — helper + CLI flag tests

No changes to `pipeline.py`, `notifier.py`, or `report.py`.

## Tasks

Task 1: `_post_run_output` helper
  File: `src/joborion/cli.py`
  `def _post_run_output(conn, *, notify: bool, report: bool, goal: str = "")`
  - `notify`: `digest_from_stats(get_stats(conn), goal=goal,
    total_cost=get_total_cost(conn))` → `build_digest` → `send_digest(cfg=
    load_notify_config())`; print success if sent, warning + continue if not
    configured. Never raises.
  - `report`: `console.print(render_report(build_report(conn=conn)))` after a
    spacer.
  Verify: ruff clean; unit tests (Task 3)
  Depends on: nothing
  Status: [x] Done

Task 2: Wire flags into `run`, `daemon`, and `_run_scheduled`
  File: `src/joborion/cli.py`
  - `run`: add `notify: bool = typer.Option(False, "--notify", ...)` and
    `report: bool = typer.Option(False, "--report", ...)`; after the
    legacy-mode `run_pipeline` call (and its errors check), call
    `_post_run_output(get_connection(), notify=notify, report=report,
    goal=goal or f"pipeline:{','.join(stage_list)}")`. Thread both into the
    `run --schedule` call.
  - `daemon`: add the same two flags; pass to `_run_scheduled`.
  - `_run_scheduled(stages, interval, at, *, notify=False, report=False)`:
    `_job` calls `run_pipeline(stages=stages)` then
    `_post_run_output(get_connection(), notify=notify, report=report,
    goal=f"pipeline:{','.join(stages)}")`.
  - Scope note: goal-driven `run --goal` paths return before legacy mode and
    are unaffected (flags documented as stage-mode only).
  Verify: `cli_flags["run"]`/`cli_flags["daemon"]` contain `--notify`,
  `--report`; scheduled path covered by tests
  Depends on: Task 1
  Status: [x] Done

Task 3: Tests
  File: `tests/test_post_run.py` (new)
  - `_post_run_output` notify path: monkeypatch `get_stats`, `get_total_cost`,
    `load_notify_config`, `send_digest` (capture digest) → asserts digest sent
    with expected goal and total cost
  - notify with no SMTP config → `send_digest` not called, no exception
  - report path: monkeypatch `build_report`/`render_report` → report text
    printed to console output
  - both flags together → digest sent AND report printed
  - CLI: `cli_flags["run"]` and `cli_flags["daemon"]` include `--notify` /
    `--report`
  Verify: `uv run pytest tests/test_post_run.py` green
  Depends on: Task 2
  Status: [x] Done

Task 4: Verification + commit
  Verify: `uv run ruff check src tests` clean; full `uv run pytest -q` green
  (683 + 9 new = 692 passed); live smoke `_post_run_output(report=True)` on
  the real DB printed the report after a run
  Commit: `feat: post-run notify/report flags for run and daemon`
  Status: [x] Done

## Verification

```bash
uv run ruff check src tests
uv run pytest -q
uv run pytest tests/test_post_run.py
uv run joborion run search --report
```

## Critical Review

1. Scope creep? Two flags + one thin helper; reuses tested digest/report
   functions. No changes to pipeline internals.
2. Missing tasks? Daemon and `run --schedule` share `_run_scheduled`, so one
   threading change covers both.
3. Wrong order? Helper → wiring → tests.
4. Over-engineered? No new module beyond the test file; automation send is
   intentionally best-effort.
5. Testable? Helper tested with monkeypatches; CLI flags via `cli_flags`.

