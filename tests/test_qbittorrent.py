"""Tests for collector/qbittorrent.py."""

from unittest.mock import MagicMock, patch

from collector.qbittorrent import QBittorrentClient


class TestQBittorrentClient:
    """Test the qBittorrent HTTP API client with mocked requests."""

    def _create_client(self):
        with patch("collector.qbittorrent.requests.Session") as mock_session_cls:
            client = QBittorrentClient()
            client.session = mock_session_cls.return_value
            return client, client.session

    def test_login_sends_post_request(self):
        client, session = self._create_client()
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        session.post.return_value = mock_response

        client.login()

        session.post.assert_called_once()
        call_kwargs = session.post.call_args
        assert "api/v2/auth/login" in call_kwargs[0][0]
        assert call_kwargs[1]["data"]["username"] == "admin"
        mock_response.raise_for_status.assert_called_once()

    def test_get_torrents_returns_json(self):
        client, session = self._create_client()
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = [
            {"hash": "abc123", "name": "Test Torrent"}
        ]
        session.get.return_value = mock_response

        result = client.get_torrents()

        assert len(result) == 1
        assert result[0]["hash"] == "abc123"
        mock_response.raise_for_status.assert_called_once()

    def test_get_torrents_empty_list(self):
        client, session = self._create_client()
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = []
        session.get.return_value = mock_response

        result = client.get_torrents()

        assert result == []

    def test_get_trackers_with_hash(self):
        client, session = self._create_client()
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = [
            {"url": "http://tracker.com/announce", "status": 1}
        ]
        session.get.return_value = mock_response

        result = client.get_trackers("abc123")

        assert len(result) == 1
        call_kwargs = session.get.call_args
        assert call_kwargs[1]["params"]["hash"] == "abc123"

    def test_get_trackers_empty(self):
        client, session = self._create_client()
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = []
        session.get.return_value = mock_response

        result = client.get_trackers("abc123")

        assert result == []

    def test_login_raises_on_failure(self):
        client, session = self._create_client()
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("403 Forbidden")
        session.post.return_value = mock_response

        try:
            client.login()
            assert False, "Expected exception"
        except Exception as e:
            assert "403" in str(e)
