from openlive import config, player


def test_command_uses_configured_player(monkeypatch, tmp_path):
    exe = tmp_path / "mpv"
    exe.write_text("")
    config.CONFIG.update(player=str(exe), quality="720p60", player_args="--volume=50")
    cmd = player.build_command("somechannel", "a title")
    assert "https://twitch.tv/somechannel" in cmd and "720p60" in cmd
    assert cmd[cmd.index("--player") + 1] == str(exe)
    assert cmd[cmd.index("--player-args") + 1] == "--volume=50"
    assert "--twitch-low-latency" in cmd


def test_no_player_is_reported(monkeypatch):
    monkeypatch.setattr(player, "find_player", lambda name=None: (None, None))
    ok, why = player.play("x")
    assert not ok and why == "no-player"


def test_twitch_plays_the_growing_recording_in_mpv(monkeypatch, tmp_path):
    import json
    exe = tmp_path / "mpv"
    exe.write_text("")
    config.CONFIG.update(player=str(exe))

    class C:
        def current_vod(self, uid, started):
            assert uid == "42"
            return "https://www.twitch.tv/videos/1"
    monkeypatch.setattr(player, "_direct_url", lambda url, q: "https://cdn/x/index-dvr.m3u8" if "videos/1" in url else None)
    row = {"platform": "twitch", "login": "a", "name": "A", "user_id": "42", "started_at": "2026-01-01T00:00:00Z"}
    cmd, bridge = player.command_for(row, "hi", C())
    assert cmd[0] == str(exe) and cmd[-1] == "https://cdn/x/index-dvr.m3u8" and "--start=-6" in cmd
    d = config.DATA / "mpv"
    assert cmd[1] == f"--config-dir={d}" and (d / "scripts" / "openlive_ui.lua").exists()
    assert "osc=no" in (d / "mpv.conf").read_text()
    session = json.loads(open(cmd[2].split("=", 2)[2]).read())
    assert session["mode"] == "vod" and session["chat"] == "a" and session["channel"] == "A" and session["text"]["live"]
    ipc = next(c for c in cmd if c.startswith("--input-ipc-server=")).split("=", 1)[1]
    assert bridge[-3:] == ["openlive.chat", ipc, "a"]


def test_no_recording_falls_back_to_streamlink_with_openlive_mpv(monkeypatch, tmp_path):
    exe = tmp_path / "mpv"
    exe.write_text("")
    config.CONFIG.update(player=str(exe))
    monkeypatch.setattr(player, "session_for", lambda *a: None)
    cmd, bridge = player.command_for({"platform": "kick", "login": "k", "name": "K"}, "t")
    assert "https://kick.com/k" in cmd and "--config-dir=" in cmd[cmd.index("--player-args") + 1]
    assert bridge is None  # chat sidebar is Twitch only for now


def test_kick_and_youtube_sessions(monkeypatch):
    monkeypatch.setattr(player, "_direct_url", lambda url, q: "https://live/k.m3u8")
    monkeypatch.setattr(player.kick, "current_vod", lambda slug: "https://vod/k.m3u8")
    s = player.session_for({"platform": "kick", "login": "k"})
    assert s["mode"] == "live" and s["vod"] == "https://vod/k.m3u8"
    monkeypatch.setattr(player, "_youtube_hls", lambda page, q: ("https://yt/v.m3u8", "https://yt/a.m3u8"))
    monkeypatch.setattr(player.net, "fetch", lambda url: ("#EXTM3U\n#EXT-X-TARGETDURATION:5\n" + "#EXTINF:5.0,\nx\n" * 720, url))
    s = player.session_for({"platform": "youtube", "login": "@x"})
    assert s["dvr"] == 3600 and s["seg"] == 5 and s["audio"] == "https://yt/a.m3u8"


def test_pick_quality_by_height():
    fs = [{"height": h} for h in (144, 480, 720, 1080)]
    assert player._pick(fs, "best")["height"] == 1080
    assert player._pick(fs, "worst")["height"] == 144
    assert player._pick(fs, "720p60")["height"] == 720
    assert player._pick(fs, "600p")["height"] == 480


def test_plain_ui_keeps_streamlink(monkeypatch, tmp_path):
    exe = tmp_path / "mpv"
    exe.write_text("")
    config.CONFIG.update(player=str(exe), player_ui="plain")
    cmd, bridge = player.command_for({"platform": "kick", "login": "k", "name": "K"}, "t")
    assert "--player" in cmd and not any("--config-dir" in c for c in cmd) and bridge is None


def test_chat_parses_twitch_messages():
    from openlive import chat
    line = r"@badge-info=;color=#1E90FF;display-name=Some\sOne;emotes= :someone!someone@someone.tmi.twitch.tv PRIVMSG #chan :hola :) que tal"
    assert chat.parse(line) == {"n": "Some One", "c": "#1E90FF", "t": "hola :) que tal"}
    assert chat.parse(":x!x@x PRIVMSG #chan :\x01ACTION waves\x01")["t"] == "waves"
    assert chat.parse(":tmi.twitch.tv 001 justinfan1 :Welcome") is None
