# 007: LLM failover gets stuck on a dead provider (backend index never reset)

## Symptom
After ONE call fails over gemini -> openrouter and the OpenRouter response is
unusable (e.g. bug 006's missing `choices`), EVERY subsequent call also starts
on OpenRouter, fails, and the job is marked ERROR. The client never returns to
the healthy primary provider. In the first real run, tailor reached 9/10 with
all later jobs `ERROR: 'choices'`, and evaluate's later jobs silently scored 0.

## Root Cause
`src/joborion/llm.py` `LLMClient.chat()` generic `except Exception` branch:
```python
except Exception as exc:
    if self._switch_backend():
        ...continue
    raise
```
`_switch_backend()` returns False once the last backend is reached, and the
code `raise`s WITHOUT resetting `self._backend_index = 0`. The next call to
`chat()` starts at the last backend again. Only the HTTP 429/503 and
timeout/connect branches reset the index to 0; the generic exception branch
does not, so a transient upstream failure makes failover sticky-permanent.

## Repro
1. Configure gemini (primary) + openrouter (secondary, returns 200 without
   `choices`).
2. Trigger one generic exception in the secondary (see bug 006).
3. All subsequent LLM calls start on the secondary and fail, even once the
   primary is healthy again.

## Fix
In the generic `except Exception` branch, when all backends are exhausted,
back off exponentially, reset `_backend_index = 0`, and retry (mirroring the
429/503 branch) instead of raising immediately:
```python
if attempt < _MAX_RETRIES - 1:
    wait = min(_RATE_LIMIT_BASE_WAIT * (2 ** attempt), 60)
    log.warning("... all providers exhausted. Retrying in %ds ...", wait)
    time.sleep(wait)
    self._backend_index = 0
    continue
raise
```

## Verification
Run tailor with gemini (healthy) + broken openrouter secondary; calls that
fail over to openrouter retry on gemini after backoff and succeed — the run
completes with no `'choices'` ERRORs and every job tailored.

## Affected Files
- src/joborion/llm.py (LLMClient.chat generic except branch)
