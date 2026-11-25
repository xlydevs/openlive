import pytest

from openlive import config, google, i18n, net, twitch


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Every test gets its own data dir, no config file, no network and English."""
    monkeypatch.setattr(config, "DATA", tmp_path / "data")
    monkeypatch.setattr(config, "CONFIG", {})
    monkeypatch.setattr(config, "OFFLINE", False)
    for var in ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "APPDATA", "LOCALAPPDATA", "OPENLIVE_CLIENT_ID", "OPENLIVE_LANG"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("OPENLIVE_CONFIG", str(tmp_path / "config.toml"))
    monkeypatch.setattr(config, "DEFAULT_CLIENT_ID", "test-client")

    def no_network(*a, **kw):
        raise AssertionError("tests must not touch the network")
    monkeypatch.setattr(twitch, "_request", no_network)
    monkeypatch.setattr(google, "_request", no_network)
    monkeypatch.setattr(net, "fetch", no_network)
    i18n.set_lang("en")
    yield tmp_path
