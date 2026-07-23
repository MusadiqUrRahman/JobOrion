# Subagent-Driven Development

**Trigger:** When a phase has 3+ independent tasks that can be parallelized.

**Iron Law:** FRESH CONTEXT PER TASK — no shared state between implementers.

## Protocol

### When to Use

Use subagent-driven development when:
- A phase has 3+ tasks with no inter-dependencies
- Each task is self-contained (1-3 files, clear test case)
- Tasks can be verified independently
- The controller needs to coordinate, not implement

Do NOT use when:
- Tasks have deep dependencies on each other
- The work requires understanding the full system context
- There are fewer than 3 independent tasks
- The task is architectural (design decisions need human judgment)

### Step 1: Prepare the Context Packet

For each task, prepare a minimal context packet:

```
Task: Add record_cost() function to database.py
Files to read: src/joborion/database.py (lines 1-50 for patterns)
Files to create/modify: src/joborion/database.py (add after line 743)
Test file: tests/test_memory.py
Test case: TestCostLedger::test_record_cost
Dependencies: start_run() must exist (it does — added in Task 1)
Verification: pytest tests/test_memory.py::TestCostLedger::test_record_cost -v
```

### Step 2: Dispatch

Create the task with:
- Exact file paths to read
- Exact file paths to modify
- Exact test to write/pass
- Exact verification command
- What NOT to touch

### Step 3: Review

After each task completes:

1. **Spec compliance** — Does the implementation match the task description?
2. **Code quality** — Does it follow project conventions?
3. **Test coverage** — Does the test actually verify the behavior?
4. **No scope creep** — Did it touch files outside its scope?

### Step 4: Integrate

After all tasks complete:

1. Run the full test suite — confirm everything works together
2. Run ruff — confirm no lint conflicts between tasks
3. Check imports — confirm no circular dependencies
4. Verify the CLI — confirm end-to-end functionality

## Task Classification by Complexity

| Complexity | Model | Files | Example |
|------------|-------|-------|---------|
| Mechanical | Fast | 1-2 | Add a database function, write its tests |
| Integration | Standard | 2-3 | Wire a module into the CLI, add tests |
| Architectural | Capable | 3+ | Design a new subsystem, define interfaces |

## Anti-Patterns

- **"I'll implement it myself, it's faster"** — For 3+ tasks, subagents are faster because they work in parallel with focused context.
- **"Give the subagent the full codebase"** — Give it only what it needs. Context pollution causes errors.
- **"Skip the review step"** — The review catches integration issues between parallel tasks.
- **"Dispatch all tasks at once"** — Dispatch in dependency order. Parallelize only independent tasks.
