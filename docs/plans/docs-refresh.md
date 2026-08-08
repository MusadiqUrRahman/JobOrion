# Documentation Refresh

## Goal

Users can discover every shipped feature from the README — `report` analytics,
the `--notify`/`--report` automation flags, multi-profile isolation, and the
job-board providers — and the repo gains a CHANGELOG plus a drift-guard test
that fails if a documented command/flag ever diverges from the real CLI.

## Facts Established

- README is 3KB and predates the last 4 feature commits: it documents none of
  `report`, `--notify`/`--report`, `--profile` / `profile create|list`,
  `JOBORION_PROFILE`, or the boards (adzuna, working nomads).
- Real CLI surface (verified via `--help`):
  - `joborion run [stages]...` flags incl. `--schedule`, `--notify`, `--report`
  - `joborion report [--days 30] [--top 10] [--json]` (read-only, no LLM)
  - `joborion daemon [--interval] [--at] [--notify] [--report]`
  - `joborion notify` (email digest), `joborion reflect [--last|--run-id]`
  - Global callback option `--profile <name>`; `JOBORION_PROFILE` env fallback
  - `joborion profile list` / `joborion profile create <name>`
- Boards (sources.yaml): jobspy, workday, adzuna (needs `ADZUNA_APP_ID` +
  `ADZUNA_APP_KEY`, skips gracefully), remote_boards (remotive, remoteok, wwr,
  jobicy, arbeitnow, workingnomads, hn), ats_boards, ai_sites.
- README docs are user-facing and must not duplicate the full `--help` output;
  keep the file concise (aim ~7-9KB).
- Commit messages: `docs:` type. `docs/marketing/` stays untracked.

## File Surface

Files to modify:
- `README.md` — new Analytics, Profiles, and Job Boards content; refresh the
  command list and the `~/.joborion/` config tree

Files to create:
- `CHANGELOG.md` — "Unreleased" section listing delivered features
- `tests/test_docs.py` — drift guard: every README example references a real
  command, and documented key flags are declared

## Tasks

Task 1: README command coverage
  File: `README.md`
  - "All Commands": add `joborion report`, `joborion reflect`,
    `joborion notify`, `joborion profile create <name>`, `joborion profile list`
  - "Pipeline" section: document `--schedule`, `--notify`, `--report` on
    `joborion run`; note they also exist on `daemon`
  - New "Analytics & Reporting" subsection: `report [--days 30] [--top 10]
    [--json]` is read-only and needs no LLM; `--notify` emails a digest after a
    run; `notify` sends on demand
  Verify: `uv run joborion --help` lines match the README text
  Depends on: nothing
  Status: [x] Done

Task 2: README Profiles + Configuration + Boards
  File: `README.md`
  - New "Profiles / Workspaces" section: `--profile <name>` prefix on any
    command, `JOBORION_PROFILE` env fallback, `profile create/list`, data lives
    in `~/.joborion/profiles/<name>/`
  - Update the config tree to show `profiles/<name>/` layout
  - New "Job Boards" note under Configuration: boards run from
    `sources.yaml`; adzuna needs `ADZUNA_APP_ID`/`ADZUNA_APP_KEY` in `~/.joborion/.env`
    and skips gracefully when absent; list the remote boards
  Verify: README text matches sources.yaml contents
  Depends on: Task 1
  Status: [x] Done

Task 3: CHANGELOG
  File: `CHANGELOG.md` (NEW)
  - "Unreleased" section with entries: multi-profile isolation, post-run
    notify/report flags, `report` analytics command, provider coverage
    (adzuna + working nomads board)
  Verify: renders as valid markdown
  Depends on: nothing
  Status: [x] Done

Task 4: Drift-guard test
  File: `tests/test_docs.py` (NEW)
  - For every README line starting with `joborion`, at least one whitespace
    token matches a known command name (from `app.registered_commands` +
    `profile` sub-app + the `profile_app.registered_commands`)
  - Key documented flags are declared: `run` → `--notify`, `--report`,
    `--schedule`; `daemon` → `--notify`, `--report`; `report` → `--days`,
    `--top`, `--json` (via the `cli_flags` fixture)
  Verify: `uv run pytest tests/test_docs.py` green
  Depends on: Task 1
  Status: [x] Done

Task 5: Verification + commit
  Verify: `uv run ruff check src tests` clean; full `uv run pytest -q` green
  (713 + 6 new = 719 passed); README examples validated against the live CLI
  by the drift-guard test
  Commit: `docs: document analytics, automation flags, and profiles`
  Status: [x] Done

## Verification

```bash
uv run ruff check src tests
uv run pytest tests/test_docs.py -v
uv run pytest -q
uv run joborion report --help
uv run joborion profile --help
```

## Critical Review

1. Scope creep? No version bump (that belongs to a release task), no
   rewriting of install/quick-start content.
2. Missing tasks? Board list verified from sources.yaml; profiles path tree
   matches `config.py` `_rebind_profile_paths`.
3. Wrong order? Commands → config/boards → changelog → test.
4. Over-engineered? Drift guard is ~30 lines and only checks README examples
   reference real commands + key flags.
5. Testable? Task 4 is the explicit verification; docs are checked against
   live `--help` output.

