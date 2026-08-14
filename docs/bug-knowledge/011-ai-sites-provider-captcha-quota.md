# 011: ai_sites provider stores 0 jobs (CAPTCHA everywhere) then kills the run with LLM 429 quota

## Symptom
Running the `ai_sites` discovery provider produces `CAPTCHA/rate-limit detected -- skipping
headful retry` for every site and `LLM: no job listings found` per site. After several
sites, Gemini fails with `429 RESOURCE_EXHAUSTED` on
`generativelanguage.googleapis.com/generate_content_free_tier_requests` (limit 15, model
gemini-3.1-flash-lite) and fails over to openrouter. The run keeps polling and the caller
hangs until timeout (180s in scratch run). Stored = 0.

## Root Cause
- The `ai_sites` provider scrapes AI-aggregation boards that sit behind CAPTCHA/rate limits,
  so every headful scrape is skipped and each site then depends on an LLM parse of an empty
  body → 0 listings.
- Free-tier Gemini has a hard 15 req/min/project/model cap. Discovery keeps hammering it
  past the cap, so the 429s cascade and the provider stalls mid-run instead of degrading
  gracefully.
- Scratch evidence: `fast_discovery`-style run with only `ai_sites` → 8 CAPTCHA skips,
  8 "LLM: no job listings found", 1 Gemini 429 failover line, timeout after 180s.

## Repro
1. `build_providers()` filtered to `name == "ai_sites"`.
2. Run `run_providers(intent, providers=[ai_sites], ...)`.
3. Observe all-CAPTCHA skips, 0 stored, then 429 failover and hang.

## Fix
- Disable `ai_sites` in `src/joborion/config/sources.yaml` (or provide a working
  CAPSOLVER_API_KEY and rate-limit the provider to 1-2 sites/run) until the boards stop
  blocking.
- Cap LLM calls per provider run so free-tier quota is never exhausted mid-run; treat 429 as
  a transient error and stop the provider cleanly (record error, return, do not hang).

## Verification
With `ai_sites: enabled: false`, the same run exits promptly with 0 sites attempted and no
LLM quota hit.

## Affected Files
- src/joborion/config/sources.yaml (ai_sites block)
- src/joborion/sources/ai_sites.py (provider scrape loop)
