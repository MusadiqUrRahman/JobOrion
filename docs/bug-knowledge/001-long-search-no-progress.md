# 001: joborion run search takes 10+ minutes with no completion feedback

## Symptom
`joborion run search --no-ask` runs for more than 10 minutes and, to the
user, appears to hang: no per-query summary is printed until all providers
finish. If the process is killed (terminal timeout), the run is left
half-finished: jobs are stored (48 in our case) but `run_history`,
`provider_metrics`, and `query_history` are never written.

## Root Cause
Discovery is a large sequential crawl: 48 Workday/ATS employers × each search
query (4 queries = ~192 employer searches), plus JobSpy, remote boards, ATS
boards, and LLM-based ai_sites. Progress is only emitted per-employer in the
log. There is no overall progress indicator and no partial-run recovery
(no `run_id` row until the very end).

## Repro
1. Fresh `~/.joborion` (empty DB, profile + searches.yaml present).
2. `joborion run search --no-ask`.
3. Wait 10+ min. No summary on the console; kill the process.

## Fix
Run long stages in the background and poll status (this is a workflow fix,
not a code fix):
- Launch with `Start-Process` and redirect output to `logs/`.
- Poll `joborion status` / the DB for the expected stage columns.
- Do not rely on a single foreground call for the whole pipeline.
Code-side improvement (future): write `run_history` at run START, print a
live per-provider progress bar, and make the run resumable.

## Verification
`joborion status` shows jobs appearing while a background run progresses.

## Affected Files
- src/joborion/pipeline.py (run_pipeline / _run_discovery_stage — end-only bookkeeping)
- src/joborion/cli.py (run command progress output)
