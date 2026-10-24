"""Core torrent processing logic."""

from .config import INTERVAL_SECONDS
from .database import get_existing_torrent, get_stored_trackers
from .trackers import should_refresh_trackers, upsert_trackers
from .utils import (
    build_magnet,
    classify_torrent,
    extract_tracker_urls,
    get_tracker_host,
    normalize_state,
    parse_timestamp,
    utcnow,
)


def process_torrent(conn, qb_client, torrent):
    """
    Process a single torrent: upsert record, trackers, snapshot, and upload delta.

    Returns:
        The upload delta in bytes for this torrent.
    """
    now = utcnow()
    torrent_hash = torrent["hash"]
    existing = get_existing_torrent(conn, torrent_hash)

    # -----------------------------------------------------------------------
    # Trackers
    # -----------------------------------------------------------------------
    refresh_trackers = should_refresh_trackers(existing, now)

    if refresh_trackers:
        tracker_data = qb_client.get_trackers(torrent_hash)
        tracker_urls = extract_tracker_urls(tracker_data)
        trackers_refreshed_at = now
    else:
        tracker_data = None
        stored = get_stored_trackers(conn, torrent_hash)
        tracker_urls = [row["tracker_url"] for row in stored]
        trackers_refreshed_at = (
            existing["trackers_refreshed_at"] if existing else now
        )

    is_private, privacy, tracker_group = classify_torrent(tracker_urls)

    primary_tracker_url = tracker_urls[0] if tracker_urls else None
    primary_tracker_host = (
        get_tracker_host(primary_tracker_url) if primary_tracker_url else None
    )

    # -----------------------------------------------------------------------
    # State & seeding time
    # -----------------------------------------------------------------------
    name = torrent.get("name") or torrent_hash
    current_state = normalize_state(torrent.get("state"))
    previous_state = existing["last_state"] if existing else None

    observed_seeding_seconds = (
        existing["observed_seeding_seconds"] if existing else 0
    )

    # Only increase observed seeding time while the previous observation
    # was in a seeding state.
    if (
        existing
        and previous_state == "seeding"
        and existing["last_seen_at"] is not None
    ):
        elapsed = (now - existing["last_seen_at"]).total_seconds()
        if 0 < elapsed <= max(INTERVAL_SECONDS * 4, 3600):
            observed_seeding_seconds += int(elapsed)

    qb_seeding_seconds = torrent.get("seeding_time")
    if qb_seeding_seconds is not None:
        try:
            qb_seeding_seconds = int(qb_seeding_seconds)
        except (TypeError, ValueError):
            qb_seeding_seconds = None
        if qb_seeding_seconds < 0:
            qb_seeding_seconds = None

    # -----------------------------------------------------------------------
    # Upload / download totals
    # -----------------------------------------------------------------------
    uploaded_total = int(torrent.get("uploaded", 0) or 0)
    downloaded_total = int(torrent.get("downloaded", 0) or 0)

    previous_uploaded = existing["uploaded_total_bytes"] if existing else None
    upload_delta = 0 if previous_uploaded is None else max(
        0, uploaded_total - int(previous_uploaded)
    )

    # -----------------------------------------------------------------------
    # Timestamps
    # -----------------------------------------------------------------------
    added_at = parse_timestamp(torrent.get("added_on"))
    last_activity_at = parse_timestamp(torrent.get("last_activity"))
    first_seen_at = existing["first_seen_at"] if existing else now

    # -----------------------------------------------------------------------
    # Upsert torrent record
    # -----------------------------------------------------------------------
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO torrents (
                torrent_hash, name, size_bytes, category, tags, save_path,
                added_at, first_seen_at, last_seen_at, removed_at,
                is_private, privacy, tracker_group, primary_tracker_url,
                primary_tracker_host, magnet_uri, qbittorrent_seeding_seconds,
                observed_seeding_seconds, last_state, last_activity_at,
                uploaded_total_bytes, downloaded_total_bytes,
                num_seeds, num_leechs, num_complete, num_incomplete,
                trackers_refreshed_at, updated_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s,
                NULL, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (torrent_hash)
            DO UPDATE SET
                name = EXCLUDED.name,
                size_bytes = EXCLUDED.size_bytes,
                category = EXCLUDED.category,
                tags = EXCLUDED.tags,
                save_path = EXCLUDED.save_path,
                added_at = COALESCE(torrents.added_at, EXCLUDED.added_at),
                last_seen_at = EXCLUDED.last_seen_at,
                removed_at = NULL,
                is_private = EXCLUDED.is_private,
                privacy = EXCLUDED.privacy,
                tracker_group = EXCLUDED.tracker_group,
                primary_tracker_url = EXCLUDED.primary_tracker_url,
                primary_tracker_host = EXCLUDED.primary_tracker_host,
                magnet_uri = EXCLUDED.magnet_uri,
                qbittorrent_seeding_seconds = EXCLUDED.qbittorrent_seeding_seconds,
                observed_seeding_seconds = EXCLUDED.observed_seeding_seconds,
                last_state = EXCLUDED.last_state,
                last_activity_at = EXCLUDED.last_activity_at,
                uploaded_total_bytes = EXCLUDED.uploaded_total_bytes,
                downloaded_total_bytes = EXCLUDED.downloaded_total_bytes,
                num_seeds = EXCLUDED.num_seeds,
                num_leechs = EXCLUDED.num_leechs,
                num_complete = EXCLUDED.num_complete,
                num_incomplete = EXCLUDED.num_incomplete,
                trackers_refreshed_at = EXCLUDED.trackers_refreshed_at,
                updated_at = EXCLUDED.updated_at
            """,
            (
                torrent_hash,
                name,
                torrent.get("size"),
                torrent.get("category"),
                torrent.get("tags"),
                torrent.get("save_path"),
                added_at,
                first_seen_at,
                now,
                is_private,
                privacy,
                tracker_group,
                primary_tracker_url,
                primary_tracker_host,
                build_magnet(torrent),
                qb_seeding_seconds,
                observed_seeding_seconds,
                current_state,
                last_activity_at,
                uploaded_total,
                downloaded_total,
                torrent.get("num_seeds"),
                torrent.get("num_leechs"),
                torrent.get("num_complete"),
                torrent.get("num_incomplete"),
                trackers_refreshed_at,
                now,
            ),
        )

        # Insert/update trackers only after parent torrent exists
        if refresh_trackers:
            upsert_trackers(conn, torrent_hash, tracker_data, now)

        # Insert snapshot
        cur.execute(
            """
            INSERT INTO snapshots (
                snapshot_at, torrent_hash, name, privacy, tracker_group,
                primary_tracker_url, magnet_uri, uploaded_total_bytes,
                downloaded_total_bytes, qbittorrent_seeding_seconds,
                observed_seeding_seconds, state
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (snapshot_at, torrent_hash) DO NOTHING
            """,
            (
                now,
                torrent_hash,
                name,
                privacy,
                tracker_group,
                primary_tracker_url,
                build_magnet(torrent),
                uploaded_total,
                downloaded_total,
                qb_seeding_seconds,
                observed_seeding_seconds,
                current_state,
            ),
        )

        # Insert upload delta
        cur.execute(
            """
            INSERT INTO upload_deltas (
                recorded_at, torrent_hash, name, uploaded_total_bytes,
                upload_delta_bytes, privacy, tracker_group, primary_tracker_url
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (recorded_at, torrent_hash) DO NOTHING
            """,
            (
                now,
                torrent_hash,
                name,
                uploaded_total,
                upload_delta,
                privacy,
                tracker_group,
                primary_tracker_url,
            ),
        )

    return upload_delta
