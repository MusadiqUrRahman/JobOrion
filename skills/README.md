# Skills Index

Actionable development skills used throughout JobOrion. Each skill is a
working protocol — not documentation. When a task matches a skill's trigger,
load and follow it.

## Available Skills

| Skill | When to Use | Iron Law |
|-------|-------------|----------|
| [writing-plans](writing-plans.md) | Before starting any implementation work | No code without a written plan first |
| [executing-plans](executing-plans.md) | When executing a plan with multiple tasks | No skipping tasks, no reordering without justification |
| [systematic-debugging](systematic-debugging.md) | When a test fails or a bug appears | No fixes without root cause investigation first |
| [verification-before-completion](verification-before-completion.md) | Before claiming any task is done | No completion claims without fresh verification evidence |
| [subagent-driven-development](subagent-driven-development.md) | When a phase has 3+ independent tasks | No monolithic implementation — dispatch per task |
| [plan-orchestrate](plan-orchestrate.md) | When converting a plan into executable actions | No action without budget estimate and dependency check |

## How Skills Work

1. **Trigger recognition** — A situation matches a skill's "When to Use"
2. **Load the skill** — Read the skill file completely before acting
3. **Follow the protocol** — Execute the steps in order, respecting iron laws
4. **Verify with evidence** — Every skill ends with verification requirements

## Skill Chain

Skills compose into a workflow:

```
writing-plans → executing-plans → verification-before-completion
                     ↓
            subagent-driven-development (for large phases)
                     ↓
              plan-orchestrate (for orchestrator phase)
                     ↓
          systematic-debugging (when things go wrong)
```

## Source Attribution

These skills are adapted from open-source agent skill libraries:

| Source | Skills Adopted | License |
|--------|---------------|---------|
| [obra/superpowers](https://github.com/obra/superpowers) | writing-plans, executing-plans, systematic-debugging, verification-before-completion, subagent-driven-development | MIT |
| [affaan-m/ecc](https://github.com/affaan-m/ecc) | plan-orchestrate | MIT |

The patterns below are distilled and adapted specifically for JobOrion's
CLI-only, Python 3.11+ architecture.
