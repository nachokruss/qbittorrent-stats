"""Main entry point — runs the collection loop."""

import logging
import os
import subprocess
import time

import psycopg
import requests

from .collector import collect_once
from .config import (
    INTERVAL_SECONDS,
    POSTGRES_DB,
    POSTGRES_HOST,
    POSTGRES_PASSWORD,
    POSTGRES_PORT,
    POSTGRES_USER,
    QB_URL,
    setup_logging,
)
from .database import connect
from .qbittorrent import QBittorrentClient


def main():
    """Run the qBittorrent statistics collector loop."""
    log = setup_logging()

    log.info("Starting qBittorrent statistics collector")
    log.info("qBittorrent: %s", QB_URL)
    log.info("PostgreSQL: %s:%s/%s", POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB)

    # Apply any pending database migrations before starting the collector.
    # dbmate is idempotent: it only runs migrations that haven't been applied yet.
    database_url = (
        f"postgres://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
        f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}?sslmode=disable"
    )
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    try:
        result = subprocess.run(
            ["dbmate", "--migrations-dir", "/app/migrations", "up"],
            capture_output=True, text=True, check=True, env=env
        )
        if result.stdout:
            for line in result.stdout.strip().splitlines():
                log.info("dbmate: %s", line)
        log.info("Database migrations applied successfully")
    except subprocess.CalledProcessError as exc:
        log.error("dbmate stderr: %s", exc.stderr.strip())
        log.exception("Failed to apply database migrations")
        return

    conn = connect()

    try:
        qb = QBittorrentClient()
        qb.login()

        while True:
            started = time.monotonic()

            # Re-authenticate before each collection to avoid stale sessions.
            # qBittorrent session cookies expire, so a fresh login ensures
            # the API calls succeed.
            try:
                qb.login()
            except Exception:
                log.exception("Failed to authenticate to qBittorrent")

            try:
                collect_once(conn, qb)

            except requests.HTTPError as exc:
                log.exception("qBittorrent API error: %s", exc)
                conn.rollback()

                # Re-authenticate and retry once in case the session expired.
                try:
                    qb.login()
                    collect_once(conn, qb)
                except Exception:
                    log.exception(
                        "Failed to re-authenticate or retry collection"
                    )

            except psycopg.Error:
                log.exception("PostgreSQL error")
                conn.rollback()

            except Exception:
                log.exception("Unexpected collector error")
                conn.rollback()

            elapsed = time.monotonic() - started
            sleep_for = max(1, INTERVAL_SECONDS - int(elapsed))

            log.info("Next collection in %s seconds", sleep_for)
            time.sleep(sleep_for)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
