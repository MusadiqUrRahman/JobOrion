# Multi-Profile Workspace Isolation

## Goal

`joborion --profile <name> <command>` runs any command against an isolated
workspace under `~/.joborion/profiles/<name>/` — its own `joborion.db`,
`profile.json`, `resume.*`, `searches.yaml`, `preferences.yaml`, tailored/
cover-letter output, and logs. `joborion profile create <name>` sets one up.
Without `--profile`, behavior is exactly as today (data in `~/.joborion/`).

## Facts Established

- `config.py` defines `APP_DIR` (from `JOBORION_DIR`) and all paths as
  module-level constants (`DB_PATH`, `PROFILE_PATH`, `RESUME_PATH`,
  `RESUME_PDF_PATH`, `SEARCH_CONFIG_PATH`, `PREFERENCES_PATH`, `ENV_PATH`,
  `TAILORED_DIR`, `COVER_LETTER_DIR`, `LOG_DIR`, `CHROME_WORKER_DIR`,
  `APPLY_WORKER_DIR`).
- Every consumer module is imported lazily inside CLI command bodies (see
  cli.py:55-56, 95, 198, 250, 406, 644, ...) — only `joborion.ui` is imported
  at cli.py module level, and `ui.py` imports no joborion modules at module
  level. So the Typer callback (cli.py:73) runs `set_profile()` before any
  consumer module is first imported.
- Existing tests patch module-level names, e.g.
  `patch("joborion.scoring.fit_scorer.RESUME_PATH", ...)`,
  `patch("joborion.database.DB_PATH", ...)` (test_pipeline_e2e.py:177-202,
  test_tools_integration.py:57-62). This forces us to KEEP the module-level
  constant imports in those modules.
- Tests that invoke the CLI in-process (CliRunner) will persist a
  `set_profile()` rebind across tests → new test module needs an autouse
  reset fixture.
- `joborion --profile foo ...` requires the option on the Typer callback
  (must precede the subcommand); `JOBORION_PROFILE` env var is the
  non-flag fallback.

## Design

Rebind-on-set: `config.set_profile(name)` validates `name`, then REBINDS the
module-level path constants to `APP_DIR / "profiles" / name / ...`. Because
consumers import lazily (after the callback), they pick up the rebound
values at first import. `set_profile(None)` restores defaults. `APP_DIR`
itself never rebinds (it is the base). No changes to `database.py`, scoring,
wizard, dashboard, pipeline, or notifier.

## File Surface

Files to modify:
- `src/joborion/config.py` — profile state, `set_profile`, `get_profile`,
  `get_profile_dir`, `_rebind_profile_paths`, `list_profiles`, name
  validation
- `src/joborion/cli.py` — `--profile` option + env fallback on the `main`
  callback; new `profile` Typer sub-app (`list`, `create`); `open` opens the
  active profile dir when one is set

Files to create:
- `tests/test_profile.py` — config + CLI tests with autouse reset fixture

## Tasks

Task 1: config.py profile state
  File: `src/joborion/config.py`
  - `_ACTIVE_PROFILE: str | None = None`
  - `_PROFILE_NAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,63})$")`
  - `get_profile() -> str | None`
  - `get_profile_dir() -> Path` — `APP_DIR / "profiles" / _ACTIVE_PROFILE`
    when set, else `APP_DIR`
  - `_rebind_profile_paths()` — reassigns all 12 path globals from
    `get_profile_dir()`
  - `set_profile(name: str | None)` — `None` resets; else validate against
    the regex (reject empty, `.`, `..`, `/`, `\`, NUL) or raise `ValueError`,
    then set `_ACTIVE_PROFILE` and rebind
  - `list_profiles() -> list[str]` — sorted subdirectory names of
    `APP_DIR / "profiles"`, always including the implicit default
  Verify: `uv run python -c "from joborion.config import set_profile, get_db..."`
  — path tests (Task 2)
  Depends on: nothing
  Status: [x] Done

Task 2: config tests
  File: `tests/test_profile.py`
  - `set_profile("a")` → `DB_PATH` == `APP_DIR/profiles/a/joborion.db`,
    `RESUME_PATH`, `TAILORED_DIR` similarly nested
  - `set_profile(None)` restores `APP_DIR/joborion.db` defaults
  - `get_profile_dir()` with/without profile
  - invalid names raise `ValueError`: "", ".", "..", "../x", "a/b", "a\\b"
  - `list_profiles()` includes created names + "default"
  Verify: `uv run pytest tests/test_profile.py::TestConfigProfile` green
  Depends on: Task 1
  Status: [x] Done

Task 3: cli.py callback `--profile`
  File: `src/joborion/cli.py`
  - `main(profile: Optional[str] = typer.Option(None, "--profile", help="Run
    in an isolated workspace profile."))` — before the existing
    load_env/ensure_dirs/init_db block: resolve
    `profile or os.environ.get("JOBORION_PROFILE")`, call
    `config.set_profile(name)`, catch `ValueError` → `print_error` +
    `raise typer.Exit(code=1)`.
  - Keep `--version` behavior (returns before bootstrap).
  Verify: `--profile` in `cli_flags["main"]`; `joborion --profile bad..x
  status` exits non-zero with error
  Depends on: Task 1
  Status: [x] Done

Task 4: cli.py `profile` sub-app
  File: `src/joborion/cli.py`
  - `profile_app = typer.Typer(name="profile", help=...)` added via
    `app.add_typer(profile_app, name="profile")`
  - `profile list`: print `list_profiles()` (mark active via `get_profile()`)
  - `profile create <name>`: `set_profile(name)` (validates), `ensure_dirs()`
    (creates profile dir + subdirs), print success + hint to run
    `joborion --profile <name> init`
  - `open` (cli.py:875): open `get_profile_dir()` instead of `APP_DIR`
  Verify: `uv run joborion profile list` and `create` work on a temp
  `JOBORION_DIR`; cli_flags via `profile_app.registered_commands`
  Depends on: Task 3
  Status: [x] Done

Task 5: CLI tests
  File: `tests/test_profile.py`
  - autouse fixture: monkeypatch `joborion.config.APP_DIR` to `tmp_path`;
    `yield`; `config.set_profile(None)`
  - `profile create a` → `tmp_path/profiles/a/joborion.db` parent + subdirs
    created, exit 0
  - `profile create` again → idempotent, exit 0
  - `profile list` → contains "a" and "default"
  - `--profile a status` → `tmp_path/profiles/a/joborion.db` exists and
    `tmp_path/joborion.db` does NOT (isolation), exit 0
  - `status` (no flag) → `tmp_path/joborion.db` created (default path), exit 0
  - `--profile ../evil status` → non-zero exit + error message
  - `--profile` present in `cli_flags["main"]`
  Verify: `uv run pytest tests/test_profile.py` green
  Depends on: Task 4
  Status: [x] Done

Task 6: Verification + commit
  Verify: `uv run ruff check src tests` clean; full `uv run pytest -q` green
  (692 + 21 new = 713 passed); live smoke on the real data dir confirmed
  `--profile smoke status` created `~/.joborion/profiles/smoke/joborion.db`
  while default `status` still read `~/.joborion/joborion.db`; smoke profile
  removed afterward
  Commit: `feat: multi-profile workspace isolation via --profile`
  Status: [x] Done

## Verification

```bash
uv run ruff check src tests
uv run pytest tests/test_profile.py -v
uv run pytest -q
uv run joborion profile list
uv run joborion profile create smoke
uv run joborion --profile smoke status
uv run joborion status
```

## Critical Review

1. Scope creep? No new persistence state, no data migration, no deletion
   command (user data safety). Only path resolution + CLI flags.
2. Missing tasks? Concurrent access / locking is out of scope (profiles are
   separate SQLite files, same guarantees as today). Env keys (`.env`) are
   per-profile; users copy keys per profile if needed — documented in the
   create hint.
3. Wrong order? config state → tests → CLI wiring → sub-app → CLI tests.
4. Over-engineered? Rebind-on-set avoids touching 7 modules and keeps every
   existing test patch pattern working; ~40 lines in config.py.
5. Testable? Every task has an explicit verification; isolation proven by
   asserting the profile DB exists while the default DB does not.

