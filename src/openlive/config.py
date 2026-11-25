"""Paths, user config and small persistent files.

Config file (optional): ~/.config/openlive/config.toml (Windows: %APPDATA%\\openlive\\config.toml),
or the path in $OPENLIVE_CONFIG. See config.example.toml.
Data (sign-in token, favourites, cache): ~/.local/share/openlive (Windows: %LOCALAPPDATA%\\openlive),
or $OPENLIVE_DATA_DIR.
"""
import json
import os
import sys
import tomllib
from pathlib import Path

APP = "openlive"
WIN = sys.platform == "win32"

# Client ID of the openlive app registered on dev.twitch.tv (type "Public": it has no secret,
# so it is fine to ship). Users can bring their own with `client_id` in the config or $OPENLIVE_CLIENT_ID.
DEFAULT_CLIENT_ID = ""


def _xdg(var, fallback):
    base = os.environ.get(var)
    return Path(base) if base else Path.home() / fallback


def default_data_dir():
    if os.environ.get("OPENLIVE_DATA_DIR"):
        return Path(os.environ["OPENLIVE_DATA_DIR"]).expanduser()
    if WIN and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / APP
    return _xdg("XDG_DATA_HOME", ".local/share") / APP


def config_path():
    if os.environ.get("OPENLIVE_CONFIG"):
        return Path(os.environ["OPENLIVE_CONFIG"]).expanduser()
    if WIN and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / APP / "config.toml"
    return _xdg("XDG_CONFIG_HOME", ".config") / APP / "config.toml"


def load_config(path=None):
    path = path or config_path()
    if not path.exists():
        return {}
    try:
        with open(path, "rb") as fh:
            return tomllib.load(fh)
    except (OSError, ValueError) as e:
        print(f"openlive: ignoring {path}: {e}", file=sys.stderr)
        return {}


CONFIG = load_config()
DATA = default_data_dir()
OFFLINE = False  # demo mode: no network, nothing read or written


def set_data_dir(path):
    global DATA
    DATA = Path(path)


def get(key, default=None):
    return CONFIG.get(key, default)


def client_id():
    return os.environ.get("OPENLIVE_CLIENT_ID") or CONFIG.get("client_id") or DEFAULT_CLIENT_ID


def refresh_seconds():
    try:
        return max(15, int(CONFIG.get("refresh", 60)))
    except (TypeError, ValueError):
        return 60


# ── small JSON files in the data dir ──

def read_json(name, default=None):
    try:
        return json.loads((DATA / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(name, obj, private=False):
    if OFFLINE:
        return
    DATA.mkdir(parents=True, exist_ok=True)
    path = DATA / name
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=1), encoding="utf-8")
    if private and not WIN:
        os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def delete(name):
    try:
        (DATA / name).unlink()
    except OSError:
        pass


def favourites():
    return set(read_json("favourites.json", []) or [])


def save_favourites(names):
    write_json("favourites.json", sorted(names))
