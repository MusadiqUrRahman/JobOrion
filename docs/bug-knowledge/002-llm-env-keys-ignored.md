# 002: .env LLM_PROVIDER and LLM_MODEL keys are silently ignored

## Symptom
User sets `LLM_PROVIDER=gemini` and `LLM_MODEL=gemini-2.5-flash` in
`~/.joborion/.env`, but all Gemini calls run with the hardcoded default
`gemini-2.0-flash` (observed in discovery log: quota error names
`model: gemini-2.0-flash`). The chosen model can never be used.

## Root Cause
`LLM_MODEL` is only read by the LOCAL provider (`src/joborion/llm.py:301`).
The Gemini provider reads `GEMINI_MODEL` and falls back to the hardcoded
`gemini-2.0-flash` (`llm.py:271`). `LLM_PROVIDER` is not read anywhere in
`src/` (grep returns nothing). The wizard writes `GEMINI_MODEL=` correctly
(`wizard/init.py:326`), so this only bites when a user hand-edits .env using
the generic names.

## Repro
1. `.env`: `LLM_PROVIDER=gemini`, `LLM_MODEL=gemini-2.5-flash`, `GEMINI_API_KEY=...`
2. Run any LLM stage (e.g. query evolution in discovery).
3. Observe quota/log errors referencing `gemini-2.0-flash`.

## Fix
Use the correct env key: add `GEMINI_MODEL=gemini-2.5-flash` to `.env`.
(Code fix, future: honor `LLM_PROVIDER` to select the backend and treat
`LLM_MODEL` as a global model override.)

## Verification
With `GEMINI_MODEL` set, LLM stage logs reference the configured model.

## Affected Files
- src/joborion/llm.py:271 (GEMINI_MODEL read), :301 (LLM_MODEL is local-only)
- src/joborion/wizard/init.py:326 (writes the correct GEMINI_MODEL key)
