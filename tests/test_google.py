import time

import pytest

from openlive import config, google, net, youtube


def test_device_login_and_refresh(monkeypatch):
    calls = []

    def fake(url, data=None, headers=None, timeout=15):
        calls.append((url, data, headers))
        if url == google.DEVICE_URL:
            return {"device_code": "dc", "user_code": "ABC-DEF", "verification_url": "https://www.google.com/device", "interval": 5}
        if url == google.TOKEN_URL and data["grant_type"].endswith("device_code"):
            if sum(1 for c in calls if c[0] == google.TOKEN_URL) < 2:
                raise google.GoogleError("pending", 428, "authorization_pending")
            return {"access_token": "at1", "refresh_token": "rt", "expires_in": 3600}
        if url == google.TOKEN_URL:
            return {"access_token": "at2", "expires_in": 3600}
        if "/channels?" in url:
            return {"items": [{"snippet": {"title": "My Channel"}}]}
        raise AssertionError(url)
    monkeypatch.setattr(google, "_request", fake)
    d = google.start_device_login()
    assert d["verification_uri"] == "https://www.google.com/device"
    assert google.poll_device_login("dc") is None
    rec = google.finish_login(google.poll_device_login("dc"))
    assert rec["name"] == "My Channel" and google.load_auth()["refresh_token"] == "rt"
    if not config.WIN:  # Windows has no Unix permissions
        assert (config.DATA / google.AUTH_FILE).stat().st_mode & 0o777 == 0o600
    rec["expires_at"] = int(time.time()) - 1
    assert google.token(rec) == "at2" and google.load_auth()["refresh_token"] == "rt"


def test_expired_refresh_signs_out(monkeypatch):
    config.write_json(google.AUTH_FILE, {"client_id": google.CLIENT_ID, "access_token": "x", "refresh_token": "rt", "expires_at": 0})

    def fake(url, data=None, headers=None, timeout=15):
        raise google.GoogleError("Token has been expired or revoked.", 400, "invalid_grant")
    monkeypatch.setattr(google, "_request", fake)
    with pytest.raises(google.NotSignedIn):
        google.token(google.load_auth())
    assert google.load_auth() is None


def test_subscriptions_paged_and_cached(monkeypatch):
    rec = {"access_token": "at", "refresh_token": "rt", "expires_at": int(time.time()) + 3600}
    pages = {None: (["UC" + "a" * 22, "UC" + "b" * 22], "p2"), "p2": (["UC" + "c" * 22], None)}
    seen = []

    def fake(url, data=None, headers=None, timeout=15):
        assert headers["Authorization"] == "Bearer at"
        tok = url.split("pageToken=")[1].split("&")[0] if "pageToken=" in url else None
        seen.append(tok)
        ids, nxt = pages[tok]
        return {"items": [{"snippet": {"title": i[-1] * 3, "resourceId": {"channelId": i}}} for i in ids], "nextPageToken": nxt}
    monkeypatch.setattr(google, "_request", fake)
    subs = google.subscriptions(rec)
    assert [s["name"] for s in subs] == ["aaa", "bbb", "ccc"] and subs[0]["channel_id"] == subs[0]["id"]
    assert google.subscriptions(rec) == subs and seen == [None, "p2"]  # second call comes from the cache


def test_check_feeds_remembers_finished_videos(monkeypatch):
    chans = [{"id": "UC" + "a" * 22, "name": "A", "channel_id": "UC" + "a" * 22}]
    monkeypatch.setattr(net, "fetch", lambda url, **kw: ("<yt:videoId>live1</yt:videoId><yt:videoId>old1</yt:videoId>", url))
    asked = []

    def lookup(ids):
        asked.append(sorted(ids))
        return [{"id": "live1", "snippet": {"liveBroadcastContent": "live", "title": "on air", "channelTitle": "A"},
                 "liveStreamingDetails": {"concurrentViewers": "42", "actualStartTime": "2026-11-25T10:00:00Z"}},
                {"id": "old1", "snippet": {"liveBroadcastContent": "none"}}]
    rows, errors = youtube.check_feeds(chans, lookup)
    assert not errors and rows[0]["live"] and rows[0]["viewers"] == 42 and rows[0]["play_url"].endswith("v=live1")
    youtube.check_feeds(chans, lookup)
    assert asked == [["live1", "old1"], ["live1"]]  # the finished video isn't asked about again


def test_merge_dedupes_by_channel_id():
    a = [{"id": "@lofigirl", "name": "Lofi Girl", "channel_id": "UCx"}]
    b = [{"id": "UCx", "name": "Lofi Girl", "channel_id": "UCx"}, {"id": "UCy", "name": "Y", "channel_id": "UCy"}]
    assert [c["id"] for c in youtube.merge(a, b)] == ["@lofigirl", "UCy"]
