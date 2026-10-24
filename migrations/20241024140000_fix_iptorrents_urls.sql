-- migrate:up
-- Reclassify "Other Private" torrents whose tracker URLs match known IPTorrents patterns.
-- The previous migration (20241024130000) only knew about the old IPTorrents URL
-- (127.0.0.1.stackoverflow.tech), but IPTorrents also uses async.empirehost.me and
-- routing.bgp.technology. Torrents with those URLs were incorrectly classified as
-- "Other Private" and need to be fixed.

UPDATE torrents
SET
    tracker_group = 'IPTorrents',
    privacy = 'private',
    is_private = TRUE,
    updated_at = NOW()
WHERE
    tracker_group = 'Other Private'
    AND (
        primary_tracker_url LIKE 'http://async.empirehost.me/%'
        OR primary_tracker_url LIKE 'http://routing.bgp.technology/%'
    );

-- Also fix upload_deltas records for consistency
UPDATE upload_deltas
SET
    tracker_group = 'IPTorrents',
    privacy = 'private'
WHERE
    tracker_group = 'Other Private'
    AND (
        primary_tracker_url LIKE 'http://async.empirehost.me/%'
        OR primary_tracker_url LIKE 'http://routing.bgp.technology/%'
    );

-- Fix snapshots records for consistency
UPDATE snapshots
SET
    tracker_group = 'IPTorrents',
    privacy = 'private'
WHERE
    tracker_group = 'Other Private'
    AND (
        primary_tracker_url LIKE 'http://async.empirehost.me/%'
        OR primary_tracker_url LIKE 'http://routing.bgp.technology/%'
    );


-- migrate:down
-- Reverse the reclassification back to "Other Private"
UPDATE torrents
SET
    tracker_group = 'Other Private',
    privacy = 'private',
    is_private = TRUE,
    updated_at = NOW()
WHERE
    tracker_group = 'IPTorrents'
    AND (
        primary_tracker_url LIKE 'http://async.empirehost.me/%'
        OR primary_tracker_url LIKE 'http://routing.bgp.technology/%'
    );

UPDATE upload_deltas
SET
    tracker_group = 'Other Private',
    privacy = 'private'
WHERE
    tracker_group = 'IPTorrents'
    AND (
        primary_tracker_url LIKE 'http://async.empirehost.me/%'
        OR primary_tracker_url LIKE 'http://routing.bgp.technology/%'
    );

UPDATE snapshots
SET
    tracker_group = 'Other Private',
    privacy = 'private'
WHERE
    tracker_group = 'IPTorrents'
    AND (
        primary_tracker_url LIKE 'http://async.empirehost.me/%'
        OR primary_tracker_url LIKE 'http://routing.bgp.technology/%'
    );
