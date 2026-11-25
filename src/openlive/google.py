"""Sign in with Google (device code flow, like Twitch) to read your YouTube subscriptions. Read-only.

The client below is an "installed app" client: Google documents that its secret can't be kept secret in an
app people download, and treats it as public. Use your own with [youtube] client_id / client_secret.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from . import __version__, config

CLIENT_ID = "390084661256-2e70rjnskdf0kaeh6ka9holm47thenhl.apps.googleusercontent.com"
CLIENT_SECRET = "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"
SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
DEVICE_URL = "https://oauth2.googleapis.com/device/code"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
API = "https://www.googleapis.com/youtube/v3"
AUTH_FILE = "google_auth.json"
SUBS_FILE = "youtube_subs.json"
SUBS_MAX_AGE = 12 * 3600
UA = f"openlive/{__version__}"


class GoogleError(Exception):
    def __init__(self, msg, status=0, code=""):
        super().__init__(msg)
        self.status, self.code = status, code


class NotSignedIn(GoogleError):
    pass


def client():
    yt = config.CONFIG.get("youtube") or {}
    return yt.get("client_id") or CLIENT_ID, yt.get("client_secret") or CLIENT_SECRET


def _request(url, data=None, headers=None, timeout=15):
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers={"User-Agent": UA, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            info = json.loads(e.read() or b"{}")
        except ValueError:
            info = {}
        err = info.get("error")
        if isinstance(err, dict):  # API errors: {"error": {"message": …}}
            raise GoogleError(err.get("message") or f"HTTP {e.code}", e.code) from None
        raise GoogleError(info.get("error_description") or err or f"HTTP {e.code}", e.code, err or "") from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise GoogleError(f"network: {getattr(e, 'reason', e)}") from None


# ───────────────────────── sign-in ─────────────────────────

def start_device_login():
    cid, _ = client()
    d = _request(DEVICE_URL, {"client_id": cid, "scope": SCOPE})
    d["verification_uri"] = d.get("verification_url") or d.get("verification_uri") or "https://www.google.com/device"
    return d


def poll_device_login(device_code):
    """The token once the user has approved; None while waiting. Raises GoogleError when denied or expired."""
    cid, secret = client()
    try:
        return _request(TOKEN_URL, {"client_id": cid, "client_secret": secret, "device_code": device_code,
                                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code"})
    except GoogleError as e:
        if e.code in ("authorization_pending", "slow_down"):
            return None
        raise


def _record(tok, old=None):
    rec = dict(old or {})
    rec.update(client_id=client()[0], access_token=tok["access_token"], expires_at=int(time.time()) + int(tok.get("expires_in", 3600)))
    if tok.get("refresh_token"):
        rec["refresh_token"] = tok["refresh_token"]
    return rec


def finish_login(tok):
    rec = _record(tok)
    try:
        items = _get("channels", {"part": "snippet", "mine": "true"}, rec).get("items") or []
        rec["name"] = items[0]["snippet"]["title"] if items else "YouTube"
    except GoogleError:
        rec["name"] = "YouTube"
    config.write_json(AUTH_FILE, rec, private=True)
    config.delete(SUBS_FILE)
    return rec


def load_auth():
    rec = config.read_json(AUTH_FILE)
    if not rec or rec.get("client_id") != client()[0] or not rec.get("refresh_token"):
        return None
    return rec


def refresh(rec):
    cid, secret = client()
    try:
        tok = _request(TOKEN_URL, {"client_id": cid, "client_secret": secret, "refresh_token": rec["refresh_token"],
                                   "grant_type": "refresh_token"})
    except GoogleError as e:
        if e.code in ("invalid_grant", "unauthorized_client") or e.status in (400, 401):
            config.delete(AUTH_FILE)
            raise NotSignedIn("Google sign-in expired") from None
        raise
    new = _record(tok, rec)
    config.write_json(AUTH_FILE, new, private=True)
    rec.update(new)
    return rec


def token(rec):
    """A valid access token, refreshed when it is about to expire."""
    if rec.get("expires_at", 0) - 60 < time.time():
        refresh(rec)
    return rec["access_token"]


def logout():
    rec = config.read_json(AUTH_FILE)
    if rec and rec.get("refresh_token"):
        try:
            _request(REVOKE_URL, {"token": rec["refresh_token"]})
        except GoogleError:
            pass
    config.delete(AUTH_FILE)
    config.delete(SUBS_FILE)


# ───────────────────────── API ─────────────────────────

def _get(path, params, rec):
    url = f"{API}/{path}?{urllib.parse.urlencode(params)}"
    for attempt in (0, 1):
        try:
            return _request(url, headers={"Authorization": f"Bearer {token(rec)}"})
        except GoogleError as e:
            if e.status == 401 and attempt == 0:
                refresh(rec)
                continue
            raise
    return {}


def subscriptions(rec, force=False):
    """Your subscriptions as channel records, cached for 12 hours (1 quota unit per 50 channels)."""
    cached = config.read_json(SUBS_FILE) or {}
    if not force and cached.get("items") is not None and time.time() - cached.get("at", 0) < SUBS_MAX_AGE:
        return cached["items"]
    items, page = [], None
    while True:
        params = {"part": "snippet", "mine": "true", "maxResults": 50, "order": "alphabetical"}
        if page:
            params["pageToken"] = page
        d = _get("subscriptions", params, rec)
        for it in d.get("items", []):
            sn = it.get("snippet", {})
            cid = (sn.get("resourceId") or {}).get("channelId")
            if cid:
                items.append({"id": cid, "name": sn.get("title") or cid, "channel_id": cid})
        page = d.get("nextPageToken")
        if not page or len(items) >= 5000:
            break
    config.write_json(SUBS_FILE, {"at": int(time.time()), "items": items})
    return items


def videos(ids, rec):
    """videos.list for up to 50 ids per call (1 quota unit each)."""
    out = []
    for i in range(0, len(ids), 50):
        out += _get("videos", {"part": "snippet,liveStreamingDetails", "id": ",".join(ids[i:i + 50])}, rec).get("items", [])
    return out
