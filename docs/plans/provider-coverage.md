# Provider Coverage

## Goal

Widen sourcing coverage cheaply: enable the already-built Adzuna API provider
and add one new verified remote job board (Working Nomads) to the remote_boards
provider. Both are free and require no new credentials.

## Facts Established

- `AdzunaProvider` is fully implemented (`src/joborion/sources/adzuna_provider.py`,
  151 lines) and registered in `_PROVIDER_CLASSES`; it only sits behind
  `enabled: false` in `src/joborion/config/sources.yaml`.
- It degrades gracefully without keys (returns `found=0, errors=0` with a
  warning) — covered by `test_missing_key_returns_empty`.
- `test_sources_registry.py` uses a hardcoded `CONFIG` fixture for
  enable/ordering tests; only `test_loads_config` touches the real YAML and
  it only asserts `jobspy` exists. Flipping adzuna breaks no tests.
- Working Nomads exposes a live public JSON feed
  (`https://www.workingnomads.com/api/exposed_jobs`, verified 200 / 44 items):
  list of `{url, title, description (HTML), company_name, category_name, tags,
  location, pub_date}`. No salary data.
- Remote.co JSON endpoint timed out (verified) — rejected as a candidate.
- `test_search_aggregates_and_stores` passes an explicit `sources` list, so
  adding a default source does not break it; it will be extended to exercise
  the new dispatch path.

## File Surface

Files to modify:
- `src/joborion/config/sources.yaml` — adzuna `enabled: true`; add `workingnomads`
  to remote_boards `sources`
- `src/joborion/sources/remote_boards.py` — add parse/fetch/dispatch for Working Nomads
- `tests/test_remote_boards.py` — add `test_workingnomads_parses`; extend aggregate test
- `docs/plans/provider-coverage.md` — this plan

## Tasks

Task 1: Enable Adzuna
  File: `src/joborion/config/sources.yaml` — adzuna `enabled: true`
  Why: provider is implemented + tested; missing keys skip gracefully
  Verify: `python -c` build_providers includes adzuna; full suite green
  Depends on: nothing
  Status: [x] Done — `build_providers()` returns
          [jobspy, workday, adzuna, remote_boards, ats_boards, ai_sites]

Task 2: Add Working Nomads board
  Files: `src/joborion/sources/remote_boards.py`, sources.yaml
  Implement:
  - `parse_workingnomads(jobs: list) -> list[RawJob]` — maps title,
    company_name, location, url, `strip_html(description)`, category_name →
    job_type, pub_date → posted_at, is_remote=True, source="workingnomads",
    site="WorkingNomads"
  - `_fetch_workingnomads(client, term)` — `_get_json(client,
    "https://www.workingnomads.com/api/exposed_jobs")` → list
  - Add to `_DEFAULT_SOURCES` (thus `_SOURCE_NAMES`) and `_run_source` dispatch
  - sources.yaml: add `workingnomads` to remote_boards `sources`
  Verify: new parser test + extended aggregate test pass
  Depends on: nothing
  Status: [x] Done — parse/fetch/dispatch added; config lists workingnomads

Task 3: Test coverage
  File: `tests/test_remote_boards.py`
  - `test_workingnomads_parses`: 2-item payload; assert title/company/location,
    HTML-stripped description, is_remote, url, site
  - extend `test_search_aggregates_and_stores`: add workingnomads payload +
    `_fetch_workingnomads` patch; expected found/stored 6 → 7
  Verify: `pytest tests/test_remote_boards.py` green
  Depends on: Task 2
  Status: [x] Done — 20 passed across remote_boards/adzuna/registry

Task 4: Verification + commit
  Verify: `uv run ruff check src tests` clean; `uv run pytest -q` full suite
  green (expect 667: 666 baseline + 1 new parser test); live smoke of Working
  Nomads fetch optional (network)
  Commit: `feat: enable adzuna and add working nomads board (provider coverage)`
  Status: [x] Done — ruff clean; full suite 667 passed (666 + 1 new test;
          aggregate test extended in place); Working Nomads feed verified live
          (200, 44 items) during planning

## Verification

```bash
uv run ruff check src tests
uv run pytest -q
uv run pytest tests/test_remote_boards.py tests/test_adzuna_provider.py
```

Manual: run `joborion search` (or the sources tool) with and without
ADZUNA_APP_ID/KEY set — with keys absent adzuna must be skipped, not fail.
Status: [x] DONE — full suite green, ruff clean, provider list verified above

## Critical Review

1. Scope creep? Adding a single verified board + flipping an existing flag.
   Other candidates (Remote.co) were checked and rejected on availability.
2. Missing tasks? No new credentials, no schema change, no CLI change.
3. Wrong order? adzuna enablement is independent of the board work.
4. Over-engineered? Follows the exact existing board pattern (parse/fetch/
   dispatch/tests) — no new abstractions.
5. Testable? Parser + aggregate tests are network-free; config flip verified by
   full suite + manual smoke.
