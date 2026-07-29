# JobOrion

AI-powered end-to-end job application pipeline. Discovers jobs, scores fit, tailors resumes, writes cover letters, and auto-applies — all from the command line.

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
joborion doctor     # Check your setup and diagnose issues
joborion open       # Open ~/.joborion/ in file explorer
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

### Advanced
```bash
joborion run --goal "your goal"  # AI plans and executes from a description
joborion apply                   # Auto-apply via browser (Tier 3)
joborion plan "your goal"        # Preview plan without executing
joborion dashboard               # Generate HTML dashboard
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
```

Set the `JOBORION_DIR` environment variable to override the default location.

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
