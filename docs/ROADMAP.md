# Roadmap

> Status document. Superseded by `docs/plans/sourcing-revamp.md` — this file is
> kept as the canonical status of delivered phases, not as forward planning.
> For active planning use `docs/plans/` instead.

## Status

All planned phases are COMPLETE and on `main`.

```
Phase 0: Foundation        COMPLETE  installable package, tests, README
Phase 1: Memory            COMPLETE  site_memory, run_log, cost_ledger
Phase 2: Tools             COMPLETE  pipeline stages as composable tools
Phase 3: Orchestrator      COMPLETE  agent decides what to do
Phase 4: Reflection        COMPLETE  learns from outcomes
Phase 5: Full Autonomy     COMPLETE  goal-driven operation with gates
Sourcing Revamp (A–F)      COMPLETE  multi-provider sourcing, scheduled runs, digest, dashboard
```

## Delivered Capabilities

### Phase 0 — Foundation
- `pip install -e .` works, `joborion` command available
- README with setup instructions
- Unit tests for database, config, output_checker, document_converter
- CI linting with ruff

### Phase 1 — Memory
- `site_memory` table tracking per-site outcomes
- `run_log` table recording each pipeline run
- `cost_ledger` tracking token usage and costs
- Memory read/write functions used by discovery and enrichment
- Source routing that uses memory to prioritize reliable sources

### Phase 2 — Tools
- Tool interface (name, description, parameters, execute)
- `tools/` — discovery, enrichment, scoring, documents, database
- Cost estimation and error classification per tool

### Phase 3 — Orchestrator
- `agent/orchestrator.py` — main decision loop
- `agent/planner.py` — goal decomposition into action sequences
- Context window management and cost budget enforcement
- Error recovery with retry and escalation
- CLI integration (`joborion run --goal "..."`)

### Phase 4 — Reflection
- `agent/reflector.py` — post-run analysis
- `reflection_log` table
- Scoring calibration analysis
- Site strategy recommendations
- CLI command: `joborion reflect`

### Phase 5 — Full Autonomy
- `joborion run --auto/--semi` — goal-driven runs with human approval gates
- Interactive gates for cost (>=50% budget) and error-rate thresholds
- Apply gate in semi mode; cost cap enforcement with automatic stop
- Run summary with reflection

### Sourcing Revamp (A–F) — see `docs/plans/sourcing-revamp.md`
- Multi-provider sourcing: jobspy + 4 direct providers, persisted to DB
- Provider-run reporting and per-provider error capture
- `SearchProvidersTool` registered in the agent registry (planner emits
  `providers` stage for goal-driven search)
- Scheduled runs: `joborion daemon [--interval daily] [--at HH:MM]` and
  `run --schedule hourly|daily|weekly`
- Email digest: `joborion notify [--to] [--goal]`
- HTML dashboard: "Matched Jobs by Provider" section in `joborion dashboard`

## Verification

```bash
uv run pytest -q         # full suite green (666 tests)
uv run ruff check src tests
```

## Next Steps (not yet planned)

Forward work lives in `docs/plans/`. Candidate directions for a future plan:

- Multi-profile / workspace isolation
- Richer provider coverage (more boards, geo/remote filters)
- Reporting analytics beyond the current digest and dashboard
- CI pipelines (GitHub Actions) for lint + tests
