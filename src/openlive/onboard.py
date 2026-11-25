"""First-run sign-in: Twitch device code flow, with links and a code to type. No keys to paste."""
import shutil
import subprocess
import sys
import time
import webbrowser

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from . import config, twitch
from .i18n import t

CSS = """
LoginScreen { align: center middle; background: #0f1420 70%; }
.dialog { width: 72; max-width: 95%; height: auto; max-height: 95%; border: round #f2cc8f; background: #141b2a; padding: 1 2; }
.dialog .title { text-style: bold; color: #eef2fa; }
.dialog .sub { color: #7c879f; margin-bottom: 1; }
.dialog .step { color: #d6deeb; }
#code { width: 100%; height: 3; content-align: center middle; text-style: bold; color: #0f1420; background: #f2cc8f; margin: 1 0; }
#url { color: #9cc8e8; text-align: center; }
#login-status { color: #7c879f; margin-top: 1; }
.buttons { height: auto; align-horizontal: right; margin-top: 1; }
.buttons Button { margin-left: 2; }
"""

NEW_APP_URL = "https://dev.twitch.tv/console/apps/create"


def copy_text(app, text):
    """Clipboard: the system tool when there is one, OSC 52 through the terminal as well."""
    try:
        app.copy_to_clipboard(text)
    except Exception:
        pass
    cmds = (["pbcopy"],) if sys.platform == "darwin" else (["clip"],) if sys.platform == "win32" else (
        ["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "-b", "-i"])
    for cmd in cmds:
        if shutil.which(cmd[0]):
            try:
                subprocess.run(cmd, input=text.encode("utf-16le" if cmd[0] == "clip" else "utf-8"), check=True, timeout=5)
                return True
            except (OSError, subprocess.SubprocessError):
                continue
    return False


class LoginScreen(ModalScreen):
    """Sign in with Twitch. Dismisses with the saved auth record, or None when cancelled."""

    BINDINGS = [("escape", "cancel", ""), ("o", "open", ""), ("c", "copy", "")]

    def __init__(self):
        super().__init__()
        self.device, self.cancelled = None, False

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Static(t("Sign in with Twitch"), classes="title")
            yield Static(t("openlive only asks to read who you follow. It can't chat, follow or change anything."), classes="sub")
            yield Static(t("1. Open the link (o) and log in to Twitch if asked."), classes="step")
            yield Static(t("2. Check that this code matches and press Activate:"), classes="step")
            yield Static("········", id="code")
            yield Static("", id="url")
            yield Static(t("Getting a code…"), id="login-status")
            with Horizontal(classes="buttons"):
                yield Button(t("Cancel"), id="cancel")
                yield Button(t("Copy link"), id="copy")
                yield Button(t("Open Twitch"), id="open", variant="primary")

    def on_mount(self):
        self.query_one("#open").focus()
        if not config.client_id():
            self.query_one("#code").update("—")
            self.query_one("#login-status").update(t("No Twitch Client ID set. Create a Public app at {url} and put its Client ID in the config file as client_id.", url=NEW_APP_URL))
            return
        self.run_login()

    @work(thread=True, exclusive=True)
    def run_login(self):
        cid = config.client_id()
        try:
            d = twitch.start_device_login(cid)
        except twitch.TwitchError as e:
            self.app.call_from_thread(self._status, t("Couldn't reach Twitch: {err}", err=e), True)
            return
        self.device = d
        self.app.call_from_thread(self._show_code, d)
        deadline = time.time() + int(d.get("expires_in", 1800))
        while not self.cancelled and time.time() < deadline:
            time.sleep(max(1, int(d.get("interval", 5))))
            if self.cancelled:
                return
            try:
                tok = twitch.poll_device_login(cid, d["device_code"])
                if tok:
                    rec = twitch.finish_login(cid, tok)
                    self.app.call_from_thread(self.dismiss, rec)
                    return
            except twitch.TwitchError as e:
                self.app.call_from_thread(self._status, t("Sign-in failed: {err}. Press Cancel and try again.", err=e), True)
                return
        if not self.cancelled:
            self.app.call_from_thread(self._status, t("The code expired. Try again."), True)

    def _show_code(self, d):
        self.query_one("#code").update(d["user_code"])
        self.query_one("#url").update(d["verification_uri"].split("?")[0])
        self._status(t("Waiting for you to authorise on Twitch…"))

    def _status(self, msg, error=False):
        w = self.query_one("#login-status")
        w.update(msg)
        w.styles.color = "#f28b82" if error else "#7c879f"

    def _url(self):
        if self.device:
            return self.device["verification_uri"]
        return NEW_APP_URL if not config.client_id() else None

    def action_open(self):
        if url := self._url():
            webbrowser.open(url)

    def action_copy(self):
        if url := self._url():
            copy_text(self.app, url)
            self.app.notify(t("Copied to the clipboard"), timeout=3)

    def action_cancel(self):
        self.cancelled = True
        self.dismiss(None)

    def on_button_pressed(self, event):
        {"open": self.action_open, "copy": self.action_copy, "cancel": self.action_cancel}[event.button.id]()
