"""Updates: is there a newer openlive on GitHub, and install it in the background.

A new version is out when __version__ on the main branch is higher than ours. Installs made by install.sh /
install.ps1 (uv tool, from the GitHub archive) update themselves; any other install gets the command to run.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from importlib import metadata
from pathlib import Path

from . import __version__, config, net

REPO = "https://github.com/xlydevs/openlive"
VERSION_URL = "https://raw.githubusercontent.com/xlydevs/openlive/main/src/openlive/__init__.py"
CHECK_EVERY = 3600  # while openlive is open; every start checks right away
STATE = "update.json"


def parse(v):
    return tuple(int(x) for x in re.findall(r"\d+", v or "")[:3])


def source():
    return f"{REPO}/archive/refs/heads/main.{'zip' if config.WIN else 'tar.gz'}"


def latest(force=False):
    """The version on GitHub (checked at most once an hour unless forced), or None when it can't be told."""
    state = config.read_json(STATE) or {}
    if not force and time.time() - state.get("checked", 0) < CHECK_EVERY:
        return state.get("version")
    try:
        text, _ = net.fetch(VERSION_URL, timeout=10)
    except net.NetError:
        return state.get("version")
    m = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    if not m:
        return state.get("version")
    config.write_json(STATE, {"checked": time.time(), "version": m[1]})
    return m[1]


def newer(force=False):
    """The newer version's number, or None when this one is the latest."""
    v = latest(force)
    return v if v and parse(v) > parse(__version__) else None


def uv_path():
    exe = "uv.exe" if config.WIN else "uv"
    return shutil.which("uv") or next((str(p) for p in (Path.home() / ".local" / "bin" / exe, Path.home() / ".cargo" / "bin" / exe)
                                       if p.exists()), None)


def installed_from_github():
    """True for installs made by openlive's installers: a uv tool from the GitHub archive (not editable, not pipx)."""
    try:
        info = json.loads(metadata.distribution("openlive").read_text("direct_url.json") or "{}")
    except (metadata.PackageNotFoundError, ValueError, OSError):
        return False
    return info.get("url", "").startswith(f"{REPO}/archive/") and "uv" in Path(sys.prefix).parts


def command():
    return [uv_path() or "uv", "tool", "install", "--force", "--python", "3.12", "--refresh-package", "openlive",
            "--reinstall-package", "openlive", f"openlive @ {source()}"]


def manual_command():
    """What to run by hand when openlive can't update itself."""
    if config.WIN:
        return "irm https://raw.githubusercontent.com/xlydevs/openlive/main/install.ps1 | iex"
    return "curl -LsSf https://raw.githubusercontent.com/xlydevs/openlive/main/install.sh | sh"


def can_update():
    return installed_from_github() and uv_path() is not None


def update():
    """Install the latest version without showing anything. Returns "done", "on_exit" (Windows: it can't replace
    openlive while it runs, so a hidden helper waits for openlive to close and updates then) or "failed"."""
    cmd = command()
    if config.WIN:
        args = " ".join("'" + a.replace("'", "''") + "'" for a in cmd[1:])
        script = f"Wait-Process -Id {os.getpid()} -ErrorAction SilentlyContinue; & '{cmd[0]}' {args} *> $null"
        try:
            subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=0x00000008 | 0x08000000)  # DETACHED_PROCESS | CREATE_NO_WINDOW
        except OSError:
            return "failed"
        return "on_exit"
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=600, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return "failed"
    return "done" if out.returncode == 0 else "failed"
