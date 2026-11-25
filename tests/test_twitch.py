import time

import pytest

from openlive import config, twitch


def stream(login, viewers=10):
    return {"user_login": login, "user_name": login.title(), "game_name": "Chess", "viewer_count": viewers,
            "title": "hi", "started_at": "2026-11-25T10:00:00Z", "language": "en", "tags": ["English"]}


def test_device_login_saves_private_token(monkeypatch):
    calls = []

    def fake(url, data=None, headers=None, timeout=15):
        calls.append(url)
        if url.endswith("/device"):
            return {"device_code": "dc", "user_code": "ABCD1234", "verification_uri": "https://www.twitch.tv/activate?x", "interval": 1}
        if url.endswith("/token"):
            if len(calls) < 4:
                raise twitch.TwitchError("authorization_pending", 400)
            return {"access_token": "at", "refresh_token": "rt", "expires_in": 3600}
        if url.endswith("/validate"):
            return {"user_id": "42", "login": "someone", "expires_in": 3600}
        raise AssertionError(url)
    monkeypatch.setattr(twitch, "_request", fake)
    d = twitch.start_device_login("test-client")
    assert twitch.poll_device_login("test-client", d["device_code"]) is None
    assert twitch.poll_device_login("test-client", d["device_code"]) is None
    rec = twitch.finish_login("test-client", twitch.poll_device_login("test-client", d["device_code"]))
    assert rec["login"] == "someone" and rec["user_id"] == "42"
    assert twitch.load_auth()["access_token"] == "at"
    path = config.DATA / twitch.AUTH_FILE
    if not config.WIN:
        assert path.stat().st_mode & 0o777 == 0o600


def test_denied_code_raises(monkeypatch):
    def fake(url, data=None, headers=None, timeout=15):
        raise twitch.TwitchError("access_denied", 400)
    monkeypatch.setattr(twitch, "_request", fake)
    with pytest.raises(twitch.TwitchError):
        twitch.poll_device_login("test-client", "dc")


def test_token_from_other_client_id_is_ignored():
    config.write_json(twitch.AUTH_FILE, {"client_id": "other", "access_token": "x", "user_id": "1", "login": "a"})
    assert twitch.load_auth() is None


def test_401_refreshes_once_and_retries(monkeypatch):
    rec = {"client_id": "test-client", "access_token": "old", "refresh_token": "rt", "expires_at": time.time() + 3600,
           "user_id": "1", "login": "me"}
    seen = []

    def fake(url, data=None, headers=None, timeout=15):
        if url.endswith("/token"):
            assert data["grant_type"] == "refresh_token" and "client_secret" not in data
            return {"access_token": "new", "refresh_token": "rt2", "expires_in": 3600}
        seen.append(headers["Authorization"])
        if headers["Authorization"] == "Bearer old":
            raise twitch.TwitchError("Invalid OAuth token", 401)
        return {"data": [stream("a", 5), stream("b", 50)]}
    monkeypatch.setattr(twitch, "_request", fake)
    rows = [twitch.norm_stream(s) for s in twitch.Client(rec).followed_live()]
    assert seen == ["Bearer old", "Bearer new"]
    assert {r["login"] for r in rows} == {"a", "b"} and rows[1]["viewers"] == 50
    assert twitch.load_auth()["refresh_token"] == "rt2"


def test_failed_refresh_signs_out(monkeypatch):
    rec = {"client_id": "test-client", "access_token": "old", "refresh_token": "rt", "expires_at": 0, "user_id": "1", "login": "me"}
    config.write_json(twitch.AUTH_FILE, rec)

    def fake(url, data=None, headers=None, timeout=15):
        raise twitch.TwitchError("Invalid refresh token", 400)
    monkeypatch.setattr(twitch, "_request", fake)
    rec["expires_at"] = time.time() + 10  # about to expire: refresh first
    with pytest.raises(twitch.NotSignedIn):
        twitch.Client(rec).followed_live()
    assert twitch.load_auth() is None


def test_paging_follows_cursor(monkeypatch):
    pages = {None: ({"data": [stream("a")], "pagination": {"cursor": "c1"}}), "c1": {"data": [stream("b")], "pagination": {}}}

    def fake(url, data=None, headers=None, timeout=15):
        cur = url.split("after=")[1] if "after=" in url else None
        return pages[cur]
    monkeypatch.setattr(twitch, "_request", fake)
    rec = {"client_id": "test-client", "access_token": "t", "expires_at": time.time() + 3600, "user_id": "1", "login": "me"}
    assert [s["user_login"] for s in twitch.Client(rec).followed_live()] == ["a", "b"]
