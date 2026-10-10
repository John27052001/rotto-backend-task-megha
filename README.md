# Rotto Backend Engineering Assessment

Python crawler for collecting UK job listings from Reed, LinkedIn, and Indeed, persisting normalized records in PostgreSQL, reconciling changes across repeated runs, and linking likely cross-source duplicates.

## Setup

Requirements:

- Python 3.9+
- Docker / Docker Compose

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create `.env` from `.env.example` and provide the assessment proxy credentials:

```env
PROXY_HOST=
PROXY_PORT=
PROXY_USERNAME=
PROXY_PASSWORD=
DB_NAME=rotto
```

Start PostgreSQL:

```bash
docker compose up -d
```

Run tests:

```bash
make test
```

Run the live crawler:

```bash
make crawl
```

`make crawl` is the single live entry point. Each run regenerates:

- `output/jobs.jsonl`
- `output/report.json`

## Architecture

Each source has its own discovery and detail parser under `crawler/sources/`.

The crawler:

1. Discovers source-specific job IDs and URLs.
2. Uses stable IDs such as `reed:<source_job_id>` and `linkedin:<source_job_id>`.
3. Fetches and validates new listings.
4. Stores normalized jobs in PostgreSQL.
5. Updates `last_seen_at` when known jobs are rediscovered.
6. Periodically refreshes detail pages to detect content changes.
7. Uses a content hash so unchanged jobs are not unnecessarily rewritten.
8. Runs conservative cross-source deduplication and assigns shared `canonical_job_id` values where confidence is high.
9. Exports the database and run statistics after the crawl.

Required fields such as title, location, and description are validated before persistence. Optional unavailable fields are stored as `NULL` rather than guessed.

## Bot Protection and Failure Handling

All crawler traffic uses the supplied Rotto UK residential proxy credentials from environment variables.

Reed and LinkedIn public logged-out pages were successfully crawled through the supplied proxy.

Indeed consistently returned HTTP 403 / security challenge responses during development. This occurred with direct HTTP requests, Chromium, and a small bounded set of fresh proxy attempts. The crawler does not use accounts, CAPTCHA-solving services, or attempt to solve interactive security challenges.

Indeed failures are recorded as blocked requests while the remaining sources continue normally.

Requests are counted by status, and blocked requests are included in `output/report.json`.

Failures are isolated per source/job so that one failed request does not terminate the complete crawl.

## Lifecycle and Removal Policy

The database preserves:

- `first_seen_at`
- `last_seen_at`
- `removed_at`
- `detail_fetched_at`
- `content_hash`

A listing disappearing from search results is not considered sufficient removal evidence.

An existing job is marked removed only when its known public detail URL provides positive evidence such as:

- HTTP `404 Not Found`
- HTTP `410 Gone`

The following are **not** treated as removal evidence:

- HTTP `403`
- HTTP `429`
- timeouts
- server failures
- parsing failures
- blocked responses
- incomplete discovery
- absence from search results

This prevents temporary blocking or partial crawls from corrupting lifecycle state.

If a previously removed listing reappears, normal reconciliation can restore it.

## Deduplication

Source listings remain separate database rows.

Cross-source deduplication conservatively compares:

- normalized company
- normalized title
- location
- description similarity

High-confidence copies of the same real-world vacancy share a `canonical_job_id`.

The matching policy intentionally favors precision over aggressive matching to reduce the risk of merging different vacancies from the same employer.

## Efficiency and Cost

Known listings do not require a full detail-page request on every crawl.

Discovery updates `last_seen_at`, while full detail pages are refreshed periodically. This reduces unnecessary proxy traffic while still allowing detail-only changes to be detected.

Request totals, blocked requests, and response-status counts are included in `output/report.json`.

The residential proxy used by the crawler was supplied as part of the assessment. Therefore, candidate-incurred proxy infrastructure cost is `$0`, and `estimated_cost_usd` is reported as `0.0`.

Under the supplied assessment proxy allocation, the candidate-incurred proxy cost for 1,000 pages is also `$0`. Request volume is reported separately so crawl efficiency remains measurable.

## Tests

Run the lifecycle test suite with:

```bash
make test
```

The tests use the isolated `rotto_test` database and verify:

- initial ingestion
- unchanged listings
- newly discovered listings
- detail-only changes
- replay / idempotency

Cross-source deduplication can also be verified with:

```bash
python3 tests/test_deduplication.py
```

## Output

After `make crawl`, the crawler writes:

```text
output/jobs.jsonl
output/report.json
```

`jobs.jsonl` contains the persisted job records.

`report.json` contains run-level metrics including:

- crawl start and finish times
- total requests
- blocked requests
- response-status counts
- live jobs by source
- duplicates linked
- new jobs
- changed jobs
- removed jobs
- estimated cost

## Current Source Status

- **Reed:** live discovery, detail parsing, persistence, incremental refresh, and lifecycle handling implemented.
- **LinkedIn:** live discovery, detail parsing, persistence, incremental refresh, and lifecycle handling implemented.
- **Indeed:** public requests currently receive Indeed security/403 responses through the supplied proxy; failures are retried in a bounded manner, recorded as blocked, and do not affect existing lifecycle data or prevent other sources from completing.

Author : Megha John Babu
