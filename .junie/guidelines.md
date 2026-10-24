# Project Guidelines

## Overview

This is a Python package that collects qBittorrent statistics and stores them in PostgreSQL. It runs as a Docker container, typically deployed on TrueNAS.

## Architecture

- **collector/** — Python package with modular code:
  - `__main__.py` — Entry point; runs dbmate migrations, then the collection loop.
  - `config.py` — Environment variable configuration and logging setup.
  - `utils.py` — Helper functions: tracker classification, state normalization, magnet URIs.
  - `qbittorrent.py` — HTTP API client for qBittorrent.
  - `database.py` — PostgreSQL connection and queries.
  - `trackers.py` — Tracker refresh logic and upsert operations.
  - `torrent.py` — Core torrent processing: upserts, snapshots, upload deltas.
  - `collector.py` — Collection orchestration; runs one full cycle.
- **migrations/** — dbmate SQL migration files for database schema changes.
- **tests/** — Pytest-based unit tests with mocked external dependencies.
- **Makefile** — Build and development targets: test, lint, build, run, clean.
- **Dockerfile** — Python 3.12 slim image with `requests`, `psycopg`, and `dbmate` dependencies.
- **docker-compose.yml** — Deployment config; connects to external TrueNAS networks.

## Data Flow

1. Authenticate to qBittorrent via HTTP API (cookie-based session)
2. Fetch all torrents and their tracker information
3. For each torrent, compute upload deltas, seeding time, and tracker classification
4. Upsert torrent records and insert snapshots and upload deltas into PostgreSQL
5. Mark missing torrents as removed
6. Sleep for the configured interval, then repeat

## Key Design Decisions

- **Re-authenticate every cycle** — qBittorrent session cookies expire; logging in before each collection prevents 403 errors. This was a bug fix (session was only authenticated at startup).
- **Per-torrent transactions** — Each torrent is processed in its own database transaction. If one torrent fails, the others are not affected.
- **Tracker classification** — Trackers are classified by announce URL prefix in `tracker_group_for_url()`. Pseudo-trackers (`[DHT]`, `[PeX]`) are ignored.
- **Upload deltas** — Only the delta (change since last collection) is stored, not the absolute value, to avoid double-counting if seeding time resets.
- **Removed detection** — Torrents disappearing from qBittorrent are marked with `removed_at`, but empty API responses are treated as unsafe and skipped.

## Coding Conventions

- **Python 3.12** — Use modern Python features (walrus operator, match statements if needed).
- **Dependencies** — Only `requests` and `psycopg` (PostgreSQL adapter). Keep dependencies minimal.
- **Logging** — Use the `log` logger throughout. No print statements.
- **Error handling** — Catch exceptions per-torrent, log them, and rollback the transaction. Never let one bad torrent crash the collector.
- **SQL** — Use parameterized queries. Schema changes go in `migrations/` as dbmate migration files.
- **No hardcoded credentials** — All configuration via environment variables read at module level.

## Database Schema

Core tables: `torrents`, `torrent_trackers`, `snapshots`, `upload_deltas`, `collector_runs`, `torrent_events`.

Views provide ready-to-query summaries: daily/weekly/monthly uploads, totals by tracker group, inactive torrents, etc. See `migrations/` for the schema definition.

## Database Migrations

The project uses **dbmate** for database migrations. Migrations are plain SQL files in the `migrations/` directory with timestamp-based filenames (e.g., `20241024120000_initial.sql`).

Each migration file has two sections:
- `-- migrate:up` — SQL to apply the migration
- `-- migrate:down` — SQL to rollback the migration

On container startup, dbmate automatically applies any pending migrations before the collector starts. It tracks applied migrations in a `schema_migrations` table, so already-applied migrations are skipped.

## Deployment

- Runs as a Docker container on TrueNAS Apps
- Connects to two external Docker networks: `ix-qbittorrent_default` and `ix-postgres_default`
- Environment variables are configured in the TrueNAS app UI, not in docker-compose.yml
- The `docker-compose.yml` in the repo is a reference template without passwords

## Common Tasks

### Adding a new tracker classification

Edit `tracker_group_for_url()` in `collector/utils.py`. Add a new `if` block that checks the announce URL prefix and returns the group name.

### Changing the collection interval

Set `INTERVAL_SECONDS` environment variable. Default is 900 (15 minutes).

### Adding a new SQL view or schema change

Create a new migration file in `migrations/` with a timestamp prefix (e.g., `20241025090000_add_view.sql`). Include both `-- migrate:up` and `-- migrate:down` sections. The migration will be applied automatically on next container startup.

### Debugging

Set `LOG_LEVEL=DEBUG` in the environment variables. Logs go to stdout, which TrueNAS captures.

### Running tests

Run `make test` to execute all unit tests. Tests use mocking for external dependencies (qBittorrent API, PostgreSQL), so they don't require running services.

To run tests with coverage: `make test-cov`.

### Adding tests

Place new test files in `tests/` with the naming convention `test_<module>.py`. Use pytest class-based tests. Mock all external dependencies — tests should run without qBittorrent or PostgreSQL.

## Makefile Targets

- `make test` — Run all unit tests
- `make test-cov` — Run tests with coverage report
- `make lint` — Check Python syntax
- `make build` — Build the local Docker image
- `make docker-login` — Log in to GHCR (reads token from `.docker-token`)
- `make docker-build` — Build multi-arch image (amd64 + arm64) and push to GHCR
- `make docker-push` — Login, build, and push to GHCR
- `make docker-deploy` — Alias for `docker-push`
- `make run` — Start the container via docker-compose
- `make stop` — Stop the running container
- `make clean` — Remove build artifacts and cache
- `make help` — List all available targets

## Docker Deployment

The project is deployed to GitHub Container Registry (GHCR) at `ghcr.io/nachokruss/qbittorrent-stats:latest`.

To deploy, create a `.docker-token` file with a GitHub personal access token (classic) with `write:packages` scope. Fine-grained tokens may not show the "Packages" permission option for all users, so classic tokens are the reliable option. The file is gitignored and never committed.

Run `make docker-push` to login, build, tag, and push the image in one step. Then restart the app in TrueNAS to pull the new image.

## What Not to Do

- **Do not** hardcode passwords or URLs in the code
- **Do not** remove the re-authentication logic — it's required for session resilience
- **Do not** assume the qBittorrent API is always available — handle HTTPError gracefully
- **Do not** commit files with real credentials
- **Do not** add heavy dependencies — keep the image small
- **Do not** automatically commit or push changes — only commit when explicitly asked, and never push without an explicit request
