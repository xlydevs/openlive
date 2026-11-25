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
DEFAULT_CLIENT_ID = "1rld97h4g34kqyaqbe1ika9i13mndl"


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


def youtube_api_key():
    return os.environ.get("OPENLIVE_YOUTUBE_KEY") or (CONFIG.get("youtube") or {}).get("api_key") or ""


def enabled_platforms():
    """Platforms chosen in the first-run picker ([platforms] enabled), or None if it was never shown."""
    v = (CONFIG.get("platforms") or {}).get("enabled")
    return [p for p in v if isinstance(p, str)] if isinstance(v, list) else None


def _toml(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_toml(x) for x in v) + "]"
    return json.dumps(str(v), ensure_ascii=False)


def save_setting(key, value, section=None, path=None):
    """Set one key in config.toml (top level, or in [section]) keeping the rest of the file as it is.
    value None removes the key."""
    target = CONFIG.setdefault(section, {}) if section else CONFIG
    if value is None:
        target.pop(key, None)
    else:
        target[key] = value
    if OFFLINE:
        return
    path = path or config_path()
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    line = None if value is None else f"{key} = {_toml(value)}"
    sec, start, insert_at = None, None, None
    found = None
    for i, ln in enumerate(lines):
        st = ln.strip()
        if st.startswith("[") and st.endswith("]"):
            if sec == section and insert_at is None:
                insert_at = i
            sec = st.strip("[]").strip()
            if sec == section:
                start = i
            continue
        if sec == section and not st.startswith("#") and st.split("=")[0].strip() == key and "=" in st:
            found = i
            break
    if found is not None:
        if line is None:
            del lines[found]
        else:
            lines[found] = line
    elif line is not None:
        if section is None:
            first = next((i for i, ln in enumerate(lines) if ln.strip().startswith("[")), len(lines))
            while first > 0 and not lines[first - 1].strip():
                first -= 1
            lines.insert(first, line)
        elif start is None:
            lines += (["", f"[{section}]"] if lines else [f"[{section}]"]) + [line]
        else:
            j = len(lines) if insert_at is None else insert_at
            while j > start + 1 and not lines[j - 1].strip():
                j -= 1
            lines.insert(j, line)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def save_platforms(names, path=None):
    """Write [platforms] enabled = [...] keeping the rest of the file as it is."""
    save_setting("enabled", list(names), "platforms", path)
