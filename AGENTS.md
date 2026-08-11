# AGENTS.md — JobOrion Development Conventions

## Project Identity

**JobOrion** — AI-powered end-to-end job application pipeline.
CLI-only. No backend. No frontend. Python 3.11+.

**Architecture principle:** Determinism by default, agency by necessity.

## Skills

Every development action follows a skill protocol. Load the relevant skill
before starting work.

| Skill | When to Use | File |
|-------|-------------|------|
| Writing Plans | Before any implementation | `skills/writing-plans.md` |
| Executing Plans | When implementing a written plan | `skills/executing-plans.md` |
| Systematic Debugging | When a test fails or bug appears | `skills/systematic-debugging.md` |
| Verification Before Completion | Before claiming anything is done | `skills/verification-before-completion.md` |
| Subagent-Driven Dev | When a phase has 3+ independent tasks | `skills/subagent-driven-development.md` |
| Plan Orchestrate | When converting plans to execution | `skills/plan-orchestrate.md` |
| Bug Knowledge | When any bug/error appears — check the KB first | `skills/bug-knowledge.md` |

Full index: `skills/README.md`

## Bug Knowledge Base

`docs/bug-knowledge/` is the registry of every confirmed issue and its fix.
**Whenever any error or unexpected behavior appears, check it FIRST** (see
`skills/bug-knowledge.md`): grep `index.md` + the `## Symptom` lines, apply the
documented fix if matched, otherwise investigate and log a new `NNN-<slug>.md`
file before the fix is done.

## Development Workflow

```
1. PLAN    — skills/writing-plans.md
2. REVIEW  — Critical review before starting (see executing-plans Step 5)
3. BUILD   — skills/executing-plans.md (TDD, sequential)
4. VERIFY  — skills/verification-before-completion.md
5. COMMIT  — Descriptive message, conventional format
```

## Code Conventions

### Style
- Line length: 120 (ruff configured)
- Python 3.11+ features: `X | None`, `match`, `type` aliases
- No type: ignore unless absolutely necessary
- No comments unless explaining WHY, not WHAT
- No docstrings on obvious functions; document non-obvious behavior

### Imports
- Group: stdlib → third-party → local
- No unused imports (ruff enforces)
- Use `from joborion.module import func` not `import joborion`

### Error Handling
- Classify every error: transient / permanent / degraded
- Transient: retry with backoff (max 2 retries)
- Permanent: skip and log, continue with remaining work
- Degraded: proceed with reduced quality, note in results
- Never silently swallow errors

### Database
- All migrations via `ensure_columns()` — add-only, never remove
- Thread-local connections via `get_connection()`
- WAL mode enabled on all connections
- Use parameterized queries, never f-strings for SQL

### LLM Calls
- Always record cost after every call
- Always check budget before expensive calls
- Classify refusal/hallucination as permanent errors
- Never retry safety refusals

## Testing Conventions

### Test Structure
- One test file per source module: `test_<module>.py`
- Test classes group related tests: `class TestFunctionName:`
- Test methods: `test_<scenario>` — no test_ prefix duplication
- Use `pytest` fixtures for setup, especially `tmp_path` for DB tests

### What to Test
- Happy path (correct input → correct output)
- Edge cases (empty input, None, boundary values)
- Error cases (invalid input → correct error)
- Integration points (DB operations with real SQLite)

### What NOT to Test
- Third-party library internals
- Obvious getters/setters
- Framework boilerplate

### Test DB Pattern
```python
@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "test.db"
    close_connection(str(db_path))
    c = init_db(str(db_path))
    yield c
    close_connection(str(db_path))
```

## Phase Roadmap

| Phase | Goal | Depends On | Status |
|-------|------|------------|--------|
| 0 | Foundation (installable, tested, documented) | — | COMPLETE |
| 1 | Memory (site_memory, run_log, cost_ledger) | 0 | COMPLETE |
| 2 | Tools (pipeline stages as composable tools) | 0 | COMPLETE |
| 3 | Orchestrator (agent decides what to do) | 1, 2 | COMPLETE |
| 4 | Reflection (learn from outcomes) | 1, 3 | COMPLETE |
| 5 | Full Autonomy (goal-driven operation) | 1-4 | COMPLETE |

## File Naming

- Modules: `snake_case.py`
- Tests: `test_snake_case.py`
- Config: `kebab-case.yaml`
- Docs: `UPPER_CASE.md` for specs, `lower_case.md` for guides
- Directories: `snake_case/`

## Commit Messages

Format: `<type>: <description>`

Types: `feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `chore:`, `perf:`

## Security Rules

- **Personal data must NEVER be pushed to GitHub.** This includes profile/resume data, CV files (e.g. `cv-data.json`, `cv.txt`), application materials, emails, or any file containing real user information. Never stage, commit, or push such files. Keep them untracked and locally only.
- Never commit secrets, API keys, or tokens
- Never log sensitive data
- Use environment variables for secrets
- Validate all external input
- Use parameterized SQL queries
- Check `BANNED_WORDS` and `LLM_LEAK_PHRASES` on all LLM output

## Cost Awareness

Every LLM call must be tracked. Budget system:
1. Pre-flight: Estimate total cost before starting
2. Per-action: Check budget before each expensive action
3. Real-time: Update cost ledger after each action
4. Hard stop: Stop at 90% of budget, report partial results
5. Post-run: Analyze cost breakdown for optimization

Default budget: $5.00 per run. Configurable via `--max-cost`.
