"""YouTube: live streams (only live, never videos) of the channels in the user's list.

Reading subscriptions needs a Google-verified app, so the list is the user's own (typed in, or imported from
Google Takeout). Without a key, openlive reads each channel's public /live page. With an optional YouTube Data
API key it uses the channels' RSS feeds plus one cheap videos.list call instead.
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


def check_api(chans, key):
    """RSS feed per channel (no quota) → recent video ids → one videos.list call per 50 ids (1 unit each)."""
    rows, errors, owner = {}, [], {}
    with_id = [c for c in chans if c.get("channel_id")]
    for c in chans:
        rows[c["id"]] = _offline(c)
    for c, res in net.parallel(lambda c: net.fetch(f"{WEB}/feeds/videos.xml?channel_id={c['channel_id']}")[0], with_id):
        if isinstance(res, Exception):
            errors.append(f"youtube/{c['id']}: {res}")
            continue
        for vid in re.findall(r"<yt:videoId>([^<]+)</yt:videoId>", res)[:5]:
            owner[vid] = c["id"]
    ids = list(owner)
    for i in range(0, len(ids), 50):
        q = f"{API}?part=snippet,liveStreamingDetails&id={','.join(ids[i:i + 50])}&key={key}"
        try:
            data = net.fetch_json(q)
        except net.NetError as e:
            errors.append(f"youtube API: {e}")
            break
        for v in data.get("items", []):
            sn, ld = v.get("snippet", {}), v.get("liveStreamingDetails", {})
            if sn.get("liveBroadcastContent") != "live":
                continue
            r = rows[owner[v["id"]]]
            r.update(live=True, name=sn.get("channelTitle") or r["name"], title=sn.get("title", ""), video_id=v["id"],
                     play_url=f"{WEB}/watch?v={v['id']}", viewers=int(ld.get("concurrentViewers") or 0),
                     started_at=ld.get("actualStartTime", ""), language=sn.get("defaultAudioLanguage", "")[:2])
    return list(rows.values()), errors


def check(chans):
    key = config.youtube_api_key()
    if key and all(c.get("channel_id") for c in chans):
        return check_api(chans, key)
    return check_pages(chans)


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
