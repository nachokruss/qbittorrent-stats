"""Collection orchestration — runs one full collection cycle."""

import logging

import psycopg
import requests

from .database import mark_missing_torrents
from .torrent import process_torrent

log = logging.getLogger("qbittorrent-stats")


def collect_once(conn, qb_client):
    """
    Run a single collection cycle: fetch torrents, process each one,
    mark missing torrents, and commit.

    Returns:
        Tuple of (torrents_processed, total_upload_delta).
    """
    log.info("Starting collection")

    torrents = qb_client.get_torrents()
    log.info("qBittorrent returned %s torrents", len(torrents))

    current_hashes = []
    total_delta = 0

    for torrent in torrents:
        torrent_hash = torrent.get("hash")

        if not torrent_hash:
            log.warning("Skipping torrent without hash: %r", torrent)
            continue

        current_hashes.append(torrent_hash)

        try:
            delta = process_torrent(conn, qb_client, torrent)
            total_delta += delta

        except Exception:
            log.exception(
                "Failed processing torrent %s (%s)",
                torrent_hash,
                torrent.get("name"),
            )
            conn.rollback()

    mark_missing_torrents(conn, current_hashes)
    conn.commit()

    log.info(
        "Collection completed: %s torrents, upload delta: %s bytes",
        len(current_hashes),
        total_delta,
    )

    return len(current_hashes), total_delta
