"""Tests for collector/trackers.py."""

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

from collector.trackers import should_refresh_trackers, upsert_trackers


class TestShouldRefreshTrackers:
    def test_refreshes_when_no_existing(self):
        now = datetime.now(timezone.utc)
        assert should_refresh_trackers(None, now) is True

    def test_refreshes_when_no_refreshed_at(self):
        existing = {"trackers_refreshed_at": None}
        now = datetime.now(timezone.utc)
        assert should_refresh_trackers(existing, now) is True

    def test_refreshes_when_interval_passed(self):
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(seconds=90000)  # More than 86400
        existing = {"trackers_refreshed_at": old_time}
        assert should_refresh_trackers(existing, now) is True

    def test_skips_when_recently_refreshed(self):
        now = datetime.now(timezone.utc)
        recent_time = now - timedelta(seconds=3600)  # 1 hour ago
        existing = {"trackers_refreshed_at": recent_time}
        assert should_refresh_trackers(existing, now) is False


class TestUpsertTrackers:
    def test_upserts_real_trackers(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        now = datetime.now(timezone.utc)
        tracker_data = [
            {
                "url": "http://tracker1.com/announce",
                "status": 1,
                "tier": 0,
                "num_peers": 10,
                "num_seeds": 5,
                "num_leeches": 3,
                "num_downloads": 100,
                "msg": "OK",
            },
            {
                "url": "http://tracker2.com/announce",
                "status": 2,
                "tier": 1,
                "num_peers": 0,
                "num_seeds": 0,
                "num_leeches": 0,
                "num_downloads": 0,
                "msg": "Error",
            },
        ]

        upsert_trackers(mock_conn, "abc123", tracker_data, now)

        # Should deactivate old trackers first
        assert mock_cur.execute.call_count >= 1
        # Then insert/update each tracker
        assert mock_cur.execute.call_count == 3  # 1 deactivate + 2 upserts

    def test_skips_pseudo_trackers(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        now = datetime.now(timezone.utc)
        tracker_data = [
            {"url": "[DHT]", "status": 0},
            {"url": "[PeX]", "status": 0},
            {"url": "http://real-tracker.com/announce", "status": 1, "tier": 0, "num_peers": 5, "num_seeds": 2, "num_leeches": 1, "num_downloads": 50, "msg": ""},
        ]

        upsert_trackers(mock_conn, "abc123", tracker_data, now)

        # Only 2 calls: 1 deactivate + 1 real tracker upsert
        assert mock_cur.execute.call_count == 2

    def test_handles_empty_tracker_data(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        now = datetime.now(timezone.utc)
        upsert_trackers(mock_conn, "abc123", [], now)

        # Only deactivates existing trackers
        assert mock_cur.execute.call_count == 1

    def test_handles_none_tracker_data(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        now = datetime.now(timezone.utc)
        upsert_trackers(mock_conn, "abc123", None, now)

        # Only deactivates existing trackers
        assert mock_cur.execute.call_count == 1
