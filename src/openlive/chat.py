"""Twitch chat for openlive's mpv sidebar. It reads the channel's chat anonymously, draws the sidebar as an
image (chatview.py: emoji, Twitch emotes, scrollback, pause) and hands it to mpv over its IPC socket. It also
sends what you write, with your openlive Twitch sign-in. openlive starts it next to mpv; it ends when mpv closes.

    python -m openlive.chat <mpv-ipc-path> <channel> [<channel-id>]

mpv → bridge: openlive_ui.lua sends "script-message openlive-chat-ui <what> …" (click x y, scroll n, send text,
toggle) and sets user-data/openlive-ui/chat when the sidebar is shown or hidden.
"""
import json
import queue
import random
import re
import socket
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request

IRC = ("irc.chat.twitch.tv", 6697)
EMOTE_URL = "https://static-cdn.jtvnw.net/emoticons/v2/{id}/default/dark/2.0"
WRITE_SCOPE = "user:write:chat"
FPS = 10


def _unescape_tag(v):
    return v.replace(r"\s", " ").replace(r"\:", ";").replace(r"\\", "\\").replace(r"\r", "").replace(r"\n", "")


def parse(line):
    """A PRIVMSG line → {"n": name, "c": "#rrggbb" or "", "t": text, "e": emotes tag[, "me": True]}; None otherwise."""
    tags = {}
    if line.startswith("@"):
        raw, _, line = line.partition(" ")
        for kv in raw[1:].split(";"):
            k, _, v = kv.partition("=")
            tags[k] = _unescape_tag(v)
    parts = line.split(" ", 3)
    if len(parts) < 4 or parts[1] != "PRIVMSG":
        return None
    nick = parts[0].lstrip(":").split("!")[0]
    text = parts[3][1:] if parts[3].startswith(":") else parts[3]
    m = {"n": tags.get("display-name") or nick, "c": tags.get("color", ""), "t": text, "e": tags.get("emotes", "")}
    if text.startswith("\x01ACTION ") and text.endswith("\x01"):
        m.update(t=text[8:-1], me=True)
    return m


# ───────────────────────── mpv ─────────────────────────

class Mpv:
    """mpv's JSON IPC (a Unix socket, or a named pipe on Windows). Events go to `events` from a reader thread."""

    def __init__(self, path, events, wait=30):
        self.events, self.lock = events, threading.Lock()
        deadline = time.time() + wait
        while True:
            try:
                if sys.platform == "win32":  # one handle to write, another to read: a pipe can't do both at once
                    self.w = open(path, "r+b", buffering=0)  # noqa: SIM115
                    self.r = open(path, "rb", buffering=0)  # noqa: SIM115
                    self.s = None
                else:
                    self.s = socket.socket(socket.AF_UNIX)
                    self.s.connect(path)
                    self.r = self.s.makefile("rb")
                break
            except OSError:
                if time.time() > deadline:
                    raise
                time.sleep(0.3)
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        try:
            for raw in self.r:
                try:
                    ev = json.loads(raw)
                except ValueError:
                    continue
                if "event" in ev:
                    self.events.put(("mpv", ev))
        except OSError:
            pass
        self.events.put(("quit", None))

    def send(self, command):
        data = (json.dumps({"command": command}) + "\n").encode()
        with self.lock:
            if self.s is None:
                self.w.write(data)
            else:
                self.s.sendall(data)


# ───────────────────────── Twitch ─────────────────────────

def _irc(channel):
    raw = socket.create_connection(IRC, timeout=15)
    s = ssl.create_default_context().wrap_socket(raw, server_hostname=IRC[0])
    nick = f"justinfan{random.randint(10000, 99999)}"  # Twitch's anonymous, read-only login
    s.sendall(f"CAP REQ :twitch.tv/tags\r\nNICK {nick}\r\nJOIN #{channel.lower()}\r\n".encode())
    s.settimeout(30)
    return s


def irc_loop(channel, events):
    backoff = 2
    while True:
        try:
            irc = _irc(channel)
        except OSError:
            events.put(("status", "offline"))
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)
            continue
        events.put(("status", "joined"))
        backoff, buf = 2, b""
        while True:
            try:
                chunk = irc.recv(65536)
            except TimeoutError:
                continue
            except OSError:
                break
            if not chunk:
                break
            buf += chunk
            *lines, buf = buf.split(b"\r\n")
            for raw in lines:
                line = raw.decode("utf-8", "replace")
                if line.startswith("PING"):
                    irc.sendall(("PONG" + line[4:] + "\r\n").encode())
                elif m := parse(line):
                    events.put(("msg", m))
        try:
            irc.close()
        except OSError:
            pass


class Emotes:
    """Twitch emote images, fetched once from Twitch's CDN and kept in openlive's data folder."""

    def __init__(self, events, folder=None):
        self.events, self.folder = events, folder
        self.images, self.pending = {}, set()
        self.lock = threading.Lock()

    def get(self, eid):
        if eid in self.images:
            return self.images[eid]
        with self.lock:
            if eid not in self.pending and re.fullmatch(r"[A-Za-z0-9_]+", eid):
                self.pending.add(eid)
                threading.Thread(target=self._fetch, args=(eid,), daemon=True).start()
        return None

    def _fetch(self, eid):
        from io import BytesIO

        from PIL import Image
        data = None
        path = self.folder / f"{eid}.png" if self.folder else None
        try:
            if path and path.exists():
                data = path.read_bytes()
            else:
                req = urllib.request.Request(EMOTE_URL.format(id=eid), headers={"User-Agent": "openlive"})
                with urllib.request.urlopen(req, timeout=10) as r:
                    data = r.read(2_000_000)
                if path:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
            img = Image.open(BytesIO(data))
            img.seek(0)  # animated emotes: the first frame
            self.images[eid] = img.convert("RGBA")
        except (OSError, ValueError, urllib.error.URLError):
            self.images[eid] = None
        self.events.put(("emote", eid))


class Sender:
    """Sends chat messages with the openlive Twitch sign-in (Helix chat/messages, scope user:write:chat)."""

    def __init__(self, channel, channel_id=""):
        self.channel, self.channel_id = channel, channel_id
        self.scopes = None

    def ready(self):
        """None when it can write, else the reason: "signin" (not signed in) or "rescope" (old sign-in)."""
        from . import twitch
        rec = twitch.load_auth()
        if not rec:
            return "signin"
        if self.scopes is None:
            try:
                if rec.get("expires_at") and rec["expires_at"] - time.time() < 60:
                    rec = twitch.refresh(rec)
                self.scopes = twitch.validate(rec["access_token"]).get("scopes") or []
            except twitch.TwitchError:
                return "signin"
        return None if WRITE_SCOPE in self.scopes else "rescope"

    def send(self, text):
        """Returns None when sent, else a short reason."""
        from . import twitch
        rec = twitch.load_auth()
        if not rec:
            return "signin"
        try:
            if rec.get("expires_at") and rec["expires_at"] - time.time() < 60:
                rec = twitch.refresh(rec)
            hdr = {"Client-Id": rec["client_id"], "Authorization": f"Bearer {rec['access_token']}"}
            if not self.channel_id:
                users = _helix("GET", f"users?login={self.channel}", hdr)
                self.channel_id = (users.get("data") or [{}])[0].get("id", "")
            res = _helix("POST", "chat/messages", hdr, {"broadcaster_id": self.channel_id, "sender_id": rec["user_id"],
                                                        "message": text[:500]})
        except twitch.TwitchError as e:
            return "rescope" if e.status in (401, 403) else str(e)
        d = (res.get("data") or [{}])[0]
        if d.get("is_sent") is False:
            return (d.get("drop_reason") or {}).get("message") or "not sent"
        return None


def _helix(method, path, headers, body=None):
    from . import twitch
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{twitch.API_URL}/{path}", data=data, method=method,
                                 headers={"User-Agent": twitch.UA, "Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read() or b"{}").get("message")
        except ValueError:
            msg = None
        raise twitch.TwitchError(msg or f"HTTP {e.code}", e.code) from None
    except (urllib.error.URLError, OSError) as e:
        raise twitch.TwitchError(f"network: {getattr(e, 'reason', e)}") from None


# ───────────────────────── the bridge ─────────────────────────

class Bridge:
    def __init__(self, mpv, view, sender, folder):
        self.mpv, self.view, self.sender, self.folder = mpv, view, sender, folder
        self.size = (0, 0)
        self.shown = True
        self.dirty, self.last = True, 0.0
        self.frame = 0
        self.overlay = False

    def handle(self, kind, val):
        v = self.view
        if kind == "msg":
            v.add(val)
        elif kind == "status":
            v.status = val
        elif kind == "emote":
            v.forget_layouts()
        elif kind == "note":
            v.add({"note": val})
        elif kind == "mpv":
            self.mpv_event(val)
            return
        self.dirty = True

    def note(self, key, fallback, **kw):
        s = self.view.tr(key, fallback)
        for k, x in kw.items():
            s = s.replace("{" + k + "}", str(x))
        self.view.add({"note": s})

    def mpv_event(self, ev):
        v = self.view
        if ev.get("event") == "property-change":
            name, data = ev.get("name"), ev.get("data")
            if name == "osd-dimensions" and isinstance(data, dict):
                self.size = (int(data.get("w") or 0), int(data.get("h") or 0))
            elif name == "user-data/openlive" and isinstance(data, dict):
                v.text = data.get("text") or {}
                v.channel = data.get("channel") or self.sender.channel
            elif name == "user-data/openlive-ui" and isinstance(data, dict):
                self.shown = bool(data.get("chat"))
            self.dirty = True
        elif ev.get("event") == "client-message":
            args = ev.get("args") or []
            if not args or args[0] != "openlive-chat-ui":
                return
            what = args[1] if len(args) > 1 else ""
            if what == "click" and len(args) >= 4:
                self.action(v.click(float(args[2]), float(args[3])))
            elif what == "scroll" and len(args) >= 3:
                v.scroll_by(float(args[2]))
            elif what == "write":
                self.action("write")
            elif what == "pause":
                v.toggle_pause()
            elif what == "send" and len(args) >= 3 and args[2].strip():
                self.send(args[2].strip())
            self.dirty = True

    def action(self, what):
        v = self.view
        if what == "hide":
            self.mpv.send(["script-message", "openlive-chat-hide"])
        elif what == "pause":
            v.toggle_pause()
        elif what == "resume":
            v.resume()
        elif what == "write":
            why = self.sender.ready()
            v.can_write = why is None
            if why is None:
                self.mpv.send(["script-message", "openlive-chat-prompt"])
            elif why == "rescope":
                self.note("chat_rescope", "To write, sign in to Twitch again in openlive (press l there).")
            else:
                self.note("chat_signin", "To write, sign in to Twitch in openlive (press l there).")
        self.dirty = True

    def send(self, text):
        def run():
            why = self.sender.send(text)
            if why == "rescope":
                self.sender.scopes = None
                self.mpv.events.put(("note", self.view.tr("chat_rescope", "To write, sign in to Twitch again in openlive (press l there).")))
            elif why == "signin":
                self.mpv.events.put(("note", self.view.tr("chat_signin", "To write, sign in to Twitch in openlive (press l there).")))
            elif why:
                self.mpv.events.put(("note", self.view.tr("chat_not_sent", "Not sent: {why}").replace("{why}", why)))
        if self.view.frozen:
            self.view.resume()
        threading.Thread(target=run, daemon=True).start()

    def draw(self):
        w, h = self.size
        if not self.shown or w < 200 or h < 150:
            if self.overlay:
                self.mpv.send(["overlay-remove", 0])
                self.overlay = False
            return
        img, x0 = self.view.render(w, h)
        self.frame ^= 1  # two files: mpv may still be reading the previous one
        path = self.folder / f"chat-{id(self)}-{self.frame}.bgra"
        path.write_bytes(img.tobytes("raw", "BGRA"))
        self.mpv.send(["overlay-add", 0, x0, 0, str(path), 0, "bgra", img.width, img.height, img.width * 4])
        self.overlay = True

    def loop(self, events):
        while True:
            try:
                kind, val = events.get(timeout=1 / FPS)
                if kind == "quit":
                    return
                self.handle(kind, val)
                while True:  # take everything waiting before drawing
                    kind, val = events.get_nowait()
                    if kind == "quit":
                        return
                    self.handle(kind, val)
            except queue.Empty:
                pass
            if self.dirty and time.time() - self.last >= 1 / FPS:
                self.dirty, self.last = False, time.time()
                self.draw()


def run(ipc_path, channel, channel_id=""):
    from . import config
    from .chatview import ChatView
    events = queue.Queue()
    folder = config.DATA / "mpv"
    folder.mkdir(parents=True, exist_ok=True)
    mpv = Mpv(ipc_path, events)
    emotes = Emotes(events, config.DATA / "emotes")
    view = ChatView(emote_image=emotes.get)
    sender = Sender(channel, channel_id)
    view.channel = channel

    def check_write():  # asks Twitch which permissions the sign-in has: don't hold up the chat for it
        try:
            view.can_write = sender.ready() is None
        except Exception:  # noqa: BLE001 — writing is optional
            view.can_write = False
        events.put(("status", view.status))
    threading.Thread(target=check_write, daemon=True).start()
    bridge = Bridge(mpv, view, sender, folder)
    for i, prop in enumerate(("osd-dimensions", "user-data/openlive", "user-data/openlive-ui"), 1):
        mpv.send(["observe_property", i, prop])
    threading.Thread(target=irc_loop, args=(channel, events), daemon=True).start()
    try:
        bridge.loop(events)
    finally:
        for f in folder.glob(f"chat-{id(bridge)}-*.bgra"):
            f.unlink(missing_ok=True)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) not in (2, 3):
        print(__doc__, file=sys.stderr)
        return 2
    try:
        run(*argv)
    except (OSError, KeyboardInterrupt):  # mpv closed
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
