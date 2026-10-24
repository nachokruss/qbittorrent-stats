"""Tests for collector/web.py — FastAPI web interface."""

from datetime import datetime
from unittest.mock import patch

from fastapi.testclient import TestClient

from collector.web import app


def _make_torrent_row(name, tracker_group="BTArg", privacy="private", last_state="seeding"):
    return {
        "torrent_hash": "abc123",
        "name": name,
        "size_bytes": 1073741824,
        "tracker_group": tracker_group,
        "privacy": privacy,
        "last_state": last_state,
        "last_seen_at": "2024-10-24T12:00:00",
        "removed_at": None,
        "uploaded_gb": 1.5,
        "seeding_days": 10.0,
    }


# ---------------------------------------------------------------------------
# Index page
# ---------------------------------------------------------------------------

class TestIndex:
    def test_returns_html_page(self):
        from fastapi.responses import HTMLResponse
        with patch("collector.web.templates.TemplateResponse") as mock_template:
            mock_template.return_value = HTMLResponse(content="<html><title>qBittorrent Stats</title></html>")
            response = TestClient(app).get("/")

        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class TestDashboard:
    def test_returns_stats_and_last_run(self):
        with patch("collector.web.query") as mock_query:
            mock_query.side_effect = [
                [
                    {
                        "total_torrents": 50,
                        "active_torrents": 45,
                        "total_uploaded_gb": 123.45,
                        "total_size_tb": 2.5,
                        "total_seeding_days": 300.0,
                    }
                ],
                [
                    {
                        "started_at": "2024-10-24T12:00:00",
                        "finished_at": "2024-10-24T12:05:00",
                        "torrents_seen": 50,
                        "torrents_processed": 50,
                        "errors": 0,
                        "status": "success",
                    }
                ],
            ]
            response = TestClient(app).get("/api/dashboard")

        assert response.status_code == 200
        data = response.json()
        assert data["stats"]["total_torrents"] == 50
        assert data["stats"]["active_torrents"] == 45
        assert data["last_run"]["torrents_seen"] == 50
        assert data["last_run"]["status"] == "success"

    def test_returns_empty_when_no_data(self):
        with patch("collector.web.query") as mock_query:
            mock_query.return_value = []
            response = TestClient(app).get("/api/dashboard")

        assert response.status_code == 200
        data = response.json()
        assert data["stats"] == {}
        assert data["last_run"] is None


# ---------------------------------------------------------------------------
# Upload Charts
# ---------------------------------------------------------------------------

class TestUploadCharts:
    def test_daily_uploads(self):
        with patch("collector.web.query") as mock_query:
            mock_query.return_value = [
                {"day": "2024-10-23", "uploaded_bytes": 1073741824, "uploaded_gb": 1.0},
                {"day": "2024-10-24", "uploaded_bytes": 536870912, "uploaded_gb": 0.5},
            ]
            response = TestClient(app).get("/api/uploads/daily")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["uploaded_gb"] == 1.0

    def test_weekly_uploads(self):
        with patch("collector.web.query") as mock_query:
            mock_query.return_value = [
                {"week": "2024-10-21", "uploaded_bytes": 5368709120, "uploaded_gb": 5.0},
            ]
            response = TestClient(app).get("/api/uploads/weekly")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["uploaded_gb"] == 5.0

    def test_monthly_uploads(self):
        with patch("collector.web.query") as mock_query:
            mock_query.return_value = [
                {"month": "2024-10-01", "uploaded_bytes": 10737418240, "uploaded_gb": 10.0},
            ]
            response = TestClient(app).get("/api/uploads/monthly")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["uploaded_gb"] == 10.0

    def test_daily_with_tracker_filter(self):
        with patch("collector.web.query") as mock_query:
            mock_query.return_value = [
                {"day": "2024-10-24", "uploaded_bytes": 536870912, "uploaded_gb": 0.5},
            ]
            response = TestClient(app).get("/api/uploads/daily?tracker=IPTorrents")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1

    def test_weekly_with_tracker_filter(self):
        with patch("collector.web.query") as mock_query:
            mock_query.return_value = []
            response = TestClient(app).get("/api/uploads/weekly?tracker=BTArg")

        assert response.status_code == 200
        data = response.json()
        assert data == []

    def test_monthly_with_tracker_filter(self):
        with patch("collector.web.query") as mock_query:
            mock_query.return_value = []
            response = TestClient(app).get("/api/uploads/monthly?tracker=Other")

        assert response.status_code == 200
        data = response.json()
        assert data == []


# ---------------------------------------------------------------------------
# Torrents
# ---------------------------------------------------------------------------

class TestTorrents:
    def test_returns_paginated_torrents(self):
        rows = [_make_torrent_row(f"Torrent {i}") for i in range(5)]
        with patch("collector.web.query") as mock_query:
            mock_query.side_effect = [
                rows,  # data query
                [{"total": 5}],  # count query
            ]
            response = TestClient(app).get("/api/torrents")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert data["page"] == 1
        assert data["page_size"] == 50
        assert len(data["torrents"]) == 5

    def test_search_filter(self):
        rows = [_make_torrent_row("My Special Torrent")]
        with patch("collector.web.query") as mock_query:
            mock_query.side_effect = [
                rows,
                [{"total": 1}],
            ]
            response = TestClient(app).get("/api/torrents?search=Special")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1

    def test_tracker_filter(self):
        rows = [_make_torrent_row("Torrent 1", tracker_group="IPTorrents")]
        with patch("collector.web.query") as mock_query:
            mock_query.side_effect = [
                rows,
                [{"total": 1}],
            ]
            response = TestClient(app).get("/api/torrents?tracker=IPTorrents")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1

    def test_privacy_filter(self):
        rows = [_make_torrent_row("Torrent 1", privacy="public")]
        with patch("collector.web.query") as mock_query:
            mock_query.side_effect = [
                rows,
                [{"total": 1}],
            ]
            response = TestClient(app).get("/api/torrents?privacy=public")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1

    def test_state_filter(self):
        rows = [_make_torrent_row("Torrent 1", last_state="downloading")]
        with patch("collector.web.query") as mock_query:
            mock_query.side_effect = [
                rows,
                [{"total": 1}],
            ]
            response = TestClient(app).get("/api/torrents?state=downloading")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1

    def test_sort_by_name_desc(self):
        rows = [
            _make_torrent_row("Zebra"),
            _make_torrent_row("Apple"),
        ]
        with patch("collector.web.query") as mock_query:
            mock_query.side_effect = [
                rows,
                [{"total": 2}],
            ]
            response = TestClient(app).get("/api/torrents?sort=name&order=desc")

        assert response.status_code == 200

    def test_sort_by_tracker_group(self):
        rows = [
            _make_torrent_row("T1", tracker_group="BTArg"),
            _make_torrent_row("T2", tracker_group="IPTorrents"),
        ]
        with patch("collector.web.query") as mock_query:
            mock_query.side_effect = [
                rows,
                [{"total": 2}],
            ]
            response = TestClient(app).get("/api/torrents?sort=tracker_group&order=asc")

        assert response.status_code == 200

    def test_sort_by_privacy(self):
        with patch("collector.web.query") as mock_query:
            mock_query.side_effect = [
                [],
                [{"total": 0}],
            ]
            response = TestClient(app).get("/api/torrents?sort=privacy")

        assert response.status_code == 200

    def test_sort_by_last_state(self):
        with patch("collector.web.query") as mock_query:
            mock_query.side_effect = [
                [],
                [{"total": 0}],
            ]
            response = TestClient(app).get("/api/torrents?sort=last_state")

        assert response.status_code == 200

    def test_invalid_sort_falls_back_to_name(self):
        with patch("collector.web.query") as mock_query:
            mock_query.side_effect = [
                [],
                [{"total": 0}],
            ]
            response = TestClient(app).get("/api/torrents?sort=invalid_field")

        assert response.status_code == 200

    def test_pagination(self):
        rows = [_make_torrent_row(f"Torrent {i}") for i in range(10)]
        with patch("collector.web.query") as mock_query:
            mock_query.side_effect = [
                rows,
                [{"total": 100}],
            ]
            response = TestClient(app).get("/api/torrents?page=2&page_size=10")

        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 2
        assert data["page_size"] == 10
        assert data["total_pages"] == 10

    def test_combined_filters(self):
        with patch("collector.web.query") as mock_query:
            mock_query.side_effect = [
                [],
                [{"total": 0}],
            ]
            response = TestClient(app).get(
                "/api/torrents?search=test&tracker=IPTorrents&privacy=private&state=seeding"
            )

        assert response.status_code == 200

    def test_last_seen_filter_15d(self):
        with patch("collector.web.query") as mock_query:
            mock_query.side_effect = [
                [],
                [{"total": 0}],
            ]
            response = TestClient(app).get("/api/torrents?last_seen=15d")

        assert response.status_code == 200

    def test_last_seen_filter_1m(self):
        with patch("collector.web.query") as mock_query:
            mock_query.side_effect = [
                [],
                [{"total": 0}],
            ]
            response = TestClient(app).get("/api/torrents?last_seen=1m")

        assert response.status_code == 200

    def test_last_seen_filter_3m(self):
        with patch("collector.web.query") as mock_query:
            mock_query.side_effect = [
                [],
                [{"total": 0}],
            ]
            response = TestClient(app).get("/api/torrents?last_seen=3m")

        assert response.status_code == 200

    def test_last_seen_filter_1y(self):
        with patch("collector.web.query") as mock_query:
            mock_query.side_effect = [
                [],
                [{"total": 0}],
            ]
            response = TestClient(app).get("/api/torrents?last_seen=1y")

        assert response.status_code == 200

    def test_last_seen_filter_all(self):
        with patch("collector.web.query") as mock_query:
            mock_query.side_effect = [
                [],
                [{"total": 0}],
            ]
            response = TestClient(app).get("/api/torrents?last_seen=all")

        assert response.status_code == 200

    def test_last_seen_default_is_15d(self):
        with patch("collector.web.query") as mock_query:
            mock_query.side_effect = [
                [],
                [{"total": 0}],
            ]
            response = TestClient(app).get("/api/torrents")

        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Trackers
# ---------------------------------------------------------------------------

class TestTrackers:
    def test_returns_tracker_totals(self):
        with patch("collector.web.query") as mock_query:
            mock_query.return_value = [
                {"tracker_group": "IPTorrents", "torrent_count": 30, "uploaded_gb": 50.0},
                {"tracker_group": "BTArg", "torrent_count": 15, "uploaded_gb": 25.5},
            ]
            response = TestClient(app).get("/api/trackers")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["tracker_group"] == "IPTorrents"
        assert data[0]["uploaded_gb"] == 50.0

    def test_returns_empty_when_no_data(self):
        with patch("collector.web.query") as mock_query:
            mock_query.return_value = []
            response = TestClient(app).get("/api/trackers")

        assert response.status_code == 200
        data = response.json()
        assert data == []


# ---------------------------------------------------------------------------
# Trackers Daily
# ---------------------------------------------------------------------------

class TestTrackersDaily:
    def test_returns_daily_by_tracker(self):
        with patch("collector.web.query") as mock_query:
            mock_query.return_value = [
                {"day": "2024-10-24", "tracker_group": "IPTorrents", "uploaded_gb": 1.0},
                {"day": "2024-10-24", "tracker_group": "BTArg", "uploaded_gb": 0.5},
            ]
            response = TestClient(app).get("/api/trackers/daily")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2


# ---------------------------------------------------------------------------
# Tracker Groups
# ---------------------------------------------------------------------------

class TestTrackerGroups:
    def test_returns_distinct_groups(self):
        with patch("collector.web.query") as mock_query:
            mock_query.return_value = [
                {"tracker_group": "BTArg"},
                {"tracker_group": "IPTorrents"},
                {"tracker_group": "Other Private"},
            ]
            response = TestClient(app).get("/api/tracker-groups")

        assert response.status_code == 200
        data = response.json()
        assert data == ["BTArg", "IPTorrents", "Other Private"]

    def test_returns_empty_list_when_no_data(self):
        with patch("collector.web.query") as mock_query:
            mock_query.return_value = []
            response = TestClient(app).get("/api/tracker-groups")

        assert response.status_code == 200
        data = response.json()
        assert data == []


# ---------------------------------------------------------------------------
# Torrent Details
# ---------------------------------------------------------------------------

class TestTorrentDetails:
    def test_returns_torrent_details(self):
        with patch("collector.web.query") as mock_query:
            mock_query.side_effect = [
                # Torrent info
                [{
                    "torrent_hash": "abc123",
                    "name": "Test Torrent",
                    "size_bytes": 1073741824,
                    "tracker_group": "IPTorrents",
                    "privacy": "private",
                    "last_state": "seeding",
                    "last_seen_at": "2024-10-24T12:00:00",
                    "removed_at": None,
                    "added_at": "2024-01-01T00:00:00",
                    "first_seen_at": "2024-01-01T00:00:00",
                    "magnet_uri": "magnet:?xt=urn:...",
                    "save_path": "/data",
                    "category": "movies",
                    "tags": "hd",
                    "uploaded_total_bytes": 2147483648,
                    "downloaded_total_bytes": 1073741824,
                    "observed_seeding_seconds": 864000,
                    "num_seeds": 10,
                    "num_leechs": 2,
                }],
                # History (snapshots)
                [{
                    "day": datetime(2024, 10, 23),
                    "uploaded_bytes": 1073741824,
                    "downloaded_bytes": 536870912,
                    "seeding_seconds": 86400,
                }],
                # Deltas
                [{
                    "day": datetime(2024, 10, 23),
                    "upload_delta_bytes": 107374182,
                }],
                # Trackers
                [{
                    "tracker_url": "https://tracker.example.com/announce",
                    "tracker_host": "tracker.example.com",
                    "tracker_group": "IPTorrents",
                    "tier": 0,
                    "status": 0,
                    "num_peers": 15,
                    "num_seeds": 10,
                    "num_leeches": 5,
                    "message": None,
                }],
                # Events
                [{
                    "event_at": datetime(2024, 10, 24, 12, 0, 0),
                    "event_type": "state_change",
                    "details": {"from": "downloading", "to": "seeding"},
                }],
                # Totals
                [{"total_upload_delta_bytes": 2147483648}],
            ]
            response = TestClient(app).get("/api/torrents/abc123")

        assert response.status_code == 200
        data = response.json()
        assert data["torrent"]["name"] == "Test Torrent"
        assert data["torrent"]["size_gb"] == 1.0
        assert data["torrent"]["uploaded_total_gb"] == 2.0
        assert data["torrent"]["downloaded_total_gb"] == 1.0
        assert data["torrent"]["seeding_days"] == 10.0
        assert len(data["history"]) == 1
        assert len(data["deltas"]) == 1
        assert len(data["trackers"]) == 1
        assert len(data["events"]) == 1
        assert data["totals"]["total_uploaded_gb"] == 2.0

    def test_returns_404_for_missing_torrent(self):
        with patch("collector.web.query") as mock_query:
            mock_query.return_value = []
            response = TestClient(app).get("/api/torrents/nonexistent")

        assert response.status_code == 404

    def test_returns_empty_details_when_no_history(self):
        with patch("collector.web.query") as mock_query:
            mock_query.side_effect = [
                # Torrent info
                [{
                    "torrent_hash": "abc123",
                    "name": "Empty Torrent",
                    "size_bytes": 500000000,
                    "tracker_group": "Other",
                    "privacy": "public",
                    "last_state": "downloading",
                    "last_seen_at": "2024-10-24T12:00:00",
                    "removed_at": None,
                    "added_at": None,
                    "first_seen_at": "2024-10-24T12:00:00",
                    "magnet_uri": None,
                    "save_path": None,
                    "category": None,
                    "tags": None,
                    "uploaded_total_bytes": 0,
                    "downloaded_total_bytes": 0,
                    "observed_seeding_seconds": 0,
                    "num_seeds": None,
                    "num_leechs": None,
                }],
                # Empty history
                [],
                # Empty deltas
                [],
                # Empty trackers
                [],
                # Empty events
                [],
                # Totals
                [{"total_upload_delta_bytes": 0}],
            ]
            response = TestClient(app).get("/api/torrents/abc123")

        assert response.status_code == 200
        data = response.json()
        assert data["torrent"]["name"] == "Empty Torrent"
        assert data["history"] == []
        assert data["deltas"] == []
        assert data["trackers"] == []
        assert data["events"] == []
        assert data["totals"]["total_uploaded_gb"] == 0
