"""Open a stream in the user's own video player.

With mpv, openlive uses its own mpv setup (in the data dir, the user's mpv.conf is left alone): the uosc
interface and a small script that rewinds the live stream, even to before you opened it, and jumps back to live.
  Twitch   plays the recording Twitch keeps of the live stream; it grows as the stream goes on.
  Kick     plays live; going back switches to Kick's recording of the stream.
  YouTube  plays live; going back reloads it earlier, as far as the channel's DVR window allows (up to ~1 h).
Other players (IINA, VLC) get the stream through streamlink as before.
"""
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser
import zipfile
from importlib import resources
from pathlib import Path

from . import config, kick, net
from .i18n import t

# name → candidate executables (first that exists wins)
PLAYERS = {
    "mpv": ["mpv", "/opt/homebrew/bin/mpv", "/usr/local/bin/mpv", "/Applications/mpv.app/Contents/MacOS/mpv"],
    "iina": ["iina", "/Applications/IINA.app/Contents/MacOS/iina-cli"],
    "vlc": ["vlc", "/Applications/VLC.app/Contents/MacOS/VLC", r"C:\Program Files\VideoLAN\VLC\vlc.exe"],
}
DEFAULT_ARGS = {"mpv": "--force-window=immediate --cache=yes", "iina": "--keep-running", "vlc": ""}


UOSC_VERSION = "5.13.0"
UOSC_URL = f"https://github.com/tomasklaen/uosc/releases/download/{UOSC_VERSION}/uosc.zip"
UOSC_SHA256 = "4be9da3289285300fa374496c3f1bfd7bb20ac08e890d25bd5a06b28eebe4882"

MPV_CONF = """# written by openlive on every start; your own ~/.config/mpv is not used for openlive's streams
osc=no
osd-bar=no
force-window=immediate
keep-open=yes
cache=yes
demuxer-max-bytes={ahead}MiB
demuxer-max-back-bytes={back}MiB
demuxer-readahead-secs=60
hls-bitrate=max
"""
UOSC_CONTROLS = ("menu,gap,command:replay_10:script-binding openlive/back?{back},"
                 "command:forward_10:script-binding openlive/forward?{fwd},gap,<stream>stream-quality,space,"
                 "command:radio_button_checked:script-binding openlive/live?{live},gap,fullscreen")
UOSC_CONF = "# written by openlive\ncontrols=" + UOSC_CONTROLS + "\ntimeline_persistency=paused\n"


def mpv_dir():
    return config.DATA / "mpv"


def _install_uosc(d):
    """Download the pinned uosc release once (checked against its hash) into openlive's mpv dir."""
    req = urllib.request.Request(UOSC_URL, headers={"User-Agent": net.UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        blob = r.read()
    if hashlib.sha256(blob).hexdigest() != UOSC_SHA256:
        raise OSError("uosc download doesn't match its checksum")
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        for name in z.namelist():
            target = (d / name).resolve()
            if not name.startswith(("scripts/", "fonts/")) or d.resolve() not in target.parents:
                continue
            if name.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(z.read(name))
                if "/bin/" in name:
                    target.chmod(0o755)
    (d / "scripts" / "uosc" / ".openlive-version").write_text(UOSC_VERSION)


def prepare_mpv():
    """openlive's mpv config dir, (re)written each time. uosc is optional: without it mpv's own OSC is used."""
    d = mpv_dir()
    (d / "scripts").mkdir(parents=True, exist_ok=True)
    (d / "script-opts").mkdir(exist_ok=True)
    mb = max(64, int(config.get("rewind_cache_mb", 1024) or 0))
    conf = MPV_CONF.format(ahead=min(mb, 400), back=mb)
    ver = d / "scripts" / "uosc" / ".openlive-version"
    if config.get("player_ui", "openlive") == "openlive" and not (ver.exists() and ver.read_text() == UOSC_VERSION):
        try:
            _install_uosc(d)
        except (OSError, zipfile.BadZipFile, ValueError):
            pass
    if not (d / "scripts" / "uosc" / "main.lua").exists():
        conf = conf.replace("osc=no\nosd-bar=no\n", "")
    (d / "mpv.conf").write_text(conf)
    (d / "script-opts" / "uosc.conf").write_text(UOSC_CONF.format(back=t("Back 10 s"), fwd=t("Forward 10 s"), live=t("Back to live")))
    (d / "scripts" / "openlive.lua").write_text(resources.files("openlive").joinpath("mpv/openlive.lua").read_text())
    for old in d.glob("session-*.json"):  # left behind if mpv never started
        if time.time() - old.stat().st_mtime > 86400:
            old.unlink(missing_ok=True)
    return d


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

def _direct_url(url, quality):
    """The HLS address streamlink finds for a page, so mpv can open (and seek) it itself."""
    sl = streamlink_cmd()
    if not sl:
        return None
    for q in dict.fromkeys((quality, "best")):
        try:
            out = subprocess.run([*sl, "--stream-url", url, q], capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            return None
        lines = out.stdout.strip().splitlines()
        if out.returncode == 0 and lines and lines[-1].startswith("http"):
            return lines[-1]
    return None


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


def _youtube_hls(page, quality):
    """(video url, audio url or None) of a YouTube live stream. The separate video/audio playlists keep the
    channel's DVR window (up to ~1 h); the combined one streamlink uses keeps only ~30 s."""
    import yt_dlp
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True, "noprogress": True}) as y:
        info = y.extract_info(page, download=False)
    fs = [f for f in info.get("formats") or [] if str(f.get("protocol", "")).startswith("m3u8") and f.get("url")]
    novideo, noaudio = (lambda f: f.get("vcodec") in (None, "none")), (lambda f: f.get("acodec") in (None, "none"))
    video = _pick([f for f in fs if not novideo(f) and noaudio(f)], quality)
    audio = max((f for f in fs if novideo(f)), key=lambda f: f.get("tbr") or f.get("abr") or 0, default=None)
    if video and audio:
        return video["url"], audio["url"]
    both = _pick([f for f in fs if not novideo(f) and not noaudio(f)], quality)
    return (both["url"], None) if both else (None, None)


def session_for(r, client=None, quality="best"):
    """What openlive's mpv script needs to rewind this stream, or None to play it through streamlink."""
    plat = r.get("platform", "twitch")
    if plat == "twitch":
        if not client or not r.get("user_id"):
            return None
        vod = client.current_vod(r["user_id"], r.get("started_at", ""))
        url = vod and _direct_url(vod, quality)
        return {"platform": "twitch", "mode": "vod", "url": url, "start": "-6"} if url else None
    if plat == "kick":
        live = _direct_url(stream_url(r), quality)
        if not live:
            return None
        try:
            vod = kick.current_vod(r["login"])
        except net.NetError:
            vod = None
        return {"platform": "kick", "mode": "live", "url": live, "live": live, "vod": vod}
    live, audio = _youtube_hls(stream_url(r), quality)
    if not live:
        return None
    try:
        seg, dvr = _hls_window(live)
    except (net.NetError, ValueError):
        seg, dvr = 5.0, 0
    return {"platform": "youtube", "mode": "live", "url": live, "live": live, "audio": audio, "seg": seg, "dvr": dvr}


def _session_file(d, sess):
    sess["text"] = {"hint": t("← → 10 s · Shift ← → 5 min · End back to live"), "live": t("Live"),
                    "rewind": t("Going back…"), "no_more": t("This stream can't go back further.")}
    path = d / f"session-{os.getpid()}-{time.time_ns()}.json"
    path.write_text(json.dumps(sess))
    return path


def mpv_command(ppath, sess, title):
    d = prepare_mpv()
    cmd = [ppath, f"--config-dir={d}", f"--script-opts=openlive-session={_session_file(d, sess)}"]
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
    """The command to run for this stream, picking openlive's mpv with rewind when it can."""
    pname, ppath = find_player()
    name = target if isinstance(target, str) else target.get("name", "")
    full = f"{name} · {title}" if title else name
    if pname != "mpv" or config.get("player_ui", "openlive") == "plain" or isinstance(target, str):
        return build_command(target, title)
    sess = None
    if config.get("rewind", True):
        try:
            sess = session_for(target, client, config.get("quality", "best"))
        except Exception:  # any platform hiccup: play it the plain way
            sess = None
    if sess:
        return mpv_command(ppath, sess, full)
    d = prepare_mpv()
    sp = _session_file(d, {"platform": target.get("platform", "twitch"), "mode": "pipe"})
    return build_command(target, title, extra_args=f'"--config-dir={d}" "--script-opts=openlive-session={sp}"')


def play(target, title="", client=None):
    """Start the player detached. target: Twitch login or a row. Returns (ok, message_key). Can block a few
    seconds (it asks the platform for the stream address), so call it from a worker thread."""
    cmd = command_for(target, title, client)
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
