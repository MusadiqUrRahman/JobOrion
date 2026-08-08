# Release Automation: Tag v0.4.0 + GitHub Release Workflow

## Goal

Close out the 0.4.0 release: tag the shipped commit and add a CI workflow
that, on every `v*` tag push, builds the package and attaches the wheel +
sdist to a GitHub Release. Users install via the release asset or the git URL.

## Facts Established

- Last release commit is `d73beec` (already pushed, tree clean except
  untracked `docs/marketing/`).
- Existing CI is `.github/workflows/ci.yml` using `astral-sh/setup-uv@v6` +
  `uv sync --extra dev`.
- **PyPI is blocked:** `pyproject.toml:29` declares
  `python-jobspy @ git+https://github.com/speedyapply/JobSpy.git`, and PyPI
  rejects packages whose dependencies are direct VCS references. A PyPI
  publish would fail at upload. GitHub Releases have no such restriction.
- `pyproject.toml` already has hatchling build config (`[tool.hatch.build]
  artifacts = ["src/joborion/config/*.yaml"]`) so `uv build` produces a
  working wheel/sdist.
- `uv.lock` already pins 0.4.0.

## Design

- Tag `v0.4.0` on `d73beec` (annotated, never amend later).
- New `.github/workflows/publish.yml`: triggered by `push: tags: ['v*']`,
  runs `uv build`, and publishes a GitHub Release with the assets using
  `softprops/action-gh-release@v2` (needs `permissions: contents: write`).
- Dev sidecar: `gh release create v0.4.0` is NOT done by the workflow here —
  the workflow creates the release from the tag automatically.
- Deferred (documented in plan, not implemented): making `python-jobspy` an
  optional extra would unblock real PyPI publishing later.

## File Surface

Files to create:
- `.github/workflows/publish.yml`

Files to modify:
- none (tag is a git ref, not a file)

## Tasks

Task 1: Publish workflow
  File: `.github/workflows/publish.yml`
  - `on.push.tags: ["v*"]`
  - `permissions: contents: write`
  - `astral-sh/setup-uv@v6` (python 3.12), `uv sync --extra dev`
  - `uv build` → `dist/*`
  - `softprops/action-gh-release@v2` with `files: dist/*`
  Verify: YAML parses; matches ci.yml conventions (same setup-uv version,
  timeout-minutes)
  Depends on: nothing
  Status: [ ] Pending

Task 2: Tag v0.4.0
  Run: `git tag -a v0.4.0 -m "JobOrion 0.4.0"` (on current HEAD `d73beec`)
  Verify: `git tag` lists it; `git show v0.4.0 --oneline -s` shows the message
  Depends on: nothing
  Status: [ ] Pending

Task 3: Verification + push
  Verify: `uv build` succeeds locally (wheel + sdist produced, config YAMLs
  included); ruff clean (workflow YAML not linted, but sanity-checked);
  `git status` clean aside from `docs/marketing/`
  Push: tag with the push — `git push origin main v0.4.0`
  Note: do NOT publish to PyPI (blocked by git dependency); GitHub Action
  runs only after the push lands on `main` + tag
  Status: [ ] Pending

## Verification

```bash
uv build
git tag -a v0.4.0 -m "JobOrion 0.4.0"
git push origin main v0.4.0
git show v0.4.0 --oneline -s
```

## Critical Review

1. Scope creep? No PyPI attempt (blocked), no optional-extra refactor — both
   explicitly deferred.
2. Missing tasks? Workflow `permissions` (needed for release upload) is
   included; sdist/wheel both built by `uv build`.
3. Wrong order? Workflow before tag so the push is atomic-ish.
4. Over-engineered? Two steps: one workflow file + one tag.
5. Testable? `uv build` is the local acceptance proof; the release trigger is
   GitHub-side (runs on the push).
