# 012: Eligibility classifier misses state/province tokens, passes US/CA-restricted jobs

## Symptom
The deterministic eligibility gate (`joborion.eligibility.evaluate_job`) passes jobs whose
location is restricted to a US state or Canadian province but whose string carries no
recognized country token. Examples observed in the pool:
- "Ontario Remote Work, More..." and "REMOTE/TELETRAVAIL, ON, CAN" → the "CAN" token in
  "ON, CAN" is NOT matched by `COMMON_COUNTRIES` ("canada" is the key, "can" is not), so the
  job is treated as worldwide remote.
- "Illinois Remote Work", "Texas - Remote", "Washington D.C. - Remote" → "us" appears nowhere
  in the string (state names are not in `COMMON_COUNTRIES`), so they pass too.
- Meanwhile "US, Remote" IS matched (token "us") and is rejected — the exact opposite of the
  province/state cases, so the gate is inconsistent job-to-job.

These pass discovery, get scored, and only fail at apply time (`not_eligible_location`),
wasting LLM scoring cost on jobs that can never be applied to.

## Root Cause
`eligibility.py:location_country()` only canonicalizes country names via the
`COMMON_COUNTRIES` dict. US states (Texas, Illinois, Virginia...), provinces (Ontario,
Quebec...), abbreviations (ON, CA, TX...), and city "Remote, Bangalore" are not mapped, so
`classify_location()` returns `country=None` and the job is treated as location-independent.
`REMOTE_WORDS` contains "remote", so remote-only mode then passes the job.

A second gap: many Workday postings store an empty `location` column while the real location
is embedded in the URL path (`/job/Brazil-So-Paulo-So-Paulo/...`, `/job/Warsaw---Poland/...`).
With no location text the gate returned "can't rule out" and passed every such job, deferring
the rejection to apply time.

## Repro
```python
from joborion.eligibility import classify_location, evaluate_job
classify_location("Ontario Remote Work, More...")   # is_remote=True, country=None
classify_location("Texas - Remote")                 # is_remote=True, country=None
classify_location("US, Remote")                     # is_remote=True, country="us"
```

## Fix
Extend `COMMON_COUNTRIES` with US state + Canadian province names and abbreviations
("texas", "ontario", "illinois", "ca" → beware "ca" ambiguity with Canada, "ga"/"va"/... )
and/or add a state->country resolver. At minimum add a `location_country()` fallback that
recognizes the standard US/CA abbreviation sets (e.g. "ON, CAN", "USA, NY"). Do NOT map
bare "CA" to a country without a disambiguation rule.

Implemented:
- `CITY_TO_COUNTRY` map for the cities observed in the pool (Bangalore→india,
  Toronto→canada, Berlin→germany, Warsaw→poland, ...). Word-boundary match so "Milan"
  never matches inside another word.
- `US_STATE_CODES` / `CA_PROVINCE_CODES` / `COUNTRY_CODES` two-letter sets matched only
  against uppercase tokens from the original string, so English words ("in", "on") can
  never be misread as codes. "CA" resolves to Canada only when another Canadian province
  code (e.g. "ON") is present; alone it means California.
- `url_location()` extracts the `/job/<Location>/` segment from Workday URLs and
  `evaluate_job()` falls back to it when the `location` column is blank.

## Verification
After the fix, "Ontario Remote Work" → country "canada", "Texas - Remote" → country "us",
"US, Remote" → country "us", "Remote, Bangalore" → country "india", and all are rejected in
remote-only mode for a Pakistan-based candidate. Blank-location Workday jobs resolve their
country from the URL ("Warsaw---Poland" → poland, "Brazil-So-Paulo" → brazil). Re-run the
pool eligibility sweep: all 9 previously "tailored + eligible" jobs now fail the gate.

## Affected Files
- src/joborion/eligibility.py (COMMON_COUNTRIES, location_country)
- tests (any eligibility unit tests)
