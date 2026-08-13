# Bug Knowledge Base

Registry of every bug/issue found during real-world testing. One file per
issue. This is the first place to check whenever JobOrion misbehaves.

## How to Use

1. **Bug appears** → search `docs/bug-knowledge/` for a matching symptom
   (grep the `## Symptom` lines, or run the skill `skills/bug-knowledge.md`).
2. **Match found** → apply the documented fix and verify.
3. **No match** → investigate root cause, then add a new file following the
   template below and update this index.

## File Format

`NNN-<slug>.md` where `NNN` is the next number and `<slug>` is 2-4 dashed words.

```markdown
# NNN: <One-line title>

## Symptom
What the user sees / the exact error.

## Root Cause
Why it happens (file:line evidence).

## Repro
Minimal steps to reproduce.

## Fix
What changed to resolve it.

## Verification
Command/evidence that proves the fix works.

## Affected Files
- src/... (or data file / env / external)
```

## Index

| # | Title | Status | Found In | Fixed |
|---|-------|--------|----------|-------|
| 001 | Search takes 10+ min with no progress/completion, killed run leaves no run_history | open | discovery | workflow fix: background + poll |
| 002 | .env LLM_PROVIDER / LLM_MODEL keys ignored; Gemini stuck on gemini-2.0-flash | open | discovery | use GEMINI_MODEL key |
| 003 | All configured LLM providers exhausted (Gemini 0 quota/denied, OpenRouter 429) — LLM stages blocked | open | discovery | add a provider key with quota |
| 004 | ATS board feeds dump all roles regardless of query (96% noise) | open | discovery | prune DB; filter titles in ATS provider |
| 005 | application_url stored as literal string "None" for jobs without an apply URL | open | discovery | str(None) guard in jobspy.py:234; SQL update for existing rows |
| 006 | OpenRouter 200 responses missing `choices` key raise KeyError -> job scored 0 | open | evaluate | defensive parse in llm.py:150 |
| 007 | LLM failover gets stuck on a dead provider (backend index never reset after generic exception) | open | tailor/evaluate | backoff + reset index to 0 in llm.py generic except branch |
| 008 | `apply --url` matches no job when apply_status is NULL (SQL NULL != trap) | open | apply | `(apply_status IS NULL OR apply_status != 'in_progress')` in runner.py |
| 009 | First apply run copies entire user Chrome profile (11 GB, ~5.5 min) | open | apply | copy minimal profile surface in browser.py setup_worker_profile |
| 010 | Cross-frame reCAPTCHA click misses using page.mouse + bounding_box (frame-relative coords); use locator.click() | fixed | apply | fill_submit.py; verified token 1294 chars + application/complete/1828281 |
| 011 | ai_sites provider stores 0 jobs (CAPTCHA everywhere) then hits Gemini 429 free-tier quota and hangs | open | discovery | disable ai_sites in sources.yaml; cap LLM calls per provider run |
| 012 | Eligibility classifier misses US state / CA province tokens (Ontario, Texas, ON, CAN) so restricted-remote jobs pass the gate and waste scoring cost | open | evaluate | extend COMMON_COUNTRIES with state/province names + abbreviations |
