# Executing Plans

**Trigger:** When you have a written plan (from `writing-plans`) and are ready
to implement.

**Iron Law:** NO SKIPPING TASKS, NO REORDERING WITHOUT JUSTIFICATION.

## Protocol

### Step 1: Load the Plan

Read the plan file completely. Understand the goal, the file surface, and
every task's dependencies. If the plan doesn't exist, go back to
`writing-plans` and create one.

### Step 2: Set Up the Workspace

Before writing any code:

```bash
# Verify clean starting state
pytest tests/ -v          # All existing tests pass
ruff check src/           # No lint errors
git status                # Clean working tree (or commit current work)
```

### Step 3: Execute Tasks Sequentially

For each task in the plan:

1. **Read the task** — Understand what file to create/modify and what test to write
2. **Write the test first** (TDD) — The test defines the contract
3. **Run the test** — Confirm it fails (red)
4. **Write the implementation** — Minimal code to make the test pass
5. **Run the test** — Confirm it passes (green)
6. **Run ruff** — Confirm no lint errors
7. **Check off the task** — Mark it complete in the plan

### Step 4: Handle Blockers

If a task fails or becomes blocked:

1. **Do NOT skip it** — Mark it as BLOCKED in the plan
2. **Do NOT reorder** — Continue with tasks that don't depend on it
3. **Document the blocker** — What failed, why, what you tried
4. **Attempt resolution** — Apply `systematic-debugging` skill
5. **If unresolved after 3 attempts** — Stop and reassess the plan

### Step 5: After All Tasks Complete

Run the full verification suite:

```bash
pytest tests/ -v          # All tests pass (including new ones)
ruff check src/           # No lint errors
joborion --version        # CLI still works
```

If any check fails, fix before claiming completion.

### Step 6: Update the Plan

Mark every task as complete (or blocked with explanation). Add any
discoveries that changed the plan from what was written.

## Execution Rules

- **Never modify a task after starting it** — If the task is wrong, finish it, then create a follow-up task
- **Never combine tasks** — Even if they seem trivial together
- **Never skip tests** — Every task has a test. Write it.
- **Never proceed past a failing test** — Fix it before moving on
- **Commit after every 2-3 tasks** — Don't accumulate uncommitted changes

## Anti-Patterns

- **"I'll do them out of order because it makes more sense"** — The plan already accounts for ordering. Follow it.
- **"This task is too small, I'll merge it with the next"** — Small tasks are the point. Don't merge.
- **"Tests can come after implementation"** — TDD means test first. Always.
- **"The plan is outdated, I'll just wing it"** — Update the plan, then follow the updated plan.
