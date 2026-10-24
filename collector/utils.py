"""Utility functions for tracker classification and data processing."""

from datetime import datetime, timezone
from urllib.parse import quote, urlparse


SEEDING_STATES = {"uploading", "stalledUP", "forcedUP", "queuedUP", "checkingUP"}


def utcnow():
    """Return the current UTC datetime."""
    return datetime.now(timezone.utc)


def normalize_state(state):
    """Normalize qBittorrent states so all uploading/seeding states count as 'seeding'."""
    if state in SEEDING_STATES:
        return "seeding"
    return state


def get_tracker_host(url):
    """Extract the hostname from a tracker URL."""
    try:
        return urlparse(url).hostname
    except Exception:
        return None


def tracker_group_for_url(url):
    """Classify a tracker based on its announce URL prefix."""
    if not url:
        return "Public"

    if url.startswith("https://announce.btarg.org/announce.php/"):
        return "BTArg"

    if (
        url.startswith("http://127.0.0.1.stackoverflow.tech/")
        or url.startswith("http://async.empirehost.me/")
        or url.startswith("http://routing.bgp.technology/")
    ):
        return "IPTorrents"

    return "Public"


def is_real_tracker(url):
    """Return False for qBittorrent's pseudo-trackers (DHT, PeX, LSD)."""
    if not url:
        return False

    value = url.strip()
    pseudo_prefixes = ("[DHT]", "[PeX]", "[LSD]", "** [DHT]", "** [PeX]", "** [LSD]")

    return not value.startswith(pseudo_prefixes)


def extract_tracker_urls(tracker_data):
    """Return a deduplicated list of real tracker URLs from tracker data."""
    result = []
    seen = set()

    for tracker in tracker_data or []:
        url = (tracker.get("url") or "").strip()

        if not is_real_tracker(url) or url in seen:
            continue

        seen.add(url)
        result.append(url)

    return result


def classify_torrent(tracker_urls, qb_private=False):
    """
    Determine privacy and tracker group for a torrent.

    Args:
        tracker_urls: List of tracker announce URLs.
        qb_private: The `private` flag from the qBittorrent API (True for private torrents).

    Returns:
        Tuple of (is_private, privacy, tracker_group).

    Priority: BTArg > IPTorrents > Other Private > Public
    - Known private tracker (BTArg/IPTorrents) → that group, private.
    - Unknown tracker but qBittorrent marks it private → "Other Private".
    - Everything else → "Public".
    """
    if not tracker_urls:
        if qb_private:
            return True, "private", "Other Private"
        return False, "public", "Public"

    groups = {tracker_group_for_url(url) for url in tracker_urls}

    if "BTArg" in groups:
        return True, "private", "BTArg"

    if "IPTorrents" in groups:
        return True, "private", "IPTorrents"

    if qb_private:
        return True, "private", "Other Private"

    return False, "public", "Public"


def build_magnet(torrent):
    """
    Build a magnet URI from qBittorrent torrent info.

    Uses the provided magnet_uri if available, otherwise constructs one
    from hash and name.
    """
    magnet = torrent.get("magnet_uri")
    if magnet:
        return magnet

    torrent_hash = torrent.get("hash")
    if not torrent_hash:
        return None

    name = torrent.get("name") or torrent_hash
    return f"magnet:?xt=urn:btih:{torrent_hash}&dn={quote(name)}"


def parse_timestamp(value):
    """Safely parse a Unix timestamp integer into a UTC datetime."""
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None
