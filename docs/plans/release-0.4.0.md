# Release 0.4.0

## Goal

Bump the version to `0.4.0` and finalize the CHANGELOG so the last four
feature releases (provider coverage, reporting analytics, post-run automation,
multi-profile isolation, legacy provider view) ship under one version tag.

## Facts Established

- Version is declared in two places plus one fallback string:
  `pyproject.toml:3`, `src/joborion/__init__.py:3`, and a hard-coded fallback
  `"0.3.0"` in `ui.py:114` (`_get_version` uses it only if the package import
  fails — keep it in sync to avoid drift).
- `CHANGELOG.md` has an `## Unreleased` section ready to promote to `0.4.0`.
- No release tooling (no bump2version/hatch); manual three-point edit.

## File Surface

Files to modify:
- `pyproject.toml` — `version = "0.4.0"`
- `src/joborion/__init__.py` — `__version__ = "0.4.0"`
- `src/joborion/ui.py` — fallback string to `"0.4.0"`
- `CHANGELOG.md` — promote Unreleased to `## [0.4.0] - <date>`

## Tasks

Task 1: Version bump
  Files: `pyproject.toml`, `src/joborion/__init__.py`, `src/joborion/ui.py`
  Verify: `uv run joborion --version` prints v0.4.0
  Depends on: nothing
  Status: [x] Done

Task 2: CHANGELOG promote
  File: `CHANGELOG.md`
  - Replace `## Unreleased` with `## [0.4.0] - 2026-08-08`
  - Add a fresh empty `## Unreleased` section at the top
  Verify: file renders as valid markdown
  Depends on: Task 1
  Status: [x] Done

Task 3: Verification + commit
  Verify: `uv run pytest tests/test_docs.py -q` green; `uv run joborion
  --version` now prints v0.4.0 (also fixed `print_banner`, which previously
  omitted the version entirely); full suite 724 passed; ruff clean
  Commit: `chore: release 0.4.0`
  Note: do NOT tag or publish — confirm with the user first
  Status: [x] Done

## Verification

```bash
uv run joborion --version
uv run ruff check src/joborion/ui.py
uv run pytest tests/test_docs.py -q
```

## Critical Review

1. Scope creep? No README version string exists, no tag, no PyPI — those are
   explicitly deferred to a user decision.
2. Missing tasks? `docs/marketing/` untouched and untracked.
3. Wrong order? Version first, then CHANGELOG, then verify.
4. Over-engineered? Three one-line edits + a changelog heading.
5. Testable? `--version` output is the acceptance proof.

