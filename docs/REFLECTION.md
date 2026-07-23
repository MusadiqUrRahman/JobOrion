# Reflection

## Overview

Reflection is how the system learns from its own performance. After each run, the reflector analyzes what happened, identifies patterns, and updates memory. Over time, the system gets better at its job — not by changing code, but by changing behavior.

Reflection is the difference between a tool and an agent. A tool does the same thing every time. An agent gets better with experience.

## When Reflection Happens

### After Every Run (Automatic)

The orchestrator triggers reflection automatically after each run:

1. Compare planned vs actual outcomes
2. Identify failures and their causes
3. Check scoring calibration
4. Update site memory
5. Generate recommendations

### On User Request (Manual)

```
joborion reflect                    # analyze last run
joborion reflect --run-id abc123    # analyze specific run
joborion reflect --last 5           # analyze last 5 runs together
```

### Periodically (Phase 5)

In autonomous mode, the system reflects weekly:
- Aggregate all runs from the past week
- Identify trending issues (sites getting worse, costs increasing)
- Update long-term memory

## Reflection Process

### Step 1: Collect Data

Gather all data from the run being analyzed:
- The goal and plan
- Each action taken (tool, parameters, result)
- Cost and duration for each action
- Errors encountered and how they were handled
- Final outcomes (jobs found, scored, applied)

### Step 2: Analyze Outcomes

Compare planned vs actual:

```
Planned:  discover 30 -> enrich 20 -> score 20 -> tailor 8 -> cover 5
Actual:   discover 47 -> enrich 35 -> score 35 -> tailor 12 -> cover 8
Status:   Exceeded expectations (more jobs found than planned)
```

### Step 3: Identify Failures

Categorize every failure:

```
Failures:
  - Indeed: rate limited after 15 jobs (E002)
  - 3 URLs: page structure changed, extraction failed (E003)
  - 2 scores: LLM returned invalid JSON, retried successfully (E005)
```

### Step 4: Check Scoring Calibration

Analyze whether scoring predictions are accurate:

```
Score distribution:
  9: 2 jobs (5%)
  8: 6 jobs (17%)
  7: 14 jobs (40%)
  6: 8 jobs (23%)
  5: 5 jobs (14%)

Assessment: Scores cluster heavily in 6-8 range.
Recommendation: Widen the score range or adjust scoring prompt.
```

If application outcomes are available:
```
Applications with scores:
  Score 9 -> 1 callback (50% response rate)
  Score 8 -> 1 callback (17% response rate)
  Score 7 -> 0 callbacks (0% response rate)

Assessment: Scores above 8 correlate with callbacks. 7 is borderline.
Recommendation: Raise the application threshold to 8.
```

### Step 5: Update Memory

Based on the analysis, update site memory:

```
Site memory updates:
  indeed.com: total_attempts +1, successful_extractions +1, rate_limited = true
  lever.co: total_attempts +1, successful_extractions +1, success_rate = 94%
  greenhouse.io: total_attempts +1, blocked_reason = "page structure changed"
```

### Step 6: Generate Recommendations

Produce actionable recommendations:

```
Recommendations:
  1. Block greenhouse.io until page structure is fixed
  2. Add 60s delay between Indeed requests to avoid rate limiting
  3. Raise application threshold from 7 to 8
  4. Consider reducing tailoring depth (current avg 3.2 sections, target 2.0)
```

## Reflection Output

The reflector produces a structured reflection record:

```python
@dataclass
class Reflection:
    reflection_id: str
    run_id: str
    analyzed_at: str
    overall_rating: str          # "good" | "ok" | "poor"
    what_went_well: list[str]
    what_failed: list[str]
    strategy_changes: list[str]
    memory_updates: list[str]
    recommendations: list[str]
    scoring_calibration: dict
    cost_analysis: dict
```

This record is stored in `reflection_log` and referenced by future runs.

## Learning Loops

### Short-Term Learning (Within a Run)

During a run, the orchestrator adapts based on immediate results:
- Discovery failed on Site A -> try Site B
- Scoring found no high matches -> lower threshold
- Enrichment is slow -> skip low-priority URLs

This is not reflection. This is real-time adjustment.

### Medium-Term Learning (Across Runs)

After each run, the reflector updates memory:
- Site reliability scores change
- Scoring calibration adjusts
- Strategy recommendations are generated

The next run reads this memory and benefits from it.

### Long-Term Learning (Over Weeks)

The periodic reflector (Phase 5) aggregates across many runs:
- Trends are identified (site X is getting worse)
- Costs are analyzed (which stage is most expensive)
- Outcomes are correlated (which strategies lead to callbacks)

This produces high-level strategy recommendations.

## Reflection Anti-Patterns

### 1. Over-Optimization

If the system optimizes too aggressively for recent outcomes, it may:
- Block a site after one failure (premature)
- Lower a threshold because one run had no matches (reactive)

**Mitigation:** Minimum sample sizes before memory updates. At least 3 attempts before blocking a site.

### 2. Confirmation Bias

If the system only looks at successful outcomes, it may:
- Ignore that low-scoring jobs sometimes succeed
- Overweight sites that happened to work once

**Mitigation:** Always analyze failures, not just successes. Track both positive and negative outcomes.

### 3. Cost of Reflection

Reflection itself costs tokens. If reflection is too detailed or too frequent:
- Each reflection costs $0.01-0.05 in LLM tokens
- Daily reflection adds up quickly

**Mitigation:** Reflection is optional and on-demand. Automatic reflection only happens after full pipeline runs. Quick diagnostic runs do not trigger reflection.
