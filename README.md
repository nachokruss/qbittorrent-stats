# qBittorrent Stats

A lightweight statistics collector for qBittorrent that tracks upload activity, seeding times, and tracker information over time. Data is stored in PostgreSQL with ready-to-query views for daily, weekly, and monthly reports.

## Features

- **Periodic collection** — Polls qBittorrent's API at configurable intervals (default: every 15 minutes)
- **Upload tracking** — Records upload deltas per torrent, so you can see exactly how much each torrent contributed
- **Seeding time** — Tracks both qBittorrent-reported seeding seconds and observed seeding time (based on state changes)
- **Tracker classification** — Automatically classifies trackers as Public, BTArg, IPTorrents, or Other Private
- **Snapshot history** — Stores periodic snapshots of torrent state for historical analysis
- **Removed torrent detection** — Marks torrents as removed when they disappear from qBittorrent
- **Session resilience** — Re-authenticates automatically if the qBittorrent session cookie expires

## Architecture

```
qBittorrent ──API──► collector.py ──SQL──► PostgreSQL
                     (Python, runs       (with materialized
                      in a container)      views for queries)
```

The collector runs as a single Python process inside a Docker container. It connects to qBittorrent over HTTP and stores all data in a PostgreSQL database. Pre-built SQL views provide convenient summaries without needing application code.

## Quick Start

### Prerequisites

- Docker and Docker Compose
- A running qBittorrent instance
- A running PostgreSQL instance

### Deployment

1. **Clone the repository:**
   ```bash
   git clone https://github.com/nachokruss/qbittorrent-stats.git
   cd qbittorrent-stats
   ```

2. **Configure environment variables** in `docker-compose.yml`:
   - `QB_PASSWORD` — Your qBittorrent password
   - `POSTGRES_PASSWORD` — Your PostgreSQL password
   - Adjust hostnames, ports, and networks to match your setup

3. **Build and run:**
   ```bash
   docker compose up -d --build
   ```

### TrueNAS Apps

This project is designed to run as a TrueNAS app. Configure the environment variables in the app configuration UI:

| Variable | Description | Default |
|---|---|---|
| `QB_URL` | qBittorrent web UI URL | `http://qbittorrent:30024` |
| `QB_USERNAME` | qBittorrent username | `admin` |
| `QB_PASSWORD` | qBittorrent password | *(required)* |
| `POSTGRES_HOST` | PostgreSQL hostname | `postgres` |
| `POSTGRES_PORT` | PostgreSQL port | `5432` |
| `POSTGRES_DB` | Database name | `qbittorrent_stats` |
| `POSTGRES_USER` | Database user | `qbittorrent_stats` |
| `POSTGRES_PASSWORD` | Database password | *(required)* |
| `INTERVAL_SECONDS` | Collection interval | `900` (15 min) |
| `TRACKER_REFRESH_SECONDS` | Tracker refresh interval | `86400` (24 hr) |
| `LOG_LEVEL` | Log verbosity | `INFO` |
| `TZ` | Timezone | `UTC` |

## Database Schema

The collector uses **dbmate** for database migrations. On first run, it applies the initial schema automatically. Subsequent schema changes are managed via migration files in the `migrations/` directory.

Tables created on first run:

| Table | Purpose |
|---|---|
| `torrents` | Core torrent information (hash, name, size, state, seeding time) |
| `torrent_trackers` | Per-torrent tracker details (URL, status, peers) |
| `snapshots` | Periodic point-in-time snapshots of torrent state |
| `upload_deltas` | Upload byte deltas recorded each collection cycle |
| `collector_runs` | Collection run metadata and error tracking |
| `torrent_events` | Event log for torrent state changes |

### SQL Views

Pre-built views for common queries:

| View | Description |
|---|---|
| `torrent_upload_totals` | Total uploaded bytes per torrent with seeding days |
| `upload_last_30_days` | Upload deltas from the last 30 days |
| `upload_last_30_days_daily` | Daily upload totals for the last 30 days |
| `upload_last_12_weeks` | Upload deltas from the last 12 weeks |
| `upload_last_12_weeks_weekly` | Weekly upload totals for the last 12 weeks |
| `upload_last_6_months` | Upload deltas from the last 6 months |
| `upload_last_6_months_monthly` | Monthly upload totals for the last 6 months |
| `torrent_summary_by_group` | Torrent count and size grouped by tracker |
| `upload_last_30_days_by_group` | 30-day uploads grouped by tracker |
| `upload_daily_by_group` | Daily uploads grouped by tracker |
| `upload_weekly_by_group` | Weekly uploads grouped by tracker |
| `upload_monthly_by_group` | Monthly uploads grouped by tracker |
| `torrent_tracker_list` | All trackers with their status and peer counts |
| `no_upload_last_30_days` | Torrents with no upload activity in 30 days |
| `uploading_last_30_days` | Torrents that uploaded in the last 30 days |

### Example Queries

**Total uploads by tracker group (last 30 days):**
```sql
SELECT * FROM upload_last_30_days_by_group;
```

**Daily upload chart data:**
```sql
SELECT day, uploaded_gb FROM upload_last_30_days_daily ORDER BY day;
```

**Top uploading torrents:**
```sql
SELECT name, uploaded_gb, seeding_days
FROM torrent_upload_totals
ORDER BY uploaded_bytes DESC
LIMIT 20;
```

**Torrents not uploading recently:**
```sql
SELECT name, seeding_days, primary_tracker_url
FROM no_upload_last_30_days
WHERE tracker_group != 'Public';
```

## Project Structure

```
├── collector/
│   ├── __init__.py     # Package init
│   ├── __main__.py     # Entry point; runs migrations, then collection loop
│   ├── config.py       # Environment variable configuration
│   ├── utils.py        # Tracker classification, state normalization
│   ├── qbittorrent.py  # qBittorrent HTTP API client
│   ├── database.py     # PostgreSQL connection and queries
│   ├── trackers.py     # Tracker refresh and upsert logic
│   ├── torrent.py      # Core torrent processing
│   └── collector.py    # Collection orchestration
├── migrations/         # dbmate SQL migration files
├── tests/              # Pytest unit tests
│   ├── conftest.py     # Shared fixtures
│   ├── test_utils.py   # Utility function tests
│   ├── test_config.py  # Configuration tests
│   ├── test_qbittorrent.py  # API client tests
│   ├── test_database.py     # Database query tests
│   ├── test_trackers.py     # Tracker logic tests
│   ├── test_torrent.py      # Torrent processing tests
│   └── test_collector.py    # Collection cycle tests
├── Makefile            # Build and development targets
├── Dockerfile          # Container build instructions
├── docker-compose.yml  # Deployment configuration
└── README.md           # This file
```

## Development Setup

On a fresh checkout, create and activate a virtual environment before running tests or other Makefile targets:

```bash
# Create the virtual environment
python3 -m venv .venv

# Activate it
source .venv/bin/activate

# Install dependencies
pip install requests psycopg[binary] pytest pytest-cov
```

Your shell prompt will change to show `(.venv)`, indicating the environment is active. Now `make test` and other targets will work correctly.

To deactivate the environment when done:

```bash
deactivate
```

The `.venv/` directory is already listed in `.gitignore` and should not be committed.

## Testing

The project uses **pytest** for unit testing. All external dependencies (qBittorrent API, PostgreSQL) are mocked, so tests run without any running services.

```bash
# Run all tests
make test

# Run tests with coverage report
make test-cov
```

## Deploying to GitHub Container Registry

To deploy updates from your laptop to TrueNAS, push the Docker image to GHCR, then restart the app on TrueNAS to pull the new image.

### One-time setup

1. **Create a GitHub personal access token (classic)**:
   - Go to [GitHub Settings → Developer settings → Personal access tokens → Tokens (classic)](https://github.com/settings/tokens)
   - Click **Generate new token → Generate new token (classic)**
   - Give it a label (e.g., "Docker Registry")
   - Under **Expiration**, choose your preferred expiry (or "No expiration")
   - Under **Select scopes**, check **write:packages**
   - Click **Generate token** and copy it (it starts with `ghp_`)

2. **Save the token locally** (not committed to git):
   ```bash
   echo "YOUR_TOKEN" > .docker-token
   ```
   The `.docker-token` file is already in `.gitignore`, so it won't be pushed.

### Deploy

```bash
# Build, tag, and push to GHCR in one step
make docker-push
```

Then in TrueNAS, change the app image to `ghcr.io/nachokruss/qbittorrent-stats:latest` and restart.

The image is built for both **AMD64** (TrueNAS) and **ARM64** (Apple Silicon Macs), so it works on any architecture.

### Makefile Targets

| Target | Description |
|---|---|
| `make test` | Run all unit tests |
| `make test-cov` | Run tests with coverage report |
| `make lint` | Check Python syntax |
| `make build` | Build the local Docker image |
| `make docker-login` | Log in to GHCR (reads token from `.docker-token`) |
| `make docker-build` | Build multi-arch image (amd64 + arm64) and push to GHCR |
| `make docker-push` | Login, build, and push to GHCR |
| `make docker-deploy` | Alias for `docker-push` |
| `make run` | Start the container via docker-compose |
| `make stop` | Stop the running container |
| `make clean` | Remove build artifacts and cache |
| `make help` | List all available targets |

## Tracker Classification

Trackers are classified based on their announce URL:

| Group | Announce URL Pattern |
|---|---|
| BTArg | `https://announce.btarg.org/announce.php/` |
| IPTorrents | `http://127.0.0.1.stackoverflow.tech/`, `http://async.empirehost.me/`, `http://routing.bgp.technology/` |
| Other Private | Any private tracker not matching above |
| Public | No tracker URL or unrecognized public trackers |

Pseudo-trackers like `[DHT]` and `[PeX]` are ignored.

To add custom tracker classifications, edit the `tracker_group_for_url()` function in `collector/utils.py`.

## License

MIT License — see [LICENSE](LICENSE) for details.
