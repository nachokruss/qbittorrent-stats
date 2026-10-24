-- migrate:up
CREATE TABLE IF NOT EXISTS torrents (
    torrent_hash TEXT PRIMARY KEY,

    name TEXT NOT NULL,

    size_bytes BIGINT,
    category TEXT,
    tags TEXT,
    save_path TEXT,

    added_at TIMESTAMPTZ,

    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    removed_at TIMESTAMPTZ,

    is_private BOOLEAN NOT NULL DEFAULT FALSE,
    privacy TEXT NOT NULL DEFAULT 'public',

    tracker_group TEXT NOT NULL DEFAULT 'Public',

    primary_tracker_url TEXT,
    primary_tracker_host TEXT,

    magnet_uri TEXT,

    qbittorrent_seeding_seconds BIGINT,
    observed_seeding_seconds BIGINT NOT NULL DEFAULT 0,

    last_state TEXT,
    last_activity_at TIMESTAMPTZ,

    uploaded_total_bytes BIGINT NOT NULL DEFAULT 0,
    downloaded_total_bytes BIGINT NOT NULL DEFAULT 0,

    num_seeds INTEGER,
    num_leechs INTEGER,
    num_complete INTEGER,
    num_incomplete INTEGER,

    trackers_refreshed_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


CREATE TABLE IF NOT EXISTS torrent_trackers (
    id BIGSERIAL PRIMARY KEY,

    torrent_hash TEXT NOT NULL
        REFERENCES torrents(torrent_hash)
        ON DELETE CASCADE,

    tracker_url TEXT NOT NULL,
    tracker_host TEXT,

    tracker_group TEXT NOT NULL DEFAULT 'Other',

    tier INTEGER,

    status INTEGER,
    num_peers INTEGER,
    num_seeds INTEGER,
    num_leeches INTEGER,
    num_downloads INTEGER,

    message TEXT,

    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    active BOOLEAN NOT NULL DEFAULT TRUE,

    UNIQUE (torrent_hash, tracker_url)
);


CREATE TABLE IF NOT EXISTS snapshots (
    id BIGSERIAL PRIMARY KEY,

    snapshot_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    torrent_hash TEXT NOT NULL
        REFERENCES torrents(torrent_hash)
        ON DELETE CASCADE,

    name TEXT NOT NULL,

    privacy TEXT NOT NULL,
    tracker_group TEXT NOT NULL,

    primary_tracker_url TEXT,
    magnet_uri TEXT,

    uploaded_total_bytes BIGINT NOT NULL DEFAULT 0,
    downloaded_total_bytes BIGINT NOT NULL DEFAULT 0,

    qbittorrent_seeding_seconds BIGINT,
    observed_seeding_seconds BIGINT NOT NULL DEFAULT 0,

    state TEXT,

    UNIQUE (snapshot_at, torrent_hash)
);


CREATE TABLE IF NOT EXISTS upload_deltas (
    id BIGSERIAL PRIMARY KEY,

    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    torrent_hash TEXT NOT NULL
        REFERENCES torrents(torrent_hash)
        ON DELETE CASCADE,

    name TEXT NOT NULL,

    uploaded_total_bytes BIGINT NOT NULL DEFAULT 0,
    upload_delta_bytes BIGINT NOT NULL DEFAULT 0,

    privacy TEXT NOT NULL,
    tracker_group TEXT NOT NULL,

    primary_tracker_url TEXT,

    UNIQUE (recorded_at, torrent_hash)
);


CREATE TABLE IF NOT EXISTS collector_runs (
    id BIGSERIAL PRIMARY KEY,

    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,

    torrents_seen INTEGER DEFAULT 0,
    torrents_processed INTEGER DEFAULT 0,

    errors INTEGER DEFAULT 0,

    status TEXT NOT NULL DEFAULT 'running',
    error_message TEXT
);


CREATE TABLE IF NOT EXISTS torrent_events (
    id BIGSERIAL PRIMARY KEY,

    event_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    torrent_hash TEXT NOT NULL
        REFERENCES torrents(torrent_hash)
        ON DELETE CASCADE,

    event_type TEXT NOT NULL,

    details JSONB
);


CREATE INDEX IF NOT EXISTS idx_torrents_tracker_group
    ON torrents(tracker_group);

CREATE INDEX IF NOT EXISTS idx_torrents_privacy
    ON torrents(privacy);

CREATE INDEX IF NOT EXISTS idx_torrents_added_at
    ON torrents(added_at);

CREATE INDEX IF NOT EXISTS idx_torrents_last_seen
    ON torrents(last_seen_at);

CREATE INDEX IF NOT EXISTS idx_torrent_trackers_hash
    ON torrent_trackers(torrent_hash);

CREATE INDEX IF NOT EXISTS idx_upload_deltas_recorded
    ON upload_deltas(recorded_at);

CREATE INDEX IF NOT EXISTS idx_upload_deltas_hash
    ON upload_deltas(torrent_hash);

CREATE INDEX IF NOT EXISTS idx_snapshots_recorded
    ON snapshots(snapshot_at);

CREATE INDEX IF NOT EXISTS idx_snapshots_hash
    ON snapshots(torrent_hash);


-- ============================================================
-- TORRENT TOTALS
-- ============================================================

CREATE OR REPLACE VIEW torrent_upload_totals AS
SELECT
    t.torrent_hash,
    t.name,
    t.added_at,

    t.privacy,
    t.tracker_group,

    t.primary_tracker_url,
    t.primary_tracker_host,

    t.magnet_uri,

    t.size_bytes,

    COALESCE(
        t.qbittorrent_seeding_seconds,
        t.observed_seeding_seconds,
        0
    ) AS seeding_seconds,

    ROUND(
        COALESCE(
            t.qbittorrent_seeding_seconds,
            t.observed_seeding_seconds,
            0
        ) / 86400.0,
        2
    ) AS seeding_days,

    COALESCE(
        SUM(ud.upload_delta_bytes),
        0
    ) AS uploaded_bytes,

    ROUND(
        COALESCE(
            SUM(ud.upload_delta_bytes),
            0
        ) / 1073741824.0,
        2
    ) AS uploaded_gb

FROM torrents t

LEFT JOIN upload_deltas ud
    ON ud.torrent_hash = t.torrent_hash

GROUP BY
    t.torrent_hash;


-- ============================================================
-- LAST 30 DAYS
-- ============================================================

CREATE OR REPLACE VIEW upload_last_30_days AS
SELECT
    ud.torrent_hash,
    ud.name,
    ud.recorded_at,
    ud.upload_delta_bytes,
    ud.privacy,
    ud.tracker_group,
    ud.primary_tracker_url
FROM upload_deltas ud
WHERE ud.recorded_at >= NOW() - INTERVAL '30 days';


CREATE OR REPLACE VIEW upload_last_30_days_daily AS
SELECT
    DATE_TRUNC('day', recorded_at) AS day,
    SUM(upload_delta_bytes) AS uploaded_bytes,
    ROUND(
        SUM(upload_delta_bytes) / 1073741824.0,
        2
    ) AS uploaded_gb
FROM upload_deltas
WHERE recorded_at >= NOW() - INTERVAL '30 days'
GROUP BY 1
ORDER BY 1;


-- ============================================================
-- LAST 12 WEEKS
-- ============================================================

CREATE OR REPLACE VIEW upload_last_12_weeks AS
SELECT
    ud.torrent_hash,
    ud.name,
    ud.recorded_at,
    ud.upload_delta_bytes,
    ud.privacy,
    ud.tracker_group,
    ud.primary_tracker_url
FROM upload_deltas ud
WHERE ud.recorded_at >= NOW() - INTERVAL '12 weeks';


CREATE OR REPLACE VIEW upload_last_12_weeks_weekly AS
SELECT
    DATE_TRUNC('week', recorded_at) AS week,
    SUM(upload_delta_bytes) AS uploaded_bytes,
    ROUND(
        SUM(upload_delta_bytes) / 1073741824.0,
        2
    ) AS uploaded_gb
FROM upload_deltas
WHERE recorded_at >= NOW() - INTERVAL '12 weeks'
GROUP BY 1
ORDER BY 1;


-- ============================================================
-- LAST 6 MONTHS
-- ============================================================

CREATE OR REPLACE VIEW upload_last_6_months AS
SELECT
    ud.torrent_hash,
    ud.name,
    ud.recorded_at,
    ud.upload_delta_bytes,
    ud.privacy,
    ud.tracker_group,
    ud.primary_tracker_url
FROM upload_deltas ud
WHERE ud.recorded_at >= NOW() - INTERVAL '6 months';


CREATE OR REPLACE VIEW upload_last_6_months_monthly AS
SELECT
    DATE_TRUNC('month', recorded_at) AS month,
    SUM(upload_delta_bytes) AS uploaded_bytes,
    ROUND(
        SUM(upload_delta_bytes) / 1073741824.0,
        2
    ) AS uploaded_gb
FROM upload_deltas
WHERE recorded_at >= NOW() - INTERVAL '6 months'
GROUP BY 1
ORDER BY 1;


-- ============================================================
-- GROUPED BY PUBLIC / PRIVATE TRACKER GROUP
-- ============================================================

CREATE OR REPLACE VIEW torrent_summary_by_group AS
SELECT
    privacy,
    tracker_group,

    COUNT(*) AS torrent_count,

    ROUND(
        SUM(size_bytes) / 1099511627776.0,
        2
    ) AS size_tb,

    ROUND(
        SUM(
            COALESCE(
                (
                    SELECT SUM(ud.upload_delta_bytes)
                    FROM upload_deltas ud
                    WHERE ud.torrent_hash = t.torrent_hash
                ),
                0
            )
        ) / 1099511627776.0,
        2
    ) AS uploaded_tb

FROM torrents t

GROUP BY
    privacy,
    tracker_group

ORDER BY
    privacy,
    tracker_group;


CREATE OR REPLACE VIEW upload_last_30_days_by_group AS
SELECT
    privacy,
    tracker_group,

    SUM(upload_delta_bytes) AS uploaded_bytes,

    ROUND(
        SUM(upload_delta_bytes) / 1073741824.0,
        2
    ) AS uploaded_gb

FROM upload_deltas

WHERE recorded_at >= NOW() - INTERVAL '30 days'

GROUP BY
    privacy,
    tracker_group

ORDER BY
    privacy,
    tracker_group;


CREATE OR REPLACE VIEW upload_last_12_weeks_by_group AS
SELECT
    privacy,
    tracker_group,

    SUM(upload_delta_bytes) AS uploaded_bytes,

    ROUND(
        SUM(upload_delta_bytes) / 1073741824.0,
        2
    ) AS uploaded_gb

FROM upload_deltas

WHERE recorded_at >= NOW() - INTERVAL '12 weeks'

GROUP BY
    privacy,
    tracker_group

ORDER BY
    privacy,
    tracker_group;


CREATE OR REPLACE VIEW upload_last_6_months_by_group AS
SELECT
    privacy,
    tracker_group,

    SUM(upload_delta_bytes) AS uploaded_bytes,

    ROUND(
        SUM(upload_delta_bytes) / 1073741824.0,
        2
    ) AS uploaded_gb

FROM upload_deltas

WHERE recorded_at >= NOW() - INTERVAL '6 months'

GROUP BY
    privacy,
    tracker_group

ORDER BY
    privacy,
    tracker_group;


CREATE OR REPLACE VIEW upload_daily_by_group AS
SELECT
    DATE_TRUNC('day', recorded_at) AS day,

    privacy,
    tracker_group,

    SUM(upload_delta_bytes) AS uploaded_bytes,

    ROUND(
        SUM(upload_delta_bytes) / 1073741824.0,
        2
    ) AS uploaded_gb

FROM upload_deltas

WHERE recorded_at >= NOW() - INTERVAL '30 days'

GROUP BY
    1, 2, 3

ORDER BY
    1, 2, 3;


CREATE OR REPLACE VIEW upload_weekly_by_group AS
SELECT
    DATE_TRUNC('week', recorded_at) AS week,

    privacy,
    tracker_group,

    SUM(upload_delta_bytes) AS uploaded_bytes,

    ROUND(
        SUM(upload_delta_bytes) / 1073741824.0,
        2
    ) AS uploaded_gb

FROM upload_deltas

WHERE recorded_at >= NOW() - INTERVAL '12 weeks'

GROUP BY
    1, 2, 3

ORDER BY
    1, 2, 3;


CREATE OR REPLACE VIEW upload_monthly_by_group AS
SELECT
    DATE_TRUNC('month', recorded_at) AS month,

    privacy,
    tracker_group,

    SUM(upload_delta_bytes) AS uploaded_bytes,

    ROUND(
        SUM(upload_delta_bytes) / 1073741824.0,
        2
    ) AS uploaded_gb

FROM upload_deltas

WHERE recorded_at >= NOW() - INTERVAL '6 months'

GROUP BY
    1, 2, 3

ORDER BY
    1, 2, 3;


-- ============================================================
-- TRACKER LIST
-- ============================================================

CREATE OR REPLACE VIEW torrent_tracker_list AS
SELECT
    t.torrent_hash,
    t.name,

    t.privacy,
    t.tracker_group,

    tt.tracker_url,
    tt.tracker_host,
    tt.tracker_group AS tracker_specific_group,

    tt.tier,
    tt.status,

    tt.num_peers,
    tt.num_seeds,
    tt.num_leeches,
    tt.num_downloads,

    tt.active,
    tt.first_seen_at,
    tt.last_seen_at

FROM torrents t

JOIN torrent_trackers tt
    ON tt.torrent_hash = t.torrent_hash

ORDER BY
    t.name,
    tt.tracker_url;


-- ============================================================
-- TORRENTS WITH NO UPLOAD IN LAST 30 DAYS
-- ============================================================

CREATE OR REPLACE VIEW no_upload_last_30_days AS
SELECT
    t.torrent_hash,
    t.name,
    t.added_at,

    t.privacy,
    t.tracker_group,

    t.primary_tracker_url,

    t.qbittorrent_seeding_seconds,

    ROUND(
        COALESCE(
            t.qbittorrent_seeding_seconds,
            t.observed_seeding_seconds,
            0
        ) / 86400.0,
        2
    ) AS seeding_days

FROM torrents t

WHERE NOT EXISTS (
    SELECT 1
    FROM upload_deltas ud
    WHERE ud.torrent_hash = t.torrent_hash
      AND ud.recorded_at >= NOW() - INTERVAL '30 days'
);


-- ============================================================
-- TORRENTS THAT UPLOADED IN LAST 30 DAYS
-- ============================================================

CREATE OR REPLACE VIEW uploading_last_30_days AS
SELECT
    t.torrent_hash,
    t.name,
    t.added_at,

    t.privacy,
    t.tracker_group,

    t.primary_tracker_url,

    SUM(ud.upload_delta_bytes) AS uploaded_bytes,

    ROUND(
        SUM(ud.upload_delta_bytes) / 1073741824.0,
        2
    ) AS uploaded_gb

FROM torrents t

JOIN upload_deltas ud
    ON ud.torrent_hash = t.torrent_hash

WHERE ud.recorded_at >= NOW() - INTERVAL '30 days'

GROUP BY
    t.torrent_hash

ORDER BY
    uploaded_bytes DESC;


-- migrate:down
DROP VIEW IF EXISTS uploading_last_30_days;
DROP VIEW IF EXISTS no_upload_last_30_days;
DROP VIEW IF EXISTS torrent_tracker_list;
DROP VIEW IF EXISTS upload_monthly_by_group;
DROP VIEW IF EXISTS upload_weekly_by_group;
DROP VIEW IF EXISTS upload_daily_by_group;
DROP VIEW IF EXISTS upload_last_6_months_by_group;
DROP VIEW IF EXISTS upload_last_12_weeks_by_group;
DROP VIEW IF EXISTS upload_last_30_days_by_group;
DROP VIEW IF EXISTS torrent_summary_by_group;
DROP VIEW IF EXISTS upload_last_6_months_monthly;
DROP VIEW IF EXISTS upload_last_6_months;
DROP VIEW IF EXISTS upload_last_12_weeks_weekly;
DROP VIEW IF EXISTS upload_last_12_weeks;
DROP VIEW IF EXISTS upload_last_30_days_daily;
DROP VIEW IF EXISTS upload_last_30_days;
DROP VIEW IF EXISTS torrent_upload_totals;

DROP INDEX IF EXISTS idx_snapshots_hash;
DROP INDEX IF EXISTS idx_snapshots_recorded;
DROP INDEX IF EXISTS idx_upload_deltas_hash;
DROP INDEX IF EXISTS idx_upload_deltas_recorded;
DROP INDEX IF EXISTS idx_torrent_trackers_hash;
DROP INDEX IF EXISTS idx_torrents_last_seen;
DROP INDEX IF EXISTS idx_torrents_added_at;
DROP INDEX IF EXISTS idx_torrents_privacy;
DROP INDEX IF EXISTS idx_torrents_tracker_group;

DROP TABLE IF EXISTS torrent_events;
DROP TABLE IF EXISTS collector_runs;
DROP TABLE IF EXISTS upload_deltas;
DROP TABLE IF EXISTS snapshots;
DROP TABLE IF EXISTS torrent_trackers;
DROP TABLE IF EXISTS torrents;
