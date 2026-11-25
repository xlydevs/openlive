"""Twitch chat for openlive's mpv sidebar: reads the channel's chat (anonymously, read-only) and hands each
message to mpv over its IPC socket. openlive starts it next to mpv; it ends when mpv closes.

    python -m openlive.chat <mpv-ipc-path> <channel>
"""
import json
import random
import socket
import ssl
import sys
import time

IRC = ("irc.chat.twitch.tv", 6697)


def _unescape_tag(v):
    return v.replace(r"\s", " ").replace(r"\:", ";").replace(r"\\", "\\").replace(r"\r", "").replace(r"\n", "")


def parse(line):
    """A PRIVMSG line → {"n": name, "c": "#rrggbb" or "", "t": text}; None for anything else."""
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
    if text.startswith("\x01ACTION ") and text.endswith("\x01"):
        text = text[8:-1]
    return {"n": tags.get("display-name") or nick, "c": tags.get("color", ""), "t": text}


class Mpv:
    """Write-only client of mpv's JSON IPC (a Unix socket, or a named pipe on Windows)."""

    def __init__(self, path, wait=30):
        deadline = time.time() + wait
        while True:
            try:
                if sys.platform == "win32":
                    self.f = open(path, "r+b", buffering=0)  # noqa: SIM115
                    self.s = None
                else:
                    self.s = socket.socket(socket.AF_UNIX)
                    self.s.connect(path)
                    self.s.setblocking(False)
                break
            except OSError:
                if time.time() > deadline:
                    raise
                time.sleep(0.3)
        self.send(["disable_event", "all"])

    def send(self, command):
        data = (json.dumps({"command": command}) + "\n").encode()
        if self.s is None:
            self.f.write(data)
            return
        self.s.sendall(data)
        try:  # drop mpv's replies so its buffer never fills
            while self.s.recv(65536):
                pass
        except BlockingIOError:
            pass

    def message(self, **kw):
        self.send(["script-message", "openlive-chat", json.dumps(kw)])


def _irc(channel):
    raw = socket.create_connection(IRC, timeout=15)
    s = ssl.create_default_context().wrap_socket(raw, server_hostname=IRC[0])
    nick = f"justinfan{random.randint(10000, 99999)}"  # Twitch's anonymous, read-only login
    s.sendall(f"CAP REQ :twitch.tv/tags\r\nNICK {nick}\r\nJOIN #{channel.lower()}\r\n".encode())
    s.settimeout(5)
    return s


def run(ipc_path, channel):
    mpv = Mpv(ipc_path)
    backoff = 2
    while True:
        try:
            irc = _irc(channel)
        except OSError:
            mpv.message(sys="offline")
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)
            continue
        mpv.message(sys="joined")
        backoff, buf, idle = 2, b"", 0
        while True:
            try:
                chunk = irc.recv(65536)
                if not chunk:
                    break
                idle = 0
            except TimeoutError:
                idle += 1
                if idle % 6 == 0:
                    mpv.send(["get_property", "pid"])  # raises once mpv is gone
                continue
            except OSError:
                break
            buf += chunk
            *lines, buf = buf.split(b"\r\n")
            for raw in lines:
                line = raw.decode("utf-8", "replace")
                if line.startswith("PING"):
                    irc.sendall(("PONG" + line[4:] + "\r\n").encode())
                elif m := parse(line):
                    mpv.message(**m)
        try:
            irc.close()
        except OSError:
            pass


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        run(*argv)
    except (OSError, KeyboardInterrupt):  # mpv closed
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
