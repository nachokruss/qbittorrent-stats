"""qBittorrent HTTP API client."""

import requests

from .config import QB_PASSWORD, QB_URL, QB_USERNAME


class QBittorrentClient:
    """Client for the qBittorrent Web API."""

    def __init__(self):
        self.session = requests.Session()

    def login(self):
        """Authenticate and store the session cookie."""
        response = self.session.post(
            f"{QB_URL}/api/v2/auth/login",
            data={"username": QB_USERNAME, "password": QB_PASSWORD},
            timeout=30,
        )
        response.raise_for_status()

    def get_torrents(self):
        """Fetch all torrents from qBittorrent."""
        response = self.session.get(
            f"{QB_URL}/api/v2/torrents/info", timeout=60
        )
        response.raise_for_status()
        return response.json()

    def get_trackers(self, torrent_hash):
        """Fetch trackers for a specific torrent."""
        response = self.session.get(
            f"{QB_URL}/api/v2/torrents/trackers",
            params={"hash": torrent_hash},
            timeout=60,
        )
        response.raise_for_status()
        return response.json()
