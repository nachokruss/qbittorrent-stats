import logging
import os
import time
from datetime import datetime, timezone
from urllib.parse import quote, urlparse

import psycopg
import requests
from psycopg.rows import dict_row


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

QB_URL = os.getenv("QB_URL", "http://qbittorrent:30024").rstrip("/")
QB_USERNAME = os.getenv("QB_USERNAME", "admin")
QB_PASSWORD = os.getenv("QB_PASSWORD", "")

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "qbittorrent_stats")
POSTGRES_USER = os.getenv("POSTGRES_USER", "qbittorrent_stats")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")

INTERVAL_SECONDS = int(os.getenv("INTERVAL_SECONDS", "900"))
TRACKER_REFRESH_SECONDS = int(
    os.getenv("TRACKER_REFRESH_SECONDS", "86400")
)

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()


logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(message)s",
)

log = logging.getLogger("qbittorrent-stats")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def utcnow():
    return datetime.now(timezone.utc)


def normalize_state(state):
    """
    Normalize qBittorrent states so that all uploading/seeding states
    count as 'seeding' for observed seeding-time calculation.
    """
    if state in {
        "uploading",
        "stalledUP",
        "forcedUP",
        "queuedUP",
        "checkingUP",
    }:
        return "seeding"

    return state


def tracker_host(url):
    try:
        return urlparse(url).hostname
    except Exception:
        return None


def tracker_group_for_url(url):
    """
    Classify a tracker based on the requested announce URL prefixes.
    """

    if not url:
        return "Public"

    if url.startswith(
        "https://announce.btarg.org/announce.php/"
    ):
        return "BTArg"

    if (
        url.startswith("http://127.0.0.1.stackoverflow.tech/")
        or url.startswith("http://async.empirehost.me/")
        or url.startswith("http://routing.bgp.technology/")
    ):
        return "IPTorrents"

    return "Other Private"


def is_real_tracker(url):
    """
    Ignore qBittorrent's pseudo-trackers.
    """
    if not url:
        return False

    value = url.strip()

    if value.startswith("[DHT]"):
        return False

    if value.startswith("[PeX]"):
        return False

    if value.startswith("[LSD]"):
        return False

    if value.startswith("** [DHT]"):
        return False

    if value.startswith("** [PeX]"):
        return False

    if value.startswith("** [LSD]"):
        return False

    return True


def extract_tracker_urls(tracker_data):
    """
    Return unique real tracker URLs.
    """
    result = []
    seen = set()

    for tracker in tracker_data or []:
        url = (tracker.get("url") or "").strip()

        if not is_real_tracker(url):
            continue

        if url in seen:
            continue

        seen.add(url)
        result.append(url)

    return result


def classify_torrent(tracker_urls):
    """
    Determine privacy and tracker group.

    Priority:
        BTArg
        IPTorrents
        Other Private
        Public
    """

    if not tracker_urls:
        return False, "public", "Public"

    groups = {
        tracker_group_for_url(url)
        for url in tracker_urls
    }

    if "BTArg" in groups:
        return True, "private", "BTArg"

    if "IPTorrents" in groups:
        return True, "private", "IPTorrents"

    return True, "private", "Other Private"


def build_magnet(torrent):
    """
    Build a magnet URI from qBittorrent information.

    qBittorrent normally exposes magnet_uri directly. If unavailable,
    construct a basic magnet from hash + name.
    """

    magnet = torrent.get("magnet_uri")

    if magnet:
        return magnet

    torrent_hash = torrent.get("hash")

    if not torrent_hash:
        return None

    name = torrent.get("name") or torrent_hash

    return (
        f"magnet:?xt=urn:btih:{torrent_hash}"
        f"&dn={quote(name)}"
    )


# ---------------------------------------------------------------------------
# qBittorrent API
# ---------------------------------------------------------------------------

class QBittorrent:
    def __init__(self):
        self.session = requests.Session()

    def login(self):
        response = self.session.post(
            f"{QB_URL}/api/v2/auth/login",
            data={
                "username": QB_USERNAME,
                "password": QB_PASSWORD,
            },
            timeout=30,
        )

        response.raise_for_status()

        log.info(
            "Authenticated to qBittorrent (HTTP %s)",
            response.status_code,
        )

    def get_torrents(self):
        response = self.session.get(
            f"{QB_URL}/api/v2/torrents/info",
            timeout=60,
        )

        response.raise_for_status()

        return response.json()

    def get_trackers(self, torrent_hash):
        response = self.session.get(
            f"{QB_URL}/api/v2/torrents/trackers",
            params={"hash": torrent_hash},
            timeout=60,
        )

        response.raise_for_status()

        return response.json()


# ---------------------------------------------------------------------------
# PostgreSQL
# ---------------------------------------------------------------------------

def connect_db():
    conn = psycopg.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        row_factory=dict_row,
    )

    conn.autocommit = False

    return conn


def initialize_database(conn):
    """
    Run schema.sql.

    The schema uses CREATE TABLE IF NOT EXISTS, so existing tables are
    preserved.
    """

    schema_path = "/app/schema.sql"

    if not os.path.exists(schema_path):
        log.warning(
            "schema.sql not found at %s; skipping initialization",
            schema_path,
        )
        return

    with open(schema_path, "r", encoding="utf-8") as f:
        schema = f.read()

    with conn.cursor() as cur:
        cur.execute(schema)

    conn.commit()

    log.info("Database schema initialized")


# ---------------------------------------------------------------------------
# Existing torrent
# ---------------------------------------------------------------------------

def get_existing_torrent(conn, torrent_hash):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                torrent_hash,
                name,
                first_seen_at,
                last_seen_at,
                removed_at,
                observed_seeding_seconds,
                last_state,
                uploaded_total_bytes,
                downloaded_total_bytes,
                trackers_refreshed_at
            FROM torrents
            WHERE torrent_hash = %s
            """,
            (torrent_hash,),
        )

        return cur.fetchone()


# ---------------------------------------------------------------------------
# Tracker handling
# ---------------------------------------------------------------------------

def should_refresh_trackers(existing, now):
    if not existing:
        return True

    refreshed = existing["trackers_refreshed_at"]

    if refreshed is None:
        return True

    age = (now - refreshed).total_seconds()

    return age >= TRACKER_REFRESH_SECONDS


def get_stored_trackers(conn, torrent_hash):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                tracker_url,
                tracker_host,
                tracker_group
            FROM torrent_trackers
            WHERE torrent_hash = %s
              AND active = TRUE
            ORDER BY id
            """,
            (torrent_hash,),
        )

        return cur.fetchall()


def upsert_trackers(conn, torrent_hash, tracker_data, now):
    """
    Replace the active tracker state for this torrent.

    Historical tracker rows remain available through first_seen_at /
    last_seen_at, while current rows are marked active.
    """

    real_trackers = []

    for tracker in tracker_data or []:
        url = (tracker.get("url") or "").strip()

        if not is_real_tracker(url):
            continue

        real_trackers.append((url, tracker))

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE torrent_trackers
            SET active = FALSE,
                last_seen_at = %s
            WHERE torrent_hash = %s
            """,
            (now, torrent_hash),
        )

        for url, tracker in real_trackers:
            host = tracker_host(url)
            group = tracker_group_for_url(url)

            cur.execute(
                """
                INSERT INTO torrent_trackers (
                    torrent_hash,
                    tracker_url,
                    tracker_host,
                    tracker_group,
                    tier,
                    status,
                    num_peers,
                    num_seeds,
                    num_leeches,
                    num_downloads,
                    message,
                    first_seen_at,
                    last_seen_at,
                    active
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
                    host,
                    group,
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


# ---------------------------------------------------------------------------
# Torrent processing
# ---------------------------------------------------------------------------

def process_torrent(conn, qb, torrent):
    now = utcnow()

    torrent_hash = torrent["hash"]

    existing = get_existing_torrent(conn, torrent_hash)

    refresh_trackers = should_refresh_trackers(existing, now)

    if refresh_trackers:
        tracker_data = qb.get_trackers(torrent_hash)
        tracker_urls = extract_tracker_urls(tracker_data)

        trackers_refreshed_at = now
    else:
        tracker_data = None

        stored = get_stored_trackers(conn, torrent_hash)

        tracker_urls = [
            row["tracker_url"]
            for row in stored
        ]

        trackers_refreshed_at = (
            existing["trackers_refreshed_at"]
            if existing
            else now
        )

    is_private, privacy, tracker_group = classify_torrent(
        tracker_urls
    )

    primary_tracker_url = (
        tracker_urls[0]
        if tracker_urls
        else None
    )

    primary_tracker_host = (
        tracker_host(primary_tracker_url)
        if primary_tracker_url
        else None
    )

    name = torrent.get("name") or torrent_hash

    current_state = normalize_state(
        torrent.get("state")
    )

    previous_state = (
        existing["last_state"]
        if existing
        else None
    )

    observed_seeding_seconds = (
        existing["observed_seeding_seconds"]
        if existing
        else 0
    )

    # Observed seeding time is only increased while the previous
    # collector observation was in a seeding state.
    if (
        existing
        and previous_state == "seeding"
        and existing["last_seen_at"] is not None
    ):
        elapsed = (
            now - existing["last_seen_at"]
        ).total_seconds()

        # Protect against clock changes and unreasonable intervals.
        if 0 < elapsed <= max(INTERVAL_SECONDS * 4, 3600):
            observed_seeding_seconds += int(elapsed)

    qb_seeding_seconds = torrent.get("seeding_time")

    if qb_seeding_seconds is not None:
        try:
            qb_seeding_seconds = int(qb_seeding_seconds)
        except (TypeError, ValueError):
            qb_seeding_seconds = None

    if qb_seeding_seconds is not None and qb_seeding_seconds < 0:
        qb_seeding_seconds = None

    uploaded_total = int(
        torrent.get("uploaded", 0) or 0
    )

    downloaded_total = int(
        torrent.get("downloaded", 0) or 0
    )

    previous_uploaded = (
        existing["uploaded_total_bytes"]
        if existing
        else None
    )

    if previous_uploaded is None:
        upload_delta = 0
    else:
        upload_delta = max(
            0,
            uploaded_total - int(previous_uploaded),
        )

    # qBittorrent fields
    added_at = None

    if torrent.get("added_on"):
        try:
            added_at = datetime.fromtimestamp(
                int(torrent["added_on"]),
                tz=timezone.utc,
            )
        except (TypeError, ValueError, OSError):
            added_at = None

    last_activity_at = None

    if torrent.get("last_activity"):
        try:
            last_activity_at = datetime.fromtimestamp(
                int(torrent["last_activity"]),
                tz=timezone.utc,
            )
        except (TypeError, ValueError, OSError):
            last_activity_at = None

    first_seen_at = (
        existing["first_seen_at"]
        if existing
        else now
    )

    # -----------------------------------------------------------------------
    # IMPORTANT:
    # Parent torrent is inserted/updated BEFORE torrent_trackers because
    # torrent_trackers has a foreign key to torrents.
    # -----------------------------------------------------------------------

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO torrents (
                torrent_hash,
                name,
                size_bytes,
                category,
                tags,
                save_path,
                added_at,
                first_seen_at,
                last_seen_at,
                removed_at,
                is_private,
                privacy,
                tracker_group,
                primary_tracker_url,
                primary_tracker_host,
                magnet_uri,
                qbittorrent_seeding_seconds,
                observed_seeding_seconds,
                last_state,
                last_activity_at,
                uploaded_total_bytes,
                downloaded_total_bytes,
                num_seeds,
                num_leechs,
                num_complete,
                num_incomplete,
                trackers_refreshed_at,
                updated_at
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
                added_at = COALESCE(
                    torrents.added_at,
                    EXCLUDED.added_at
                ),
                last_seen_at = EXCLUDED.last_seen_at,
                removed_at = NULL,
                is_private = EXCLUDED.is_private,
                privacy = EXCLUDED.privacy,
                tracker_group = EXCLUDED.tracker_group,
                primary_tracker_url = EXCLUDED.primary_tracker_url,
                primary_tracker_host = EXCLUDED.primary_tracker_host,
                magnet_uri = EXCLUDED.magnet_uri,
                qbittorrent_seeding_seconds =
                    EXCLUDED.qbittorrent_seeding_seconds,
                observed_seeding_seconds =
                    EXCLUDED.observed_seeding_seconds,
                last_state = EXCLUDED.last_state,
                last_activity_at = EXCLUDED.last_activity_at,
                uploaded_total_bytes =
                    EXCLUDED.uploaded_total_bytes,
                downloaded_total_bytes =
                    EXCLUDED.downloaded_total_bytes,
                num_seeds = EXCLUDED.num_seeds,
                num_leechs = EXCLUDED.num_leechs,
                num_complete = EXCLUDED.num_complete,
                num_incomplete = EXCLUDED.num_incomplete,
                trackers_refreshed_at =
                    EXCLUDED.trackers_refreshed_at,
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

        # Insert/update trackers only after parent torrent exists.
        if refresh_trackers:
            upsert_trackers(
                conn,
                torrent_hash,
                tracker_data,
                now,
            )

        # Snapshot
        cur.execute(
            """
            INSERT INTO snapshots (
                snapshot_at,
                torrent_hash,
                name,
                privacy,
                tracker_group,
                primary_tracker_url,
                magnet_uri,
                uploaded_total_bytes,
                downloaded_total_bytes,
                qbittorrent_seeding_seconds,
                observed_seeding_seconds,
                state
            )
            VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (snapshot_at, torrent_hash)
            DO NOTHING
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

        # Upload delta
        cur.execute(
            """
            INSERT INTO upload_deltas (
                recorded_at,
                torrent_hash,
                name,
                uploaded_total_bytes,
                upload_delta_bytes,
                privacy,
                tracker_group,
                primary_tracker_url
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (recorded_at, torrent_hash)
            DO NOTHING
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


# ---------------------------------------------------------------------------
# Missing torrents
# ---------------------------------------------------------------------------

def mark_missing_torrents(conn, current_hashes):
    """
    Mark torrents that disappeared from qBittorrent.

    Empty API responses are treated as unsafe and do not mark everything
    as removed.
    """

    if not current_hashes:
        log.warning(
            "qBittorrent returned an empty torrent list; "
            "not marking torrents as removed"
        )
        return

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE torrents
            SET removed_at = NOW(),
                updated_at = NOW()
            WHERE removed_at IS NULL
              AND NOT (torrent_hash = ANY(%s))
            """,
            (current_hashes,),
        )

        if cur.rowcount:
            log.info(
                "Marked %s torrent(s) as removed",
                cur.rowcount,
            )


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------

def collect_once(conn, qb):
    log.info("Starting collection")

    torrents = qb.get_torrents()

    log.info(
        "qBittorrent returned %s torrents",
        len(torrents),
    )

    current_hashes = []
    total_delta = 0

    for torrent in torrents:
        torrent_hash = torrent.get("hash")

        if not torrent_hash:
            log.warning(
                "Skipping torrent without hash: %r",
                torrent,
            )
            continue

        current_hashes.append(torrent_hash)

        try:
            delta = process_torrent(
                conn,
                qb,
                torrent,
            )

            total_delta += delta

        except Exception:
            log.exception(
                "Failed processing torrent %s (%s)",
                torrent_hash,
                torrent.get("name"),
            )

            # Roll back this torrent's transaction so that one bad
            # torrent does not poison the whole PostgreSQL transaction.
            conn.rollback()

    mark_missing_torrents(
        conn,
        current_hashes,
    )

    conn.commit()

    log.info(
        "Collection completed: %s torrents, "
        "upload delta: %s bytes",
        len(current_hashes),
        total_delta,
    )

    return len(current_hashes), total_delta


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    log.info(
        "Starting qBittorrent statistics collector"
    )

    log.info(
        "qBittorrent: %s",
        QB_URL,
    )

    log.info(
        "PostgreSQL: %s:%s/%s",
        POSTGRES_HOST,
        POSTGRES_PORT,
        POSTGRES_DB,
    )

    conn = connect_db()

    try:
        initialize_database(conn)

        qb = QBittorrent()
        qb.login()

        while True:
            started = time.monotonic()

            # Re-authenticate before each collection to avoid stale sessions.
            # qBittorrent session cookies expire, so a fresh login ensures
            # the API calls succeed.
            try:
                qb.login()
            except Exception:
                log.exception(
                    "Failed to authenticate to qBittorrent"
                )

            try:
                collect_once(
                    conn,
                    qb,
                )

            except requests.HTTPError as exc:
                log.exception(
                    "qBittorrent API error: %s",
                    exc,
                )

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
                log.exception(
                    "PostgreSQL error"
                )
                conn.rollback()

            except Exception:
                log.exception(
                    "Unexpected collector error"
                )
                conn.rollback()

            elapsed = time.monotonic() - started

            sleep_for = max(
                1,
                INTERVAL_SECONDS - int(elapsed),
            )

            log.info(
                "Next collection in %s seconds",
                sleep_for,
            )

            time.sleep(sleep_for)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
