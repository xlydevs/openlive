"""Twitch sign-in (device code flow, no secret needed) and the few Helix calls openlive uses.

Only the standard library: urllib + json. The token lives in the data dir (auth.json, mode 0600).
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from . import __version__, config

ID_URL = "https://id.twitch.tv/oauth2"
API_URL = "https://api.twitch.tv/helix"
SCOPES = "user:read:follows"
AUTH_FILE = "auth.json"
UA = f"openlive/{__version__}"


class TwitchError(Exception):
    def __init__(self, msg, status=0):
        super().__init__(msg)
        self.status = status


class NotSignedIn(TwitchError):
    pass


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
        raise TwitchError(info.get("message") or f"HTTP {e.code}", e.code) from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise TwitchError(f"network: {getattr(e, 'reason', e)}") from None


# ───────────────────────── sign-in ─────────────────────────

def start_device_login(client_id):
    """Returns {device_code, user_code, verification_uri, expires_in, interval}."""
    return _request(f"{ID_URL}/device", {"client_id": client_id, "scopes": SCOPES})


def poll_device_login(client_id, device_code):
    """One poll. Returns the token dict when the user has authorised, None while pending.
    Raises TwitchError when the code expired or was denied."""
    try:
        tok = _request(f"{ID_URL}/token", {"client_id": client_id, "scopes": SCOPES, "device_code": device_code,
                                           "grant_type": "urn:ietf:params:oauth:grant-type:device_code"})
    except TwitchError as e:
        if "pending" in str(e).lower() or "slow_down" in str(e).lower():
            return None
        raise
    return tok


def finish_login(client_id, tok):
    """Validate the fresh token, store it with the user's id/login and return the saved record."""
    info = validate(tok["access_token"])
    rec = {"client_id": client_id, "access_token": tok["access_token"], "refresh_token": tok.get("refresh_token"),
           "expires_at": time.time() + int(tok.get("expires_in") or info.get("expires_in") or 0),
           "user_id": info["user_id"], "login": info["login"]}
    config.write_json(AUTH_FILE, rec, private=True)
    return rec


def validate(access_token):
    return _request(f"{ID_URL}/validate", headers={"Authorization": f"OAuth {access_token}"})


def load_auth():
    rec = config.read_json(AUTH_FILE)
    if not rec or not rec.get("access_token"):
        return None
    if rec.get("client_id") != config.client_id():  # signed in through another app id: start over
        return None
    return rec


def logout():
    rec = config.read_json(AUTH_FILE)
    config.delete(AUTH_FILE)
    if rec and rec.get("access_token"):
        try:
            _request(f"{ID_URL}/revoke", {"client_id": rec.get("client_id", ""), "token": rec["access_token"]})
        except TwitchError:
            pass


def refresh(rec):
    if not rec.get("refresh_token"):
        raise NotSignedIn("session expired")
    try:
        tok = _request(f"{ID_URL}/token", {"client_id": rec["client_id"], "grant_type": "refresh_token",
                                           "refresh_token": rec["refresh_token"]})
    except TwitchError as e:
        if e.status in (400, 401):
            config.delete(AUTH_FILE)
            raise NotSignedIn("session expired") from None
        raise
    rec.update(access_token=tok["access_token"], refresh_token=tok.get("refresh_token", rec["refresh_token"]),
               expires_at=time.time() + int(tok.get("expires_in") or 0))
    config.write_json(AUTH_FILE, rec, private=True)
    return rec


def run_terminal_login(client_id, out=print, open_browser=True):
    """Sign in without the TUI (for `openlive --login`)."""
    from .i18n import t
    d = start_device_login(client_id)
    url = d["verification_uri"]
    out(t("Open {url} and enter this code: {code}", url=url, code=d["user_code"]))
    if open_browser:
        import webbrowser
        webbrowser.open(url)
    deadline = time.time() + int(d.get("expires_in", 1800))
    while time.time() < deadline:
        time.sleep(max(1, int(d.get("interval", 5))))
        tok = poll_device_login(client_id, d["device_code"])
        if tok:
            return finish_login(client_id, tok)
    raise TwitchError(t("The code expired. Try again."))


# ───────────────────────── Helix ─────────────────────────

class Client:
    def __init__(self, auth):
        self.auth = auth

    @property
    def login(self):
        return self.auth["login"]

    def get(self, path, params):
        if self.auth.get("expires_at") and self.auth["expires_at"] - time.time() < 60:
            refresh(self.auth)
        for attempt in (0, 1):
            q = urllib.parse.urlencode(params, doseq=True)
            try:
                return _request(f"{API_URL}/{path}?{q}", headers={"Client-Id": self.auth["client_id"],
                                                                  "Authorization": f"Bearer {self.auth['access_token']}"})
            except TwitchError as e:
                if e.status == 401 and attempt == 0:
                    refresh(self.auth)
                    continue
                raise

    def paged(self, path, params, limit=1000):
        out, cursor = [], None
        while len(out) < limit:
            p = dict(params, first=100)
            if cursor: p["after"] = cursor
            r = self.get(path, p)
            out += r.get("data", [])
            cursor = (r.get("pagination") or {}).get("cursor")
            if not cursor or not r.get("data"):
                break
        return out[:limit]

    def followed_live(self):
        return self.paged("streams/followed", {"user_id": self.auth["user_id"]})

    def followed_channels(self):
        return self.paged("channels/followed", {"user_id": self.auth["user_id"]}, limit=2000)

    def top_streams(self, language=None, limit=100):
        p = {"language": language} if language else {}
        return self.paged("streams", p, limit=limit)

    def streams_by_login(self, logins):
        out, logins = [], list(logins)
        for i in range(0, len(logins), 100):
            out += self.get("streams", {"user_login": logins[i:i + 100], "first": 100}).get("data", [])
        return out

    def search(self, query, limit=50):
        r = self.get("search/channels", {"query": query, "first": min(100, limit)})
        return r.get("data", [])


def norm_stream(s):
    """Helix stream → the row dict the UI uses."""
    return {"platform": "twitch", "login": s.get("user_login", ""), "name": s.get("user_name") or s.get("user_login", ""),
            "game": s.get("game_name", ""), "viewers": int(s.get("viewer_count") or 0), "title": s.get("title", ""),
            "started_at": s.get("started_at", ""), "language": s.get("language", ""), "tags": s.get("tags") or [],
            "live": True}


def norm_search(c):
    return {"platform": "twitch", "login": c.get("broadcaster_login", ""), "name": c.get("display_name") or c.get("broadcaster_login", ""),
            "game": c.get("game_name", ""), "viewers": 0, "title": c.get("title", ""),
            "started_at": c.get("started_at", "") if c.get("is_live") else "", "language": c.get("broadcaster_language", ""),
            "tags": c.get("tags") or [], "live": bool(c.get("is_live"))}


def norm_followed(c):
    return {"platform": "twitch", "login": c.get("broadcaster_login", ""), "name": c.get("broadcaster_name") or c.get("broadcaster_login", ""),
            "game": "", "viewers": 0, "title": "", "started_at": "", "language": "", "tags": [], "live": False,
            "followed_at": c.get("followed_at", "")}
