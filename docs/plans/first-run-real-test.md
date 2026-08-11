# First-Run Real-World Test Plan

**Goal:** Test JobOrion exactly as a first-time user would, end-to-end, from a
fresh job database through a real submitted application, logging every bug
found into a reusable knowledge base.

**Decision:** Keep existing workspace setup (profile, resume, searches.yaml,
.env), wipe only job data, set a real `target_role`, run the full pipeline,
submit one real application. Bug knowledge base lives in `docs/bug-knowledge/`
and is committed.

## File Surface

- `docs/plans/first-run-real-test.md` (NEW) — this plan
- `docs/bug-knowledge/index.md` (NEW) — registry of issues, one file each
- `docs/bug-knowledge/NNN-<slug>.md` (NEW) — one per bug found during testing
- `skills/bug-knowledge.md` (NEW) — skill: on any bug/error, check the KB,
  apply fix, log a new entry when unknown
- `skills/README.md` — add bug-knowledge row
- `AGENTS.md` — add Bug Knowledge Base section + skill table row
- `~/.joborion/profile.json` — add `experience.target_role` (data, not code)
- `~/.joborion/searches.yaml` — align queries with target_role
- `~/.joborion/joborion.db` — wiped (job data reset)

## Tasks

1. **Baseline & environment capture**
   - Run `joborion check` and `joborion status`, save output to a log
   - Record versions: python, joborion, playwright, chrome
   - Verify: 257 old jobs, 0 tailored (captured: Tier 3, all deps ready)

2. **Bug knowledge base scaffolding**
   - Create `docs/bug-knowledge/index.md` (format spec + table)
   - Create `skills/bug-knowledge.md` and wire into `skills/README.md` + `AGENTS.md`
   - Template: symptom / root cause / repro / fix / verification / affected files

3. **Fresh job data**
   - Delete `joborion.db` (+ `-wal`/`-shm`), empty `tailored_resumes/`, `cover_letters/`
   - Confirm 0 jobs via `joborion status`

4. **First-run setup completion**
   - Set `experience.target_role` in profile.json (via `configure` or direct edit)
   - Align `searches.yaml` queries/locations with the target role and mode
   - Confirm preferences exist (`preferences.yaml`) or run configure questionnaire

5. **Discovery** — `joborion run search`
   - Expect fresh jobs stored; log provider results, failures, retries

6. **Enrichment** — `joborion run details`
   - Expect `full_description` + `application_url`; Playwright + LLM fallback

7. **Scoring** — `joborion run evaluate`
   - Expect fit_score 1-10 + rejection reasons; verify apply URLs

8. **Tailor + letter + export** — `joborion run tailor letter export`
   - Expect tailored resumes (score >= 7), cover letters, PDFs

9. **Apply** — `joborion apply --limit 1`
   - Expect one real application submitted; classify result (applied/failed/expired)
   - If CAPTCHA/login blocks, log as bug KB entry

10. **Bug log review** — consolidate all KB entries, review fixes,
    update CHANGELOG, commit.

## Verification

- `joborion check` → Tier 3, all green
- `joborion status` → 0 jobs after reset; >0 after search
- `joborion jobs --stage applied` → 1 applied job after apply (or a logged failure)
- `pytest tests/ -q` and `ruff check src/ tests/` still green after code-side fixes
- Every bug encountered has a KB file with a root cause + fix

## Notes

- Personal data must NEVER be committed (profile.json, resume, cv files stay local).
- Bug KB entries must not contain personal info — job URLs ok, identity data no.
- This plan is a living contract: bugs found during steps 3-9 update the KB.
