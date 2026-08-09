# Changelog

All notable changes to this project are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased

### Added
- Dynamic agent loop (`joborion run --goal "..." --autonomous`): the LLM picks
  each tool based on observed results, self-corrects on errors, and stops when
  the goal is met or budget limits are reached. `--agentic` remains as an alias.
- Field-agnostic goal search: query extraction works for any profession
  (accountant, nurse, designer, ...), falling back to the profile's target role.

## [0.4.0] - 2026-08-08

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
- Legacy provider view in `joborion report`: databases created before
  `provider_metrics` existed now show providers from `source_stats` + job
  strategy history.
