from openlive import __version__, config, net, updater
from openlive.updater import latest as real_latest


def test_latest_is_read_from_github_and_cached(monkeypatch):
    monkeypatch.setattr(updater, "latest", real_latest)
    calls = []

    def fetch(url, headers=None, timeout=15):
        calls.append(url)
        return '"""openlive"""\n__version__ = "99.0.1"\n', url
    monkeypatch.setattr(net, "fetch", fetch)
    assert updater.newer() == "99.0.1"
    assert updater.newer() == "99.0.1" and len(calls) == 1  # cached for a few hours
    assert config.read_json(updater.STATE)["version"] == "99.0.1"


def test_no_update_when_same_or_offline(monkeypatch):
    monkeypatch.setattr(updater, "latest", real_latest)
    monkeypatch.setattr(net, "fetch", lambda url, headers=None, timeout=15: (f'__version__ = "{__version__}"', url))
    assert updater.newer(force=True) is None

    def down(*a, **k):
        raise net.NetError("network: down")
    monkeypatch.setattr(net, "fetch", down)
    assert updater.newer(force=True) is None  # the last known version, which is ours


def test_version_order():
    assert updater.parse("0.10.0") > updater.parse("0.9.3") > updater.parse("0.9")


def test_source_installs_only_update_by_hand():
    assert not updater.installed_from_github()  # tests run from an editable checkout
    assert "install." in updater.manual_command()


def test_update_runs_uv(monkeypatch):
    monkeypatch.setattr(config, "WIN", False)
    monkeypatch.setattr(updater, "uv_path", lambda: "/bin/uv")
    seen = []

    class Done:
        returncode = 0
    monkeypatch.setattr(updater.subprocess, "run", lambda cmd, **k: seen.append(cmd) or Done())
    assert updater.update() == "done"
    assert seen[0][:3] == ["/bin/uv", "tool", "install"] and seen[0][-1].endswith("main.tar.gz")


def test_how_installed_picks_the_update_command(monkeypatch):
    monkeypatch.setattr(updater, "uv_path", lambda: "uv")
    monkeypatch.setattr(updater, "how_installed", lambda: "uv")
    assert updater.can_update() and updater.command() == ["uv", "tool", "upgrade", "openlive"]
    monkeypatch.setattr(updater, "how_installed", lambda: "github")
    assert updater.can_update() and updater.command()[-1].startswith("openlive @ https://github.com/")
    monkeypatch.setattr(updater, "how_installed", lambda: "pipx")
    assert not updater.can_update() and updater.manual_command() == "pipx upgrade openlive"
    monkeypatch.setattr(updater, "how_installed", lambda: "pip")
    assert updater.manual_command() == "pip install --upgrade openlive"
