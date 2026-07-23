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

# Run the full pipeline
joborion run

# Run individual stages
joborion run search
joborion run details
joborion run evaluate
joborion run tailor
joborion run letter
joborion run export

# Goal-driven mode (AI plans and executes)
joborion plan "Find 10 remote Python jobs"
joborion run --goal "Find senior React jobs, score them, tailor resumes"
```

## Tier System

JobOrion unlocks features progressively based on installed dependencies:

| Tier | Features | Requirements |
|------|----------|--------------|
| 1 - Discovery | Job scraping, search config | Python + pip |
| 2 - AI Scoring | Fit scoring, resume tailoring, cover letters | + LLM API key |
| 3 - Auto-Apply | Automated applications via Chrome | + Claude Code CLI + Chrome |

## Commands

```bash
joborion --help              # Show all commands
joborion init                # Set up config and profile
joborion run                 # Run full pipeline
joborion run search           # Scrape job boards
joborion run details         # Enrich job descriptions
joborion run evaluate        # Score jobs against your resume
joborion run tailor          # Tailor resumes for top jobs
joborion run letter          # Generate cover letters
joborion run export          # Convert tailored resumes to PDF
joborion status              # Show pipeline status
joborion dashboard           # Generate HTML dashboard
joborion apply               # Auto-apply to jobs (Tier 3)
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
