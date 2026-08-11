# 003: All configured LLM providers exhausted stalls the pipeline

## Symptom
During `joborion run search` (and by extension any LLM stage), every call
ends in `429 RESOURCE_EXHAUSTED` (Gemini) or `429 Too Many Requests`
(OpenRouter), then the code enters "all providers exhausted. Waiting 40s
before retry 3/5" loops. The run crawls to a standstill; query evolution
is skipped, ai_sites falls back to deterministic strategies, and the
evaluate/tailor/letter stages (which require LLM) cannot run at all.

## Root Cause
Free-tier LLM quotas were exhausted/denied on the user's account:
- `gemini-2.0-flash` free tier: daily request/input-token quota = 0
- `gemini-2.5-flash`: `403 PERMISSION_DENIED` (project denied access)
- OpenRouter `nvidia/nemotron-3-ultra-550b-a55b:free`: `429` rate-limited

The fallback chain in `llm.py` (Gemini → Anthropic → OpenAI → Custom →
Local) works, but when every configured provider is exhausted the retry
loop burns ~40s per call and the message gives no actionable next step.

## Repro
1. `.env` with only a free-tier Gemini key + OpenRouter free model.
2. Run any pipeline stage that calls the LLM.
3. Watch repeated 40s retries with no clear "add a key with quota" message.

## Fix
Have at least one provider with available quota configured. Options:
- Add `ANTHROPIC_API_KEY`, `CUSTOM_API_KEY` (+`CUSTOM_BASE_URL`), or a paid
  OpenRouter model, or a local endpoint via `LLM_URL`.
- Wait for the daily quota reset (Gemini free tier resets ~midnight PT).
(Code improvement, future: fail fast with an actionable message listing
which providers are exhausted instead of looping retries.)

## Verification
A direct call to any configured model returns 200 (see
`test_gemini.py`/`test_openrouter.py` pattern in the temp dir).

## Affected Files
- src/joborion/llm.py (retry loop, provider fallback)
- Environment: `~/.joborion/.env`
