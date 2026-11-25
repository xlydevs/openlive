"""Open a stream in the user's own video player through streamlink."""
import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

from . import config

# name → candidate executables (first that exists wins)
PLAYERS = {
    "mpv": ["mpv", "/opt/homebrew/bin/mpv", "/usr/local/bin/mpv", "/Applications/mpv.app/Contents/MacOS/mpv"],
    "iina": ["iina", "/Applications/IINA.app/Contents/MacOS/iina-cli"],
    "vlc": ["vlc", "/Applications/VLC.app/Contents/MacOS/VLC", r"C:\Program Files\VideoLAN\VLC\vlc.exe"],
}
DEFAULT_ARGS = {"mpv": "--force-window=immediate --cache=yes", "iina": "--keep-running", "vlc": ""}


def find_player(name=None):
    """(name, path) of the configured player, or the first one installed. (None, None) if none."""
    want = name or config.get("player")
    names = [want] if want else list(PLAYERS)
    for n in names:
        if n and (os.sep in n or "/" in n) and Path(n).exists():
            return Path(n).stem.lower(), n
        for cand in PLAYERS.get(n, [n] if n else []):
            p = shutil.which(cand) or (cand if os.path.isabs(cand) and Path(cand).exists() else None)
            if p:
                return n, p
    return None, None


def streamlink_cmd():
    try:
        import streamlink  # noqa: F401
        return [sys.executable, "-m", "streamlink"]
    except ImportError:
        exe = shutil.which("streamlink")
        return [exe] if exe else None


def stream_url(row_or_channel):
    if isinstance(row_or_channel, str):
        return f"https://twitch.tv/{row_or_channel}"
    r = row_or_channel
    if r.get("play_url"):
        return r["play_url"]
    return {"kick": f"https://kick.com/{r['login']}", "youtube": f"https://www.youtube.com/{_yt_path(r['login'])}/live"}.get(
        r.get("platform"), f"https://twitch.tv/{r['login']}")


def _yt_path(ch):
    return ch if ch.startswith("@") else f"channel/{ch}"


def build_command(target, title="", quality=None, player=None):
    """target: a Twitch login (str) or a row dict from any platform."""
    sl = streamlink_cmd()
    pname, ppath = find_player(player)
    if not sl or not ppath:
        return None
    url = stream_url(target)
    name = target if isinstance(target, str) else target["name"]
    args = config.get("player_args", DEFAULT_ARGS.get(pname, ""))
    cmd = [*sl, url, quality or config.get("quality", "best"), "--player", ppath]
    if args:
        cmd += ["--player-args", args]
    if title:
        cmd += ["--title", f"{name} · {title}"]
    if config.get("low_latency", True) and "twitch.tv/" in url:
        cmd += ["--twitch-low-latency"]
    return cmd


def play(target, title=""):
    """Start the player detached. target: Twitch login or a row. Returns (ok, message_key)."""
    cmd = build_command(target, title)
    if cmd is None:
        return False, "no-player" if streamlink_cmd() else "no-streamlink"
    log = None
    if not config.OFFLINE:
        config.DATA.mkdir(parents=True, exist_ok=True)
        log = open(config.DATA / "player.log", "ab")  # noqa: SIM115 (handed to the child)
    kw = {"creationflags": 0x00000008} if config.WIN else {"start_new_session": True}  # DETACHED_PROCESS
    try:
        subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log or subprocess.DEVNULL, stderr=subprocess.STDOUT, **kw)
    except OSError:
        return False, "no-player"
    finally:
        if log: log.close()
    return True, "ok"


def web_url(r):
    if isinstance(r, str):
        return f"https://www.twitch.tv/{r}"
    if r.get("platform") == "kick":
        return f"https://kick.com/{r['login']}"
    if r.get("platform") == "youtube":
        return f"https://www.youtube.com/watch?v={r['video_id']}" if r.get("video_id") else f"https://www.youtube.com/{_yt_path(r['login'])}"
    return f"https://www.twitch.tv/{r['login']}"


def chat_url(r):
    if isinstance(r, str):
        return f"https://www.twitch.tv/popout/{r}/chat?popout="
    if r.get("platform") == "kick":
        return f"https://kick.com/popout/{r['login']}/chat"
    if r.get("platform") == "youtube":
        return f"https://www.youtube.com/live_chat?v={r['video_id']}" if r.get("video_id") else None
    return f"https://www.twitch.tv/popout/{r['login']}/chat?popout="


def open_web(r):
    webbrowser.open(web_url(r))


def open_chat(r):
    if url := chat_url(r):
        webbrowser.open(url)
