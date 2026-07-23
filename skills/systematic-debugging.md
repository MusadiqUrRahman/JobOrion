# Systematic Debugging

**Trigger:** When a test fails, a bug appears, or behavior is unexpected.

**Iron Law:** NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST.

## Protocol

### Phase 1: Evidence Gathering

Before proposing ANY fix:

1. **Read the error message** — The full error, not just the last line
2. **Read the traceback** — Which file, which line, which function
3. **Read the code** — The function that failed, and its callers
4. **Read the test** — What the test expects vs. what actually happened
5. **Reproduce the failure** — Run the exact command that triggers it

Document what you found:

```
Error: sqlite3.IntegrityError: UNIQUE constraint failed: run_log.run_id
File: src/joborion/database.py:929
Function: start_run()
Reproduction: start_run("test"); start_run("test") — second call fails
Root cause hypothesis: run_id is timestamp-based, two calls/sec = collision
```

### Phase 2: Pattern Recognition

Ask:

- Is this a known pattern in this codebase? (Check other modules for similar issues)
- Have we seen this error before? (Check validation_errors table, git log)
- Is this a transient or permanent failure?

### Phase 3: Hypothesis

Form exactly ONE hypothesis. Not two. Not "it could be X or Y." One.

```
Hypothesis: The run_id generation uses second-precision timestamps,
causing collisions when start_run() is called multiple times per second.
```

Test the hypothesis with the minimum code change needed to confirm or deny it.

### Phase 4: Implement the Fix

Only after confirming the root cause:

1. Write a test that reproduces the exact failure
2. Confirm the test fails (red)
3. Implement the fix — minimal change to resolve the root cause
4. Confirm the test passes (green)
5. Run the full test suite — confirm no regressions
6. Run ruff — confirm no lint errors

### Phase 5: Verify the Fix

```bash
pytest tests/ -v              # All pass
ruff check src/               # Clean
# Run the specific reproduction case that triggered the bug
```

## The Rule of Three

After 3 failed fix attempts for the same bug:

1. **STOP** — Do not attempt a 4th fix
2. **Question the architecture** — Is the design fundamentally wrong?
3. **Escalate** — Document what you've tried and ask for guidance
4. **Consider reverting** — If recent changes caused this, undo them

## Error Classification

Every error falls into one of three categories:

| Category | Response | Example |
|----------|----------|---------|
| **Transient** | Retry with backoff (max 2) | Rate limit, timeout, network blip |
| **Permanent** | Skip and log, continue | Invalid input, safety refusal, budget exceeded |
| **Degraded** | Proceed with reduced quality | Partial data, missing optional field |

Never silently swallow errors. Always log classification and action taken.

## Anti-Patterns

- **"It's probably just a typo"** — Read the traceback. It tells you exactly where the problem is.
- **"Let me just add a try/except"** — That hides the error, it doesn't fix it.
- **"I'll fix the symptom and move on"** — The symptom will come back. Find the root cause.
- **"This worked before, must be a flake"** — "Flaky" is a label, not an explanation. Investigate.
- **"Let me refactor everything while I'm here"** — Fix the specific bug. Refactor separately.
