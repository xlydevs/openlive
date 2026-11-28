"""Open a stream in the user's own video player.

With mpv, openlive uses its own mpv setup (in the data dir, the user's mpv.conf is left alone): its own control
bar, a Twitch chat sidebar, and a script that rewinds the live stream, even to before you opened it.
  Twitch   plays the recording Twitch keeps of the live stream; it grows as the stream goes on.
  Kick     plays live; going back switches to Kick's recording of the stream.
  YouTube  plays live; going back reloads it earlier, as far as the channel's DVR window allows (up to ~1 h).
Other players (IINA, VLC) get the stream through streamlink as before.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
import webbrowser
from importlib import resources
from pathlib import Path

from . import config, kick, net
from .i18n import t


def _win_paths(*parts):
    """Where Windows installers usually put a program, for when it isn't on the PATH."""
    roots = [os.environ.get(v) for v in ("LOCALAPPDATA", "ProgramFiles", "ProgramFiles(x86)", "ProgramData", "USERPROFILE")]
    return [os.path.join(r, *parts) for r in roots if r]


MPV_WIN = [*_win_paths("Microsoft", "WinGet", "Links", "mpv.exe"), *_win_paths("Programs", "mpv", "mpv.exe"),
           *_win_paths("mpv", "mpv.exe"), *_win_paths("chocolatey", "bin", "mpv.exe"), *_win_paths("scoop", "shims", "mpv.exe")]
MIN_MPV = (0, 38)  # mp.input, used to write in the chat

# name → candidate executables (first that exists wins)
PLAYERS = {
    "mpv": ["mpv", "/opt/homebrew/bin/mpv", "/usr/local/bin/mpv", "/Applications/mpv.app/Contents/MacOS/mpv",
            "/usr/bin/mpv", "/snap/bin/mpv", *(MPV_WIN if sys.platform == "win32" else [])],
    "iina": ["iina", "/Applications/IINA.app/Contents/MacOS/iina-cli"],
    "vlc": ["vlc", "/Applications/VLC.app/Contents/MacOS/VLC", r"C:\Program Files\VideoLAN\VLC\vlc.exe"],
}
# Windows: start console programs (streamlink, the chat bridge, uv's python launcher) without opening a console window
NO_WINDOW = {"creationflags": 0x08000000} if sys.platform == "win32" else {}  # CREATE_NO_WINDOW
DEFAULT_ARGS = {"mpv": "--force-window=immediate --cache=yes", "iina": "--keep-running", "vlc": ""}


MPV_CONF = """# written by openlive on every start; your own ~/.config/mpv is not used for openlive's streams
osc=no
osd-bar=no
osd-font="Helvetica Neue,Segoe UI,Noto Sans,sans-serif"
background-color="#0f1420"
force-window=immediate
keep-open=yes
cache=yes
demuxer-max-bytes={ahead}MiB
demuxer-max-back-bytes={back}MiB
demuxer-readahead-secs=60
hls-bitrate=max
"""
# Windows starts moving the window on any click mpv itself doesn't handle, even on the control bar; openlive_ui.lua
# starts the move itself when the click lands on the video
MPV_CONF_WIN = "window-dragging=no\n"
def mpv_dir():
    return config.DATA / "mpv"


def prepare_mpv():
    """openlive's mpv config dir, (re)written each time."""
    d = mpv_dir()
    (d / "scripts").mkdir(parents=True, exist_ok=True)
    (d / "script-opts").mkdir(exist_ok=True)
    mb = max(64, int(config.get("rewind_cache_mb", 1024) or 0))
    conf = MPV_CONF.format(ahead=min(mb, 400), back=mb) + (MPV_CONF_WIN if config.WIN else "")
    (d / "mpv.conf").write_text(conf)
    shutil.rmtree(d / "scripts" / "uosc", ignore_errors=True)  # earlier versions used uosc
    shutil.rmtree(d / "fonts", ignore_errors=True)
    (d / "script-opts" / "uosc.conf").unlink(missing_ok=True)
    for name in ("openlive.lua", "openlive_ui.lua"):
        (d / "scripts" / name).write_text(resources.files("openlive").joinpath(f"mpv/{name}").read_text(encoding="utf-8"), encoding="utf-8")
    for old in [*d.glob("session-*.json"), *d.glob("ipc-*")]:  # left behind if mpv never started
        if time.time() - old.stat().st_mtime > 86400:
            old.unlink(missing_ok=True)
    return d


def find_player(name=None):
    """(name, path) of the configured player (mpv unless another one is chosen). (None, None) if it isn't installed."""
    want = name or config.get("player")
    names = [want] if want else ["mpv"]  # other players only when chosen in Settings: mpv has rewind and chat
    for n in names:
        if n and (os.sep in n or "/" in n) and Path(n).exists():
            return Path(n).stem.lower(), n
        for cand in PLAYERS.get(n, [n] if n else []):
            p = shutil.which(cand) or (cand if os.path.isabs(cand) and Path(cand).exists() else None)
            if p:
                return n, p
    return None, None


def mpv_version(path):
    """(major, minor) of an mpv executable, or None when it can't be told."""
    try:
        out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=10, **NO_WINDOW).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"mpv v?(\d+)\.(\d+)", out)
    return (int(m[1]), int(m[2])) if m else None


def install_plan(upgrade=False):
    """How to get (or update) mpv on this computer: {"cmd": argv openlive can run itself or None,
    "show": the command to show and copy, or None, "url": a download page}. Commands that need sudo are only shown,
    since they ask for a password in a terminal."""
    url = "https://mpv.io/installation/"
    if sys.platform == "darwin":
        brew = shutil.which("brew") or next((b for b in ("/opt/homebrew/bin/brew", "/usr/local/bin/brew") if Path(b).exists()), None)
        if brew:
            cmd = [brew, "upgrade" if upgrade else "install", "mpv"]
            return {"cmd": cmd, "show": f"brew {cmd[1]} mpv", "url": url}
        return {"cmd": None, "show": None, "url": "https://brew.sh"}
    if sys.platform == "win32":
        if winget := shutil.which("winget"):
            verb = "upgrade" if upgrade else "install"
            cmd = [winget, verb, "--id", "shinchiro.mpv", "--exact", "--source", "winget",
                   "--accept-package-agreements", "--accept-source-agreements"]
            return {"cmd": cmd, "show": f"winget {verb} --id shinchiro.mpv --exact", "url": url}
        if scoop := shutil.which("scoop"):
            return {"cmd": [scoop, "update" if upgrade else "install", "mpv"], "show": f"scoop {'update' if upgrade else 'install'} mpv", "url": url}
        return {"cmd": None, "show": None, "url": url}
    for tool, line in (("apt-get", "sudo apt install mpv"), ("dnf", "sudo dnf install mpv"), ("pacman", "sudo pacman -S mpv"),
                       ("zypper", "sudo zypper install mpv"), ("apk", "sudo apk add mpv")):
        if shutil.which(tool):
            if upgrade:
                line = line.replace(" install ", " upgrade ").replace(" -S ", " -Syu ").replace(" add ", " upgrade ")
            return {"cmd": None, "show": line, "url": url}
    return {"cmd": None, "show": None, "url": url}


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


def build_command(target, title="", quality=None, player=None, extra_args=""):
    """streamlink → player. target: a Twitch login (str) or a row dict from any platform."""
    sl = streamlink_cmd()
    pname, ppath = find_player(player)
    if not sl or not ppath:
        return None
    url = stream_url(target)
    name = target if isinstance(target, str) else target["name"]
    args = " ".join(a for a in (extra_args, config.get("player_args", "" if extra_args else DEFAULT_ARGS.get(pname, ""))) if a)
    cmd = [*sl, url, quality or config.get("quality", "best"), "--player", ppath]
    if args:
        cmd += ["--player-args", args]
    if title:
        cmd += ["--title", f"{name} · {title}"]
    if config.get("low_latency", True) and "twitch.tv/" in url:
        cmd += ["--twitch-low-latency"]
    return cmd


# ───────────────────────── mpv with rewind ─────────────────────────

def _rank(name):
    """(height, fps) of a quality name such as '1080p60', for sorting."""
    m = re.match(r"(\d+)p(\d*)", name)
    return (int(m[1]), int(m[2] or 30)) if m else (0, 0)


def _choose(streams, quality):
    """The (name, url) to start with from a best-first list: the asked quality, or the best one up to its height."""
    if not streams:
        return None
    named = dict(streams)
    if quality in named:
        return quality, named[quality]
    if quality == "worst":
        return streams[-1]
    h = _rank(str(quality or ""))[0]
    return next((st for st in streams if h and _rank(st[0])[0] <= h), streams[0] if not h else streams[-1])


def _streams(url):
    """[(quality, HLS url)] streamlink finds for a page, best first, without its 'best'/'worst' aliases or audio."""
    sl = streamlink_cmd()
    if not sl:
        return []
    try:
        out = subprocess.run([*sl, "--json", url], capture_output=True, text=True, timeout=30, **NO_WINDOW)
        found = json.loads(out.stdout or "{}").get("streams") or {}
    except (OSError, subprocess.TimeoutExpired, ValueError, AttributeError):
        return []
    streams = [(k, v["url"]) for k, v in found.items()
               if isinstance(v, dict) and str(v.get("url", "")).startswith("http") and _rank(k)[0]]
    return sorted(streams, key=lambda st: _rank(st[0]), reverse=True)


def _variants(master):
    """[(quality, url)] of an HLS master playlist (Kick's recording), best first, named like streamlink does."""
    from urllib.parse import urljoin
    try:
        text, _ = net.fetch(master)
    except net.NetError:
        return []
    lines, out = text.splitlines(), {}
    for i, line in enumerate(lines[:-1]):
        if line.startswith("#EXT-X-STREAM-INF:") and (m := re.search(r"RESOLUTION=\d+x(\d+)", line)):
            fps = re.search(r"FRAME-RATE=([\d.]+)", line)
            out.setdefault(f"{m[1]}p{round(float(fps[1])) if fps else 30}", urljoin(master, lines[i + 1].strip()))
    return sorted(out.items(), key=lambda st: _rank(st[0]), reverse=True)


def _qualities(streams):
    return [{"name": k, "url": u} for k, u in streams]


def _hls_window(url):
    """(segment length, seconds the playlist holds) of an HLS media playlist."""
    text, _ = net.fetch(url)
    lines = text.splitlines()
    seg = next((float(x.split(":", 1)[1]) for x in lines if x.startswith("#EXT-X-TARGETDURATION:")), 5.0)
    return seg, sum(float(x[8:].split(",")[0] or 0) for x in lines if x.startswith("#EXTINF:"))


def _pick(formats, quality):
    """The format closest to a streamlink-style quality ('best', 'worst', '720p60'…) by height."""
    formats = sorted(formats, key=lambda f: (f.get("height") or 0, f.get("tbr") or 0))
    if not formats or quality in (None, "", "best"):
        return formats[-1] if formats else None
    if quality == "worst":
        return formats[0]
    try:
        h = int(str(quality).split("p")[0])
    except ValueError:
        return formats[-1]
    fit = [f for f in formats if (f.get("height") or 0) <= h]
    return fit[-1] if fit else formats[0]


def _yt_name(f):
    fps = f.get("fps") or 30
    return f"{f.get('height') or 0}p{round(fps) if fps > 30 else ''}"


def _youtube_hls(page, quality):
    """(video url, audio url or None, [(quality, video url)] best first) of a YouTube live stream. The separate
    video/audio playlists keep the channel's DVR window (up to ~1 h); the combined one streamlink uses keeps ~30 s."""
    import yt_dlp
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True, "noprogress": True}) as y:
        info = y.extract_info(page, download=False)
    fs = [f for f in info.get("formats") or [] if str(f.get("protocol", "")).startswith("m3u8") and f.get("url")]
    novideo, noaudio = (lambda f: f.get("vcodec") in (None, "none")), (lambda f: f.get("acodec") in (None, "none"))
    videos = [f for f in fs if not novideo(f) and noaudio(f)]
    audio = max((f for f in fs if novideo(f)), key=lambda f: f.get("tbr") or f.get("abr") or 0, default=None)
    if not (videos and audio):
        videos, audio = [f for f in fs if not novideo(f) and not noaudio(f)], None
    video = _pick(videos, quality)
    if not video:
        return None, None, []
    best = {}
    for f in sorted(videos, key=lambda f: f.get("tbr") or 0):  # one per quality name, the highest bitrate
        if f.get("height"):
            best[_yt_name(f)] = f["url"]
    streams = sorted(best.items(), key=lambda st: _rank(st[0]), reverse=True)
    return video["url"], audio and audio["url"], streams


def session_for(r, client=None, quality="best"):
    """What openlive's mpv script needs to rewind this stream (and change its quality), or None to play it through
    streamlink."""
    plat = r.get("platform", "twitch")
    if plat == "twitch":
        if not client or not r.get("user_id"):
            return None
        vod = client.current_vod(r["user_id"], r.get("started_at", ""))
        streams = _streams(vod) if vod else []
        pick = _choose(streams, quality)
        if not pick:
            return None
        return {"platform": "twitch", "mode": "vod", "url": pick[1], "start": "-6", "quality": pick[0],
                "qualities": _qualities(streams)}
    if plat == "kick":
        streams = _streams(stream_url(r))
        pick = _choose(streams, quality)
        if not pick:
            return None
        try:
            vod = kick.current_vod(r["login"])
        except net.NetError:
            vod = None
        return {"platform": "kick", "mode": "live", "url": pick[1], "live": pick[1], "vod": vod, "quality": pick[0],
                "qualities": _qualities(streams), "vod_qualities": _qualities(_variants(vod)) if vod else []}
    live, audio, streams = _youtube_hls(stream_url(r), quality)
    if not live:
        return None
    try:
        seg, dvr = _hls_window(live)
    except (net.NetError, ValueError):
        seg, dvr = 5.0, 0
    name = next((k for k, u in streams if u == live), "")
    return {"platform": "youtube", "mode": "live", "url": live, "live": live, "audio": audio, "seg": seg, "dvr": dvr,
            "quality": name, "qualities": _qualities(streams)}


def _session_file(d, sess):
    sess["text"] = {"live": t("LIVE"), "rewind": t("Going back…"), "no_more": t("This stream can't go back further."),
                    "chat": t("Chat"), "hide": t("hide"), "chat_connecting": t("Connecting to the chat…"),
                    "chat_quiet": t("Nobody has written yet."), "chat_offline": t("Can't reach the chat, retrying…"),
                    "write": t("Write"), "say": t("Say"), "paused": t("Chat paused"), "new_msgs": t("{n} new messages"),
                    "chat_signin": t("To write, sign in to Twitch in openlive (press l there)."),
                    "chat_rescope": t("To write, sign in to Twitch again in openlive (press l there)."),
                    "chat_not_sent": t("Not sent: {why}"), "chat_no_input": t("Writing needs mpv 0.38 or newer."),
                    "play": t("Play"), "pause": t("Pause"), "back10": t("Back 10 s"), "fwd10": t("Forward 10 s"),
                    "mute": t("Mute"), "unmute": t("Unmute"), "go_live": t("Go live"), "loading": t("Loading…"),
                    "fullscreen": t("Full screen"), "open_chat": t("Open chat"), "close_chat": t("Close chat"),
                    "quality": t("Quality"), "quality_set": t("Quality: {q}")}
    path = d / f"session-{os.getpid()}-{time.time_ns()}.json"
    path.write_text(json.dumps(sess))
    return path


def _ipc_path(d):
    name = f"ipc-{os.getpid()}-{time.time_ns() % 10**9}"
    return rf"\\.\pipe\openlive-{name}" if config.WIN else str(d / name)


def _with_ui(sess, target, title):
    """Add what the interface shows: channel, title, and the Twitch chat (only Twitch for now)."""
    sess.update(channel=target.get("name", ""), title=title or "", chat_on=bool(config.get("chat_open", False)),
                chat=target.get("login", "") if target.get("platform", "twitch") == "twitch" else "",
                chat_id=target.get("user_id", ""))
    return sess


def mpv_command(ppath, sess, title, ipc=None):
    d = prepare_mpv()
    cmd = [ppath, f"--config-dir={d}", f"--script-opts=openlive-session={_session_file(d, sess)}"]
    if ipc:
        cmd.append(f"--input-ipc-server={ipc}")
    if title:
        cmd += [f"--force-media-title={title}", f"--title={title}"]
    if sess.get("start"):
        cmd.append(f"--start={sess['start']}")
    if sess.get("audio"):
        cmd.append(f"--audio-file={sess['audio']}")
    if args := config.get("player_args"):
        cmd += args.split()
    return [*cmd, "--", sess["url"]]


def command_for(target, title="", client=None):
    """(command, chat bridge command or None) for this stream, picking openlive's mpv with rewind when it can."""
    pname, ppath = find_player()
    name = target if isinstance(target, str) else target.get("name", "")
    full = f"{name} · {title}" if title else name
    if pname != "mpv" or config.get("player_ui", "openlive") == "plain" or isinstance(target, str):
        return build_command(target, title), None
    sess = None
    if config.get("rewind", True):
        try:
            sess = session_for(target, client, config.get("quality", "best"))
        except Exception:  # any platform hiccup: play it the plain way
            sess = None
    sess = _with_ui(sess or {"platform": target.get("platform", "twitch"), "mode": "pipe"}, target, title)
    d = prepare_mpv()
    ipc = _ipc_path(d) if sess["chat"] else None
    bridge = [sys.executable, "-m", "openlive.chat", ipc, sess["chat"], sess.get("chat_id") or ""] if ipc else None
    if sess["mode"] != "pipe":
        return mpv_command(ppath, sess, full, ipc), bridge
    extra = f'"--config-dir={d}" "--script-opts=openlive-session={_session_file(d, sess)}"'
    if ipc:
        extra += f' "--input-ipc-server={ipc}"'
    return build_command(target, title, extra_args=extra), bridge


RUNNING = {}  # channel key → the player process openlive started for it


def channel_key(target):
    """'platform:channel' for a row or a Twitch login, so the same streamer is recognised on any tab."""
    if isinstance(target, str):
        return f"twitch:{target.lower()}"
    ch = target.get("login") or target.get("channel_id") or target.get("name") or ""
    return f"{target.get('platform', 'twitch')}:{str(ch).lower()}"


def is_open(target):
    """True while a player openlive started for this streamer is still running."""
    proc = RUNNING.get(channel_key(target))
    if proc is not None and proc.poll() is None:
        return True
    RUNNING.pop(channel_key(target), None)
    return False


def play(target, title="", client=None):
    """Start the player detached. target: Twitch login or a row. Returns (ok, message_key). Can block a few
    seconds (it asks the platform for the stream address), so call it from a worker thread."""
    cmd, bridge = command_for(target, title, client)
    if cmd is None:
        return False, "no-player" if streamlink_cmd() else "no-streamlink"
    log = None
    if not config.OFFLINE:
        config.DATA.mkdir(parents=True, exist_ok=True)
        log = open(config.DATA / "player.log", "ab")  # noqa: SIM115 (handed to the child)
    # Windows: CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP. Not DETACHED_PROCESS: uv's python.exe is a launcher, and
    # the real python it starts would then open a console window of its own
    kw = {"creationflags": 0x08000000 | 0x00000200} if config.WIN else {"start_new_session": True}
    try:
        RUNNING[channel_key(target)] = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log or subprocess.DEVNULL,
                                                        stderr=subprocess.STDOUT, **kw)
        if bridge:  # waits for mpv's socket, ends when mpv closes
            subprocess.Popen(bridge, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=log or subprocess.DEVNULL, **kw)
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
