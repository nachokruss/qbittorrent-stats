"""Database connection and schema management."""

import os

import psycopg
from psycopg.rows import dict_row

from .config import (
    POSTGRES_DB,
    POSTGRES_HOST,
    POSTGRES_PASSWORD,
    POSTGRES_PORT,
    POSTGRES_USER,
)


def connect():
    """Create and return a new PostgreSQL connection."""
    return psycopg.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        row_factory=dict_row,
    )


def initialize_schema(conn):
    """
    Apply schema.sql to the database.

    The schema uses CREATE TABLE IF NOT EXISTS, so existing tables are preserved.
    """
    schema_path = "/app/schema.sql"

    if not os.path.exists(schema_path):
        return

    with open(schema_path, "r", encoding="utf-8") as f:
        schema = f.read()

    with conn.cursor() as cur:
        cur.execute(schema)

    conn.commit()


def get_existing_torrent(conn, torrent_hash):
    """Fetch the existing torrent record, if any."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                torrent_hash, name, first_seen_at, last_seen_at, removed_at,
                observed_seeding_seconds, last_state, uploaded_total_bytes,
                downloaded_total_bytes, trackers_refreshed_at
            FROM torrents
            WHERE torrent_hash = %s
            """,
            (torrent_hash,),
        )
        return cur.fetchone()


def get_stored_trackers(conn, torrent_hash):
    """Fetch active tracker records for a torrent."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT tracker_url, tracker_host, tracker_group
            FROM torrent_trackers
            WHERE torrent_hash = %s AND active = TRUE
            ORDER BY id
            """,
            (torrent_hash,),
        )
        return cur.fetchall()


def mark_missing_torrents(conn, current_hashes):
    """
    Mark torrents that disappeared from qBittorrent as removed.

    Empty API responses are treated as unsafe and skipped.
    """
    if not current_hashes:
        return

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE torrents
            SET removed_at = NOW(), updated_at = NOW()
            WHERE removed_at IS NULL
              AND NOT (torrent_hash = ANY(%s))
            """,
            (current_hashes,),
        )
