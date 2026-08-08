# Changelog

All notable changes to this project are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased

### Added
- Multi-profile workspace isolation: `joborion --profile <name> <command>`
  runs in an isolated workspace, plus `joborion profile create/list` and the
  `JOBORION_PROFILE` environment variable.
- Post-run automation flags: `--notify` (email a digest) and `--report`
  (print the analytics report) on `joborion run` and `joborion daemon`.
- `joborion report` analytics command — pipeline funnel, provider metrics,
  cost ledger, and run history (read-only, no LLM).
- Adzuna job provider (requires `ADZUNA_APP_ID` / `ADZUNA_APP_KEY`) and the
  Working Nomads remote board.
