import pytest

from openlive import channels, kick, net, player, youtube

LIVE_PAGE = ('<link rel="canonical" href="https://www.youtube.com/watch?v=abc123XYZ_0">'
             '"videoDetails":{"videoId":"abc123XYZ_0","title":"radio \\u2014 live"} "isLiveNow":true "channelId":"UC' + "x" * 22 + '"'
             ' "ownerChannelName":"Cozy Radio" "originalViewCount":"4321" "startTimestamp":"2026-11-25T08:00:00+00:00" "category":"Music"')
OFF_PAGE = '<link rel="canonical" href="https://www.youtube.com/channel/UC' + "y" * 22 + '"> "externalId":"UC' + "y" * 22 + '"' \
           ' <meta property="og:title" content="Garden &amp; Grid">'


@pytest.mark.parametrize("text,want", [("xqc", "xqc"), ("https://kick.com/XQC/videos", "xqc"), ("kick.com/a_b-c", "a_b-c"),
                                       ("not a channel!", None)])
def test_kick_parse(text, want):
    assert kick.parse(text) == want


@pytest.mark.parametrize("text,want", [("@LofiGirl", "@LofiGirl"), ("https://www.youtube.com/@mkbhd/streams", "@mkbhd"),
                                       ("youtube.com/channel/UC" + "a" * 22, "UC" + "a" * 22), ("mkbhd", "@mkbhd"), ("??", None)])
def test_youtube_parse(text, want):
    assert youtube.parse(text) == want


def test_kick_row_live_uses_hls_link():
    d = {"slug": "someone", "user": {"username": "SomeOne"}, "playback_url": "https://x/y.m3u8",
         "livestream": {"is_live": True, "viewer_count": 12, "session_title": "hi", "start_time": "2026-11-25 08:00:00",
                        "lang_iso": "es", "categories": [{"name": "IRL"}]}}
    r = kick.row(d)
    assert r["live"] and r["viewers"] == 12 and r["game"] == "IRL" and r["started_at"] == "2026-11-25T08:00:00Z"
    assert player.stream_url(r) == "hls://https://x/y.m3u8"
    off = kick.row({"slug": "someone", "user": {"username": "SomeOne"}, "livestream": None})
    assert not off["live"] and "play_url" not in off and player.stream_url(off) == "https://kick.com/someone"


def test_youtube_live_and_offline_pages(monkeypatch):
    pages = {"@cozy": LIVE_PAGE, "@garden": OFF_PAGE}
    monkeypatch.setattr(net, "fetch", lambda url, headers=None, timeout=15: (pages[url.split("/")[3]], url))
    rows, errors = youtube.check([{"id": "@cozy"}, {"id": "@garden"}])
    assert not errors
    live, off = rows
    assert live["live"] and live["name"] == "Cozy Radio" and live["viewers"] == 4321 and live["title"] == "radio — live"
    assert player.stream_url(live) == "https://www.youtube.com/watch?v=abc123XYZ_0"
    assert player.chat_url(live) == "https://www.youtube.com/live_chat?v=abc123XYZ_0"
    assert not off["live"] and off["name"] == "Garden & Grid" and off["channel_id"] == "UC" + "y" * 22


def test_youtube_errors_keep_the_channel_listed(monkeypatch):
    def boom(url, headers=None, timeout=15):
        raise net.NetError("HTTP 500", 500)
    monkeypatch.setattr(net, "fetch", boom)
    rows, errors = youtube.check([{"id": "@gone", "name": "Gone"}])
    assert rows[0]["name"] == "Gone" and not rows[0]["live"] and errors


def test_takeout_import(tmp_path):
    f = tmp_path / "subscriptions.csv"
    f.write_text("Channel Id,Channel Url,Channel Title\nUC" + "b" * 22 + ",http://www.youtube.com/channel/UC" + "b" * 22 + ",Some Channel\n\n",
                 encoding="utf-8")
    assert youtube.read_takeout(f) == [{"id": "UC" + "b" * 22, "name": "Some Channel", "channel_id": "UC" + "b" * 22}]


def test_channel_lists_add_remove():
    d = channels.load()
    assert channels.add(d, "kick", {"id": "xqc", "name": "xQc"})
    assert not channels.add(d, "kick", {"id": "XQC", "name": "xQc"})  # no duplicates
    channels.save(d)
    assert channels.load()["kick"] == [{"id": "xqc", "name": "xQc"}]
    assert channels.remove(d, "kick", "xqc") and d["kick"] == []
    assert channels.row_key({"platform": "kick", "login": "xqc"}) == "kick:xqc"
    assert channels.row_key({"platform": "twitch", "login": "xqc"}) == "xqc"
