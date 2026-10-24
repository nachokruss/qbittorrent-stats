"""Tests for collector/torrent.py."""

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from collector.torrent import process_torrent


class TestProcessTorrent:
    """Test torrent processing with mocked dependencies."""

    def _create_mock_conn(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        return mock_conn, mock_cur

    def _create_mock_qb_client(self):
        mock_client = MagicMock()
        mock_client.get_trackers.return_value = [
            {"url": "http://tracker.com/announce", "status": 1, "tier": 0, "num_peers": 5, "num_seeds": 2, "num_leeches": 1, "num_downloads": 50, "msg": ""}
        ]
        return mock_client

    def test_new_torrent_inserts_record(self):
        mock_conn, mock_cur = self._create_mock_conn()
        mock_qb = self._create_mock_qb_client()

        # No existing torrent
        mock_cur.fetchone.return_value = None
        mock_cur.fetchall.return_value = []

        torrent = {
            "hash": "abc123",
            "name": "New Torrent",
            "size": 1073741824,
            "category": "movies",
            "tags": "",
            "savepath": "/downloads/",
            "add_date": 1609459200,
            "state": "uploading",
            "seeding_time": 3600,
            "uploaded": 536870912,
            "downloaded": 1073741824,
            "num_seeds": 5,
            "num_leechs": 1,
            "magnet_uri": None,
        }

        with patch("collector.torrent.get_existing_torrent", return_value=None):
            with patch("collector.torrent.get_stored_trackers", return_value=[]):
                with patch("collector.torrent.should_refresh_trackers", return_value=True):
                    delta = process_torrent(mock_conn, mock_qb, torrent)

        # Verify execute was called for upsert, trackers, snapshot, and delta
        assert mock_cur.execute.call_count >= 3

    def test_existing_torrent_updates_record(self):
        mock_conn, mock_cur = self._create_mock_conn()
        mock_qb = self._create_mock_qb_client()

        now = datetime.now(timezone.utc)
        last_seen = now - timedelta(seconds=900)

        existing = {
            "torrent_hash": "abc123",
            "name": "Existing Torrent",
            "first_seen_at": now - timedelta(days=1),
            "last_seen_at": last_seen,
            "removed_at": None,
            "observed_seeding_seconds": 3600,
            "last_state": "seeding",
            "uploaded_total_bytes": 1073741824,
            "downloaded_total_bytes": 2147483648,
            "trackers_refreshed_at": now - timedelta(seconds=3600),
        }

        torrent = {
            "hash": "abc123",
            "name": "Existing Torrent",
            "size": 1073741824,
            "category": "movies",
            "tags": "",
            "savepath": "/downloads/",
            "add_date": 1609459200,
            "state": "uploading",
            "seeding_time": 4500,
            "uploaded": 1610612736,  # Increased by 536870912
            "downloaded": 2147483648,
            "num_seeds": 5,
            "num_leechs": 1,
            "magnet_uri": None,
        }

        with patch("collector.torrent.get_existing_torrent", return_value=existing):
            with patch("collector.torrent.get_stored_trackers", return_value=[]):
                with patch("collector.torrent.should_refresh_trackers", return_value=True):
                    delta = process_torrent(mock_conn, mock_qb, torrent)

        # Should have upload delta
        assert delta == 536870912

    def test_no_upload_delta_when_same_value(self):
        mock_conn, mock_cur = self._create_mock_conn()
        mock_qb = self._create_mock_qb_client()

        now = datetime.now(timezone.utc)
        existing = {
            "torrent_hash": "abc123",
            "name": "Torrent",
            "first_seen_at": now,
            "last_seen_at": now - timedelta(seconds=900),
            "removed_at": None,
            "observed_seeding_seconds": 0,
            "last_state": "downloading",
            "uploaded_total_bytes": 1000,
            "downloaded_total_bytes": 2000,
            "trackers_refreshed_at": now,
        }

        torrent = {
            "hash": "abc123",
            "name": "Torrent",
            "size": 1073741824,
            "category": "",
            "tags": "",
            "savepath": "/downloads/",
            "add_date": 1609459200,
            "state": "downloading",
            "seeding_time": 0,
            "uploaded": 1000,  # Same as existing
            "downloaded": 2000,
            "num_seeds": 0,
            "num_leechs": 0,
            "magnet_uri": None,
        }

        with patch("collector.torrent.get_existing_torrent", return_value=existing):
            with patch("collector.torrent.get_stored_trackers", return_value=[]):
                with patch("collector.torrent.should_refresh_trackers", return_value=True):
                    delta = process_torrent(mock_conn, mock_qb, torrent)

        assert delta == 0

    def test_handles_missing_hash(self):
        mock_conn, mock_cur = self._create_mock_conn()
        mock_qb = self._create_mock_qb_client()

        torrent = {"name": "No Hash Torrent"}

        try:
            process_torrent(mock_conn, mock_qb, torrent)
            assert False, "Expected KeyError"
        except KeyError:
            pass  # Expected

    def test_handles_negative_seeding_time(self):
        mock_conn, mock_cur = self._create_mock_conn()
        mock_qb = self._create_mock_qb_client()

        now = datetime.now(timezone.utc)
        existing = {
            "torrent_hash": "abc123",
            "name": "Torrent",
            "first_seen_at": now,
            "last_seen_at": now - timedelta(seconds=900),
            "removed_at": None,
            "observed_seeding_seconds": 0,
            "last_state": None,
            "uploaded_total_bytes": 0,
            "downloaded_total_bytes": 0,
            "trackers_refreshed_at": now,
        }

        torrent = {
            "hash": "abc123",
            "name": "Torrent",
            "size": 1073741824,
            "category": "",
            "tags": "",
            "savepath": "/downloads/",
            "add_date": 1609459200,
            "state": "downloading",
            "seeding_time": -1,  # Invalid
            "uploaded": 0,
            "downloaded": 0,
            "num_seeds": 0,
            "num_leechs": 0,
            "magnet_uri": None,
        }

        with patch("collector.torrent.get_existing_torrent", return_value=existing):
            with patch("collector.torrent.get_stored_trackers", return_value=[]):
                with patch("collector.torrent.should_refresh_trackers", return_value=True):
                    delta = process_torrent(mock_conn, mock_qb, torrent)

        # Should not crash
        assert delta == 0
