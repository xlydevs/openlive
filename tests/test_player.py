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
    monkeypatch.setattr(player, "_streams", lambda url: [("1080p60", "https://cdn/x/index-dvr.m3u8"), ("720p60", "https://cdn/7")]
                        if "videos/1" in url else [])
    row = {"platform": "twitch", "login": "a", "name": "A", "user_id": "42", "started_at": "2026-01-01T00:00:00Z"}
    cmd, bridge = player.command_for(row, "hi", C())
    assert cmd[0] == str(exe) and cmd[-1] == "https://cdn/x/index-dvr.m3u8" and "--start=-6" in cmd
    d = config.DATA / "mpv"
    assert cmd[1] == f"--config-dir={d}" and (d / "scripts" / "openlive_ui.lua").exists()
    assert "osc=no" in (d / "mpv.conf").read_text()
    session = json.loads(open(cmd[2].split("=", 2)[2]).read())
    assert session["mode"] == "vod" and session["chat"] == "a" and session["channel"] == "A" and session["text"]["live"]
    assert session["quality"] == "1080p60" and [q["name"] for q in session["qualities"]] == ["1080p60", "720p60"]
    ipc = next(c for c in cmd if c.startswith("--input-ipc-server=")).split("=", 1)[1]
    assert bridge[-4:] == ["openlive.chat", ipc, "a", "42"]


def test_no_recording_falls_back_to_streamlink_with_openlive_mpv(monkeypatch, tmp_path):
    exe = tmp_path / "mpv"
    exe.write_text("")
    config.CONFIG.update(player=str(exe))
    monkeypatch.setattr(player, "session_for", lambda *a: None)
    cmd, bridge = player.command_for({"platform": "kick", "login": "k", "name": "K"}, "t")
    assert "https://kick.com/k" in cmd and "--config-dir=" in cmd[cmd.index("--player-args") + 1]
    assert bridge is None  # chat sidebar is Twitch only for now


def test_kick_and_youtube_sessions(monkeypatch):
    monkeypatch.setattr(player, "_streams", lambda url: [("720p60", "https://live/k.m3u8")])
    monkeypatch.setattr(player.kick, "current_vod", lambda slug: "https://vod/k.m3u8")
    monkeypatch.setattr(player, "_variants", lambda url: [("720p60", "https://vod/720.m3u8")])
    s = player.session_for({"platform": "kick", "login": "k"})
    assert s["mode"] == "live" and s["vod"] == "https://vod/k.m3u8" and s["vod_qualities"][0]["url"] == "https://vod/720.m3u8"
    monkeypatch.setattr(player, "_youtube_hls", lambda page, q: ("https://yt/v.m3u8", "https://yt/a.m3u8",
                                                                  [("1080p60", "https://yt/v.m3u8"), ("720p", "https://yt/7")]))
    monkeypatch.setattr(player.net, "fetch", lambda url: ("#EXTM3U\n#EXT-X-TARGETDURATION:5\n" + "#EXTINF:5.0,\nx\n" * 720, url))
    s = player.session_for({"platform": "youtube", "login": "@x"})
    assert s["dvr"] == 3600 and s["seg"] == 5 and s["audio"] == "https://yt/a.m3u8" and s["quality"] == "1080p60"


REAL_STREAMS = player._streams  # conftest swaps it for a no-network stub


def test_streams_from_streamlink_json(monkeypatch):
    import json
    import subprocess
    monkeypatch.setattr(player, "_streams", REAL_STREAMS)
    found = {"streams": {n: {"type": "hls", "url": f"https://h/{n}"} for n in
                         ("audio_only", "160p30", "720p60", "1080p60", "480p30", "worst", "best")}}
    monkeypatch.setattr(player, "streamlink_cmd", lambda: ["streamlink"])
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a, 0, json.dumps(found), ""))
    streams = player._streams("https://twitch.tv/x")
    assert [n for n, _ in streams] == ["1080p60", "720p60", "480p30", "160p30"]
    assert player._choose(streams, "best") == ("1080p60", "https://h/1080p60")
    assert player._choose(streams, "720p")[0] == "720p60"
    assert player._choose(streams, "480p30")[0] == "480p30"
    assert player._choose(streams, "worst")[0] == "160p30"
    assert player._choose(streams, "100p")[0] == "160p30"
    assert player._choose([], "best") is None


def test_kick_recording_variants(monkeypatch):
    master = ("#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1,RESOLUTION=1280x720,FRAME-RATE=60.000\n720p60/playlist.m3u8\n"
              "#EXT-X-STREAM-INF:BANDWIDTH=2,RESOLUTION=1920x1080,FRAME-RATE=60.000\n1080p60/playlist.m3u8\n")
    monkeypatch.setattr(player.net, "fetch", lambda url: (master, url))
    assert player._variants("https://vod/k/master.m3u8") == [("1080p60", "https://vod/k/1080p60/playlist.m3u8"),
                                                             ("720p60", "https://vod/k/720p60/playlist.m3u8")]


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
    assert chat.parse(line) == {"n": "Some One", "c": "#1E90FF", "t": "hola :) que tal", "e": ""}
    assert chat.parse(":x!x@x PRIVMSG #chan :\x01ACTION waves\x01") == {"n": "x", "c": "", "t": "waves", "e": "", "me": True}
    assert chat.parse(":tmi.twitch.tv 001 justinfan1 :Welcome") is None


def test_chat_sender_posts_to_helix_and_explains_missing_permission(monkeypatch):
    from openlive import chat, twitch
    rec = {"client_id": "c", "access_token": "tok", "user_id": "7", "login": "me", "expires_at": 0}
    monkeypatch.setattr(twitch, "load_auth", lambda: dict(rec))
    calls = []

    def helix(method, path, headers, body=None):
        calls.append((method, path, headers["Authorization"], body))
        if path.startswith("users"):
            return {"data": [{"id": "99"}]}
        return {"data": [{"is_sent": True}]}
    monkeypatch.setattr(chat, "_helix", helix)
    s = chat.Sender("somechan")
    assert s.send("hola") is None
    assert calls[-1] == ("POST", "chat/messages", "Bearer tok", {"broadcaster_id": "99", "sender_id": "7", "message": "hola"})
    monkeypatch.setattr(twitch, "validate", lambda tok: {"scopes": ["user:read:follows"]})
    assert chat.Sender("x", "1").ready() == "rescope"  # signed in before writing was possible
    monkeypatch.setattr(twitch, "load_auth", lambda: None)
    assert chat.Sender("x", "1").ready() == "signin"


def test_channel_key_matches_rows_and_logins(monkeypatch):
    assert player.channel_key("SomeOne") == player.channel_key({"platform": "twitch", "login": "someone"})
    assert player.channel_key({"platform": "kick", "login": "a"}) != player.channel_key({"platform": "twitch", "login": "a"})

    class Done:
        def poll(self): return 0
    monkeypatch.setitem(player.RUNNING, "twitch:gone", Done())
    assert not player.is_open("gone") and "twitch:gone" not in player.RUNNING


def test_install_plan_per_system(monkeypatch):
    which = {"brew": "/opt/homebrew/bin/brew", "winget": r"C:\winget.exe", "apt-get": "/usr/bin/apt-get"}
    monkeypatch.setattr(player.shutil, "which", lambda n: which.get(n))
    monkeypatch.setattr(player.sys, "platform", "darwin")
    assert player.install_plan()["cmd"] == ["/opt/homebrew/bin/brew", "install", "mpv"]
    assert player.install_plan(upgrade=True)["show"] == "brew upgrade mpv"
    monkeypatch.setattr(player.sys, "platform", "win32")
    plan = player.install_plan()
    assert plan["cmd"][:4] == [r"C:\winget.exe", "install", "--id", "shinchiro.mpv"]
    monkeypatch.setattr(player.sys, "platform", "linux")
    plan = player.install_plan()
    assert plan["cmd"] is None and plan["show"] == "sudo apt install mpv"  # needs a password: shown, not run
    monkeypatch.setattr(player.shutil, "which", lambda n: None)
    assert player.install_plan() == {"cmd": None, "show": None, "url": "https://mpv.io/installation/"}


def test_mpv_version(monkeypatch):
    class Out:
        stdout = "mpv v0.37.0 Copyright © 2000-2023 mpv/MPlayer/mplayer2 projects\n"
    monkeypatch.setattr(player.subprocess, "run", lambda *a, **k: Out())
    assert player.mpv_version("mpv") == (0, 37) < player.MIN_MPV
