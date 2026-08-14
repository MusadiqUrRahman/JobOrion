# 013: Truncated score responses parsed as score 0, persisted, never rescored

## Symptom
Jobs whose LLM scoring response got cut off mid-reasoning (no `SCORE:` line)
were silently written to the DB with `fit_score = 0` and never re-attempted:
`pending_score` required `fit_score IS NULL`, so the fake 0 froze the job out
of future runs. In one real run, 6 of 33 scored jobs ended at 0 this way
(Motorola "AI Agent Platform", Thomson Reuters "LLM Agents" roles), plus 1
more via `LLM error: 'choices'` (covered separately by bug 006). The stored
`score_reasoning` text for these jobs ends mid-sentence, e.g. "...The role is"
or "...candidate has".

## Root Cause
- `src/joborion/scoring/fit_scorer.py` called `client.chat(..., max_tokens=512)`.
  The scoring prompt asks for `SCORE:` then `REASONING:`, and models often
  write long prose first, so the response was truncated before the `SCORE:`
  line was emitted.
- `_parse_score_response` defaults to `score = 0` when no `SCORE:` line
  exists, with no way to distinguish "real 0" (impossible; clamps to 1-10)
  from "parse failed".
- `score_jobs` persisted every result unconditionally, writing the fake 0.
- `database.py` `pending_score` / `pipeline.py` evaluate SQL only matched
  `fit_score IS NULL`, so score-0 rows were never retried.

## Repro
1. Mock `client.chat` to return a truncated string with no `SCORE:` line.
2. `score_jobs(rescore=True)`.
3. `SELECT COUNT(*) FROM jobs WHERE fit_score = 0` is inflated, and a later
   `score_jobs()` run skips those jobs (they no longer match `pending_score`).

## Fix
- Bump scoring `max_tokens` 512 -> 1024.
- Add `_chat_for_score`: if the response has no `SCORE:` line, retry up to 2
  times with a terse follow-up ("Output only the score, as exactly: SCORE: [1-10]").
- `score_jobs` skips persisting results with `score == 0`, leaving `fit_score
  NULL` so the job is retried on the next run.
- `ScoreSingleJobTool` returns an error (and does not persist) when score is 0.
- `pending_score` and the pipeline `evaluate` count now match
  `(fit_score IS NULL OR fit_score = 0)`, so legacy fake-0 rows self-heal.

## Verification
`pytest tests/test_fit_scorer.py tests/test_database.py` passes; new tests
cover truncated-parse retry, zero-after-retries, and no persistence of score 0.

## Affected Files
- src/joborion/scoring/fit_scorer.py
- src/joborion/tools/scoring.py
- src/joborion/database.py
- src/joborion/pipeline.py
- tests/test_fit_scorer.py (new)
- tests/test_database.py
