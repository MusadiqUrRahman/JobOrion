# Legacy Provider View for Reports

## Goal

`joborion report`'s Providers section shows real data on databases created
before `provider_metrics` existed — by falling back at read time to the
`source_stats` + `jobs` tables the legacy pipeline already wrote. No data
writes, no schema change, no new flags.

## Facts Established

- The user's DB (and any pre-registry DB): `provider_metrics` is empty (0
  rows), but `source_stats` has `jobspy` (3 runs), `workday` (3 runs),
  `smartextract` (3 runs), all with `total_jobs = 0`, `last_success_at` in
  window. `jobs` has 257 rows with `strategy`: `workday_api` (234), `jobspy`
  (20), `css_selectors` (3); all `source_provider IS NULL`.
- Legacy `strategy` values map to legacy provider names: `jobspy`→`jobspy`,
  `workday_api`→`workday`, `css_selectors`→`smartextract`. Modern rows use
  `strategy='provider'` + `source_provider=<name>`, so this map never
  conflicts with modern DBs.
- `report.py::provider_report` (report.py:70) reads `provider_metrics` via
  `_PROVIDER_SQL` (window-filtered, ordered stored DESC, LIMIT top), merges
  `source_stats.disabled` via `_DISABLED_SQL`. Row dicts have keys: provider,
  runs, found, stored, passed, scored, applied, rejected, errors, avg_fit,
  avg_latency_ms, disabled.
- `render_report` renders `data["providers"]` generically — same row shape
  works with no render change. `build_report`/`--json` inherit automatically.
- Read-only report contract: no writes, no LLM, no network (report.py:5-6).
- `source_stats` is updated by `record_provider_run` (learning.py:26) only on
  NEW runs, so it cannot be backfilled from; the fallback must read, not write.

## Design

Read-time fallback: in `provider_report`, when the windowed
`provider_metrics` query returns zero rows, build the provider list from
`source_stats` (runs = total_runs, errors = failed_runs, passed =
total_passed, avg_fit, disabled) enriched with `found`/`stored` from `jobs`
counts grouped by the legacy strategy map. Only rows with `total_runs > 0`
appear. Sort by stored DESC, apply `top` limit. If any `provider_metrics`
row exists in the window, behavior is unchanged (modern DBs).

## File Surface

Files to modify:
- `src/joborion/report.py` — legacy strategy map, fallback SQL, and the
  fallback branch in `provider_report`

Files to create:
- none (tests extend `tests/test_report.py`)

## Tasks

Task 1: Legacy fallback in provider_report
  File: `src/joborion/report.py`
  - `_LEGACY_STRATEGY_PROVIDERS = {"jobspy": "jobspy", "workday_api": "workday",
    "css_selectors": "smartextract"}`
  - `_LEGACY_RUNS_SQL` = `SELECT source_name, total_runs, failed_runs,
    total_passed, avg_fit FROM source_stats WHERE total_runs > 0`
  - `_JOBS_BY_STRATEGY_SQL` = `SELECT strategy, COUNT(*) AS n FROM jobs
    GROUP BY strategy`
  - In `provider_report`, when `rows` is empty: build legacy rows per
    `_LEGACY_RUNS_SQL` with found/stored summed from `_JOBS_BY_STRATEGY_SQL`
    via the map; `scored`/`applied`/`rejected` = 0, `avg_latency_ms` = 0;
    reuse the existing `disabled` dict; sort stored DESC; apply `top` limit.
  Verify: `uv run python -c` import + existing tests green
  Depends on: nothing
  Status: [x] Done

Task 2: Tests
  File: `tests/test_report.py` — extend `TestProviderReport`
  - empty provider_metrics + source_stats rows + jobs with legacy strategies →
    legacy rows with correct runs/found/errors and stored DESC order
  - provider_metrics has rows → fallback NOT triggered (modern behavior)
  - legacy source_stats row with no matching jobs → found 0, still listed
  - unmapped job strategy (e.g. `provider`) → ignored, no phantom provider
  - `top` limit applies to legacy rows
  Verify: `uv run pytest tests/test_report.py -q` green
  Depends on: Task 1
  Status: [x] Done

Task 3: Verification + commit
  Verify: `uv run ruff check src tests` clean; full `uv run pytest -q` green
  (719 + 5 new = 724 passed); live smoke on the real DB confirmed `joborion
  report` now shows Providers (workday 234, jobspy 20, smartextract 3 found)
  and `joborion report --json` includes the same
  Commit: `feat: legacy provider view in report (source_stats fallback)`
  Status: [x] Done

## Verification

```bash
uv run ruff check src tests
uv run pytest tests/test_report.py -v
uv run pytest -q
uv run joborion report
uv run joborion report --json
```

## Critical Review

1. Scope creep? Read-only fallback only; no flag, no migration, no CLI change.
2. Missing tasks? render/build inherit automatically (same row shape);
   `--json` covered by live smoke.
3. Wrong order? fallback → tests → verify.
4. Over-engineered? ~25 lines + one strategy map; avoids fabricating
   per-run timestamps or writing data.
5. Testable? Window-empty and window-populated branches both tested; live
   smoke on the user's real DB is the acceptance proof.

