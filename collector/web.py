"""FastAPI web interface for querying qBittorrent statistics."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from psycopg import connect as pg_connect
from psycopg.rows import dict_row

from .config import (
    POSTGRES_DB,
    POSTGRES_HOST,
    POSTGRES_PASSWORD,
    POSTGRES_PORT,
    POSTGRES_USER,
)

log = logging.getLogger("qbittorrent-stats")

# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start up and shut down the web server."""
    log.info("Web server starting")
    yield
    log.info("Web server shutting down")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="qBittorrent Stats", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_conn():
    """Return a short-lived PostgreSQL connection for a single query."""
    return pg_connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        row_factory=dict_row,
    )


def query(sql: str, params=None):
    """Execute a query and return all rows as dicts."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchall()


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve the single-page application."""
    return templates.TemplateResponse("index.html", {"request": request})


# ---------------------------------------------------------------------------
# API — Dashboard
# ---------------------------------------------------------------------------

@app.get("/api/dashboard")
def api_dashboard():
    """Return summary statistics for the dashboard."""
    stats = query("""
        SELECT
            COUNT(*) AS total_torrents,
            COUNT(*) FILTER (WHERE removed_at IS NULL) AS active_torrents,
            ROUND(COALESCE(SUM(uploaded_total_bytes), 0) / 1073741824.0, 2) AS total_uploaded_gb,
            ROUND(COALESCE(SUM(size_bytes), 0) / 1099511627776.0, 2) AS total_size_tb,
            ROUND(COALESCE(SUM(observed_seeding_seconds), 0) / 86400.0, 2) AS total_seeding_days
        FROM torrents
    """)
    # Last collection run info
    runs = query("""
        SELECT started_at, finished_at, torrents_seen, torrents_processed, errors, status
        FROM collector_runs
        ORDER BY started_at DESC
        LIMIT 1
    """)
    return {
        "stats": stats[0] if stats else {},
        "last_run": runs[0] if runs else None,
    }


# ---------------------------------------------------------------------------
# API — Upload Charts
# ---------------------------------------------------------------------------

def _uploads_by_period(granularity: str, tracker: Optional[str] = None):
    """Generic query for upload charts, optionally filtered by tracker group.

    granularity: 'day', 'week', or 'month'
    tracker: optional tracker_group filter
    """
    intervals = {
        "day": "30 days",
        "week": "12 weeks",
        "month": "6 months",
    }
    interval = intervals.get(granularity, "30 days")
    label_col = f"DATE_TRUNC('%s', recorded_at) AS {granularity}" % granularity

    sql = f"""
        SELECT
            {label_col},
            SUM(upload_delta_bytes) AS uploaded_bytes,
            ROUND(SUM(upload_delta_bytes) / 1073741824.0, 2) AS uploaded_gb
        FROM upload_deltas
        WHERE recorded_at >= NOW() - INTERVAL '%s'
    """ % interval
    params = []

    if tracker:
        sql += " AND tracker_group = %s"
        params.append(tracker)

    sql += " GROUP BY 1 ORDER BY 1"
    return query(sql, params)


@app.get("/api/uploads/daily")
def api_uploads_daily(tracker: Optional[str] = Query(None, description="Filter by tracker group")):
    """Daily upload data for the last 30 days."""
    return _uploads_by_period("day", tracker)


@app.get("/api/uploads/weekly")
def api_uploads_weekly(tracker: Optional[str] = Query(None, description="Filter by tracker group")):
    """Weekly upload data for the last 12 weeks."""
    return _uploads_by_period("week", tracker)


@app.get("/api/uploads/monthly")
def api_uploads_monthly(tracker: Optional[str] = Query(None, description="Filter by tracker group")):
    """Monthly upload data for the last 6 months."""
    return _uploads_by_period("month", tracker)


# ---------------------------------------------------------------------------
# API — Torrents
# ---------------------------------------------------------------------------

@app.get("/api/torrents")
def api_torrents(
    search: str = Query("", description="Search by name"),
    tracker: str = Query("", description="Filter by tracker group"),
    privacy: str = Query("", description="Filter by privacy (public/private)"),
    state: str = Query("", description="Filter by state"),
    sort: str = Query("name", description="Sort field: name, uploaded_gb, seeding_days, last_seen_at"),
    order: str = Query("asc", description="Sort order: asc or desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """Return a paginated, filterable list of torrents."""
    conditions = []
    params = []

    if search:
        conditions.append("t.name ILIKE %s")
        params.append(f"%{search}%")
    if tracker:
        conditions.append("t.tracker_group = %s")
        params.append(tracker)
    if privacy:
        conditions.append("t.privacy = %s")
        params.append(privacy)
    if state:
        conditions.append("t.last_state = %s")
        params.append(state)

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    # Validate sort field
    allowed_sort = {"name", "tracker_group", "privacy", "last_state", "uploaded_gb", "seeding_days", "last_seen_at"}
    sort_field = sort if sort in allowed_sort else "name"
    order_dir = "DESC" if order == "desc" else "ASC"

    offset = (page - 1) * page_size

    rows = query(f"""
        SELECT
            t.torrent_hash, t.name, t.size_bytes, t.tracker_group, t.privacy,
            t.last_state, t.last_seen_at, t.removed_at,
            ROUND(COALESCE(tut.uploaded_gb, 0), 2) AS uploaded_gb,
            ROUND(COALESCE(tut.seeding_days, 0), 2) AS seeding_days
        FROM torrents t
        LEFT JOIN torrent_upload_totals tut ON tut.torrent_hash = t.torrent_hash
        {where_clause}
        ORDER BY {sort_field} {order_dir}
        LIMIT %s OFFSET %s
    """, params + [page_size, offset])

    count_params = params[:]
    total = query(f"""
        SELECT COUNT(*) AS total
        FROM torrents t
        {where_clause}
    """, count_params)[0]["total"]

    return {
        "torrents": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


# ---------------------------------------------------------------------------
# API — Trackers
# ---------------------------------------------------------------------------

@app.get("/api/trackers")
def api_trackers():
    """Return upload totals grouped by tracker."""
    return query("""
        SELECT
            tracker_group,
            COUNT(*) AS torrent_count,
            ROUND(
                COALESCE(SUM(uploaded_bytes), 0) / 1073741824.0,
                2
            ) AS uploaded_gb
        FROM torrent_upload_totals
        GROUP BY tracker_group
        ORDER BY uploaded_gb DESC
    """)


@app.get("/api/trackers/daily")
def api_trackers_daily():
    """Daily uploads grouped by tracker for the last 30 days."""
    return query("SELECT * FROM upload_daily_by_group ORDER BY day, tracker_group")


@app.get("/api/tracker-groups")
def api_tracker_groups():
    """Return distinct tracker groups available for filtering."""
    rows = query("""
        SELECT DISTINCT tracker_group
        FROM upload_deltas
        ORDER BY tracker_group
    """)
    return [r["tracker_group"] for r in rows]


# ---------------------------------------------------------------------------
# API — Torrent Details
# ---------------------------------------------------------------------------

@app.get("/api/torrents/{torrent_hash}")
def api_torrent_details(torrent_hash: str):
    """Return detailed information for a single torrent."""
    # Torrent info
    torrent = query("""
        SELECT
            torrent_hash, name, size_bytes, tracker_group, privacy,
            last_state, last_seen_at, removed_at, added_at, first_seen_at,
            magnet_uri, save_path, category, tags,
            uploaded_total_bytes, downloaded_total_bytes,
            observed_seeding_seconds, num_seeds, num_leechs
        FROM torrents
        WHERE torrent_hash = %s
    """, [torrent_hash])
    if not torrent:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Torrent not found")
    t = torrent[0]

    # Upload/download history from snapshots (last 90 days, daily aggregation)
    history = query("""
        SELECT
            DATE_TRUNC('day', snapshot_at) AS day,
            AVG(uploaded_total_bytes) AS uploaded_bytes,
            AVG(downloaded_total_bytes) AS downloaded_bytes,
            AVG(observed_seeding_seconds) AS seeding_seconds
        FROM snapshots
        WHERE torrent_hash = %s
            AND snapshot_at >= NOW() - INTERVAL '90 days'
        GROUP BY 1
        ORDER BY 1
    """, [torrent_hash])

    # Upload deltas (last 90 days)
    deltas = query("""
        SELECT
            DATE_TRUNC('day', recorded_at) AS day,
            SUM(upload_delta_bytes) AS upload_delta_bytes
        FROM upload_deltas
        WHERE torrent_hash = %s
            AND recorded_at >= NOW() - INTERVAL '90 days'
        GROUP BY 1
        ORDER BY 1
    """, [torrent_hash])

    # Trackers for this torrent
    trackers = query("""
        SELECT tracker_url, tracker_host, tracker_group, tier, status, num_peers, num_seeds, num_leeches, message
        FROM torrent_trackers
        WHERE torrent_hash = %s AND active = TRUE
        ORDER BY tier, tracker_url
    """, [torrent_hash])

    # Recent events (last 20)
    events = query("""
        SELECT event_at, event_type, details
        FROM torrent_events
        WHERE torrent_hash = %s
        ORDER BY event_at DESC
        LIMIT 20
    """, [torrent_hash])

    # Total upload/download stats
    totals = query("""
        SELECT
            COALESCE(SUM(upload_delta_bytes), 0) AS total_upload_delta_bytes
        FROM upload_deltas
        WHERE torrent_hash = %s
    """, [torrent_hash])

    return {
        "torrent": {
            **t,
            "size_gb": round(float(t["size_bytes"]) / 1073741824.0, 2) if t["size_bytes"] else 0,
            "uploaded_total_gb": round(float(t["uploaded_total_bytes"]) / 1073741824.0, 2),
            "downloaded_total_gb": round(float(t["downloaded_total_bytes"]) / 1073741824.0, 2),
            "seeding_days": round(float(t["observed_seeding_seconds"]) / 86400.0, 2) if t["observed_seeding_seconds"] else 0,
        },
        "history": [
            {
                "day": h["day"].isoformat() if h["day"] else None,
                "uploaded_gb": round(float(h["uploaded_bytes"]) / 1073741824.0, 2) if h["uploaded_bytes"] else 0,
                "downloaded_gb": round(float(h["downloaded_bytes"]) / 1073741824.0, 2) if h["downloaded_bytes"] else 0,
            }
            for h in history
        ],
        "deltas": [
            {
                "day": d["day"].isoformat() if d["day"] else None,
                "uploaded_gb": round(float(d["upload_delta_bytes"]) / 1073741824.0, 4) if d["upload_delta_bytes"] else 0,
            }
            for d in deltas
        ],
        "trackers": trackers,
        "events": [
            {
                "event_at": e["event_at"].isoformat() if e["event_at"] else None,
                "event_type": e["event_type"],
                "details": e["details"],
            }
            for e in events
        ],
        "totals": {
            "total_uploaded_gb": round(float(totals[0]["total_upload_delta_bytes"]) / 1073741824.0, 2) if totals else 0,
        },
    }
