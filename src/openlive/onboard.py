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
from textual.widgets import Button, Input, OptionList, Select, SelectionList, Static
from textual.widgets.option_list import Option

from . import __version__, channels, config, demo, google, kick, net, player, twitch, updater, youtube
from .common import human
from .i18n import t

CSS = """
LoginScreen, PlatformsScreen, AddChannelScreen, PlayerSetupScreen, UpdateScreen { align: center middle; background: #0f1420 70%; }
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
#results { height: auto; max-height: 9; background: #0f1420; border: none; margin: -1 0 1 0; display: none; }
#results > .option-list--option-highlighted { background: #2a3754; }
.dialog { width: 72; max-width: 95%; height: auto; max-height: 95%; border: round #f2cc8f; background: #141b2a; padding: 1 2; }
.dialog .title { text-style: bold; color: #eef2fa; }
.dialog .sub { color: #7c879f; margin-bottom: 1; }
.dialog .step { color: #d6deeb; }
#code { width: 100%; height: 3; content-align: center middle; text-style: bold; color: #0f1420; background: #f2cc8f; margin: 1 0; }
#url { color: #9cc8e8; text-align: center; }
#login-status { color: #7c879f; margin-top: 1; }
#install-cmd { width: 100%; height: auto; min-height: 3; padding: 0 1; content-align: center middle; text-align: center; color: #eef2fa; background: #0f1420; border: round #263044; margin: 1 0 0 0; }
#install-status { color: #7c879f; margin-top: 1; height: auto; }
#login-dialog { width: 88; }
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


class _Twitch:
    title = "Sign in with Twitch"
    sub = "openlive only asks to read who you follow. It can't chat, follow or change anything."
    step1 = "1. Open the link (o) and log in to Twitch if asked."
    step2 = "2. Check that this code matches and press Activate:"
    open_label = "Open Twitch"
    waiting = "Waiting for you to authorise on Twitch…"
    unreachable = "Couldn't reach Twitch: {err}"
    error = twitch.TwitchError

    def ready(self):
        return bool(config.client_id())

    def start(self):
        return twitch.start_device_login(config.client_id())

    def poll(self, device_code):
        cid = config.client_id()
        tok = twitch.poll_device_login(cid, device_code)
        return twitch.finish_login(cid, tok) if tok else None


class _Google:
    title = "Sign in with Google"
    sub = "For your YouTube subscriptions. openlive only asks to read them: it can't comment, subscribe or change anything."
    step1 = "1. Open the link (o) and choose your YouTube account."
    step2 = "2. Type this code there and allow access:"
    open_label = "Open Google"
    waiting = "Waiting for you to allow access on Google…"
    unreachable = "Couldn't reach Google: {err}"
    error = google.GoogleError

    def ready(self):
        return True

    def start(self):
        return google.start_device_login()

    def poll(self, device_code):
        tok = google.poll_device_login(device_code)
        return google.finish_login(tok) if tok else None


class LoginScreen(ModalScreen):
    """Sign in with a code (Twitch or Google). Dismisses with the saved auth record, or None when cancelled."""

    BINDINGS = [("escape", "cancel", ""), ("o", "open", ""), ("c", "copy", ""), ("k", "copy_code", "")]

    def __init__(self, provider="twitch"):
        super().__init__()
        self.provider = provider
        self.p = _Google() if provider == "google" else _Twitch()
        self.device, self.cancelled = None, False

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog", id="login-dialog"):
            yield Static(t(self.p.title), classes="title")
            yield Static(t(self.p.sub), classes="sub")
            yield Static(t(self.p.step1), classes="step")
            yield Static(t(self.p.step2), classes="step")
            yield Static("········", id="code")
            yield Static("", id="url")
            yield Static(t("Getting a code…"), id="login-status")
            with Horizontal(classes="buttons"):
                yield Button(t("Skip") if self.provider == "google" else t("Cancel"), id="cancel")
                yield Button(t("Copy link"), id="copy")
                yield Button(t("Copy code"), id="copy-code", disabled=True)
                yield Button(t(self.p.open_label), id="open", variant="primary")

    def on_mount(self):
        self.query_one("#open").focus()
        if not self.p.ready():
            self.query_one("#code").update("—")
            self.query_one("#login-status").update(t("No Twitch Client ID set. Create a Public app at {url} and put its Client ID in the config file as client_id.", url=NEW_APP_URL))
            return
        self.run_login()

    @work(thread=True, exclusive=True)
    def run_login(self):
        try:
            d = self.p.start()
        except self.p.error as e:
            self.app.call_from_thread(self._status, t(self.p.unreachable, err=e), True)
            return
        self.device = d
        self.app.call_from_thread(self._show_code, d)
        deadline = time.time() + int(d.get("expires_in", 1800))
        interval = max(1, int(d.get("interval", 5)))
        while not self.cancelled and time.time() < deadline:
            wake = time.time() + interval
            while time.time() < wake and not self.cancelled:
                time.sleep(0.2)
            if self.cancelled:
                return
            try:
                rec = self.p.poll(d["device_code"])
                if rec:
                    self.app.call_from_thread(self.dismiss, rec)
                    return
            except self.p.error as e:
                self.app.call_from_thread(self._status, t("Sign-in failed: {err}. Press Cancel and try again.", err=e), True)
                return
        if not self.cancelled:
            self.app.call_from_thread(self._status, t("The code expired. Try again."), True)

    def _show_code(self, d):
        self.query_one("#code").update(d["user_code"])
        self.query_one("#copy-code").disabled = False
        self.query_one("#url").update(d["verification_uri"].split("?")[0])
        self._status(t(self.p.waiting))

    def _status(self, msg, error=False):
        w = self.query_one("#login-status")
        w.update(msg)
        w.styles.color = "#f28b82" if error else "#7c879f"

    def _url(self):
        if self.device:
            return self.device["verification_uri"]
        return NEW_APP_URL if not self.p.ready() else None

    def action_open(self):
        if url := self._url():
            webbrowser.open(url)

    def action_copy(self):
        if url := self._url():
            copy_text(self.app, url)
            self.app.notify(t("Copied to the clipboard"), timeout=3)

    def action_copy_code(self):
        if self.device:  # without dashes or spaces, ready to paste in the sign-in page
            copy_text(self.app, "".join(ch for ch in self.device["user_code"] if ch.isalnum()))
            self.app.notify(t("Code copied"), timeout=3)

    def action_cancel(self):
        self.cancelled = True
        self.dismiss(None)

    def on_button_pressed(self, event):
        {"open": self.action_open, "copy": self.action_copy, "copy-code": self.action_copy_code,
         "cancel": self.action_cancel}[event.button.id]()


# ───────────────────────── video player ─────────────────────────

class PlayerSetupScreen(ModalScreen):
    """No video player yet (or an old mpv): show the command that installs mpv, copy it or run it.
    Dismisses with True once a player is found, else None."""

    BINDINGS = [("escape", "close", ""), ("c", "copy", "")]

    def __init__(self, upgrade=False, version=None):
        super().__init__()
        self.upgrade, self.version = upgrade, version
        self.plan = player.install_plan(upgrade)
        self.busy = False

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            if self.upgrade:
                yield Static(t("Update mpv"), classes="title")
                yield Static(t("Your mpv is {v}. Writing in the chat needs 0.38 or newer; the rest works.",
                               v=".".join(map(str, self.version or ()))), classes="sub")
            else:
                yield Static(t("Install a video player"), classes="title")
                yield Static(t("openlive plays streams in mpv, and it isn't on this computer yet. openlive sets it up by itself once it's installed."), classes="sub")
            show = self.plan["show"]
            yield Static(show or self.plan["url"], id="install-cmd")
            if self.plan["cmd"]:
                msg = t("Update runs this command for you. It can take a few minutes.") if self.upgrade else \
                    t("Install runs this command for you. It can take a few minutes.")
            elif show:
                msg = t("Run it in a terminal (it asks for your password), then open the stream again.")
            else:
                msg = t("Download mpv from this page, then open the stream again.")
            yield Static(msg, id="install-status")
            with Horizontal(classes="buttons"):
                yield Button(t("Close"), id="close")
                yield Button(t("Copy"), id="copy")
                if self.plan["cmd"]:
                    yield Button(t("Update") if self.upgrade else t("Install"), id="install", variant="primary")
                elif not show:
                    yield Button(t("Open page"), id="open", variant="primary")

    def on_mount(self):
        self.query_one("Button.-primary" if self.query("Button.-primary") else "#copy").focus()

    def _status(self, msg, color="#7c879f"):
        w = self.query_one("#install-status")
        w.update(msg)
        w.styles.color = color

    def action_copy(self):
        copy_text(self.app, self.plan["show"] or self.plan["url"])
        self.app.notify(t("Copied to the clipboard"), timeout=3)

    def action_close(self):
        if not self.busy:
            self.dismiss(None)

    @work(thread=True, exclusive=True)
    def run_install(self):
        try:
            out = subprocess.run(self.plan["cmd"], capture_output=True, text=True, timeout=900, stdin=subprocess.DEVNULL)
            ok, tail = out.returncode == 0, (out.stderr or out.stdout or "").strip().splitlines()[-1:]
        except (OSError, subprocess.SubprocessError) as e:
            ok, tail = False, [str(e)]
        self.app.call_from_thread(self._installed, ok, tail[0] if tail else "")

    def _installed(self, ok, last):
        self.busy = False
        self.query_one("#install").disabled = False
        name, path = player.find_player("mpv")
        if path and (not self.upgrade or (player.mpv_version(path) or (0, 0)) >= player.MIN_MPV):
            self.app.notify(t("mpv is ready."), timeout=4)
            self.dismiss(True)
        elif ok:
            self._status(t("Installed, but openlive can't find mpv yet. Restart openlive (a new terminal may be needed)."), "#f2cc8f")
        else:
            self._status(t("It didn't work: {err}", err=last[:160] or "?"), "#f28b82")

    def on_button_pressed(self, event):
        bid = event.button.id
        if bid == "install" and not self.busy:
            self.busy = True
            event.button.disabled = True
            self._status(t("Installing… it can take a few minutes."), "#9cc8e8")
            self.run_install()
        elif bid == "open":
            webbrowser.open(self.plan["url"])
        elif bid == "copy":
            self.action_copy()
        elif bid == "close":
            self.action_close()


# ───────────────────────── updates ─────────────────────────

class UpdateScreen(ModalScreen):
    """A newer openlive is out. Dismisses with "update" (update in the background) or None (later)."""

    BINDINGS = [("escape", "later", ""), ("c", "copy", "")]

    def __init__(self, version):
        super().__init__()
        self.version = version
        self.auto = updater.can_update()

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Static(t("openlive {v} is out", v=self.version), classes="title")
            yield Static(t("You have {cur}.", cur=__version__), classes="sub")
            if self.auto:
                yield Static(t("It updates in the background; you can keep watching."), classes="step")
            else:
                yield Static(t("To update, run this in a terminal:"), classes="step")
                yield Static(updater.manual_command(), id="install-cmd")
            with Horizontal(classes="buttons"):
                yield Button(t("Later"), id="later")
                if self.auto:
                    yield Button(t("Update"), id="update", variant="primary")
                else:
                    yield Button(t("Copy"), id="copy", variant="primary")

    def on_mount(self):
        self.query_one("#update" if self.auto else "#copy").focus()

    def action_later(self):
        self.dismiss(None)

    def action_copy(self):
        if not self.auto:
            copy_text(self.app, updater.manual_command())
            self.app.notify(t("Copied to the clipboard"), timeout=3)

    def on_button_pressed(self, event):
        if event.button.id == "update":
            self.dismiss("update")
        elif event.button.id == "copy":
            self.action_copy()
        else:
            self.dismiss(None)


# ───────────────────────── platforms ─────────────────────────

PLATFORM_HINT = {
    "twitch": "sign in once; your follows come from your account",
    "kick": "add the channels you watch (no sign-in)",
    "youtube": "live only; sign in with Google for your subscriptions",
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
    """Add Kick/YouTube channels to the user's lists. Dismisses with the number of channels added.

    Kick: results appear as you type (Enter adds the highlighted one). YouTube: a name or link, or a Takeout file.
    """

    BINDINGS = [("escape", "cancel", "")]

    def __init__(self, platforms, platform=None):
        super().__init__()
        self.platforms = [p for p in channels.LISTED if p in platforms] or ["kick"]
        self.platform = platform if platform in self.platforms else self.platforms[0]
        self.added = 0
        self.results = []
        self._timer = None

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Static(t("Add channels"), classes="title")
            yield Static("", classes="sub", id="add-sub")
            yield Select([(channels.LABEL[p], p) for p in self.platforms], value=self.platform, allow_blank=False, id="add-platform")
            yield Static("", classes="label", id="add-label")
            yield Input(placeholder="", id="add-input")
            yield OptionList(id="results")
            yield Static("", classes="hint", id="add-example")
            yield Static(t("Or import your YouTube subscriptions: path to subscriptions.csv from Google Takeout"), classes="label", id="takeout-label")
            yield Input(placeholder="~/Downloads/Takeout/YouTube and YouTube Music/subscriptions/subscriptions.csv", id="takeout")
            yield Static("", id="add-status")
            with Horizontal(classes="buttons"):
                yield Button(t("Close"), id="cancel")
                yield Button(t("Open Takeout"), id="open-takeout")
                yield Button(t("Add"), id="add", variant="primary")

    def on_mount(self):
        self.query_one("#add-platform").display = len(self.platforms) > 1
        self._sync()
        self.query_one("#add-input").focus()

    def _sync(self):
        yt = self.platform == "youtube"
        for sel in ("#takeout-label", "#takeout", "#open-takeout"):
            self.query_one(sel).display = yt
        self.query_one("#add-sub").update(
            t("Kick doesn't share who you follow, so openlive keeps its own list.") if not yt
            else t("Signed in with Google, your subscriptions come on their own. Here you can add others.") if google.load_auth()
            else t("Sign in with Google (g) to bring your subscriptions, or add channels here."))
        self.query_one("#add-label").update(t("Type a channel name: results show up as you type.") if not yt
                                            else t("Channel name or link. Several at once: separate them with commas."))
        self.query_one("#add-example").update(
            t("e.g. @LofiGirl, youtube.com/@mkbhd") if yt else t("↑↓ pick · Enter add · Esc close"))
        self._show_results([])

    def on_select_changed(self, event):
        if event.value in channels.LISTED:
            self.platform = event.value
            self._sync()

    # --- Kick search as you type ---
    def on_input_changed(self, event):
        if event.input.id != "add-input" or self.platform != "kick":
            return
        if self._timer:
            self._timer.stop()
        q = event.value.strip()
        if len(q) < 2 or "," in q:
            self._show_results([])
            return
        self._timer = self.set_timer(0.35, lambda: self.run_search(q))

    @work(thread=True, exclusive=True, group="search")
    def run_search(self, q):
        try:
            res = demo.kick_search(q) if (config.OFFLINE or getattr(self.app, "demo", False)) else kick.search(q)
        except Exception:
            res = []
        if self.query_one("#add-input", Input).value.strip() == q:
            self.app.call_from_thread(self._show_results, res)

    def _show_results(self, res, keep=0):
        self.results = res
        ol = self.query_one("#results", OptionList)
        ol.clear_options()
        have = {c["id"].lower() for c in channels.load().get(self.platform, [])}
        for r in res:
            line = Text()
            line.append("● ", style="#f28b82" if r.get("live") else "#4b5570")
            line.append(r["name"], style="bold #eef2fa")
            line.append(f"  {human(r.get('followers', 0))} " + t("followers"), style="#7c879f")
            if r.get("live"):
                line.append("  " + t("live"), style="#f28b82")
            if r["id"].lower() in have:
                line.append("  ✓ " + t("added"), style="#a5d68f")
            ol.add_option(Option(line, id=r["id"]))
        ol.display = bool(res)
        if res:
            ol.highlighted = min(keep, len(res) - 1)

    def on_key(self, event):
        ol = self.query_one("#results", OptionList)
        if not ol.display or self.focused is not self.query_one("#add-input"):
            return
        if event.key in ("down", "up"):
            n = ol.option_count
            ol.highlighted = ((ol.highlighted or 0) + (1 if event.key == "down" else -1)) % n
            event.stop()
            event.prevent_default()

    def on_option_list_option_selected(self, event):
        self._add_result(event.option_index)

    def _add_result(self, i):
        if not (0 <= i < len(self.results)):
            return
        r = self.results[i]
        lists = channels.load()
        if channels.add(lists, self.platform, {"id": r["id"], "name": r["name"]}):
            channels.save(lists)
            self.added += 1
            self._status(t("Added {n}: {names}", n=1, names=r["name"]))
        else:
            self._status(t("{name} is already on your list.", name=r["name"]))
        self._show_results(self.results, i)
        self.query_one("#add-input").focus()

    # --- typed names / links, Takeout ---
    def on_input_submitted(self, event):
        ol = self.query_one("#results", OptionList)
        if event.input.id == "add-input" and ol.display and ol.highlighted is not None:
            self._add_result(ol.highlighted)
            return
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
        ol = self.query_one("#results", OptionList)
        if ol.display and ol.highlighted is not None:
            self._add_result(ol.highlighted)
            return
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
        self._show_results([])
        self.query_one("#add-input").focus()

    def action_cancel(self):
        self.dismiss(self.added)
