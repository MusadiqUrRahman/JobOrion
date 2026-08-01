# Plan: Global Search Modes + Profile-Driven Eligibility

## Step 1: Goal

User can configure JobOrion to search in any of 4 modes —
`remote`, `local`, `sponsorship`, `all` — via `searches.yaml` or
`joborion run search --mode <mode>`. Eligibility is decided by the
candidate's profile (country, work authorization, sponsorship need,
relocation willingness), every rejected job carries a structured
`rejection_reason` + human-readable `suggestion`, and the whole thing
works for users in any country with zero code changes.

Observable outcomes:
- `joborion run search --mode remote` stores only remote jobs.
- `joborion run search --mode local` searches the candidate's home country.
- `joborion run search --mode sponsorship` keeps international/remote jobs
  the candidate could take (relocation willing / authorized).
- `joborion run search --mode all` searches everything, eligibility applies
  at evaluate + apply.
- `joborion jobs --stage scored` shows a Rejection + Suggestion column for
  ineligible jobs.
- Apply location check uses profile-driven rules, not hardcoded cities.

## Step 2: File Surface

### Files to CREATE
- `src/joborion/eligibility.py` — pure eligibility engine (no LLM, no I/O):
  `classify_location()`, `EligibilityResult`, `evaluate_job()`,
  `constraints_from_profile()`. Single source of truth for the country map,
  remote words, and rules.
- `tests/test_eligibility.py` — unit tests for the engine.

### Files to MODIFY
- `src/joborion/scoring/fit_scorer.py` — delete local `_REMOTE_WORDS`,
  `_COMMON_COUNTRIES`, `_location_country`, `_prefilter_ineligible`;
  import from `eligibility`; `score_job()` uses `evaluate_job()` and
  returns reason/suggestion; `score_jobs()` writes `rejection_reason` +
  `rejection_suggestion` columns.
- `src/joborion/database.py` — add `rejection_reason TEXT` and
  `rejection_suggestion TEXT` to jobs CREATE TABLE + `ensure_columns()`.
- `src/joborion/discovery/jobspy.py` — `_full_crawl()` reads
  `defaults.search_mode`; `scrape_jobspy(cfg, mode=None)` override;
  mode-aware search-combination builder + post-filter.
- `src/joborion/pipeline.py` — `_run_discovery_stage(workers, mode=None)`,
  thread `mode` through `run_pipeline()` → `_run_sequential` /
  `_run_streaming` → discovery stage.
- `src/joborion/cli.py` — `run` command gains `--mode` option
  (values remote/local/sponsorship/all, default from searches.yaml);
  passes it into `run_pipeline`.
- `src/joborion/apply/prompt.py` — `_build_location_check()` rewritten to
  produce profile/mode-driven decision rules + structured reasons/suggestions
  (still emits `RESULT:FAILED:not_eligible_location`).
- `src/joborion/apply/runner.py` — `mark_result()` stores
  `rejection_reason`/`rejection_suggestion`; add reason→suggestion map for
  permanent failures.
- `src/joborion/wizard/init.py` — `_setup_profile()` asks authorized
  countries + relocation willingness; `_setup_searches()` asks search mode.
- `src/joborion/config/searches.example.yaml` — document `search_mode` +
  new profile fields.
- `src/joborion/ui.py` — `make_jobs_table()` optionally shows
  rejection/suggestion columns.
- `tests/test_config.py` — search_mode default parsing.
- `tests/test_pipeline_e2e.py` — mode threading smoke test (if cheap).

## Step 3: Tasks

### Task 1 — Eligibility engine module
- **File:** `src/joborion/eligibility.py` (NEW)
- Move `_REMOTE_WORDS`, `_COMMON_COUNTRIES`, `_location_country` here as
  `REMOTE_WORDS`, `COMMON_COUNTRIES`, `location_country()`.
- `classify_location(location) -> dict` → `{is_remote, country, has_country}`.
- `EligibilityResult` dataclass: `eligible: bool`, `reason: str | None`,
  `suggestion: str | None`.
- `constraints_from_profile(profile) -> dict` — home country, authorized
  countries list, sponsorship_needed bool, relocation_willing bool.
- `evaluate_job(job, profile, mode="all") -> EligibilityResult` with rules:

  | Mode | Non-remote rule | Remote (unrestricted) | Remote (country-restricted) |
  |------|-----------------|------------------------|------------------------------|
  | remote | reject `not_remote` | eligible | eligible if authorized/relocatable else reject |
  | local | eligible only in home country | eligible | reject unless home country |
  | sponsorship | eligible if relocation_willing OR authorized | eligible | eligible if relocation_willing OR authorized |
  | all | reject if foreign AND needs sponsorship AND not willing to relocate | eligible | reject if foreign AND needs sponsorship AND not authorized |

- Every rejection produces `reason` (stable code: `not_remote`,
  `not_eligible_location`, `requires_sponsorship`, `country_restricted`)
  and a `suggestion` (actionable, e.g. "Switch to --mode sponsorship to
  include international roles you're willing to relocate for.").
- **Test:** `tests/test_eligibility.py` — matrix across modes × location
  shapes for a Pakistan profile (sponsorship needed) + a US-citizen profile.
- **Depends on:** nothing.

### Task 2 — DB columns for rejection + suggestion
- **Files:** `src/joborion/database.py`
- Add to `CREATE TABLE IF NOT EXISTS jobs` and to `ensure_columns()`
  map: `rejection_reason TEXT`, `rejection_suggestion TEXT`.
- **Test:** `tests/test_database.py` — columns present after `init_db()`
  and `ensure_columns()` on an old DB.
- **Depends on:** nothing (can parallelize with Task 1).

### Task 3 — Refactor fit_scorer onto eligibility engine
- **Files:** `src/joborion/scoring/fit_scorer.py`
- Delete local constants + `_prefilter_ineligible`. `_candidate_constraints()`
  → build via `constraints_from_profile(profile)`.
- `score_job()`: call `evaluate_job(job, profile, mode)`; on ineligible,
  return `score: 1` + `reason` + `suggestion` (kept in `reasoning` too).
- `score_jobs()`: UPDATE also sets `rejection_reason = ?`,
  `rejection_suggestion = ?`.
- **Test:** `tests/test_eligibility.py` (pure engine) + manual
  `pytest tests/test_tools_integration.py` to catch scorer regressions.
- **Depends on:** Tasks 1, 2.

### Task 4 — search_mode in discovery
- **Files:** `src/joborion/discovery/jobspy.py`
- `_full_crawl()` reads `mode = defaults.get("search_mode", "all")`.
- Build search combinations per mode:
  - `remote`: locations → [{location: "worldwide", remote: true}];
    post-filter `_keep_remote_only()`.
  - `local`: locations → [candidate country via profile]; `country_indeed`
    forced to profile country; remote allowed only if config says so.
  - `sponsorship`: keep config locations but widen `location_accept` to
    include international markers; no remote-only post-filter.
  - `all`: current behavior.
- `scrape_jobspy(cfg=None, mode=None)` — CLI override wins over config.
- **Test:** unit test the search-combination builder for each mode.
- **Depends on:** Task 1 (uses `constraints_from_profile` for local country).

### Task 5 — thread mode through pipeline + CLI
- **Files:** `src/joborion/pipeline.py`, `src/joborion/cli.py`
- `run_pipeline(..., mode=None)` → `_run_discovery_stage(mode)` →
  `scrape_jobspy(mode=mode)`.
- CLI: `mode: Optional[str] = typer.Option(None, "--mode")`, validate
  against 4 values, pass through.
- **Test:** `pytest tests/test_pipeline_e2e.py` (existing smoke tests still
  green); manual `joborion run search --dry-run`.
- **Depends on:** Task 4.

### Task 6 — profile-driven apply location check
- **Files:** `src/joborion/apply/prompt.py`
- Rewrite `_build_location_check(profile, search_config)`: derive the
  decision tree from `constraints_from_profile` + current `search_mode`
  instead of hardcoded city list. Include relocation/sponsorship-aware
  branches and suggested reason codes.
- **Test:** `tests/test_config.py` or new focused unit test asserting the
  emitted text contains profile-derived country + mode keywords.
- **Depends on:** Task 1.

### Task 7 — rejection reason + suggestion surfaced on apply
- **Files:** `src/joborion/apply/runner.py`
- `mark_result()`: when failing, accept optional `reason`/`suggestion`
  params and write them to the new columns.
- Add `PERMANENT_FAILURE_SUGGESTIONS` map for known codes
  (`not_eligible_location`, `blocked_by_waf_embargo`, etc.).
- **Test:** `tests/test_pipeline_e2e.py` or manual `--mark-failed`.
- **Depends on:** Task 2.

### Task 8 — wizard + examples + UI
- **Files:** `src/joborion/wizard/init.py`,
  `src/joborion/config/searches.example.yaml`, `src/joborion/ui.py`
- `_setup_profile()`: ask "Countries you're authorized to work in" +
  "Willing to relocate for a job?" → write to profile.
- `_setup_searches()`: ask "Search mode?" (remote/local/sponsorship/all).
- Example YAML: document `search_mode` + `authorized_countries` +
  `relocation_willing`.
- `make_jobs_table()`: add rejection + suggestion columns when jobs have
  non-null `rejection_reason`.
- **Test:** `pytest tests/test_config.py`.
- **Depends on:** Tasks 1, 2.

## Step 4: Verification

Per-task:
```bash
pytest tests/test_eligibility.py -v
pytest tests/test_database.py -v
pytest tests/test_config.py -v
pytest tests/test_tools_integration.py -v
pytest tests/test_pipeline_e2e.py -v
```

Full suite:
```bash
uv run ruff check src/joborion/eligibility.py src/joborion/scoring/fit_scorer.py src/joborion/database.py src/joborion/discovery/jobspy.py src/joborion/pipeline.py src/joborion/cli.py src/joborion/apply/prompt.py src/joborion/apply/runner.py src/joborion/wizard/init.py src/joborion/ui.py
uv run pytest tests/ -q
```

Manual:
```bash
joborion run search --mode remote --dry-run
joborion run search --mode local --dry-run
joborion jobs --stage scored -l 5
```

## Step 5: Critical Review

1. **Scope creep?** No — everything listed serves the user's stated feature
   (modes, profile eligibility, reasons/suggestions, generic by design).
2. **Missing tasks?** Config default handling covered in Task 4; old DBs
   covered in Task 2 via `ensure_columns()`.
3. **Wrong order?** Tasks 1 and 2 are independent; 3–8 depend on them.
4. **Over-engineered?** The eligibility engine is pure functions +
   dataclass, no framework, mirrors existing `_prefilter_ineligible`
   behavior — the minimal way to make rules reusable across scorer + apply.
5. **Testable?** Every task has a verification command; the engine matrix
   is the core risk and is covered first.
