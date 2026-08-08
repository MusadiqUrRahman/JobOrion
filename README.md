# JobOrion

AI-powered end-to-end job application pipeline. Discovers jobs, scores fit,
tailors resumes, writes cover letters, and auto-applies — all from the command
line.

<!-- commitagent: 2026-08-04T01:53:12.987Z -->

## Features

- **Discovery** — scrapes 15+ sources: job boards (Indeed, LinkedIn, RemoteOK,
  Remotive, WeWorkRemotely, Jobicy, Arbeitnow, Working Nomads, Hacker News),
  Workday ATS portals, Adzuna, and ATS feeds (Greenhouse, Lever, Ashby)
- **AI scoring** — fit-scores every job against your resume and profile
- **Tailoring** — generates tailored resumes and cover letters per job
- **Auto-apply** — submits applications via Chrome (Tier 3)
- **Goal-driven mode** — describe what you want; JobOrion plans and executes
- **Analytics** — `joborion report` prints pipeline telemetry (read-only, no LLM)
- **Workspaces** — isolated profiles for separate job hunts (`--profile`)

## Requirements

- Python 3.11+
- Chrome/Chromium (for auto-apply, Tier 3)
- An LLM API key (Gemini or OpenAI, for scoring/tailoring, Tier 2)

## Quick Start

```bash
# Install
pip install -e .

# Initialize (creates ~/.joborion/ with config files)
joborion init

# One command — runs everything: search → score → tailor → cover letters
joborion run
```

## Tier System

JobOrion unlocks features progressively based on installed dependencies:

| Tier | Features | Requirements |
|------|----------|--------------|
| 1 - Discovery | Job scraping, search config | Python + pip |
| 2 - AI Scoring | Fit scoring, resume tailoring, cover letters | + LLM API key |
| 3 - Auto-Apply | Automated applications via Chrome | + Claude Code CLI + Chrome |

## All Commands

### Setup
```bash
joborion init       # First-time setup (profile, resume, API key)
joborion configure  # Set search preferences (arrangement, locations, types)
joborion check      # Check your setup and diagnose issues
joborion open       # Open your data folder in the file explorer
joborion status     # Show pipeline statistics
```

### Pipeline (runs sequentially)
```bash
joborion run                     # Run ALL stages (search → details → evaluate → tailor → letter → export)
joborion run search              # Stage 1: Scrape job boards
joborion run details             # Stage 2: Enrich job descriptions
joborion run evaluate            # Stage 3: Score jobs vs your resume (needs LLM)
joborion run tailor              # Stage 4: Tailor resumes for top jobs (needs LLM)
joborion run letter              # Stage 5: Generate cover letters (needs LLM)
joborion run export              # Stage 6: Convert to PDF
```

Pipeline automation:
```bash
joborion run --schedule daily    # Repeat hourly, daily, or weekly
joborion run --notify            # Email a digest when the run finishes
joborion run --report            # Print the analytics report after the run
```

### Analytics & Reporting
```bash
joborion report                  # Pipeline funnel, providers, cost, run history (read-only, no LLM)
joborion report --days 30        # Lookback window in days
joborion report --top 10         # Max providers/runs shown
joborion report --json           # Machine-readable JSON output
joborion notify                  # Email a digest of the latest stats on demand
joborion reflect                 # Analyze past runs and generate insights
```

### Profiles / Workspaces
```bash
joborion profile create myjob    # Create an isolated workspace
joborion profile list            # List all profiles
joborion --profile myjob run     # Run any command inside a workspace
```

Each profile gets its own database, resume, and config under
`~/.joborion/profiles/<name>/`, so you can run separate job hunts side by side.
Set the `JOBORION_PROFILE` environment variable instead of the flag if you
prefer.

### Advanced
```bash
joborion run --goal "your goal"  # AI plans and executes from a description
joborion apply                   # Auto-apply via browser (Tier 3)
joborion plan "your goal"        # Preview plan without executing
joborion dashboard               # Generate HTML dashboard
joborion jobs                    # Browse jobs from the database
```

## Configuration

All user data lives in `~/.joborion/`:

```
~/.joborion/
  profile.json         # Your profile (skills, experience, preferences)
  resume.txt           # Your base resume
  searches.yaml        # Search queries and filters
  .env                 # API keys and environment variables
  joborion.db          # SQLite database (job records, history)
  tailored_resumes/    # Generated tailored resumes
  cover_letters/       # Generated cover letters
  logs/                # Pipeline logs
  profiles/            # Isolated workspaces (one folder per profile)
```

Set the `JOBORION_DIR` environment variable to override the default location,
and `JOBORION_PROFILE` to default to a specific workspace.

### Job Boards

Sources are configured in the package-shipped `sources.yaml` and run in
priority order. Most are free public feeds that need no keys:

- **Adzuna** needs `ADZUNA_APP_ID` and `ADZUNA_APP_KEY` in `~/.joborion/.env`;
  without them the provider is skipped gracefully
- **Remote boards**: Remotive, RemoteOK, WeWorkRemotely, Jobicy, Arbeitnow,
  Working Nomads, Hacker News "Who is Hiring"
- **ATS boards**: Greenhouse, Lever, Ashby, SmartRecruiters public feeds

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check src/
ruff format src/
```

## License

AGPL-3.0-only
