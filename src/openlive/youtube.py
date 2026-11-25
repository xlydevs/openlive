"""YouTube: live streams (only live, never videos) of the channels in the user's list.

Channels come from your Google sign-in (subscriptions, see google.py) and/or your own list (typed in, or imported
from Google Takeout). Signed in, or with an optional API key, openlive reads the channels' RSS feeds plus one cheap
videos.list call. Otherwise it reads each channel's public /live page (unofficial).
"""
import csv
import html
import json
import re
from pathlib import Path

from . import config, net

WEB = "https://www.youtube.com"
API = "https://www.googleapis.com/youtube/v3/videos"
TAKEOUT_URL = "https://takeout.google.com/takeout/custom/youtube"
KEY_URL = "https://console.cloud.google.com/apis/library/youtube.googleapis.com"
UC_RE = re.compile(r"^UC[A-Za-z0-9_\-]{22}$")


def parse(text):
    """Handle, channel URL or UC id → the path part used in URLs ('@handle' or 'UC…'), or None."""
    s = text.strip().rstrip("/")
    m = re.search(r"youtube\.com/(@[^/?#]+|channel/(UC[^/?#]+)|c/[^/?#]+|user/[^/?#]+)", s)
    if m:
        s = m.group(2) or m.group(1)
    if UC_RE.match(s):
        return s
    if s.startswith("@") and len(s) > 1:
        return s
    if re.match(r"^(c|user)/", s):
        return s
    if re.match(r"^[A-Za-z0-9_.\-]{3,30}$", s):
        return "@" + s
    return None


def _path(ch):
    return f"channel/{ch}" if UC_RE.match(ch) else ch


def _find(pat, s):
    m = re.search(pat, s)
    return m.group(1) if m else ""


def _unescape(s):
    try:
        return json.loads(f'"{s}"')
    except ValueError:
        return s


def live_page(ch, name=""):
    """Read https://www.youtube.com/<channel>/live: a watch page while live, the channel page otherwise."""
    text, _ = net.fetch(f"{WEB}/{_path(ch)}/live")
    cid = _find(r'"externalId":"(UC[^"]+)"', text) or _find(r'"channelId":"(UC[^"]+)"', text)
    canon = _find(r'<link rel="canonical" href="([^"]+)"', text)
    live = '"isLiveNow":true' in text and "/watch?v=" in canon
    author = _unescape(_find(r'"ownerChannelName":"((?:[^"\\]|\\.)*)"', text) or _find(r'"author":"((?:[^"\\]|\\.)*)"', text))
    title_meta = html.unescape(_find(r'<meta property="og:title" content="([^"]*)"', text))
    r = {"platform": "youtube", "login": ch, "name": author or (title_meta if not live else "") or name or ch.lstrip("@"),
         "channel_id": cid, "live": live, "viewers": 0, "game": "", "title": "", "started_at": "", "language": "", "tags": []}
    if live:
        vid = canon.split("v=")[1].split("&")[0]
        r.update(video_id=vid, play_url=f"{WEB}/watch?v={vid}",
                 title=_unescape(_find(r'"videoDetails":\{"videoId":"[^"]+","title":"((?:[^"\\]|\\.)*)"', text)) or title_meta,
                 viewers=int(_find(r'"originalViewCount":"(\d+)"', text) or 0),
                 started_at=_find(r'"startTimestamp":"([^"]+)"', text),
                 game=_unescape(_find(r'"category":"((?:[^"\\]|\\.)*)"', text)))
    return r


def _offline(c):
    return {"platform": "youtube", "login": c["id"], "name": c.get("name") or c["id"].lstrip("@"), "channel_id": c.get("channel_id", ""),
            "live": False, "viewers": 0, "game": "", "title": "", "started_at": "", "language": "", "tags": []}


def check_pages(chans):
    rows, errors = [], []
    for c, res in net.parallel(lambda c: live_page(c["id"], c.get("name", "")), chans):
        if isinstance(res, Exception):
            errors.append(f"youtube/{c['id']}: {res}")
            rows.append(_offline(c))
        else:
            rows.append(res)
    return rows, errors


SEEN_FILE = "youtube_seen.json"


def check_feeds(chans, lookup):
    """RSS feed per channel (no quota) → recent video ids → lookup(ids) = videos.list items (1 unit per 50 ids).

    Videos already known not to be live (finished streams, uploads) are remembered and never asked about again,
    so after the first run a refresh costs about one quota unit.
    """
    rows, errors, owner = {}, [], {}
    seen = set(config.read_json(SEEN_FILE, []) or [])
    for c in chans:
        rows[c["id"]] = _offline(c)
    for c, res in net.parallel(lambda c: net.fetch(f"{WEB}/feeds/videos.xml?channel_id={c['channel_id']}")[0], chans):
        if isinstance(res, Exception):
            errors.append(f"youtube/{c['id']}: {res}")
            continue
        for vid in re.findall(r"<yt:videoId>([^<]+)</yt:videoId>", res):
            if vid not in seen:
                owner[vid] = c["id"]
    try:
        items = lookup(list(owner)) if owner else []
    except Exception as e:
        errors.append(f"youtube API: {e}")
        items = []
    for v in items:
        sn, ld = v.get("snippet", {}), v.get("liveStreamingDetails", {})
        state = sn.get("liveBroadcastContent")
        if state == "none":
            seen.add(v["id"])
            continue
        if state != "live" or v["id"] not in owner:
            continue
        r = rows[owner[v["id"]]]
        r.update(live=True, name=sn.get("channelTitle") or r["name"], title=sn.get("title", ""), video_id=v["id"],
                 play_url=f"{WEB}/watch?v={v['id']}", viewers=int(ld.get("concurrentViewers") or 0),
                 started_at=ld.get("actualStartTime", ""), language=(sn.get("defaultAudioLanguage") or "")[:2])
    if items:
        config.write_json(SEEN_FILE, sorted(seen)[-50000:])
    return list(rows.values()), errors


def _key_lookup(key):
    def lookup(ids):
        out = []
        for i in range(0, len(ids), 50):
            out += net.fetch_json(f"{API}?part=snippet,liveStreamingDetails&id={','.join(ids[i:i + 50])}&key={key}").get("items", [])
        return out
    return lookup


def check(chans, google_rec=None):
    """Live rows for the channels. Signed in with Google (or with an API key): RSS + videos.list. Otherwise /live pages."""
    from . import google
    key = config.youtube_api_key()
    lookup = (lambda ids: google.videos(ids, google_rec)) if google_rec else _key_lookup(key) if key else None
    if not lookup:
        return check_pages(chans)
    with_id = [c for c in chans if c.get("channel_id")]
    rows, errors = check_feeds(with_id, lookup)
    rest = [c for c in chans if not c.get("channel_id")]
    if rest:
        r2, e2 = check_pages(rest)
        rows += r2; errors += e2
    return rows, errors


def merge(*lists):
    """One channel list from several (your own list + subscriptions), without duplicates."""
    out, ids = [], set()
    for lst in lists:
        for c in lst or []:
            k = c.get("channel_id") or c["id"].lower()
            if k not in ids:
                ids.add(k)
                out.append(c)
    return out


def resolve(text):
    """Validate a channel the user typed. Returns {'id', 'name', 'channel_id'} or raises net.NetError."""
    ch = parse(text)
    if not ch:
        raise net.NetError("not a YouTube channel")
    try:
        r = live_page(ch)
    except net.NetError as e:
        if e.status == 404:
            raise net.NetError("channel not found", 404) from None
        raise
    if not r["channel_id"]:
        raise net.NetError("channel not found", 404)
    return {"id": ch, "name": r["name"], "channel_id": r["channel_id"]}


def read_takeout(path):
    """Google Takeout subscriptions.csv (Channel Id, Channel Url, Channel Title) → channel records."""
    out = []
    with open(Path(path).expanduser(), newline="", encoding="utf-8-sig") as fh:
        for rec in csv.reader(fh):
            if len(rec) < 3 or not UC_RE.match(rec[0].strip()):
                continue  # header or junk
            out.append({"id": rec[0].strip(), "name": rec[2].strip(), "channel_id": rec[0].strip()})
    return out


LIVE_FILTER = "EgJAAQ%253D%253D"  # YouTube's own "Live" search filter


def search(query, limit=15):
    """Live streams on YouTube matching the query, through yt-dlp (no API quota)."""
    import urllib.parse

    import yt_dlp
    q = query.strip()
    if len(q) < 2:
        return []
    url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(q)}&sp={LIVE_FILTER}"
    opts = {"quiet": True, "no_warnings": True, "extract_flat": True, "playlistend": limit, "noprogress": True}
    with yt_dlp.YoutubeDL(opts) as y:
        info = y.extract_info(url, download=False) or {}
    out = []
    for e in info.get("entries") or []:
        if not e.get("id") or e.get("live_status") not in (None, "is_live"):
            continue
        cid = e.get("channel_id") or ""
        out.append({"platform": "youtube", "login": e.get("uploader_id") or cid, "name": e.get("channel") or e.get("uploader") or cid,
                    "channel_id": cid, "video_id": e["id"], "play_url": f"https://www.youtube.com/watch?v={e['id']}",
                    "live": True, "viewers": int(e.get("concurrent_view_count") or 0), "game": "", "title": e.get("title") or "",
                    "started_at": "", "language": "", "tags": []})
    return out
