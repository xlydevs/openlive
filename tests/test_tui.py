import pytest

from openlive import config, i18n, onboard, twitch


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
        assert live.shown and live.shown[0]["login"] in app.favs  # favourites first
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
        assert [r["login"] for r in p.shown] == sorted(r["login"] for r in p.rows)


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
