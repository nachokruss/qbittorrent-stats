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
            ROUND(COALESCE(SUM(size_bytes) FILTER (WHERE removed_at IS NULL), 0) / 1099511627776.0, 2) AS total_size_tb
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


def _uploads_by_tracker(granularity: str):
    """Upload data broken down by tracker group for stacked chart."""
    intervals = {
        "day": "30 days",
        "week": "12 weeks",
        "month": "6 months",
    }
    interval = intervals.get(granularity, "30 days")
    label_col = f"DATE_TRUNC('%s', recorded_at) AS {granularity}" % granularity

    rows = query(f"""
        SELECT
            {label_col},
            tracker_group,
            SUM(upload_delta_bytes) AS uploaded_bytes,
            ROUND(SUM(upload_delta_bytes) / 1073741824.0, 2) AS uploaded_gb
        FROM upload_deltas
        WHERE recorded_at >= NOW() - INTERVAL '{interval}'
        GROUP BY 1, 2
        ORDER BY 1, 2
    """)

    # Get distinct tracker groups and periods
    tracker_groups = sorted(set(r["tracker_group"] for r in rows))
    periods = sorted(set(r[granularity] for r in rows))

    # Build a map: period -> {tracker_group: uploaded_gb}
    data_map = {}
    for r in rows:
        period_key = r[granularity]
        if period_key not in data_map:
            data_map[period_key] = {}
        data_map[period_key][r["tracker_group"]] = r["uploaded_gb"]

    # Build datasets for Chart.js
    datasets = []
    colors = [
        "rgba(74, 144, 217, 0.8)",
        "rgba(255, 99, 132, 0.8)",
        "rgba(75, 192, 192, 0.8)",
        "rgba(255, 159, 64, 0.8)",
        "rgba(153, 102, 255, 0.8)",
        "rgba(255, 205, 86, 0.8)",
        "rgba(54, 162, 235, 0.8)",
        "rgba(255, 99, 255, 0.8)",
        "rgba(75, 0, 130, 0.8)",
        "rgba(119, 136, 153, 0.8)",
    ]
    for i, tg in enumerate(tracker_groups):
        color = colors[i % len(colors)]
        datasets.append({
            "label": tg,
            "data": [data_map.get(p, {}).get(tg, 0) for p in periods],
            "backgroundColor": color,
            "borderColor": color.replace("0.8", "1"),
            "borderWidth": 1,
        })

    # Format labels
    label_key = granularity
    labels = []
    for p in periods:
        val = p
        if hasattr(val, "strftime"):
            if granularity == "day":
                labels.append(val.strftime("%b %d"))
            elif granularity == "week":
                labels.append(val.strftime("%b %d"))
            else:
                labels.append(val.strftime("%b %Y"))
        else:
            labels.append(str(val))

    return {
        "labels": labels,
        "datasets": datasets,
        "label_key": label_key,
    }


@app.get("/api/uploads/by-tracker/daily")
def api_uploads_by_tracker_daily():
    """Daily upload data broken down by tracker group."""
    return _uploads_by_tracker("day")


@app.get("/api/uploads/by-tracker/weekly")
def api_uploads_by_tracker_weekly():
    """Weekly upload data broken down by tracker group."""
    return _uploads_by_tracker("week")


@app.get("/api/uploads/by-tracker/monthly")
def api_uploads_by_tracker_monthly():
    """Monthly upload data broken down by tracker group."""
    return _uploads_by_tracker("month")


# ---------------------------------------------------------------------------
# API — Torrents
# ---------------------------------------------------------------------------

@app.get("/api/torrents")
def api_torrents(
    search: str = Query("", description="Search by name"),
    tracker: str = Query("", description="Filter by tracker group"),
    privacy: str = Query("", description="Filter by privacy (public/private)"),
    state: str = Query("", description="Filter by state"),
    show_deleted: Optional[str] = Query(None, description="Show deleted torrents: true or false"),
    last_seen: str = Query("15d", description="Last seen range: 15d, 1m, 3m, 1y, all"),
    sort: str = Query("name", description="Sort field: name, uploaded_gb, last_seen_at"),
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
    if show_deleted == "false":
        conditions.append("t.removed_at IS NULL")
    if last_seen and last_seen != "all":
        interval_map = {
            "15d": "15 days",
            "1m": "1 month",
            "3m": "3 months",
            "1y": "1 year",
        }
        interval_str = interval_map.get(last_seen)
        if interval_str:
            # PostgreSQL requires a literal value after INTERVAL, not a parameter
            conditions.append(f"t.last_seen_at >= NOW() - INTERVAL '{interval_str}'")

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    # Validate sort field
    allowed_sort = {"name", "tracker_group", "privacy", "last_state", "uploaded_gb", "last_seen_at"}
    sort_field = sort if sort in allowed_sort else "name"
    order_dir = "DESC" if order == "desc" else "ASC"

    offset = (page - 1) * page_size

    rows = query(f"""
        SELECT
            t.torrent_hash, t.name, t.size_bytes, t.tracker_group, t.privacy,
            t.last_state, t.last_seen_at, t.removed_at,
            ROUND(COALESCE(tut.uploaded_gb, 0), 2) AS uploaded_gb
        FROM torrents t
        LEFT JOIN torrent_upload_totals tut ON tut.torrent_hash = t.torrent_hash
        {where_clause}
        ORDER BY {sort_field} {order_dir}, t.name ASC, t.removed_at IS NULL DESC
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
    """Return upload totals grouped by tracker (active torrents only)."""
    return query("""
        SELECT
            t.tracker_group,
            COUNT(*) AS torrent_count,
            ROUND(
                COALESCE(SUM(tut.uploaded_bytes), 0) / 1073741824.0,
                2
            ) AS uploaded_gb
        FROM torrents t
        LEFT JOIN torrent_upload_totals tut ON tut.torrent_hash = t.torrent_hash
        WHERE t.removed_at IS NULL
        GROUP BY t.tracker_group
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
        FROM (
            SELECT tracker_group FROM upload_deltas
            UNION
            SELECT tracker_group FROM torrents WHERE removed_at IS NULL
        ) AS all_groups
        WHERE tracker_group IS NOT NULL
        ORDER BY tracker_group
    """)
    return [r["tracker_group"] for r in rows]


@app.get("/api/tracker-details/{tracker_group}")
def api_tracker_details(tracker_group: str):
    """Return detailed statistics for a tracker group."""
    # Summary stats
    summary = query("""
        SELECT
            COUNT(*) FILTER (WHERE removed_at IS NULL) AS active_torrents,
            COUNT(*) FILTER (WHERE removed_at IS NOT NULL) AS removed_torrents,
            COUNT(*) AS total_torrents,
            ROUND(COALESCE(SUM(size_bytes) FILTER (WHERE removed_at IS NULL), 0) / 1073741824.0, 2) AS active_size_gb,
            ROUND(COALESCE(SUM(uploaded_total_bytes), 0) / 1073741824.0, 2) AS total_uploaded_gb,
            ROUND(COALESCE(SUM(downloaded_total_bytes), 0) / 1073741824.0, 2) AS total_downloaded_gb,
            MIN(first_seen_at) AS earliest_seen,
            MAX(last_seen_at) AS latest_seen
        FROM torrents
        WHERE tracker_group = %s
    """, [tracker_group])

    # State breakdown for active torrents
    states = query("""
        SELECT
            last_state,
            COUNT(*) AS count
        FROM torrents
        WHERE tracker_group = %s AND removed_at IS NULL
        GROUP BY last_state
        ORDER BY count DESC
    """, [tracker_group])

    # Top 10 torrents by upload (active only)
    top_torrents = query("""
        SELECT
            torrent_hash, name, size_bytes, privacy, last_state,
            uploaded_total_bytes, first_seen_at, last_seen_at
        FROM torrents
        WHERE tracker_group = %s AND removed_at IS NULL
        ORDER BY uploaded_total_bytes DESC
        LIMIT 10
    """, [tracker_group])

    # Upload history (last 90 days, daily aggregation)
    upload_history = query("""
        SELECT
            DATE_TRUNC('day', recorded_at)::date AS day,
            SUM(upload_delta_bytes) AS uploaded_bytes
        FROM upload_deltas
        WHERE tracker_group = %s
            AND recorded_at >= NOW() - INTERVAL '90 days'
        GROUP BY 1
        ORDER BY 1
    """, [tracker_group])

    s = summary[0] if summary else {}
    return {
        "tracker_group": tracker_group,
        "summary": {
            **s,
            "earliest_seen_str": s.get("earliest_seen").isoformat() if s.get("earliest_seen") else None,
            "latest_seen_str": s.get("latest_seen").isoformat() if s.get("latest_seen") else None,
        },
        "states": states,
        "top_torrents": [
            {
                **t,
                "size_gb": round(float(t["size_bytes"]) / 1073741824.0, 2) if t["size_bytes"] else 0,
                "uploaded_gb": round(float(t["uploaded_total_bytes"]) / 1073741824.0, 2),
                "first_seen_str": t["first_seen_at"].isoformat() if t["first_seen_at"] else None,
                "last_seen_str": t["last_seen_at"].isoformat() if t["last_seen_at"] else None,
            }
            for t in top_torrents
        ],
        "upload_history": [
            {
                "day": h["day"].isoformat() if h["day"] else None,
                "uploaded_gb": round(float(h["uploaded_bytes"]) / 1073741824.0, 4) if h["uploaded_bytes"] else 0,
            }
            for h in upload_history
        ],
    }


# ---------------------------------------------------------------------------
# API — Analytics
# ---------------------------------------------------------------------------

@app.get("/api/analytics/top5-daily")
def api_analytics_top5_daily(
    tracker: Optional[str] = Query(None, description="Filter by tracker group"),
    period: str = Query("weekly", description="Period: weekly, monthly, quarter, year"),
    limit: int = Query(5, ge=1, le=50, description="Number of top torrents per day"),
):
    """Return top N torrents by upload delta per period, with period totals."""
    period_config = {
        "daily": {"days": 14, "trunc": "day", "label": "DAILY TOTAL"},
        "weekly": {"days": 28, "trunc": "week", "label": "WEEKLY TOTAL"},
        "monthly": {"days": 60, "trunc": "month", "label": "MONTHLY TOTAL"},
        "quarter": {"days": 90, "trunc": "quarter", "label": "QUARTERLY TOTAL"},
        "year": {"days": 365, "trunc": "year", "label": "YEARLY TOTAL"},
    }
    config = period_config.get(period, period_config["weekly"])
    days = config["days"]
    trunc = config["trunc"]
    total_label = config["label"]

    conditions = [f"recorded_at >= NOW() - INTERVAL '{days} days'"]

    if tracker:
        conditions.append(f"tracker_group = '{tracker}'")

    where_clause = "WHERE " + " AND ".join(conditions)

    rows = query(f"""
        WITH period_torrent_upload AS (
            SELECT
                DATE_TRUNC('{trunc}', recorded_at)::date AS period_start,
                torrent_hash,
                name,
                privacy,
                tracker_group,
                SUM(upload_delta_bytes) AS uploaded_bytes
            FROM upload_deltas
            {where_clause}
            GROUP BY
                DATE_TRUNC('{trunc}', recorded_at)::date,
                torrent_hash,
                name,
                privacy,
                tracker_group
        ),
        ranked AS (
            SELECT
                *,
                ROW_NUMBER() OVER (
                    PARTITION BY period_start
                    ORDER BY uploaded_bytes DESC
                ) AS rank
            FROM period_torrent_upload
        ),
        topN AS (
            SELECT
                period_start,
                rank,
                torrent_hash,
                name,
                privacy,
                tracker_group,
                uploaded_bytes
            FROM ranked
            WHERE rank <= {limit}
        ),
        period_totals AS (
            SELECT
                DATE_TRUNC('{trunc}', recorded_at)::date AS period_start,
                SUM(upload_delta_bytes) AS uploaded_bytes
            FROM upload_deltas
            {where_clause}
            GROUP BY DATE_TRUNC('{trunc}', recorded_at)::date
        )
        SELECT
            period_start,
            rank,
            torrent_hash,
            name,
            privacy,
            tracker_group,
            uploaded_bytes
        FROM topN

        UNION ALL

        SELECT
            period_start,
            NULL AS rank,
            NULL AS torrent_hash,
            '{total_label}' AS name,
            NULL AS privacy,
            NULL AS tracker_group,
            uploaded_bytes
        FROM period_totals

        ORDER BY
            period_start DESC,
            rank NULLS LAST
    """)

    return [
        {
            **r,
            "day": r["period_start"].isoformat() if r["period_start"] else None,
            "period": period,
        }
        for r in rows
    ]


@app.get("/api/analytics/efficiency")
def api_analytics_efficiency(
    tracker: Optional[str] = Query(None, description="Filter by tracker group"),
    days: int = Query(15, ge=1, le=90, description="Number of days for upload window"),
    min_seeding_days: int = Query(0, ge=0, le=365, description="Minimum seeding days filter"),
):
    """Return efficiency ranking of active torrents."""
    conditions = ["t.removed_at IS NULL", "t.size_bytes > 0"]
    params: list = []

    if tracker:
        conditions.append("t.tracker_group = %s")
        params.append(tracker)

    if min_seeding_days > 0:
        conditions.append(f"t.observed_seeding_seconds >= {min_seeding_days} * 86400")

    where_clause = "WHERE " + " AND ".join(conditions)

    rows = query(f"""
        WITH upload_{days}d AS (
            SELECT
                torrent_hash,
                SUM(upload_delta_bytes) AS upload_{days}d_bytes,
                COUNT(DISTINCT recorded_at::date) AS active_upload_days
            FROM upload_deltas
            WHERE recorded_at >= NOW() - INTERVAL '{days} days'
            GROUP BY torrent_hash
        ),
        torrent_data AS (
            SELECT
                t.torrent_hash,
                t.name,
                t.size_bytes,
                t.privacy,
                t.tracker_group,
                t.added_at,
                t.observed_seeding_seconds,
                COALESCE(u.upload_{days}d_bytes, 0) AS upload_{days}d_bytes,
                COALESCE(u.active_upload_days, 0) AS active_upload_days
            FROM torrents t
            LEFT JOIN upload_{days}d u
                ON u.torrent_hash = t.torrent_hash
            {where_clause}
        ),
        ranking AS (
            SELECT
                *,

                -- Upload relativo al tamaño del torrent
                upload_{days}d_bytes::numeric / size_bytes AS upload_size_ratio,

                -- GB subidos por día de seeding
                CASE
                    WHEN observed_seeding_seconds > 0
                    THEN upload_{days}d_bytes::numeric
                         / (observed_seeding_seconds / 86400.0)
                    ELSE 0
                END AS upload_per_seeding_day_bytes,

                -- Eficiencia combinada:
                -- upload / tamaño / días de seeding
                CASE
                    WHEN observed_seeding_seconds > 0
                    THEN
                        (upload_{days}d_bytes::numeric / size_bytes)
                        / (observed_seeding_seconds / 86400.0)
                    ELSE 0
                END AS efficiency
            FROM torrent_data
        )
        SELECT
            ROW_NUMBER() OVER (
                ORDER BY efficiency DESC
            ) AS ranking,

            torrent_hash,

            name,

            ROUND(size_bytes / 1073741824.0, 2) AS size_gb,

            ROUND(
                upload_{days}d_bytes / 1073741824.0,
                2
            ) AS upload_{days}d_gb,

            ROUND(
                upload_size_ratio,
                2
            ) AS upload_vs_size,

            ROUND(
                upload_per_seeding_day_bytes
                / 1073741824.0,
                2
            ) AS upload_gb_per_seeding_day,

            ROUND(
                efficiency,
                5
            ) AS efficiency,

            ROUND(observed_seeding_seconds / 86400.0, 1) AS seeding_days,

            privacy,
            tracker_group,

            CASE
                WHEN efficiency >= 0.10 THEN 'High'
                WHEN efficiency >= 0.03 THEN 'Medium'
                WHEN efficiency >= 0.01 THEN 'Low'
                ELSE 'Very Low'
            END AS classification

        FROM ranking
        ORDER BY efficiency DESC
    """, params)

    return rows


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
