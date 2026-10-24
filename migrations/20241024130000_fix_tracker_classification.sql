-- migrate:up
-- Fix tracker classification for existing records.
-- Logic matches `classify_torrent()` in collector/utils.py:
-- known trackers (BTArg/IPTorrents) take priority,
-- private torrents with unknown trackers become "Other Private",
-- public torrents become "Public".

UPDATE torrents
SET
    privacy = CASE
        WHEN is_private THEN 'private'
        ELSE 'public'
    END,
    tracker_group = CASE
        -- Known trackers take priority regardless of is_private flag
        WHEN primary_tracker_url LIKE 'https://announce.btarg.org/%' THEN 'BTArg'
        WHEN primary_tracker_url LIKE 'http://127.0.0.1.stackoverflow.tech/%' THEN 'IPTorrents'
        -- Private but unknown tracker
        WHEN is_private THEN 'Other Private'
        -- Public
        ELSE 'Public'
    END,
    updated_at = NOW()
WHERE
    -- Only update rows whose classification would actually change
    NOT (
        privacy = CASE WHEN is_private THEN 'private' ELSE 'public' END
        AND tracker_group = CASE
            WHEN primary_tracker_url LIKE 'https://announce.btarg.org/%' THEN 'BTArg'
            WHEN primary_tracker_url LIKE 'http://127.0.0.1.stackoverflow.tech/%' THEN 'IPTorrents'
            WHEN is_private THEN 'Other Private'
            ELSE 'Public'
        END
    );


-- migrate:down
-- Cannot perfectly reverse without knowing the original values,
-- but we can at least note the rollback is a no-op.
