"""Tests for collector/database.py."""

from unittest.mock import MagicMock

from collector.database import (
    get_existing_torrent,
    get_stored_trackers,
    mark_missing_torrents,
)


class TestGetExistingTorrent:
    def test_returns_torrent_when_exists(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = {
            "torrent_hash": "abc123",
            "name": "Test Torrent",
            "observed_seeding_seconds": 3600,
        }
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        result = get_existing_torrent(mock_conn, "abc123")

        assert result["torrent_hash"] == "abc123"
        mock_cur.execute.assert_called_once()
        assert mock_cur.execute.call_args[0][1] == ("abc123",)

    def test_returns_none_when_missing(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = None
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        result = get_existing_torrent(mock_conn, "missing")

        assert result is None


class TestGetStoredTrackers:
    def test_returns_active_trackers(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = [
            {"tracker_url": "http://tracker1.com/announce", "tracker_group": "BTArg"},
            {"tracker_url": "http://tracker2.com/announce", "tracker_group": "Other Private"},
        ]
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        result = get_stored_trackers(mock_conn, "abc123")

        assert len(result) == 2
        assert result[0]["tracker_group"] == "BTArg"

    def test_returns_empty_when_no_trackers(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = []
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        result = get_stored_trackers(mock_conn, "abc123")

        assert result == []


class TestMarkMissingTorrents:
    def test_marks_disappeared_torrents(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        current_hashes = ["hash1", "hash2"]
        mark_missing_torrents(mock_conn, current_hashes)

        mock_cur.execute.assert_called_once()
        # Verify the query uses the current hashes
        call_args = mock_cur.execute.call_args
        assert call_args[0][1] == (["hash1", "hash2"],)

    def test_skips_when_empty_list(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        mark_missing_torrents(mock_conn, [])

        mock_cur.execute.assert_not_called()

    def test_skips_when_none(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        mark_missing_torrents(mock_conn, None)

        mock_cur.execute.assert_not_called()


