# Planning

## Overview

Planning is how the orchestrator decomposes a user goal into a sequence of actions. The planner does not execute anything — it produces a plan. The orchestrator executes it.

Planning is the primary form of agency in JobOrion. Everything else is tooling.

## Goal Structure

A goal is a natural language description of what the user wants. The goal parser converts it into a structured goal object:

```python
@dataclass
class Goal:
    query: str                    # search terms
    filters: dict                 # remote, salary, location
    actions: set[str]             # discover, enrich, score, tailor, cover, apply
    limits: dict                  # max_jobs, max_applications
    constraints: dict             # max_cost, max_duration
```

## Planning Process

### Step 1: Parse Goal

Convert natural language to structured goal:

```
"Find 10 remote Python jobs paying 150k+, apply to the best"

-> Goal(
    query="python",
    filters={"remote": True, "min_salary": 150000},
    actions={"discover", "enrich", "score", "tailor", "cover", "apply"},
    limits={"max_jobs": 10, "max_applications": 5},
    constraints={"max_cost": None, "max_duration": None}
)
```

### Step 2: Check Memory

Before planning, check what memory says:
- Which sites are reliable? (use those first)
- Which sites are blocked? (skip those)
- What strategies worked before? (replicate success)
- What failed before? (avoid repeating failures)

### Step 3: Estimate Costs

For each action in the plan, estimate:
- Token cost (for LLM calls)
- Time cost (for scraping, enrichment)
- Dollar cost (for API calls)

Sum the estimates and compare against the user's budget (or default budget).

### Step 4: Generate Plan

A plan is an ordered list of steps. Each step has:
- Tool to call
- Parameters to pass
- Estimated cost
- Dependencies (which steps must complete first)
- Failure handling (what to do if this step fails)

### Step 5: Present for Approval

Show the plan to the user:

```
Plan: Find 10 remote Python jobs

Step 1: Discover jobs
  Tool: scrape_jobspy(query="python", remote=True)
  Estimate: $0.00, 30s
  Depends on: nothing

Step 2: Enrich top 20 results
  Tool: enrich_batch(urls=[...])
  Estimate: $0.02, 2m
  Depends on: Step 1

Step 3: Score enriched jobs
  Tool: score_batch(urls=[...], resume="resume.md")
  Estimate: $0.15, 1m
  Depends on: Step 2

Step 4: Tailor top 8 resumes
  Tool: tailor_resume(url=..., job=..., resume=...)
  Estimate: $0.40, 3m
  Depends on: Step 3

Step 5: Write top 5 cover letters
  Tool: write_cover_letter(url=..., job=..., resume=..., profile=...)
  Estimate: $0.20, 2m
  Depends on: Step 3

Step 6: Generate PDFs
  Tool: convert_all_to_pdf()
  Estimate: $0.00, 10s
  Depends on: Step 4, Step 5

Total estimated cost: $0.77
Total estimated time: 8m 40s

Proceed? [y/N]
```

## Plan Types

### Discovery-Only Plan

For users who want to find jobs but not apply:

```
Goal: "Find 10 remote Python jobs"
Plan: discover -> enrich -> score -> generate report
No tailoring, no cover letters, no applications
```

### Full Pipeline Plan

For users who want the complete flow:

```
Goal: "Find and apply to 5 Python jobs"
Plan: discover -> enrich -> score -> tailor -> cover -> convert -> apply
```

### Targeted Plan

For users who already have specific jobs:

```
Goal: "Score and tailor for these 3 URLs"
Plan: enrich(3 URLs) -> score -> tailor -> cover -> convert
No discovery step needed
```

### Maintenance Plan

For periodic background runs:

```
Goal: "Check for new Python jobs daily"
Plan: discover -> enrich -> score -> filter new jobs -> report
No application without explicit approval
```

## Plan Adaptation

The orchestrator adapts the plan during execution:

**When a step fails:**
- If discovery from Site A fails, try Site B
- If enrichment fails for a URL, skip it and continue with the rest
- If scoring fails, use the last known score (if available)

**When results are better than expected:**
- If discovery finds 50 jobs instead of 10, limit scoring to top 20
- If scoring finds 15 high-scoring jobs instead of 5, increase tailoring batch

**When results are worse than expected:**
- If discovery finds 3 jobs instead of 10, reduce tailoring to top 3
- If scoring finds no jobs above threshold, lower the threshold and re-score
- If no jobs survive enrichment, report the failure and stop

**When budget is running low:**
- Skip optional steps (cover letters, advanced tailoring)
- Reduce batch sizes
- Use cheaper LLM models for lower-stakes decisions

## Replanning

After each major step, the orchestrator evaluates whether the plan still makes sense:

```
After discovery:
  Found 47 jobs. Original plan: enrich 20. Adjusted: enrich 20 (cost-aware).

After scoring:
  3 jobs scored 8+. Original plan: tailor top 8. Adjusted: tailor top 3.

After enrichment:
  8 URLs failed. Original plan: score 20. Adjusted: score 12.
```

Replanning is not a sign of failure — it is a sign of intelligence. The plan is a hypothesis about what will work. Reality is the test.

## Cost-Aware Planning

The planner respects budgets:

1. **Pre-flight check:** Before executing, sum all estimated costs. If total exceeds budget, reduce scope.
2. **Stage budgets:** Allocate budget across stages. Discovery gets 10%, enrichment 20%, scoring 20%, tailoring 30%, cover letters 20%.
3. **Real-time adjustment:** After each stage, check actual spend vs estimate. If over budget, reduce the next stage.
4. **Hard stop:** If total cost exceeds 90% of budget, stop immediately. Report what was completed.
