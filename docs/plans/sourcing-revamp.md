# Sourcing Revamp — Complete Plan & Roadmap

Status: IN PROGRESS — Phase A COMPLETE (2026-08-03); Phase B next
Date: 2026-08-03
Supersedes: `docs/ROADMAP.md` (kept for history) — replace its content when this plan is approved.

---

## 0. Goal

The user uploads a CV / answers a short profile, the system asks a few preference
questions, and then sources the highest-quality, most relevant jobs from as many
reliable worldwide sources as possible — **automatically improving its own
relevance over time** so every recommendation matches the user's skills,
experience, field, location, and priorities.

Observable outcome after this plan is complete:

> A new user runs `joborion run search`, is asked 4 quick questions
> (arrangement / locations / job types / other preferences), and JobOrion then
> searches JobSpy boards, Adzuna, remote-first boards, and company ATS boards
> (Greenhouse/Lever/Ashby/SmartRecruiters/Workday), returning only jobs that
> match their profile and preferences — and each run gets more relevant than the
> last with no config edits.

---

## 1. Current State (facts, verified)

| Area | Today |
|------|-------|
| Search config | Static `~/.joborion/searches.yaml` (3 queries, hardcoded) |
| Profile use | `profile.json` has `target_role`, `skills_boundary` — **never used for sourcing** |
| Interactive setup | `joborion init` wizard exists; `target_role` defaults to empty; no preference questions before search |
| Providers | 3 hardcoded adapters: JobSpy (indeed/linkedin/bayt), Workday (48 Canada employers), AI-scraper (sites.yaml) |
| Filtering | Keyword check only: location text must contain "remote"/"worldwide" (jobspy.py:102) |
| Why Bangkok jobs pass | `location: worldwide` + remote-only → any listing whose text contains "Remote" passes, including Thailand-remote roles (Salesforce/NVIDIA, verified in DB) |
| Source learning | `site_memory` table exists; reflector (Phase 4) in progress; **nothing feeds back into sourcing** |
| LLM | Gemini (free) + OpenRouter failover; Gemini quota exhausted today (`limit: 0`) |
| Known failures | Bayt 403 always; Netflix/ServiceNow/DocuSign/Uber 422 (Workday API params); Eluta CAPTCHA; CareerJet timeout |

Gaps the plan closes: (1) no preference-driven search, (2) profile ignored by
sourcing, (3) only 3 adapters, (4) crude filter admits irrelevant jobs,
(5) no feedback loop, (6) Canada-centric employer list, (7) no structured job
fields (salary/job_type/seniority/is_remote) for scoring.

---

## 2. The User Workflow (the core request)

```
joborion run search
  1. If ~/.joborion/preferences.yaml missing → run interactive questionnaire
  2. Load profile.json (CV facts: target_role, skills, country)
  3. Build search intents = profile queries × preference filters
  4. Run all enabled providers (parallel, reliability-ordered)
  5. Normalize + relevance-filter every raw job (no LLM for filtering)
  6. Store passing jobs with structured fields
  7. Record per-provider metrics (feeding the learning loop)
  8. Report: found / passed / filtered by reason
```

### 2.1 The Questionnaire (4 questions, rich-select)

```text
Q1. Work arrangement?          Remote | Hybrid | On-site | All
Q2. Locations?                 multi-select or free text:
                               e.g. Worldwide, United States, Pakistan, Germany
                               (Hybrid/On-site require concrete places;
                                Remote implies Worldwide unless restricted)
Q3. Job types?                 Full-time | Part-time | Contract | Internship | All
Q4. Other preferences:         minimum salary (USD/year), seniority levels
                               (Entry/Mid/Senior/Lead), need visa sponsorship?
                               preferred industries?
```

Behavior:
- `Remote` → `arrangement=remote` → all providers pass `is_remote=True`, filter
  requires remote, sources default to worldwide.
- `All` → no arrangement restriction → every relevant job from every source.
- Defaults cached in `preferences.yaml`; next run re-prompts but pre-fills last
  answers (one Enter each). `--no-ask` skips the prompt entirely; `--ask` forces it.
- Answers can also be given as flags for scripting:
  `joborion run search --arrangement remote --locations "US,GB" --job-type fulltime --min-salary 60000`.

### 2.2 Preference Model

```yaml
# ~/.joborion/preferences.yaml  (written by the questionnaire)
arrangement: remote            # remote | hybrid | onsite | all
locations: ["worldwide"]       # worldwide OR list of countries/cities/regions
job_types: ["fulltime"]        # fulltime | parttime | contract | internship
min_salary: 60000              # USD annual, optional
seniority: ["mid", "senior"]   # entry | mid | senior | lead | staff
sponsorship_ok: true           # user willing to take sponsorship / relocation
industries: ["software", "ai", "finance"]
```

Backward compatibility: `searches.yaml` still works. If both exist, preferences
win; `joborion configure` migrates old `search_mode` into `arrangement`.

---

## 3. Architecture

### 3.1 New modules

```
src/joborion/
  sourcing/                      # NEW package: the heart of the revamp
    intent.py                    # profile+preferences -> SearchIntent(s)
    normalize.py                 # raw job -> structured fields (no LLM)
    filter.py                    # relevance gate: arrangement/location/type/
                                 # salary/seniority/title
    learning.py                  # source_metrics + provider ranking + pruning
    query_evolution.py           # LLM query expansion from top-fit jobs
  sources/                       # NEW package: provider layer
    base.py                      # JobProvider protocol + RawJob schema
    registry.py                  # load sources.yaml, order by reliability
    jobspy_provider.py           # wraps discovery/jobspy.py (+ job_type etc.)
    workday_provider.py          # wraps discovery/workday.py (profile-driven)
    adzuna_provider.py           # NEW: Adzuna API (free key)
    remote_boards.py             # NEW: Remotive, RemoteOK, WeWorkRemotely(RSS),
                                 # Jobicy, Arbeitnow, HN Who-is-Hiring
    ats_boards.py                # NEW: Greenhouse, Lever, Ashby, SmartRecruiters
    ai_site_provider.py          # wraps discovery/ai_scraper.py (best-effort)
  wizard/
    preferences.py               # NEW: the 4-question interactive wizard
```

### 3.2 Config files

```
src/joborion/config/
  sources.yaml       # NEW: provider enable/disable, API-key env refs, limits
  companies.yaml     # NEW: company -> platform(slug) + industry + tags + region
                     #      (curated 100+ global + remote-friendly companies)
  employers.yaml     # KEEP (Workday) — migrate entries into companies.yaml later
  sites.yaml         # KEEP (AI-scraper registry) — mark Canada sites as region
```

`~/.joborion/preferences.yaml` — user preferences (written by wizard).

### 3.3 DB additions (via `ensure_columns()`, add-only)

```sql
jobs:   is_remote, country, city, job_type, seniority, salary_min, salary_max,
        salary_currency, salary_interval, source_provider, apply_url_direct, posted_at
        (index on provider, is_remote, fit_score)
source_metrics: provider, run_at, jobs_found, jobs_passed, jobs_scored,
        avg_fit_score, applied, rejected, errors, latency_ms, consecutive_failures
query_history: query, tier, provider, run_at, found, passed, avg_fit_score
user_feedback: job_url, verdict (liked/disliked), reason, created_at
```

### 3.4 Data flow

```
preferences.yaml ─┐
profile.json ─────┼─> intent.py ─> SearchIntent(query, arrangement, locations,
                   │                  job_types, min_salary, seniority, ...)
searches.yaml ────┘
                     │
                     v
sources.yaml ──> registry.py (ordered by reliability)
  ├─ jobspy_provider     ──> JobSpy lib (indeed/linkedin/zip/glassdoor/google/naukri)
  ├─ adzuna_provider     ──> api.adzuna.com/v1/api/jobs/{country}/search
  ├─ remote_boards       ──> Remotive/RemoteOK/WWR RSS/Jobicy/Arbeitnow/HN(Algolia)
  ├─ ats_boards          ──> Greenhouse/Lever/Ashby/SmartRecruiters APIs
  ├─ workday_provider    ──> Workday API (companies.yaml, profile-driven)
  └─ ai_site_provider    ──> existing smart-extract (best-effort, LLM-heavy)
                     │
                     v
        RawJob(title, company, location, desc, url, apply_url,
               salary_*, job_type, is_remote, seniority, posted_at, provider)
                     │
                     v
   normalize.py + filter.py  ──> PASS (store with structured fields) / DROP (reason)
                     │
                     v
                DB (jobs)  +  source_metrics  (learning.py)
                     │
                     v
        query_evolution.py  ──> next run's intents improve
```

---

## 4. Source & API Catalog

Tier = integration type. **Free/keyless** wherever possible; each entry records
what to build in which phase.

| Source | Type | Provider module | Key | Countries/Scope |
|---|---|---|---|---|
| Indeed | board lib | jobspy_provider | none | global |
| LinkedIn | board lib | jobspy_provider | none (rate-limits, proxy help) | global |
| ZipRecruiter | board lib | jobspy_provider | none | US/CA |
| Google Jobs | board lib | jobspy_provider | none (flakey) | global |
| Glassdoor | board lib | jobspy_provider | none (rate-limits) | global |
| Bayt | board lib | jobspy_provider | none (currently 403 — keep best-effort) | MENA |
| Naukri | board lib | jobspy_provider | none | India |
| **Adzuna** | REST API | adzuna_provider | **free key** | 45+ countries, salary+contract metadata |
| **Remotive** | JSON API | remote_boards | none | remote |
| **RemoteOK** | JSON API | remote_boards | none | remote |
| **WeWorkRemotely** | RSS | remote_boards | none | remote |
| **Jobicy** | JSON API | remote_boards | none | remote (categories) |
| **Arbeitnow** | JSON API | remote_boards | none | EU + remote |
| **HN "Who is Hiring"** | Algolia API | remote_boards | none | remote/global, very high quality |
| **Greenhouse** | ATS JSON API | ats_boards | none | companies from registry |
| **Lever** | ATS JSON API | ats_boards | none | companies from registry |
| **Ashby** | ATS JSON API | ats_boards | none | companies from registry |
| **SmartRecruiters** | ATS JSON API | ats_boards | none | companies from registry |
| **Workday** | ATS API | workday_provider | none | companies from registry |
| **USAJobs** | REST API (official) | (Phase B, optional) | free key | US government |
| **Careerjet** | REST API | (Phase B, optional) | free key | global |
| Job Bank Canada | REST | (Phase B, optional) | none | Canada |
| AI-site smart extract | HTML | ai_site_provider | LLM | sites.yaml (region-tagged) |

**Why this set:** board libs give breadth; Adzuna gives structured breadth with
salary data; remote boards give high-quality remote (the user's dominant mode);
ATS APIs give **direct-on-company career-site jobs** (highest application
success, structured, no anti-bot); Workday/AI-scraper stay as best-effort.

**Company registry (`companies.yaml`)** is the secret weapon for quality: 100+
curated companies with their ATS platform (e.g. `spotify: greenhouse`,
`gitlab: greenhouse`, `stripe: lever`, `notion: ashby`, `airbnb: smartrecruiters`),
filtered by the user's `industries` + `sponsorship_ok` + region.

---

## 5. Package / Library Catalog

Current (`pyproject.toml`): typer, rich, httpx, beautifulsoup4, playwright,
python-dotenv, pyyaml, pandas, pyfiglet, python-jobspy (git), google-genai,
anthropic.

| Package | Phase | Why |
|---|---|---|
| `feedparser` | B | WeWorkRemotely + other RSS boards |
| `pycountry` | B/C | country normalization for filters |
| `rapidfuzz` | C | fuzzy title/company dedup + relevance |
| `tenacity` | B | uniform retry/backoff across all providers (already installed) |
| `lxml` | B | faster/robust HTML parsing for board scrapes |
| `orjson` | B | fast JSON for large provider responses |
| `httpx-socks` | E | proxy support for blocked boards (optional) |
| `litellm` | E | unify LLM providers + cost tracking (optional; failover already exists) |
| `apscheduler` | F | scheduled autonomous runs (Phase F) |
| `typer`/`rich` | existing | CLI + prompts (extend with `rich.prompt` multi-select) |

Keep CLI-only. No heavy ML/GPU deps. JobSpy requires pandas (already present).

---

## 6. Phases & Task Decomposition

Each task = one purpose, one test, exact files. `✓` = check off at completion.

### Phase A — Preference-Driven Search (the requested workflow) ✓ COMPLETE

**A1. Preferences schema + wizard** ✓
- Files: `src/joborion/wizard/preferences.py` (NEW), `src/joborion/config.py` (add `PREFERENCES_PATH`)
- Wizard asks Q1–Q4 with rich prompts; writes `preferences.yaml`; `load/save/validate`
- Test: `tests/test_preferences.py::TestPreferencesWizard::test_writes_yaml_with_answers` (mock prompts)
- Verify: `pytest tests/test_preferences.py -v`

**A2. Preferences → search-mode mapping** ✓
- Files: `src/joborion/sourcing/intent.py` (NEW, first part)
- `map_arrangement(prefs) -> dict` translating arrangement/locations/job_types into provider kwargs + filter flags; backward-compat with `search_mode`
- Test: `test_intent.py::TestIntent::test_remote_maps_to_remote_only`

**A3. `joborion configure` CLI command** ✓
- Files: `src/joborion/cli.py`
- `configure` command runs the wizard anytime
- Test: `test_cli.py::test_configure_command` (invoke, mocked prompts)

**A4. Pre-search interactive hook in `joborion run search`** ✓
- Files: `src/joborion/cli.py`, `src/joborion/pipeline.py`
- If `preferences.yaml` missing → run wizard; `--ask/--no-ask` flags; `--arrangement/--locations/--job-type/--min-salary` flags
- Test: `test_cli.py::test_run_search_prompts_when_no_preferences`
- Note: prompt runs every run by default (pre-filled) unless `--no-ask` or flags; target_role enforced at search time per user decision; resolved `mode` flows into `run_pipeline`.

**A5. Wizard writes required `target_role`** ✓
- Files: `src/joborion/wizard/init.py`
- Step 2 no longer allows empty target role; prompts for it if blank (`_prompt_target_role`)
- Test: `test_init_wizard.py::test_target_role_required`

### Phase B — Unified Provider Architecture + Source Expansion

**B1. Provider base + RawJob schema** ✓
- Files: `src/joborion/sources/base.py` (NEW)
- `RawJob` dataclass (normalized fields), `JobProvider` protocol, `ProviderResult`
- Test: `test_sources_base.py::TestRawJob::test_normalizes_fields`

**B2. sources.yaml config + registry** ✓
- Files: `src/joborion/config/sources.yaml` (NEW), `src/joborion/sources/registry.py` (NEW)
- Enable/disable, API-key env refs, per-provider result caps, reliability ordering
- Test: `test_registry.py::TestRegistry::test_disabled_provider_skipped`

**B3. Wrap existing JobSpy + Workday as providers** ✓
- Files: `src/joborion/sources/jobspy_provider.py`, `src/joborion/sources/workday_provider.py` (NEW)
- Pass arrangement/job_types/locations into jobspy kwargs (`is_remote`, `job_type`, `country_indeed`); Workday employer list filtered by `companies.yaml` + industries
- Test: `test_sources_jobspy.py::test_remote_only_kwargs` (mock scrape_jobs)

**B4. Adzuna provider** ✓
- Files: `src/joborion/sources/adzuna_provider.py` (NEW)
- `api.adzuna.com/v1/api/jobs/{country}/search` with `what`, `location0`, `full_time`, `salary_min`, `contract_type` params; maps to RawJob; cost/rate aware
- Test: `test_adzuna_provider.py::test_parses_response` (mock httpx)

**B5. Remote boards provider** ✓
- Files: `src/joborion/sources/remote_boards.py` (NEW)
- Remotive `/api/remote-jobs`, RemoteOK `/api`, WeWorkRemotely RSS (feedparser), Jobicy `/api/v2/remote-jobs`, Arbeitnow, HN Who-is-Hiring (Algolia `search_by_date`, HN Algolia on story 35288000 etc.)
- Test: `test_remote_boards.py::test_remotive_parses` + per-source param tests

**B6. ATS boards provider** ✓
- Files: `src/joborion/sources/ats_boards.py` (NEW), `src/joborion/config/companies.yaml` (NEW)
- Greenhouse `boards-api.greenhouse.io/v1/boards/{company}/jobs`, Lever `api.lever.co/v0/postings/{company}?mode=json`, Ashby `api.ashbyhq.com/posting-api/job-board/{org}`, SmartRecruiters `api.smartrecruiters.com/v1/companies/{company}/postings`
- 100+ curated companies with platform mapping; industry/region filters from prefs
- Test: `test_ats_boards.py::TestGreenhouse::test_parses_postings`

**B7. Wire providers into `pipeline.py` search stage** ✓
- Files: `src/joborion/pipeline.py`, `src/joborion/sources/registry.py`
- Run providers in reliability order, cap results per provider, record metrics
- Test: `test_pipeline.py::test_search_runs_all_enabled_providers` (mock providers)

### Phase C — Relevance Engine

> Discoveries (2026-08-05): the gate runs *after* provider insert (providers store
> via `store_raw_jobs`), then fills structured columns on PASS and deletes DROPped
> jobs, so enrichment/scoring never touch irrelevant rows. Added `company` column
> (was never persisted) + `company` on insert in `base.py` — dedup needs it. Title
> gate keywords come from profile `experience.target_role` + `skills_boundary`
> (roles fuzzy-match ≥80, skill tokens must appear in title). Salary gate compares
> annualized USD only when the scale is confident (explicit interval or ≥20k).
> Filtering is entirely LLM-free (pycountry + rapidfuzz, both new deps).

**C1. Structured job normalization** ✓
- Files: `src/joborion/sourcing/normalize.py` (NEW)
- Extract country/city (pycountry + fuzzy), is_remote, job_type, seniority, salary (regex) — **no LLM**
- Test: `test_normalize.py::test_extracts_salary_and_country`

**C2. Relevance gate** ✓
- Files: `src/joborion/sourcing/filter.py` (NEW)
- Arrangement (remote/hybrid/onsite), location (remote→worldwide or preferred list), job_type, min_salary, seniority, title relevance (rapidfuzz vs target terms) → PASS/DROP with reason
- Test: `test_filter.py::test_drops_bangkok_remote_for_restricted_locations` etc.

**C3. Store structured fields in DB** ✓
- Files: `src/joborion/database.py` (add `ensure_columns`), `src/joborion/sourcing/filter.py`
- Write `is_remote/country/job_type/seniority/salary_*` on insert
- Test: `test_database.py::test_jobs_have_structured_columns`

**C4. Dedup by normalized title+company** ✓
- Files: `src/joborion/sourcing/filter.py`
- rapidfuzz matching against recent jobs (avoid cross-provider duplicates, e.g. same job on Indeed + Greenhouse)
- Test: `test_filter.py::test_dedupes_across_providers`

### Phase D — Self-Improving Sourcing

> Discoveries (2026-08-05): `source_provider` was keyed off the *board* (site
> column, e.g. "Remotive") while pipeline metrics are keyed off the *provider*
> (e.g. "remote_boards") -- attributed `passed` counts were being lost. Fixed by
> writing the provider name into `source_provider` at insert across all five
> storage paths (store_raw_jobs gains a `provider` arg; jobspy/workday/ai_scraper
> INSERTs updated; jobspy/workday/ai_scraper now also persist `company` so C4
> dedup works on their jobs too). record_provider_run replaces record_source_run
> in the discovery stage; reliability_ordering is applied before running.

**D1. Source metrics recording** ✓
- Files: `src/joborion/sourcing/learning.py` (NEW), `src/joborion/database.py`
- Record found/passed/scored/avg_fit/applied/rejected/errors/latency per provider; `consecutive_failures` counter
- Test: `test_learning.py::test_records_metrics`

**D2. Reliability ordering + auto-disable** ✓
- Files: `src/joborion/sources/registry.py`
- Disable provider after N consecutive failures (e.g. Bayt); deprioritize low-yield; re-enable after cooldown
- Test: `test_learning.py::test_auto_disable_after_failures`

**D3. Company auto-prune** ✓
- Files: `src/joborion/sourcing/learning.py`
- Drop ATS/Workday companies with 0 passing jobs over 2 runs; surface in report
- Test: `test_learning.py::test_prunes_zero_yield_companies`

**D4. LLM query evolution** ✓
- Files: `src/joborion/sourcing/query_evolution.py` (NEW), `src/joborion/sourcing/intent.py`
- After evaluate: LLM generates expanded queries from top-fit job titles + profile; `query_history` table; tier rotation
- Test: `test_query_evolution.py::test_expands_queries_from_fit` (mock LLM)

**D5. User feedback loop** ✓
- Files: `src/joborion/sourcing/learning.py`, `src/joborion/cli.py`
- `joborion feedback <url> like|dislike` → `user_feedback` → weights in relevance gate
- Test: `test_learning.py::test_feedback_weights_title_terms`

**D6. Wire reflection (Phase 4) into sourcing** ✓
- Files: `src/joborion/agent/reflector.py`
- Reflection report includes source metrics + next-run recommendations
- Test: `test_reflector.py::test_mentions_source_metrics`

### Phase E — Hardening

**E1. Dead-link verification before apply**
- Files: `src/joborion/enrichment/page_scraper.py`, `src/joborion/sourcing/filter.py`
- HEAD/GET check on `apply_url_direct` before scoring/apply; mark expired
- Test: `test_filter.py::test_marks_expired_urls`
- [x] Done

**E2. Cost control per source**
- Files: `src/joborion/sources/registry.py`, `src/joborion/llm.py` (existing)
- Pre-flight cost estimate per provider; per-run caps; LLM used only by AI-scraper + query evolution (not filtering)
- Test: `test_registry.py::test_respects_result_caps`
- [x] Done

**E3. Proxy support for blocked boards**
- Files: `src/joborion/config/sources.yaml`, `src/joborion/sources/jobspy_provider.py`
- Optional `JOBSPY_PROXY` env; pass proxies to jobspy + httpx providers
- Test: `test_sources_jobspy.py::test_proxy_kwargs`
- [x] Done

**E4. Rate limiting + polite crawling**
- Files: `src/joborion/sources/base.py`
- Per-provider delay/backoff via tenacity; avoid hammering boards
- Test: `test_sources_base.py::test_rate_limit_respected`
- [x] Done (delay via `RateLimiter`; retry/backoff via jobspy's existing `_scrape_with_retry`)

### Phase F — Full Autonomy (optional stretch)

**F1. Scheduled runs** — `joborion daemon` / `--schedule daily` (apscheduler)
- [x] Done (`src/joborion/scheduler.py`: `interval_to_trigger` + `ScheduledRunner`; `run --schedule` and `daemon` CLI with `--interval`/`--at`; 14 tests in `tests/test_scheduler.py`)
**F2. Goal-driven search** — wire new providers into existing Orchestrator tools
- [x] Done (`SearchProvidersTool` in `tools/discovery.py` calls `run_providers`; registered in default registry; planner emits `search_providers` step for goals mentioning providers/all sources; 6 tests in `tests/test_search_providers_tool.py`)
**F3. Notification/report** — rich summary + optional email digest
- [x] Done (`src/joborion/notifier.py`: `load_notify_config`/`build_digest`/`digest_from_stats`/`send_digest`; `joborion notify` CLI with `--to`/`--goal`; 10 tests in `tests/test_notifier.py`)
**F4. Personalization dashboard** — HTML report of matched jobs by provider
- [x] Done (`dashboard.py`: `group_by_provider` helper + "Matched Jobs by Provider" section in `generate_dashboard` (scored, non-expired jobs, HTML-escaped, per-provider tables); 6 tests in `tests/test_dashboard.py`; integration test tool count 13→14)

---

## 7. Verification (whole plan)

```bash
uv run pytest -q                     # all suites (existing 405 + new) green
uv run ruff check src tests
# Manual smoke (with a test preferences.yaml):
joborion run search --no-ask --arrangement remote --min-salary 50000
# Expect: providers report found/passed/dropped reasons; DB rows have
# is_remote/country/job_type/seniority/salary fields; source_metrics populated.
```

---

## 8. Critical Review

- **Scope creep?** Phases E/F are optional hardening/autonomy — not required for
  the core workflow (A–D). Kept for completeness per the "full roadmap" request.
- **Missing?** `litellm` (provider unification) is optional; existing failover
  covers it. Timezone-based remote matching deferred (E/F) — not needed to ship.
- **Wrong order?** A (workflow) before B (sources) before C (relevance) before
  D (learning) — each phase is independently useful.
- **Over-engineered?** Filtering is explicitly **LLM-free** (regex/fuzzy) to
  control cost; LLM only where it adds value (query evolution).
- **Testable?** Every task has an exact test + command.

---

## 9. Success Criteria

1. `joborion run search` prompts 4 questions, then sources across **≥ 10 providers**
   (JobSpy boards + Adzuna + 5 remote boards + 4 ATS platforms + Workday).
2. Jobs match profile + preferences: no mail-clerk/Bangkok-remote noise when the
   user wants specific locations; remote-only when they pick Remote.
3. Structured fields (is_remote, country, job_type, seniority, salary) present in
   DB and used by scoring.
4. After 3 runs, the system disables failing sources (Bayt), prunes zero-yield
   companies, and expands queries from what scored well — **no config edits**.
5. Cost stays bounded: filtering is free, LLM calls tracked and capped.
6. Existing 405 tests remain green; new suites cover wizard, intent, providers,
   filter, learning.

---

## 10. Suggested Build Order

Phase A → Phase B → Phase C → Phase D → (E/F optional). A, B, C, D are
independently shippable; each ends in a working, verifiable system.
