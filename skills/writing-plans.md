# Writing Plans

**Trigger:** Before starting any implementation work that touches 2+ files or
adds a new feature.

**Iron Law:** NO CODE WITHOUT A WRITTEN PLAN FIRST.

## Protocol

### Step 1: Define the Goal

Write one sentence stating what the user will have when this plan is complete.
Be specific about observable outcomes, not internal states.

```
GOOD: "User can run `joborion run --goal 'remote python'` and see a
       structured plan before execution"
BAD:  "Add goal parsing functionality"
```

### Step 2: Map the File Surface

List every file that will be created or modified. For each file, state
exactly what changes. No vague "update X" — say what specifically changes.

```
Files to modify:
- src/joborion/agent/goal_parser.py (NEW) — GoalParser class with parse() method
- src/joborion/cli.py — add `plan` command, add `--goal` flag to `run`
- src/joborion/agent/__init__.py (NEW) — empty, makes agent a package

Files to create:
- tests/test_goal_parser.py — 8 test cases
```

### Step 3: Decompose into Tasks

Each task follows these rules:

- **One purpose** — If a task does two things, split it
- **2-5 minutes** — If it takes longer, decompose further
- **Exactly one test case** — Every task has a verification step
- **Exact file paths** — No ambiguity about what gets touched
- **Dependency-aware** — Tasks that depend on each other are sequenced

```
Task 1: Create GoalParser class
  File: src/joborion/agent/goal_parser.py
  Test: tests/test_goal_parser.py::TestGoalParser::test_parse_basic_goal
  Depends on: nothing

Task 2: Add GoalParser.parse() with regex extraction
  File: src/joborion/agent/goal_parser.py
  Test: tests/test_goal_parser.py::TestGoalParser::test_extracts_query_and_filters
  Depends on: Task 1

Task 3: Wire GoalParser into CLI plan command
  File: src/joborion/cli.py
  Test: tests/test_cli.py::test_plan_command_shows_plan
  Depends on: Task 2
```

### Step 4: Define Verification

For each task, specify the exact command that proves it works:

```bash
pytest tests/test_goal_parser.py::TestGoalParser::test_parse_basic_goal -v
```

For the overall plan, specify the full verification suite:

```bash
pytest tests/ -v
ruff check src/
joborion plan --goal "test"
```

### Step 5: Critical Review

Before executing, ask:

1. **Scope creep?** — Does the plan touch things not in the goal?
2. **Missing tasks?** — Is there a gap between steps?
3. **Wrong order?** — Can any tasks be parallelized?
4. **Over-engineered?** — Is the simplest approach sufficient?
5. **Testable?** — Can every task be verified independently?

If any answer reveals a problem, revise the plan before starting.

## Plan Output Format

Plans are saved to `docs/plans/` as markdown files:

```
docs/plans/phase-2-tools.md
```

The plan file contains Steps 1-5 above. During execution, check off tasks
as they complete.

## Anti-Patterns

- **"I'll figure it out as I go"** — You won't. Write the plan.
- **"This is too simple to plan"** — If it touches 2+ files, plan it.
- **"I'll add tests later"** — Tests are part of the plan, not an afterthought.
- **Planning then ignoring the plan** — The plan is a contract. Follow it.
