"""Configuration loaded from environment variables."""

import logging
import os


# ---------------------------------------------------------------------------
# qBittorrent
# ---------------------------------------------------------------------------

QB_URL = os.getenv("QB_URL", "http://qbittorrent:30024").rstrip("/")
QB_USERNAME = os.getenv("QB_USERNAME", "admin")
QB_PASSWORD = os.getenv("QB_PASSWORD", "")


# ---------------------------------------------------------------------------
# PostgreSQL
# ---------------------------------------------------------------------------

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "qbittorrent_stats")
POSTGRES_USER = os.getenv("POSTGRES_USER", "qbittorrent_stats")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")


# ---------------------------------------------------------------------------
# Timing
# ---------------------------------------------------------------------------

INTERVAL_SECONDS = int(os.getenv("INTERVAL_SECONDS", "900"))
TRACKER_REFRESH_SECONDS = int(os.getenv("TRACKER_REFRESH_SECONDS", "86400"))


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()


def setup_logging():
    """Configure the root logger and return the application logger."""
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    return logging.getLogger("qbittorrent-stats")
