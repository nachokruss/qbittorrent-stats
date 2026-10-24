-- migrate:up
-- Reclassify ALL remaining "Other Private" records across all tables.
-- This catches historical records in upload_deltas and snapshots that were
-- classified before tracker URL patterns were updated.
-- It uses all known tracker URL patterns from collector/utils.py.
-- Any "Other Private" records that do not match a known private tracker
-- are reclassified as "Public" since the user only uses BTArg and IPTorrents
-- as private trackers.

-- Fix upload_deltas: reclassify "Other Private" where URL matches a known tracker
UPDATE upload_deltas
SET
    tracker_group = CASE
        WHEN primary_tracker_url LIKE 'https://announce.btarg.org/%' THEN 'BTArg'
        WHEN primary_tracker_url LIKE 'http://127.0.0.1.stackoverflow.tech/%' THEN 'IPTorrents'
        WHEN primary_tracker_url LIKE 'http://async.empirehost.me/%' THEN 'IPTorrents'
        WHEN primary_tracker_url LIKE 'http://routing.bgp.technology/%' THEN 'IPTorrents'
        ELSE 'Public'  -- Remaining "Other Private" → Public
    END,
    privacy = CASE
        WHEN primary_tracker_url LIKE 'https://announce.btarg.org/%' THEN 'private'
        WHEN primary_tracker_url LIKE 'http://127.0.0.1.stackoverflow.tech/%' THEN 'private'
        WHEN primary_tracker_url LIKE 'http://async.empirehost.me/%' THEN 'private'
        WHEN primary_tracker_url LIKE 'http://routing.bgp.technology/%' THEN 'private'
        ELSE 'public'
    END
WHERE
    tracker_group = 'Other Private';

-- Fix snapshots: same logic
UPDATE snapshots
SET
    tracker_group = CASE
        WHEN primary_tracker_url LIKE 'https://announce.btarg.org/%' THEN 'BTArg'
        WHEN primary_tracker_url LIKE 'http://127.0.0.1.stackoverflow.tech/%' THEN 'IPTorrents'
        WHEN primary_tracker_url LIKE 'http://async.empirehost.me/%' THEN 'IPTorrents'
        WHEN primary_tracker_url LIKE 'http://routing.bgp.technology/%' THEN 'IPTorrents'
        ELSE 'Public'
    END,
    privacy = CASE
        WHEN primary_tracker_url LIKE 'https://announce.btarg.org/%' THEN 'private'
        WHEN primary_tracker_url LIKE 'http://127.0.0.1.stackoverflow.tech/%' THEN 'private'
        WHEN primary_tracker_url LIKE 'http://async.empirehost.me/%' THEN 'private'
        WHEN primary_tracker_url LIKE 'http://routing.bgp.technology/%' THEN 'private'
        ELSE 'public'
    END
WHERE
    tracker_group = 'Other Private';

-- Fix torrents: same logic (in case any were missed by previous migrations)
UPDATE torrents
SET
    tracker_group = CASE
        WHEN primary_tracker_url LIKE 'https://announce.btarg.org/%' THEN 'BTArg'
        WHEN primary_tracker_url LIKE 'http://127.0.0.1.stackoverflow.tech/%' THEN 'IPTorrents'
        WHEN primary_tracker_url LIKE 'http://async.empirehost.me/%' THEN 'IPTorrents'
        WHEN primary_tracker_url LIKE 'http://routing.bgp.technology/%' THEN 'IPTorrents'
        ELSE 'Public'
    END,
    privacy = CASE
        WHEN primary_tracker_url LIKE 'https://announce.btarg.org/%' THEN 'private'
        WHEN primary_tracker_url LIKE 'http://127.0.0.1.stackoverflow.tech/%' THEN 'private'
        WHEN primary_tracker_url LIKE 'http://async.empirehost.me/%' THEN 'private'
        WHEN primary_tracker_url LIKE 'http://routing.bgp.technology/%' THEN 'private'
        ELSE 'public'
    END,
    is_private = CASE
        WHEN primary_tracker_url LIKE 'https://announce.btarg.org/%' THEN TRUE
        WHEN primary_tracker_url LIKE 'http://127.0.0.1.stackoverflow.tech/%' THEN TRUE
        WHEN primary_tracker_url LIKE 'http://async.empirehost.me/%' THEN TRUE
        WHEN primary_tracker_url LIKE 'http://routing.bgp.technology/%' THEN TRUE
        ELSE FALSE
    END,
    updated_at = NOW()
WHERE
    tracker_group = 'Other Private';


-- migrate:down
-- Reverse: change reclassified records back to "Other Private"
UPDATE upload_deltas
SET
    tracker_group = 'Other Private',
    privacy = 'private'
WHERE
    tracker_group IN ('BTArg', 'IPTorrents', 'Public')
    AND (
        primary_tracker_url LIKE 'https://announce.btarg.org/%'
        OR primary_tracker_url LIKE 'http://127.0.0.1.stackoverflow.tech/%'
        OR primary_tracker_url LIKE 'http://async.empirehost.me/%'
        OR primary_tracker_url LIKE 'http://routing.bgp.technology/%'
    );

UPDATE upload_deltas
SET
    tracker_group = 'Other Private',
    privacy = 'private'
WHERE
    tracker_group = 'Public'
    AND primary_tracker_url NOT LIKE 'https://announce.btarg.org/%'
    AND primary_tracker_url NOT LIKE 'http://127.0.0.1.stackoverflow.tech/%'
    AND primary_tracker_url NOT LIKE 'http://async.empirehost.me/%'
    AND primary_tracker_url NOT LIKE 'http://routing.bgp.technology/%';

UPDATE snapshots
SET
    tracker_group = 'Other Private',
    privacy = 'private'
WHERE
    tracker_group IN ('BTArg', 'IPTorrents', 'Public')
    AND (
        primary_tracker_url LIKE 'https://announce.btarg.org/%'
        OR primary_tracker_url LIKE 'http://127.0.0.1.stackoverflow.tech/%'
        OR primary_tracker_url LIKE 'http://async.empirehost.me/%'
        OR primary_tracker_url LIKE 'http://routing.bgp.technology/%'
    );

UPDATE snapshots
SET
    tracker_group = 'Other Private',
    privacy = 'private'
WHERE
    tracker_group = 'Public'
    AND primary_tracker_url NOT LIKE 'https://announce.btarg.org/%'
    AND primary_tracker_url NOT LIKE 'http://127.0.0.1.stackoverflow.tech/%'
    AND primary_tracker_url NOT LIKE 'http://async.empirehost.me/%'
    AND primary_tracker_url NOT LIKE 'http://routing.bgp.technology/%';

UPDATE torrents
SET
    tracker_group = 'Other Private',
    privacy = 'private',
    is_private = TRUE,
    updated_at = NOW()
WHERE
    tracker_group IN ('BTArg', 'IPTorrents', 'Public')
    AND (
        primary_tracker_url LIKE 'https://announce.btarg.org/%'
        OR primary_tracker_url LIKE 'http://127.0.0.1.stackoverflow.tech/%'
        OR primary_tracker_url LIKE 'http://async.empirehost.me/%'
        OR primary_tracker_url LIKE 'http://routing.bgp.technology/%'
    );

UPDATE torrents
SET
    tracker_group = 'Other Private',
    privacy = 'private',
    is_private = TRUE,
    updated_at = NOW()
WHERE
    tracker_group = 'Public'
    AND primary_tracker_url NOT LIKE 'https://announce.btarg.org/%'
    AND primary_tracker_url NOT LIKE 'http://127.0.0.1.stackoverflow.tech/%'
    AND primary_tracker_url NOT LIKE 'http://async.empirehost.me/%'
    AND primary_tracker_url NOT LIKE 'http://routing.bgp.technology/%';
