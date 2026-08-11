# 009: First apply run copies the entire user Chrome profile (11 GB, ~5.5 min)

## Symptom
On a machine with no prior worker profiles, `joborion apply` spends ~5.5
minutes on `Copying Chrome profile from User Data (first time setup)...`
before the agent starts. The copy walks the user's full Chrome profile
(11.4 GB here) recursively, copying even `Default` (history, cookies,
extensions, IndexedDB) minus a few cache dirs.

## Root Cause
`src/joborion/apply/browser.py` `setup_worker_profile()` falls back to
`config.get_chrome_user_data()` when no worker profile exists, then copies
every top-level dir in the user profile with `shutil.copytree`, skipping only
cache-named dirs. A profile with heavy browsing data is gigabytes and slow to
copy. (Subsequent runs are fast: line 114 reuses the existing worker profile.)

## Repro
1. Delete `~/.joborion/chrome-workers/` (no worker profile).
2. `joborion apply --limit 1`
3. Watch `[worker-0] Copying Chrome profile ...` for minutes.

## Fix
Copy only the minimal profile surface needed for browsing + autofill (Local
State, Preferences, `Default` subset: cookies, login data, autofill,
History) instead of the whole tree; or use a fresh profile and log in
per-application. Avoid copying the user's full browsing profile wholesale.

## Verification
First `apply` on a clean machine reaches "Starting: <job>" in under a minute.

## Affected Files
- src/joborion/apply/browser.py (setup_worker_profile)
