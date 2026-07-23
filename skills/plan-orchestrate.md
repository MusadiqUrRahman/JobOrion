# Plan Orchestrate

**Trigger:** When converting a written plan into executable actions with
budget and dependency awareness.

**Iron Law:** NO ACTION WITHOUT BUDGET ESTIMATE AND DEPENDENCY CHECK.

## Protocol

### Step 1: Parse the Plan

Read the plan file and extract:
- All tasks with their file surfaces
- Dependencies between tasks
- Estimated complexity per task

### Step 2: Build the Execution Graph

```
Task 1 (no deps) ──→ Task 2 (depends on 1) ──→ Task 4 (depends on 2, 3)
Task 3 (no deps) ──→ Task 4
```

Identify:
- **Independent tasks** — Can run in parallel
- **Critical path** — Longest dependency chain
- **Bottlenecks** — Tasks that block the most other tasks

### Step 3: Estimate Budget

For each task, estimate:

| Resource | Estimate Method |
|----------|----------------|
| LLM tokens | Number of API calls × avg tokens per call |
| Time | Based on complexity class (mechanical/integration/architectural) |
| Files touched | Directly from plan |

For the overall plan:
- Sum all task estimates
- Add 20% buffer for unexpected issues
- Check against `LLM_MAX_COST` budget

### Step 4: Generate the Execution Plan

```
=== Execution Plan ===
Total tasks: 8
Estimated time: 15-20 minutes
Estimated LLM cost: $0.50-0.80
Critical path: Task 1 → Task 2 → Task 5 → Task 7

Parallel group 1: [Task 1, Task 3] (no dependencies)
Sequential: Task 2 → Task 5 → Task 7
Parallel group 2: [Task 4, Task 6] (independent of each other)

Budget check: PASS (estimated $0.80 < $5.00 limit)
```

### Step 5: Execute with Monitoring

During execution:
- Track actual vs. estimated cost per task
- Track actual vs. estimated time per task
- If cost exceeds estimate by 2x, pause and reassess
- If a task takes longer than 5 minutes, consider splitting

### Step 6: Post-Execution Analysis

After the plan completes:
- Compare actual cost vs. estimate
- Compare actual time vs. estimate
- Note which estimates were accurate and which weren't
- Feed back into future plan estimates

## Integration with JobOrion

This skill is particularly relevant for:
- **Phase 2 (Tools)** — 8 tasks with parallel groups
- **Phase 3 (Orchestrator)** — Complex dependency graph
- **Phase 5 (Autonomy)** — Budget-critical execution

For each phase:
1. Write the plan (using `writing-plans`)
2. Orchestrate execution (using this skill)
3. Verify completion (using `verification-before-completion`)

## Anti-Patterns

- **"Just execute, we'll track costs later"** — Budget surprises kill projects. Estimate first.
- **"The critical path doesn't matter"** — It determines your minimum execution time. Know it.
- **"I'll parallelize everything"** — Only parallelize truly independent tasks. Dependencies cause race conditions.
- **"Estimates are a waste of time"** — A 2-minute estimate saves 20 minutes of surprised debugging when costs blow up.
