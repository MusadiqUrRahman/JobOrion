# 005: application_url stored as literal string "None" for jobs without an apply URL

## Symptom
Some jobs have `application_url = 'None'` (the four-character string, not
NULL) in the DB. Since `apply/runner.py` uses `application_url or url` and
the acquire query treats `'None'` as a non-null value, `joborion apply`
would attempt to open the URL `None` instead of skipping the job.

## Root Cause
`src/joborion/discovery/jobspy.py:234`:
```python
apply_url = str(row.get("job_url_direct", "")) if str(row.get("job_url_direct", "")) != "nan" else None
```
When JobSpy returns `job_url_direct=None`, `str(None)` == `"None"`, which is
not `"nan"`, so the literal string `"None"` is stored.

## Repro
1. Run search via JobSpy; a result without a direct apply URL is returned.
2. `SELECT application_url FROM jobs WHERE application_url='None'` returns rows.

## Fix
Treat None/empty like nan:
```python
direct = row.get("job_url_direct") or ""
direct_str = str(direct)
apply_url = direct_str if direct_str not in ("", "nan") else None
```

## Verification
Re-run search (or fix existing rows: `UPDATE jobs SET application_url=NULL
WHERE application_url='None'`); no rows with the `'None'` string.

## Affected Files
- src/joborion/discovery/jobspy.py:234
