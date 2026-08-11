# 008: `apply --url` matches no job when apply_status is NULL

## Symptom
`joborion apply --url <job-url> --gen` returns `✗ No matching job found`
for a job that exists, is tailored, and has never been applied to
(`apply_status IS NULL`).

## Root Cause
`src/joborion/apply/runner.py` `acquire_job()` target_url branch:
```python
AND apply_status != 'in_progress'
```
In SQLite, `NULL != 'in_progress'` evaluates to NULL (unknown), not TRUE, so
every row with `apply_status IS NULL` is filtered out. The queue branch
(lines ~153-154) uses the correct `(apply_status IS NULL OR apply_status =
'failed')`; only the target_url branch has the bug.

## Repro
1. Tailor any job so `tailored_resume_path` is set; leave `apply_status` NULL.
2. `python -m joborion apply --url <that job's url> --gen`
3. Result: "No matching job found". The equivalent query without the `--url`
   branch returns the job.

## Fix
```python
AND (apply_status IS NULL OR apply_status != 'in_progress')
```

## Verification
`apply --url <url> --gen` now finds the job and writes a prompt file.

## Affected Files
- src/joborion/apply/runner.py (acquire_job target_url branch)
