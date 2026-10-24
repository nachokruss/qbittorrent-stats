"""Main entry point — runs the collection loop and web server."""

import logging
import os
import subprocess
import threading
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
    WEB_PORT,
    setup_logging,
)
from .database import connect, record_run_finish, record_run_start
from .qbittorrent import QBittorrentClient


def run_web_server():
    """Run the FastAPI web server in a background thread."""
    from uvicorn import Config, Server

    from .web import app

    config = Config(app, host="0.0.0.0", port=WEB_PORT, log_level="info")
    server = Server(config)
    server.run()


def main():
    """Run the qBittorrent statistics collector loop and web server."""
    log = setup_logging()

    log.info("Starting qBittorrent statistics collector")
    log.info("qBittorrent: %s", QB_URL)
    log.info("PostgreSQL: %s:%s/%s", POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB)
    log.info("Web server: port %s", WEB_PORT)

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

    # Start the web server in a background thread.
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    log.info("Web server started on port %s", WEB_PORT)

    conn = connect()

    try:
        qb = QBittorrentClient()
        qb.login()

        while True:
            started = time.monotonic()

            # Record the start of this collection run in the database.
            run_id = None
            errors = 0
            try:
                run_id = record_run_start(conn)
                conn.commit()
            except Exception:
                log.exception("Failed to record run start")
                conn.rollback()

            # Re-authenticate before each collection to avoid stale sessions.
            # qBittorrent session cookies expire, so a fresh login ensures
            # the API calls succeed.
            try:
                qb.login()
            except Exception:
                log.exception("Failed to authenticate to qBittorrent")

            try:
                torrents_processed, total_delta = collect_once(conn, qb)

            except requests.HTTPError as exc:
                log.exception("qBittorrent API error: %s", exc)
                conn.rollback()
                errors += 1

                # Re-authenticate and retry once in case the session expired.
                try:
                    qb.login()
                    torrents_processed, total_delta = collect_once(conn, qb)
                except Exception:
                    log.exception(
                        "Failed to re-authenticate or retry collection"
                    )
                    errors += 1
                    torrents_processed = 0

            except psycopg.Error:
                log.exception("PostgreSQL error")
                conn.rollback()
                errors += 1
                torrents_processed = 0

            except Exception:
                log.exception("Unexpected collector error")
                conn.rollback()
                errors += 1
                torrents_processed = 0

            # Record the finish of this collection run.
            if run_id is not None:
                status = "error" if errors > 0 else "success"
                try:
                    record_run_finish(
                        conn, run_id,
                        torrents_seen=torrents_processed,
                        torrents_processed=torrents_processed,
                        errors=errors,
                        status=status,
                    )
                    conn.commit()
                except Exception:
                    log.exception("Failed to record run finish")
                    conn.rollback()

            elapsed = time.monotonic() - started
            sleep_for = max(1, INTERVAL_SECONDS - int(elapsed))

            log.info("Next collection in %s seconds", sleep_for)
            time.sleep(sleep_for)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
