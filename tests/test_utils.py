"""Tests for collector/utils.py."""

from datetime import datetime, timezone

from collector.utils import (
    build_magnet,
    classify_torrent,
    extract_tracker_urls,
    get_tracker_host,
    is_real_tracker,
    normalize_state,
    parse_timestamp,
    tracker_group_for_url,
    utcnow,
)


class TestUtcNow:
    def test_returns_aware_datetime(self):
        now = utcnow()
        assert now.tzinfo == timezone.utc

    def test_returns_recent_time(self):
        now = utcnow()
        diff = (now - datetime.now(timezone.utc)).total_seconds()
        assert abs(diff) < 5


class TestNormalizeState:
    def test_uploading_becomes_seeding(self):
        assert normalize_state("uploading") == "seeding"

    def test_stalledUP_becomes_seeding(self):
        assert normalize_state("stalledUP") == "seeding"

    def test_forcedUP_becomes_seeding(self):
        assert normalize_state("forcedUP") == "seeding"

    def test_queuedUP_becomes_seeding(self):
        assert normalize_state("queuedUP") == "seeding"

    def test_checkingUP_becomes_seeding(self):
        assert normalize_state("checkingUP") == "seeding"

    def test_downloading_unchanged(self):
        assert normalize_state("downloading") == "downloading"

    def test_paused_unchanged(self):
        assert normalize_state("pausedUP") == "pausedUP"


class TestGetTrackerHost:
    def test_http_url(self):
        assert get_tracker_host("http://example.com/announce") == "example.com"

    def test_https_url(self):
        assert get_tracker_host("https://tracker.example.org/announce.php") == "tracker.example.org"

    def test_invalid_url(self):
        assert get_tracker_host("not-a-url") is None

    def test_empty_string(self):
        assert get_tracker_host("") is None


class TestTrackerGroupForUrl:
    def test_btarg_url(self):
        url = "https://announce.btarg.org/announce.php/pass123"
        assert tracker_group_for_url(url) == "BTArg"

    def test_iptorrents_url_variant_1(self):
        url = "http://127.0.0.1.stackoverflow.tech/announce.php"
        assert tracker_group_for_url(url) == "IPTorrents"

    def test_iptorrents_url_variant_2(self):
        url = "http://async.empirehost.me/announce.php"
        assert tracker_group_for_url(url) == "IPTorrents"

    def test_iptorrents_url_variant_3(self):
        url = "http://routing.bgp.technology/announce.php"
        assert tracker_group_for_url(url) == "IPTorrents"

    def test_other_private_url(self):
        url = "https://private-tracker.example.com/announce"
        assert tracker_group_for_url(url) == "Other Private"

    def test_none_url(self):
        assert tracker_group_for_url(None) == "Public"

    def test_empty_url(self):
        assert tracker_group_for_url("") == "Public"


class TestIsRealTracker:
    def test_real_tracker(self):
        assert is_real_tracker("http://tracker.example.com/announce") is True

    def test_dht_pseudo_tracker(self):
        assert is_real_tracker("[DHT]") is False

    def test_pex_pseudo_tracker(self):
        assert is_real_tracker("[PeX]") is False

    def test_lsd_pseudo_tracker(self):
        assert is_real_tracker("[LSD]") is False

    def test_starred_dht(self):
        assert is_real_tracker("** [DHT]") is False

    def test_starred_pex(self):
        assert is_real_tracker("** [PeX]") is False

    def test_none_url(self):
        assert is_real_tracker(None) is False

    def test_empty_string(self):
        assert is_real_tracker("") is False


class TestExtractTrackerUrls:
    def test_empty_data(self):
        assert extract_tracker_urls([]) == []

    def test_none_data(self):
        assert extract_tracker_urls(None) == []

    def test_filters_pseudo_trackers(self):
        data = [
            {"url": "http://real-tracker.com/announce"},
            {"url": "[DHT]"},
            {"url": "[PeX]"},
        ]
        urls = extract_tracker_urls(data)
        assert urls == ["http://real-tracker.com/announce"]

    def test_deduplicates_urls(self):
        data = [
            {"url": "http://tracker.com/announce"},
            {"url": "http://tracker.com/announce"},
        ]
        urls = extract_tracker_urls(data)
        assert len(urls) == 1

    def test_strips_whitespace(self):
        data = [{"url": "  http://tracker.com/announce  "}]
        urls = extract_tracker_urls(data)
        assert urls == ["http://tracker.com/announce"]


class TestClassifyTorrent:
    def test_no_trackers_is_public(self):
        is_priv, privacy, group = classify_torrent([])
        assert is_priv is False
        assert privacy == "public"
        assert group == "Public"

    def test_none_trackers_is_public(self):
        is_priv, privacy, group = classify_torrent(None)
        assert is_priv is False
        assert privacy == "public"
        assert group == "Public"

    def test_btarg_has_priority(self):
        urls = [
            "https://announce.btarg.org/announce.php/pass",
            "http://127.0.0.1.stackoverflow.tech/announce",
        ]
        is_priv, privacy, group = classify_torrent(urls)
        assert is_priv is True
        assert privacy == "private"
        assert group == "BTArg"

    def test_iptorrents_without_btarg(self):
        urls = ["http://async.empirehost.me/announce.php"]
        is_priv, privacy, group = classify_torrent(urls)
        assert is_priv is True
        assert privacy == "private"
        assert group == "IPTorrents"

    def test_other_private(self):
        urls = ["https://private.example.com/announce"]
        is_priv, privacy, group = classify_torrent(urls)
        assert is_priv is True
        assert privacy == "private"
        assert group == "Other Private"


class TestBuildMagnet:
    def test_uses_existing_magnet(self):
        torrent = {
            "hash": "abc123",
            "name": "Test Torrent",
            "magnet_uri": "magnet:?xt=urn:btih:existing",
        }
        assert build_magnet(torrent) == "magnet:?xt=urn:btih:existing"

    def test_builds_from_hash_and_name(self):
        torrent = {"hash": "abc123", "name": "Test Torrent"}
        magnet = build_magnet(torrent)
        assert magnet.startswith("magnet:?xt=urn:btih:abc123")
        # quote() encodes spaces as %20, not +
        assert "Test%20Torrent" in magnet

    def test_none_when_no_hash(self):
        torrent = {"name": "No Hash"}
        assert build_magnet(torrent) is None

    def test_uses_hash_as_name_when_missing(self):
        torrent = {"hash": "abc123"}
        magnet = build_magnet(torrent)
        assert "abc123" in magnet


class TestParseTimestamp:
    def test_valid_timestamp(self):
        result = parse_timestamp(1609459200)
        assert result == datetime(2021, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    def test_none_value(self):
        assert parse_timestamp(None) is None

    def test_invalid_value(self):
        assert parse_timestamp("not-a-number") is None

    def test_zero_timestamp(self):
        result = parse_timestamp(0)
        assert result == datetime(1970, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
