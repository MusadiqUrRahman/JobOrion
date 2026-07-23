# Autonomous Workflow

## Overview

Autonomous mode is the culmination of JobOrion's agent capabilities. In this mode, the system receives a goal, plans the work, executes the plan, learns from the results, and reports back — all without human intervention.

This is Phase 5. It depends on memory (Phase 1), tools (Phase 2), orchestrator (Phase 3), and reflection (Phase 4) all being in place.

## Workflow States

```
IDLE -> PLANNING -> APPROVED -> EXECUTING -> REFLECTING -> IDLE
  ^        |           |           |            |
  |        v           v           v            |
  |     REJECTED    PAUSED     FAILED -----+    |
  |                                |      |    |
  +---- CANCELLED <----------------+      +--->+
```

**IDLE:** No active run. System is waiting for a goal.

**PLANNING:** The system is parsing the goal, checking memory, and generating a plan.

**APPROVED:** The plan has been approved by the user (or auto-approved in `--yes` mode).

**EXECUTING:** The system is running the plan, calling tools, recording results.

**PAUSED:** The system is waiting for human input (approval gate, error escalation).

**REFLECTING:** The run is complete. The system is analyzing results and updating memory.

**FAILED:** The run encountered an unrecoverable error. Results are saved, memory is updated.

**REJECTED:** The user rejected the plan. The system returns to IDLE.

**CANCELLED:** The user interrupted execution. Progress is saved, partial results are reported.

## Execution Modes

### Interactive Mode (Default)

```
joborion run --goal "find 10 remote Python jobs"
```

The system presents a plan, waits for approval, executes with progress updates, and reports results. The user can interrupt at any point.

### Semi-Autonomous Mode

```
joborion run --goal "..." --semi
```

The system executes the plan but pauses before each application submission for approval. Everything else (discovery, enrichment, scoring, tailoring) runs automatically.

### Fully Autonomous Mode

```
joborion run --goal "..." --auto
```

The system executes the entire plan without pausing. It still respects the cost cap and application limit. It reports results when done.

### Autonomous with Auto-Approve

```
joborion run --goal "..." --auto --yes
```

No approval gates at all. The system runs everything, including applications. Use with caution.

## Autonomous Run Lifecycle

### 1. Goal Reception

The user provides a goal via CLI or scheduled trigger:

```
$ joborion run --goal "Find 5 remote senior Python jobs, apply to the best 3"
```

### 2. Goal Parsing

The system parses the goal into structured parameters:

```
Goal:
  query: "senior python"
  filters: {remote: true}
  actions: {discover, enrich, score, tailor, cover, apply}
  limits: {max_jobs: 5, max_applications: 3}
```

### 3. Plan Generation

The planner generates a step-by-step plan:

```
Step 1: Discover jobs (scrape_jobspy)
Step 2: Enrich discovered jobs (enrich_batch)
Step 3: Score enriched jobs (score_batch)
Step 4: Tailor top resumes (tailor_resume x3)
Step 5: Write cover letters (write_cover_letter x3)
Step 6: Generate PDFs (convert_all_to_pdf)
Step 7: Apply to top 3 (batch_apply)

Estimated cost: $1.12
Estimated time: 11m
```

### 4. Approval Gate (Interactive/Semi Modes)

The system presents the plan and waits for approval:

```
Proceed with this plan? [y/N]
```

In `--auto` mode, this step is skipped. In `--auto --yes` mode, all subsequent gates are also skipped.

### 5. Execution

The orchestrator executes each step:

```
[1/7] Discovering jobs... 30 found (2m 14s, $0.00)
[2/7] Enriching jobs... 25 enriched, 5 failed (3m 02s, $0.03)
[3/7] Scoring jobs... 8 scored 7+ (1m 18s, $0.18)
[4/7] Tailoring resumes... 3 tailored (2m 45s, $0.42)
[5/7] Writing cover letters... 3 written (1m 52s, $0.21)
[6/7] Generating PDFs... 3 PDFs (8s, $0.00)
[7/7] Applying... 3 applied (1m 34s, $0.00)
```

### 6. Reflection

After execution completes:

```
Reflection:
  Overall: Good run. Found 30 jobs, applied to 3.
  Failures: 5 URLs failed enrichment (page structure changed)
  Scoring: Avg score 7.2, range 4-9
  Cost: $0.84 total ($0.16 under budget)
  Recommendations: Consider blocking greenhouse.io, add retry for E003 errors
```

### 7. Report

Final report to the user:

```
=== JobOrion Run Complete ===
Goal: Find 5 remote senior Python jobs, apply to best 3
Duration: 12m 55s | Cost: $0.84

Applied to:
  1. Senior Python Engineer @ Stripe (score: 9)
  2. Backend Engineer @ Notion (score: 8)
  3. Sr. SWE @ Vercel (score: 8)

Results saved to ~/.joborion/results/run_20250716_abc123/
```

## Cost Budget System

### Setting Budgets

```
joborion run --goal "..." --max-cost 2.00
joborion run --goal "..." --max-cost 0.50
```

Default budget: $5.00 per run.

### Budget Allocation

```
Total budget: $5.00

  Discovery:      $0.50  (10%)
  Enrichment:     $1.00  (20%)
  Scoring:        $1.00  (20%)
  Tailoring:      $1.50  (30%)
  Cover letters:  $0.75  (15%)
  Buffer:         $0.25  (5%)
```

### Budget Enforcement

- Before each action, check if remaining budget allows it
- If a stage exceeds its allocation, reduce scope for the next stage
- If total cost hits 90% of budget, stop immediately
- If total cost hits 100% of budget, hard stop with error

### Budget Reporting

```
Cost breakdown:
  Discovery:    $0.02  (2%)
  Enrichment:   $0.18  (18%)
  Scoring:      $0.42  (42%)
  Tailoring:    $0.22  (22%)
  Cover:        $0.00  (0% — used cache)
  Total:        $0.84  (84% of $1.00 budget)
```

## Error Handling in Autonomous Mode

### Transient Errors (E001, E002)

Automatic retry with exponential backoff:
- 1st retry: wait 5s
- 2nd retry: wait 15s
- 3rd failure: skip and log

### Permanent Errors (E003, E004, E005)

Skip immediately, log the error, continue with remaining work. Do not retry.

### Budget Errors (E006)

Stop immediately. Do not proceed. Report partial results.

### Database Errors (E008)

Retry once. If still failing, abort the run. Save progress to a JSON file as fallback.

### Unknown Errors (E010)

Log full context (error message, stack trace, action parameters). Skip and continue.

## Scheduled Runs (Phase 5)

### Configuration

```json
{
  "schedule": {
    "enabled": true,
    "goal": "Find new Python jobs, score and tailoring ready",
    "frequency": "daily",
    "time": "08:00",
    "max_cost_per_run": 2.00,
    "max_cost_per_week": 10.00,
    "auto_apply": false,
    "notify": true
  }
}
```

### Behavior

- Daily runs discover new jobs and score them
- New jobs are added to the "ready to apply" queue
- No applications without explicit user approval (unless `auto_apply: true`)
- Weekly summary email sent every Sunday
- Cost tracked across the week, auto-stop if weekly budget exceeded

### Notification

When a scheduled run completes:
- Terminal notification (if interactive)
- Email summary (if configured)
- Update to `~/.joborion/inbox.json` for external tools to pick up
