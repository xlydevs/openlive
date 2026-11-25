"""Platforms and the user's own channel lists (Kick and YouTube have no 'channels you follow' openlive can read)."""
from . import config

# key, label, colour (soft version of the brand), toggle key
PLATFORMS = (
    ("twitch", "Twitch", "#b39ddb", "t"),
    ("kick", "Kick", "#7be36a", "k"),
    ("youtube", "YouTube", "#f47c7c", "y"),
)
ALL = tuple(p[0] for p in PLATFORMS)
LABEL = {p[0]: p[1] for p in PLATFORMS}
COLOR = {p[0]: p[2] for p in PLATFORMS}
KEY = {p[0]: p[3] for p in PLATFORMS}
LISTED = ("kick", "youtube")  # platforms whose channels live in channels.json
FILE = "channels.json"


def row_key(r):
    """Unique id of a row. Twitch keeps the bare login so favourites from 0.1 still match."""
    p = r.get("platform", "twitch")
    return r["login"] if p == "twitch" else f"{p}:{r['login']}"


def load():
    d = config.read_json(FILE, {}) or {}
    return {p: list(d.get(p) or []) for p in LISTED}


def save(d):
    config.write_json(FILE, {p: d.get(p, []) for p in LISTED})


def add(d, platform, rec):
    """Add {'id', 'name', ...} unless it is already there. Returns True when added."""
    lst = d.setdefault(platform, [])
    if any(c["id"].lower() == rec["id"].lower() or (rec.get("channel_id") and c.get("channel_id") == rec["channel_id"]) for c in lst):
        return False
    lst.append(rec)
    return True


def remove(d, platform, cid):
    before = len(d.get(platform, []))
    d[platform] = [c for c in d.get(platform, []) if c["id"].lower() != cid.lower()]
    return len(d[platform]) < before


def guess_platform(text):
    s = text.lower()
    for p, host in (("kick", "kick.com"), ("youtube", "youtube.com"), ("youtube", "youtu.be"), ("twitch", "twitch.tv")):
        if host in s:
            return p
    return None
