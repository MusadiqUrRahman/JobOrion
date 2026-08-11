# 006: OpenRouter responses missing `choices` crash score parser -> silent score 0

## Symptom
During `run evaluate`, when Gemini's per-minute quota is exhausted the app
fails over to OpenRouter. Many OpenRouter calls log `HTTP/1.1 200 OK` but
raise `LLM error scoring job '<title>': 'choices'` (a KeyError). Those jobs
receive `fit_score = 0`, silently corrupting the score distribution. In the
first real run, 7 of 33 scored jobs ended at 0 this way (max score was 4).

## Root Cause
`src/joborion/llm.py:150`:
```python
return resp.json()["choices"][0]["message"]["content"]
```
OpenRouter (especially free tier models like `nvidia/nemotron-3-ultra-550b-a55b:free`)
sometimes returns HTTP 200 with a body that has no `choices` key (e.g. an
`error` object when the upstream provider is throttled/overloaded). The
KeyError propagates into the caller, which treats any exception as a failed
call and assigns score 0 / falls back.

## Repro
1. Exhaust the primary provider quota so failover to OpenRouter engages.
2. Run evaluate; watch logs for `'choices'` KeyError on 200 responses.
3. `SELECT fit_score, count(*) FROM jobs WHERE fit_score=0` shows inflated 0s.

## Fix
Parse defensively: only accept a response that has a `choices[0].message.content`
string; treat anything else (error object, missing key, empty content) as a
non-200 / retryable failure instead of raising.

## Verification
Evaluate again with primary quota exhausted; no `'choices'` KeyError in logs,
and jobs scored via OpenRouter receive a real score rather than 0.

## Affected Files
- src/joborion/llm.py:150
