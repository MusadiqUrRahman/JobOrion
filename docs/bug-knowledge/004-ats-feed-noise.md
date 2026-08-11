# 004: ATS board feeds flood the DB with irrelevant jobs (96% noise)

## Symptom
After `run search` with queries "ai agent / agentic chat bot / python
developer / calling agent", the DB held 760 jobs but only 33 titles matched
the queries at all. greenhouse-pinterest, greenhouse-instacart,
greenhouse-gitlab, greenhouse-datadog, etc. contributed ~290 jobs of every
job family (Counsel, Account Executive, Customer Success, HR, ...).

## Root Cause
The ATS-board providers (Greenhouse/Lever/Ashby/SmartRecruiters public job
feeds, `src/joborion/discovery/` + `config/companies.yaml`) pull the FULL
job feed per company and do not apply the search query. The relevance gate
applies only location/arrangement/dedup filters, not title relevance.
Discovery runs on every query, so an unfiltered dump is stored on each run.

## Repro
1. `searches.yaml` with queries for a niche role.
2. `joborion run search`.
3. `joborion status` shows hundreds of unrelated titles; only a handful
   match the query.

## Fix
Apply a query/title relevance filter to ATS-board results before storing
(score title against query terms; store only matches, or tag non-matches as
low priority). Until fixed, prune the DB to the relevant subset before
scoring to avoid burning LLM quota on noise.

## Verification
`joborion jobs` after search shows mostly query-relevant titles.

## Affected Files
- src/joborion/discovery/ (ATS provider)
- src/joborion/filter/ (apply_relevance_gate — add title-vs-query check)
