"""Tracker management for torrents."""

from .config import TRACKER_REFRESH_SECONDS
from .utils import get_tracker_host, is_real_tracker, tracker_group_for_url


def should_refresh_trackers(existing, now):
    """Check if trackers should be refreshed based on the refresh interval."""
    if not existing:
        return True

    refreshed = existing["trackers_refreshed_at"]
    if refreshed is None:
        return True

    return (now - refreshed).total_seconds() >= TRACKER_REFRESH_SECONDS


def upsert_trackers(conn, torrent_hash, tracker_data, now):
    """
    Replace the active tracker state for a torrent.

    Historical tracker rows remain available through first_seen_at / last_seen_at,
    while current rows are marked active.
    """
    real_trackers = []
    for tracker in tracker_data or []:
        url = (tracker.get("url") or "").strip()
        if is_real_tracker(url):
            real_trackers.append((url, tracker))

    with conn.cursor() as cur:
        # Deactivate all existing trackers for this torrent
        cur.execute(
            """
            UPDATE torrent_trackers
            SET active = FALSE, last_seen_at = %s
            WHERE torrent_hash = %s
            """,
            (now, torrent_hash),
        )

        # Insert or update each real tracker
        for url, tracker in real_trackers:
            cur.execute(
                """
                INSERT INTO torrent_trackers (
                    torrent_hash, tracker_url, tracker_host, tracker_group,
                    tier, status, num_peers, num_seeds, num_leeches,
                    num_downloads, message, first_seen_at, last_seen_at, active
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, TRUE
                )
                ON CONFLICT (torrent_hash, tracker_url)
                DO UPDATE SET
                    tracker_host = EXCLUDED.tracker_host,
                    tracker_group = EXCLUDED.tracker_group,
                    tier = EXCLUDED.tier,
                    status = EXCLUDED.status,
                    num_peers = EXCLUDED.num_peers,
                    num_seeds = EXCLUDED.num_seeds,
                    num_leeches = EXCLUDED.num_leeches,
                    num_downloads = EXCLUDED.num_downloads,
                    message = EXCLUDED.message,
                    last_seen_at = EXCLUDED.last_seen_at,
                    active = TRUE
                """,
                (
                    torrent_hash,
                    url,
                    get_tracker_host(url),
                    tracker_group_for_url(url),
                    tracker.get("tier"),
                    tracker.get("status"),
                    tracker.get("num_peers"),
                    tracker.get("num_seeds"),
                    tracker.get("num_leeches"),
                    tracker.get("num_downloads"),
                    tracker.get("msg"),
                    now,
                    now,
                ),
            )
