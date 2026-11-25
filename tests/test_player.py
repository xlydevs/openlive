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
