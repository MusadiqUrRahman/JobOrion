# Verification Before Completion

**Trigger:** Before claiming any task, phase, or milestone is done.

**Iron Law:** NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE.

## Protocol

### The Gate Function

Before any completion claim:

```
1. IDENTIFY  — What command proves this is done?
2. RUN       — Execute the command RIGHT NOW (not from cache)
3. READ      — Read the FULL output and exit code
4. CONFIRM   — Does the output match what the claim requires?
5. ATTACH    — Include the evidence in your response
```

### What Counts as Evidence

| Claim | Required Evidence |
|-------|-------------------|
| "Tests pass" | Full `pytest tests/ -v` output showing all tests pass |
| "No lint errors" | `ruff check src/` output showing "All checks passed" |
| "CLI works" | `joborion --version` or `joborion --help` output |
| "Feature X works" | Specific test output for feature X |
| "Phase complete" | All milestones for that phase verified individually |

### What Does NOT Count as Evidence

- "I ran the tests earlier and they passed" — Stale evidence
- "The code looks correct" — Code review is not verification
- "It should work because..." — Assumptions are not evidence
- "I only changed docs, so tests must still pass" — Run them anyway
- A truncated test output — Show the full result

### Evidence Format

When claiming completion, always include:

```
Verification evidence:
- pytest tests/ -v: 171 passed in 18.47s
- ruff check src/: All checks passed
```

Not:
```
Tests pass and lint is clean.
```

The difference is **specific, fresh, verifiable output** vs. **assertion without evidence**.

## Application to JobOrion

### Per-Task Verification

After completing each task in a plan:

```bash
pytest tests/<specific_test>.py -v
ruff check src/<modified_file>.py
```

### Per-Phase Verification

After completing a phase:

```bash
pytest tests/ -v              # ALL tests pass
ruff check src/               # ALL checks pass
joborion --version            # CLI works
joborion --help               # Commands listed
```

### Pre-Commit Verification

Before every commit:

```bash
pytest tests/ -v
ruff check src/
git status                    # Only intended files changed
git diff                      # Review actual changes
```

## Anti-Patterns

- **"I'm confident it works"** — Confidence is not evidence. Run the command.
- **"Only a 1-line change, surely it's fine"** — 1-line changes break things. Verify.
- **"The tests are slow, I'll skip them this once"** — Never skip verification.
- **"I'll verify after the next task"** — Verify NOW, before moving on.
- **Showing partial output** — Show the full output. If it's long, show the summary line.
