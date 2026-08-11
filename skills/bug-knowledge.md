# Bug Knowledge Base

**Trigger:** Any bug, error, crash, or unexpected behavior appears during
development or real-world use.

**Iron Law:** No fix without checking the knowledge base first, and no unknown
bug fixed without logging it.

## Protocol

### Step 1: Check the KB

Grep `docs/bug-knowledge/index.md` and the `## Symptom` lines of every file in
`docs/bug-knowledge/` for a matching symptom.

- **Match found** → read that file, apply the documented fix, run the
  documented verification. Done.
- **No match** → continue to Step 2.

### Step 2: Root cause first

Follow `skills/systematic-debugging.md` before touching any code. Confirm the
root cause with evidence (file:line, repro, error text).

### Step 3: Fix

Apply the minimal fix. Run the relevant tests + `ruff check src/ tests/`.

### Step 4: Log the bug

Create `docs/bug-knowledge/NNN-<slug>.md` using this template:

```markdown
# NNN: <One-line title>

## Symptom
What the user sees / the exact error.

## Root Cause
Why it happens (file:line evidence).

## Repro
Minimal steps to reproduce.

## Fix
What changed to resolve it.

## Verification
Command/evidence that proves the fix works.

## Affected Files
- ...
```

Then add a row to `docs/bug-knowledge/index.md` and update the count.

### Step 5: Verify

Run the full verification suite and confirm the original symptom is gone.

## Rules

- One file per issue. Never append to an existing file unless it is the exact
  same root cause.
- Log the bug even if it was a data/env problem, not code — the fix matters.
- Never put personal data in a KB file (identity, resume contents, keys).
- Job URLs and site names are fine.
