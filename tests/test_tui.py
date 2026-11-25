import pytest

from openlive import channels, config, i18n, kick, onboard, twitch


@pytest.mark.parametrize("lang", ["en", "es"])
@pytest.mark.parametrize("size", [(160, 48), (80, 40)])
async def test_tui_demo_smoke(lang, size):
    config.OFFLINE = True
    i18n.set_lang(lang)
    from openlive.tui import make_app
    app = make_app(demo_mode=True)
    async with app.run_test(size=size) as pilot:
        await pilot.pause(0.2)
        live = app.pane("live")
        assert live.shown and channels.row_key(live.shown[0]) in app.favs  # favourites first
        assert {r["platform"] for r in live.shown} == {"twitch", "kick", "youtube"}
        await pilot.press("k")  # hide Kick
        assert all(r["platform"] != "kick" for r in live.shown)
        await pilot.press("k")
        await pilot.press("a")
        await pilot.pause(0.1)
        assert isinstance(app.screen, onboard.AddChannelScreen)
        await pilot.press("escape")
        for key in ("2", "3", "4", "1"):
            await pilot.press(key)
            await pilot.pause(0.1)
        await pilot.press("down", "f")
        await pilot.press("slash", *"chess", "escape")
        await pilot.press("4", "slash", *"pixel", "enter")
        await pilot.pause(0.3)
        assert [r["login"] for r in app.pane("search").rows] == ["pixelharbor"]
        await pilot.press("1", "enter")
        await pilot.pause(0.1)


async def test_header_click_sorts():
    config.OFFLINE = True
    from openlive.tui import make_app
    app = make_app(demo_mode=True)
    async with app.run_test(size=(160, 48)) as pilot:
        await pilot.pause(0.2)
        p = app.pane("live")
        p.on_data_table_header_selected(type("E", (), {"column_key": type("K", (), {"value": "name"})()})())
        assert [r["name"].lower() for r in p.shown] == sorted(r["name"].lower() for r in p.rows)


async def test_first_run_opens_sign_in(monkeypatch):
    shown = {}

    def fake(url, data=None, headers=None, timeout=15):
        if url.endswith("/device"):
            return {"device_code": "dc", "user_code": "WXYZ5678", "verification_uri": "https://www.twitch.tv/activate?d", "interval": 1,
                    "expires_in": 60}
        if url.endswith("/token"):
            raise twitch.TwitchError("authorization_pending", 400)
        raise AssertionError(url)
    monkeypatch.setattr(twitch, "_request", fake)
    monkeypatch.setattr(onboard.webbrowser, "open", lambda url: shown.setdefault("url", url))
    config.CONFIG["platforms"] = {"enabled": ["twitch"]}
    from openlive.tui import make_app
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.5)
        assert isinstance(app.screen, onboard.LoginScreen)
        assert "WXYZ5678" in str(app.screen.query_one("#code").render())
        await pilot.press("o")
        assert shown["url"].startswith("https://www.twitch.tv/activate")
        await pilot.press("escape")
        await pilot.pause(0.1)
        assert not isinstance(app.screen, onboard.LoginScreen)
        assert app.auth is None


async def test_first_run_picks_platforms_and_adds_kick_channel(monkeypatch, tmp_path):
    monkeypatch.setattr(kick, "resolve", lambda text: {"id": kick.parse(text), "name": "SomeOne"})
    monkeypatch.setattr(kick, "check", lambda slugs: ([{"platform": "kick", "login": s, "name": "SomeOne", "live": True, "viewers": 5,
                                                         "game": "Chess", "title": "hi", "started_at": "", "language": "", "tags": []}
                                                        for s in slugs], []))
    from openlive.tui import make_app
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.3)
        assert isinstance(app.screen, onboard.PlatformsScreen)
        sel = app.screen.query_one("#platforms")
        sel.deselect_all()
        sel.select("kick")
        await pilot.click("#save")
        await pilot.pause(0.3)
        assert app.platforms == ["kick"]
        assert isinstance(app.screen, onboard.AddChannelScreen)  # Kick list is empty: ask for channels
        app.screen.query_one("#add-input").value = "kick.com/someone"
        await pilot.press("enter")
        await pilot.pause(0.5)
        await pilot.press("escape")
        await pilot.pause(0.5)
        assert channels.load()["kick"] == [{"id": "someone", "name": "SomeOne"}]
        assert [r["login"] for r in app.pane("live").shown] == ["someone"]
    assert 'enabled = ["kick"]' in (tmp_path / "config.toml").read_text()


async def test_add_dialog_kick_search(tmp_path):
    from openlive import channels, onboard
    from openlive.tui import make_app
    app = make_app(True)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.3)
        await pilot.press("a")
        await pilot.pause(0.2)
        assert isinstance(app.screen, onboard.AddChannelScreen)
        await pilot.press(*"ember")
        await pilot.pause(0.8)
        assert [r["id"] for r in app.screen.results][:2] == ["emberfox", "emberfox_clips"]
        await pilot.press("down", "enter")
        await pilot.pause(0.2)
        assert channels.load()["kick"] == [{"id": "emberfox_clips", "name": "EmberFoxClips"}]


async def test_first_run_youtube_offers_google_sign_in(tmp_path, monkeypatch):
    from openlive import config, google, onboard
    from openlive.tui import make_app
    monkeypatch.setattr(config, "CONFIG", {"platforms": {"enabled": ["youtube"]}})
    monkeypatch.setattr(google, "start_device_login", lambda: {"device_code": "d", "user_code": "ABC-DEF", "verification_uri": "https://www.google.com/device", "interval": 30})
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.5)
        assert isinstance(app.screen, onboard.LoginScreen) and app.screen.provider == "google"
        assert "ABC-DEF" in str(app.screen.query_one("#code").render())
        await pilot.press("escape")  # skip: then it asks for channels by hand
        await pilot.pause(0.3)
        assert isinstance(app.screen, onboard.AddChannelScreen)


async def test_add_dialog_hides_youtube_when_signed_in_to_google():
    from openlive import onboard
    from openlive.tui import make_app
    app = make_app(True)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.3)
        app.gauth = {"name": "Me"}
        await pilot.press("a")
        await pilot.pause(0.2)
        assert isinstance(app.screen, onboard.AddChannelScreen)
        assert app.screen.platforms == ["kick"] and not app.screen.query_one("#add-platform").display


async def test_settings_tab_saves_options(tmp_path, monkeypatch):
    from openlive import config, settings
    from openlive.tui import make_app
    monkeypatch.setattr(config, "CONFIG", {"platforms": {"enabled": ["kick"]}})
    from openlive import channels as ch
    ch.save({"kick": [{"id": "emberfox", "name": "EmberFox"}], "youtube": []})
    monkeypatch.setattr(kick, "check", lambda slugs: ([], []))
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.3)
        await pilot.press("5")
        await pilot.pause(0.2)
        assert app.current == "settings"
        pane = app.query_one(settings.SettingsPane)
        pane.query_one("#set-rewind").value = False
        await pilot.pause(0.1)
        await pilot.click("#kick-remove")
        await pilot.pause(0.2)
    text = (tmp_path / "config.toml").read_text()
    assert "rewind = false" in text
    assert ch.load()["kick"] == []
