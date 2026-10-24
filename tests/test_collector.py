"""Tests for collector/collector.py."""

from unittest.mock import MagicMock, patch

from collector.collector import collect_once


class TestCollectOnce:
    """Test the collection orchestration with mocked dependencies."""

    def test_collects_torrents_and_trackers(self):
        mock_conn = MagicMock()
        mock_qb = MagicMock()

        mock_qb.get_torrents.return_value = [
            {"hash": "abc123", "name": "Torrent 1"},
            {"hash": "def456", "name": "Torrent 2"},
        ]

        with patch("collector.collector.process_torrent", return_value=0):
            with patch("collector.collector.mark_missing_torrents"):
                processed, delta = collect_once(mock_conn, mock_qb)

        assert processed == 2
        assert delta == 0

    def test_handles_empty_torrent_list(self):
        mock_conn = MagicMock()
        mock_qb = MagicMock()
        mock_qb.get_torrents.return_value = []

        with patch("collector.collector.process_torrent", return_value=0):
            with patch("collector.collector.mark_missing_torrents"):
                processed, delta = collect_once(mock_conn, mock_qb)

        assert processed == 0
        assert delta == 0

    def test_handles_processing_error(self):
        mock_conn = MagicMock()
        mock_qb = MagicMock()

        mock_qb.get_torrents.return_value = [
            {"hash": "abc123", "name": "Good Torrent"},
            {"hash": "def456", "name": "Bad Torrent"},
        ]

        # First torrent succeeds, second fails
        def side_effect(conn, qb, torrent):
            if torrent["hash"] == "def456":
                raise Exception("Simulated error")
            return 0

        with patch("collector.collector.process_torrent", side_effect=side_effect):
            with patch("collector.collector.mark_missing_torrents"):
                processed, delta = collect_once(mock_conn, mock_qb)

        # Both torrents are seen (added to current_hashes), but only one succeeds
        assert processed == 2
        # conn.rollback() should have been called for the failed torrent
        mock_conn.rollback.assert_called_once()

    def test_marks_missing_torrents(self):
        mock_conn = MagicMock()
        mock_qb = MagicMock()

        mock_qb.get_torrents.return_value = [
            {"hash": "abc123", "name": "Torrent 1"},
        ]

        with patch("collector.collector.process_torrent", return_value=0):
            with patch("collector.collector.mark_missing_torrents") as mock_mark:
                collect_once(mock_conn, mock_qb)

        mock_mark.assert_called_once()
        call_args = mock_mark.call_args
        assert call_args[0][1] == ["abc123"]

    def test_accumulates_upload_delta(self):
        mock_conn = MagicMock()
        mock_qb = MagicMock()

        mock_qb.get_torrents.return_value = [
            {"hash": "abc123", "name": "Torrent 1"},
            {"hash": "def456", "name": "Torrent 2"},
        ]

        def side_effect(conn, qb, torrent):
            if torrent["hash"] == "abc123":
                return 1000
            return 2000

        with patch("collector.collector.process_torrent", side_effect=side_effect):
            with patch("collector.collector.mark_missing_torrents"):
                processed, delta = collect_once(mock_conn, mock_qb)

        assert processed == 2
        assert delta == 3000

    def test_handles_api_error(self):
        mock_conn = MagicMock()
        mock_qb = MagicMock()
        mock_qb.get_torrents.side_effect = Exception("API error")

        with patch("collector.collector.process_torrent", return_value=0):
            with patch("collector.collector.mark_missing_torrents"):
                try:
                    collect_once(mock_conn, mock_qb)
                    assert False, "Expected exception"
                except Exception as e:
                    assert "API error" in str(e)
