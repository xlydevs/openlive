"""First-run sign-in: Twitch device code flow, with links and a code to type. No keys to paste."""
import shutil
import subprocess
import sys
import time
import webbrowser

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Select, SelectionList, Static

from . import channels, config, kick, net, twitch, youtube
from .i18n import t

CSS = """
LoginScreen, PlatformsScreen, AddChannelScreen { align: center middle; background: #0f1420 70%; }
#platforms { height: auto; background: #141b2a; border: none; padding: 0; }
#platforms:focus { background-tint: transparent; }
#platforms > .selection-list--button { color: #1a2335; background: #1a2335; }
#platforms > .selection-list--button-highlighted { color: #2a3754; background: #2a3754; }
#platforms > .selection-list--button-selected, #platforms > .selection-list--button-selected-highlighted { color: #0f1420; background: #a5d68f; text-style: bold; }
#platforms > .option-list--option-highlighted { background: #222c42; }
.dialog Input { background: #0f1420; border: round #263044; margin-bottom: 1; }
.dialog Input:focus { border: round #f2cc8f; }
.dialog Select { margin-bottom: 1; }
.dialog SelectCurrent { background: #0f1420; border: round #263044; }
.dialog .label { color: #7c879f; }
.dialog .hint { color: #4b5570; margin-bottom: 1; }
#add-status { color: #7c879f; height: auto; }
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


# ───────────────────────── platforms ─────────────────────────

PLATFORM_HINT = {
    "twitch": "sign in once; your follows come from your account",
    "kick": "add the channels you watch (no sign-in)",
    "youtube": "live only; add channels or import subscriptions",
}


class PlatformsScreen(ModalScreen):
    """Pick the platforms openlive shows. Dismisses with the list, or None when cancelled."""

    BINDINGS = [("escape", "cancel", "")]

    def __init__(self, selected, first_run=False):
        super().__init__()
        self.selected, self.first_run = set(selected), first_run

    def compose(self) -> ComposeResult:
        opts = []
        for p in channels.ALL:
            lbl = Text()
            lbl.append("● ", style=channels.COLOR[p])
            lbl.append(f"{channels.LABEL[p]:<9}", style="#eef2fa")
            lbl.append(t(PLATFORM_HINT[p]), style="#7c879f")
            opts.append((lbl, p, p in self.selected))
        with Vertical(classes="dialog"):
            yield Static(t("Which platforms do you watch?"), classes="title")
            yield Static(t("You can change this any time with the p key."), classes="sub")
            yield SelectionList(*opts, id="platforms")
            with Horizontal(classes="buttons"):
                if not self.first_run:
                    yield Button(t("Cancel"), id="cancel")
                yield Button(t("Save"), id="save", variant="primary")

    def on_mount(self):
        self.query_one("#platforms").focus()

    def _chosen(self):
        return [p for p in channels.ALL if p in self.query_one("#platforms", SelectionList).selected]

    def on_button_pressed(self, event):
        if event.button.id == "save":
            ch = self._chosen()
            if not ch:
                self.app.notify(t("Pick at least one platform."), severity="warning", timeout=3)
                return
            self.dismiss(ch)
        else:
            self.dismiss(None)

    def action_cancel(self):
        self.dismiss((self._chosen() or ["twitch"]) if self.first_run else None)


class AddChannelScreen(ModalScreen):
    """Add Kick/YouTube channels to the user's lists. Dismisses with the number of channels added."""

    BINDINGS = [("escape", "cancel", "")]

    def __init__(self, platforms, platform=None):
        super().__init__()
        self.platforms = [p for p in channels.LISTED if p in platforms] or list(channels.LISTED)
        self.platform = platform if platform in self.platforms else self.platforms[0]
        self.added = 0

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Static(t("Add channels"), classes="title")
            yield Static(t("Kick and YouTube don't share who you follow, so openlive keeps its own list."), classes="sub")
            yield Select([(channels.LABEL[p], p) for p in self.platforms], value=self.platform, allow_blank=False, id="add-platform")
            yield Static(t("Channel name or link. Several at once: separate them with commas."), classes="label")
            yield Input(placeholder="", id="add-input")
            yield Static("", classes="hint", id="add-example")
            yield Static(t("Or import your YouTube subscriptions: path to subscriptions.csv from Google Takeout"), classes="label", id="takeout-label")
            yield Input(placeholder="~/Downloads/Takeout/YouTube and YouTube Music/subscriptions/subscriptions.csv", id="takeout")
            yield Static("", id="add-status")
            with Horizontal(classes="buttons"):
                yield Button(t("Close"), id="cancel")
                yield Button(t("Open Takeout"), id="open-takeout")
                yield Button(t("Add"), id="add", variant="primary")

    def on_mount(self):
        self._sync()
        self.query_one("#add-input").focus()

    def _sync(self):
        yt = self.platform == "youtube"
        for sel in ("#takeout-label", "#takeout", "#open-takeout"):
            self.query_one(sel).display = yt
        self.query_one("#add-example").update(
            t("e.g. @LofiGirl, youtube.com/@mkbhd") if yt else t("e.g. xqc, kick.com/trainwreckstv"))

    def on_select_changed(self, event):
        if event.value in channels.LISTED:
            self.platform = event.value
            self._sync()

    def on_input_submitted(self, event):
        self.action_add()

    def on_button_pressed(self, event):
        {"add": self.action_add, "cancel": self.action_cancel, "open-takeout": self.action_takeout}[event.button.id]()

    def action_takeout(self):
        webbrowser.open(youtube.TAKEOUT_URL)
        self._status(t("In Takeout pick only YouTube → subscriptions, export, unzip, then paste the path of subscriptions.csv here."))

    def _status(self, msg, error=False):
        w = self.query_one("#add-status")
        w.update(msg)
        w.styles.color = "#f28b82" if error else "#7c879f"

    def action_add(self):
        text = self.query_one("#add-input", Input).value
        path = self.query_one("#takeout", Input).value.strip() if self.platform == "youtube" else ""
        items = [x for x in (s.strip() for s in text.replace("\n", ",").split(",")) if x]
        if not items and not path:
            self.query_one("#add-input").focus()
            return
        self._status(t("Checking…"))
        self.run_add(self.platform, items, path)

    @work(thread=True, exclusive=True)
    def run_add(self, platform, items, path):
        lists = channels.load()
        added, failed = [], []
        if path:
            try:
                for rec in youtube.read_takeout(path):
                    if channels.add(lists, "youtube", rec):
                        added.append(rec["name"])
            except (OSError, ValueError) as e:
                failed.append(f"{path}: {e}")
        resolver = kick.resolve if platform == "kick" else youtube.resolve
        for item, res in net.parallel(resolver, items):
            if isinstance(res, Exception):
                failed.append(f"{item}: {res}")
            elif channels.add(lists, platform, res):
                added.append(res["name"])
        channels.save(lists)
        self.added += len(added)
        msg = t("Added {n}: {names}", n=len(added), names=", ".join(added[:6]) + ("…" if len(added) > 6 else "")) if added else t("Nothing new added.")
        if failed:
            msg += "\n" + t("Couldn't add: {items}", items="; ".join(failed[:4]))
        self.app.call_from_thread(self._done, msg, bool(failed) and not added)

    def _done(self, msg, error):
        self._status(msg, error)
        self.query_one("#add-input", Input).value = ""
        self.query_one("#takeout", Input).value = ""
        self.query_one("#add-input").focus()

    def action_cancel(self):
        self.dismiss(self.added)
