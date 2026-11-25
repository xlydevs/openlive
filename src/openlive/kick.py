"""Kick: who is live among the channels in the user's list.

Kick's official API has no "channels you follow" and needs a secret for app tokens, so openlive uses the
public JSON that kick.com itself serves (no keys). It is unofficial and may change.
"""
import re

from . import net

API = "https://kick.com/api/v2/channels/{slug}"
SLUG_RE = re.compile(r"^[A-Za-z0-9_\-]{2,40}$")


def parse(text):
    """'kick.com/xqc', 'https://kick.com/xqc/videos', 'xqc' → 'xqc' (None if it doesn't look like a channel)."""
    s = text.strip().rstrip("/")
    m = re.search(r"kick\.com/([^/?#]+)", s)
    if m: s = m.group(1)
    s = s.lstrip("@").lower()
    return s if SLUG_RE.match(s) else None


def _kick_time(s):
    """'2026-11-24 04:19:21' (UTC) → ISO with Z."""
    return s.replace(" ", "T") + "Z" if s and "T" not in s else (s or "")


def row(d):
    slug = d.get("slug", "")
    name = (d.get("user") or {}).get("username") or slug
    ls = d.get("livestream") or {}
    live = bool(ls.get("is_live"))
    cats = ls.get("categories") or []
    r = {"platform": "kick", "login": slug, "name": name, "live": live, "viewers": int(ls.get("viewer_count") or 0) if live else 0,
         "game": cats[0].get("name", "") if live and cats else "", "title": ls.get("session_title", "") if live else "",
         "started_at": _kick_time(ls.get("start_time") or ls.get("created_at")) if live else "",
         "language": ls.get("lang_iso", "") if live else "", "tags": ls.get("tags") or [] if live else []}
    if live and d.get("playback_url"):
        r["play_url"] = "hls://" + d["playback_url"]
    return r


def channel(slug):
    return row(net.fetch_json(API.format(slug=slug)))


def check(slugs):
    """Rows for every slug (offline ones too). Channels that failed are left out and reported."""
    rows, errors = [], []
    for slug, res in net.parallel(channel, list(slugs)):
        if isinstance(res, Exception):
            errors.append(f"kick/{slug}: {res}")
        else:
            rows.append(res)
    return rows, errors


def resolve(text):
    """Validate a channel the user typed. Returns {'id', 'name'} or raises net.NetError."""
    slug = parse(text)
    if not slug:
        raise net.NetError("not a Kick channel")
    try:
        r = channel(slug)
    except net.NetError as e:
        if e.status == 404:
            raise net.NetError("channel not found", 404) from None
        raise
    return {"id": r["login"], "name": r["name"]}
