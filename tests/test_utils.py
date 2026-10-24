"""Tests for collector/utils.py — Tracker classification and utilities."""

from collector.utils import (
    classify_torrent,
    extract_tracker_urls,
    get_tracker_host,
    is_real_tracker,
    normalize_state,
    tracker_group_for_url,
)


# ---------------------------------------------------------------------------
# tracker_group_for_url
# ---------------------------------------------------------------------------

class TestTrackerGroupForUrl:
    def test_none_url(self):
        assert tracker_group_for_url(None) == "Public"

    def test_empty_url(self):
        assert tracker_group_for_url("") == "Public"

    def test_btarg_tracker(self):
        assert (
            tracker_group_for_url("https://announce.btarg.org/announce.php/abc")
            == "BTArg"
        )

    def test_iptorrents_tracker_1(self):
        assert (
            tracker_group_for_url("http://127.0.0.1.stackoverflow.tech/announce.php")
            == "IPTorrents"
        )

    def test_iptorrents_tracker_2(self):
        assert (
            tracker_group_for_url("http://async.empirehost.me/announce.php")
            == "IPTorrents"
        )

    def test_iptorrents_tracker_3(self):
        assert (
            tracker_group_for_url("http://routing.bgp.technology/announce.php")
            == "IPTorrents"
        )

    def test_unknown_tracker_is_public(self):
        assert (
            tracker_group_for_url("https://tracker.openbittorrent.com/announce")
            == "Public"
        )

    def test_public_tracker_site(self):
        assert (
            tracker_group_for_url("https://public.popcorn-tracker.org/announce")
            == "Public"
        )


# ---------------------------------------------------------------------------
# classify_torrent
# ---------------------------------------------------------------------------

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

    def test_btarg_only(self):
        urls = ["https://announce.btarg.org/announce.php/abc"]
        is_priv, privacy, group = classify_torrent(urls)
        assert is_priv is True
        assert privacy == "private"
        assert group == "BTArg"

    def test_iptorrents_only(self):
        urls = ["http://127.0.0.1.stackoverflow.tech/announce.php"]
        is_priv, privacy, group = classify_torrent(urls)
        assert is_priv is True
        assert privacy == "private"
        assert group == "IPTorrents"

    def test_public_tracker_only(self):
        urls = ["https://tracker.openbittorrent.com/announce"]
        is_priv, privacy, group = classify_torrent(urls)
        assert is_priv is False
        assert privacy == "public"
        assert group == "Public"

    def test_btarg_priority_over_public(self):
        urls = [
            "https://announce.btarg.org/announce.php/abc",
            "https://tracker.openbittorrent.com/announce",
        ]
        is_priv, privacy, group = classify_torrent(urls)
        assert is_priv is True
        assert privacy == "private"
        assert group == "BTArg"

    def test_iptorrents_priority_over_public(self):
        urls = [
            "http://127.0.0.1.stackoverflow.tech/announce.php",
            "https://tracker.openbittorrent.com/announce",
        ]
        is_priv, privacy, group = classify_torrent(urls)
        assert is_priv is True
        assert privacy == "private"
        assert group == "IPTorrents"

    def test_btarg_priority_over_iptorrents(self):
        urls = [
            "https://announce.btarg.org/announce.php/abc",
            "http://127.0.0.1.stackoverflow.tech/announce.php",
        ]
        is_priv, privacy, group = classify_torrent(urls)
        assert is_priv is True
        assert privacy == "private"
        assert group == "BTArg"

    def test_multiple_public_trackers(self):
        urls = [
            "https://tracker.openbittorrent.com/announce",
            "https://public.popcorn-tracker.org/announce",
        ]
        is_priv, privacy, group = classify_torrent(urls)
        assert is_priv is False
        assert privacy == "public"
        assert group == "Public"

    def test_unknown_tracker_marked_private(self):
        urls = ["https://private-tracker.example.com/announce"]
        is_priv, privacy, group = classify_torrent(urls, qb_private=True)
        assert is_priv is True
        assert privacy == "private"
        assert group == "Other Private"

    def test_unknown_tracker_marked_public(self):
        urls = ["https://private-tracker.example.com/announce"]
        is_priv, privacy, group = classify_torrent(urls, qb_private=False)
        assert is_priv is False
        assert privacy == "public"
        assert group == "Public"

    def test_no_trackers_marked_private(self):
        is_priv, privacy, group = classify_torrent([], qb_private=True)
        assert is_priv is True
        assert privacy == "private"
        assert group == "Other Private"

    def test_btarg_ignores_qb_private_false(self):
        urls = ["https://announce.btarg.org/announce.php/abc"]
        is_priv, privacy, group = classify_torrent(urls, qb_private=False)
        assert is_priv is True
        assert privacy == "private"
        assert group == "BTArg"

    def test_iptorrents_ignores_qb_private_false(self):
        urls = ["http://127.0.0.1.stackoverflow.tech/announce.php"]
        is_priv, privacy, group = classify_torrent(urls, qb_private=False)
        assert is_priv is True
        assert privacy == "private"
        assert group == "IPTorrents"

    def test_btarg_priority_over_other_private(self):
        urls = [
            "https://announce.btarg.org/announce.php/abc",
            "https://private-tracker.example.com/announce",
        ]
        is_priv, privacy, group = classify_torrent(urls, qb_private=True)
        assert is_priv is True
        assert privacy == "private"
        assert group == "BTArg"

    def test_iptorrents_priority_over_other_private(self):
        urls = [
            "http://127.0.0.1.stackoverflow.tech/announce.php",
            "https://private-tracker.example.com/announce",
        ]
        is_priv, privacy, group = classify_torrent(urls, qb_private=True)
        assert is_priv is True
        assert privacy == "private"
        assert group == "IPTorrents"


# ---------------------------------------------------------------------------
# is_real_tracker
# ---------------------------------------------------------------------------

class TestIsRealTracker:
    def test_real_tracker(self):
        assert is_real_tracker("https://tracker.example.com/announce") is True

    def test_dht_pseudo_tracker(self):
        assert is_real_tracker("[DHT]") is False

    def test_pex_pseudo_tracker(self):
        assert is_real_tracker("[PeX]") is False

    def test_lsd_pseudo_tracker(self):
        assert is_real_tracker("[LSD]") is False

    def test_none_url(self):
        assert is_real_tracker(None) is False

    def test_empty_url(self):
        assert is_real_tracker("") is False


# ---------------------------------------------------------------------------
# extract_tracker_urls
# ---------------------------------------------------------------------------

class TestExtractTrackerUrls:
    def test_empty_data(self):
        assert extract_tracker_urls([]) == []

    def test_none_data(self):
        assert extract_tracker_urls(None) == []

    def test_filters_pseudo_trackers(self):
        data = [
            {"url": "[DHT]"},
            {"url": "https://tracker.example.com/announce"},
        ]
        assert extract_tracker_urls(data) == ["https://tracker.example.com/announce"]

    def test_deduplicates(self):
        data = [
            {"url": "https://tracker.example.com/announce"},
            {"url": "https://tracker.example.com/announce"},
        ]
        assert extract_tracker_urls(data) == ["https://tracker.example.com/announce"]


# ---------------------------------------------------------------------------
# normalize_state
# ---------------------------------------------------------------------------

class TestNormalizeState:
    def test_seeding_states(self):
        for state in ["uploading", "stalledUP", "forcedUP", "queuedUP", "checkingUP"]:
            assert normalize_state(state) == "seeding"

    def test_non_seeding_state(self):
        assert normalize_state("downloading") == "downloading"

    def test_metaDL_state(self):
        assert normalize_state("metaDL") == "metaDL"


# ---------------------------------------------------------------------------
# get_tracker_host
# ---------------------------------------------------------------------------

class TestGetTrackerHost:
    def test_https_url(self):
        assert (
            get_tracker_host("https://tracker.example.com/announce")
            == "tracker.example.com"
        )

    def test_http_url(self):
        assert get_tracker_host("http://127.0.0.1.stackoverflow.tech/") == "127.0.0.1.stackoverflow.tech"

    def test_empty_url(self):
        assert get_tracker_host("") is None
