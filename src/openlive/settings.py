"""The Settings tab: accounts (Twitch, Google, Kick list), player options and general settings.

Changes are saved to config.toml right away (nothing is written in demo mode).
"""
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, OptionList, Select, Static, Switch
from textual.widgets.option_list import Option

from . import channels, config, i18n
from .i18n import t

CSS = """
#settings-pane { padding: 0 1; scrollbar-size-vertical: 1; scrollbar-color: #263044; scrollbar-background: #0f1420;
                 scrollbar-color-hover: #33415f; scrollbar-color-active: #f2cc8f; }
.set-section { height: auto; border: round #263044; border-title-color: #7c879f; border-title-style: bold;
               padding: 0 1; margin-bottom: 1; background: #0f1420; }
.set-row { height: 3; }
.set-row > .set-name { width: 22; padding-top: 1; color: #eef2fa; }
.set-row > .set-value { width: 1fr; padding-top: 1; color: #7c879f; }
.set-row Button { min-width: 14; margin-left: 1; background: #1a2335; color: #d6deeb; border: tall #1a2335; }
.set-row Button:hover { background: #222c42; border: tall #222c42; }
.set-row Button:focus { text-style: bold; border: tall #f2cc8f; background-tint: transparent; }
.set-row Button.-primary { background: #f2cc8f; color: #0f1420; border: tall #f2cc8f; }
.set-row Button:disabled { color: #4b5570; }
.set-row Switch { background: #0f1420; border: tall #0f1420; }
.set-row Switch:focus { border: tall #f2cc8f; background-tint: transparent; }
.set-row Switch > .switch--slider { color: #4b5570; background: #1a2335; }
.set-row Switch.-on > .switch--slider { color: #a5d68f; }
.set-row Select { width: 30; }
.set-row SelectCurrent { background: #0f1420; border: round #263044; }
.set-note { color: #4b5570; height: auto; padding: 0 0 1 0; }
#kick-list { height: auto; max-height: 8; background: #0f1420; border: none; margin: 0 0 1 22; }
#kick-list > .option-list--option-highlighted { background: #2a3754; }
.-narrow .set-row > .set-name { width: 14; }
.-narrow #kick-list { margin-left: 0; }
"""

PLAYERS = [("mpv (recommended)", ""), ("IINA", "iina"), ("VLC", "vlc")]
QUALITIES = ["best", "1080p60", "720p60", "720p", "480p", "360p", "audio_only"]


def _name(platform):
    txt = Text()
    txt.append("● ", style=channels.COLOR[platform])
    txt.append(channels.LABEL[platform], style="bold #eef2fa")
    return txt


class SettingsPane(VerticalScroll):
    def compose(self) -> ComposeResult:
        with Vertical(classes="set-section", id="sec-accounts") as v:
            v.border_title = t("Accounts").upper()
            with Horizontal(classes="set-row"):
                yield Static(_name("twitch"), classes="set-name")
                yield Static("", classes="set-value", id="twitch-state")
                yield Button("", id="twitch-btn")
            with Horizontal(classes="set-row"):
                yield Static(_name("youtube"), classes="set-name")
                yield Static("", classes="set-value", id="google-state")
                yield Button("", id="google-btn")
            with Horizontal(classes="set-row"):
                yield Static(_name("kick"), classes="set-name")
                yield Static("", classes="set-value", id="kick-state")
                yield Button(t("Remove"), id="kick-remove")
                yield Button(t("Add"), id="kick-add", variant="primary")
            yield OptionList(id="kick-list")
        with Vertical(classes="set-section", id="sec-player") as v:
            v.border_title = t("Player").upper()
            with Horizontal(classes="set-row"):
                yield Static(t("Rewind"), classes="set-name")
                yield Static(t("go back in live streams, even to before you opened them"), classes="set-value")
                yield Switch(value=bool(config.get("rewind", True)), id="set-rewind")
            with Horizontal(classes="set-row"):
                yield Static(t("Chat"), classes="set-name")
                yield Static(t("open the chat sidebar when a stream starts (c toggles it)"), classes="set-value")
                yield Switch(value=bool(config.get("chat_open", False)), id="set-chat")
            with Horizontal(classes="set-row"):
                yield Static(t("One per streamer"), classes="set-name")
                yield Static(t("don't open a second player for a streamer already playing"), classes="set-value")
                yield Switch(value=bool(config.get("one_per_channel", True)), id="set-one")
            with Horizontal(classes="set-row"):
                yield Static(t("Video player"), classes="set-name")
                yield Static(t("IINA and VLC play the stream without rewind or chat."), classes="set-value")
                cur = config.get("player") or ""
                cur = "" if cur == "mpv" else cur
                opts = [(t(n), v) for n, v in PLAYERS]
                if cur and cur not in [v for _, v in PLAYERS]:
                    opts.append((cur, cur))
                yield Select(opts, value=cur, allow_blank=False, id="set-player")
            with Horizontal(classes="set-row"):
                yield Static(t("Quality"), classes="set-name")
                yield Static("", classes="set-value")
                q = config.get("quality", "best")
                yield Select([(x, x) for x in dict.fromkeys([*QUALITIES, q])], value=q, allow_blank=False, id="set-quality")
            yield Static(t("Rewind and chat work with mpv, using openlive's own player look."), classes="set-note")
        with Vertical(classes="set-section", id="sec-general") as v:
            v.border_title = t("General").upper()
            with Horizontal(classes="set-row"):
                yield Static(t("Platforms"), classes="set-name")
                yield Static("", classes="set-value", id="platforms-state")
                yield Button(t("Choose"), id="platforms-btn")
            with Horizontal(classes="set-row"):
                yield Static(t("Language"), classes="set-name")
                yield Static(t("takes effect next time you open openlive"), classes="set-value")
                yield Select([("English", "en"), ("Español", "es")], value=i18n.LANG, allow_blank=False, id="set-lang")
            yield Static(t("Settings file: {path}", path=str(config.config_path())), classes="set-note")

    def on_mount(self):
        self.sync()

    def sync(self):
        """Refresh what depends on the app's state (sign-ins, lists)."""
        app = self.app
        demo = getattr(app, "demo", False)
        if app.auth:
            self.query_one("#twitch-state", Static).update(t("Signed in as {login}", login=app.auth.get("login", "")))
        else:
            self.query_one("#twitch-state", Static).update(t("Not signed in"))
        self.query_one("#twitch-btn", Button).label = t("Sign out") if app.auth else t("Sign in")
        if app.gauth:
            self.query_one("#google-state", Static).update(t("Signed in with Google: {name}", name=app.gauth.get("name", "")))
        else:
            self.query_one("#google-state", Static).update(t("Not signed in (your subscriptions come from Google)"))
        self.query_one("#google-btn", Button).label = t("Sign out") if app.gauth else t("Sign in")
        kicks = [] if demo else channels.load()["kick"]
        self.query_one("#kick-state", Static).update(t("{n} channel(s) in your list", n=len(kicks)))
        ol = self.query_one("#kick-list", OptionList)
        keep = ol.highlighted
        ol.clear_options()
        ol.add_options([Option(c.get("name") or c["id"], id=c["id"]) for c in kicks])
        ol.display = bool(kicks)
        if kicks:
            ol.highlighted = min(keep or 0, len(kicks) - 1)
        self.query_one("#kick-remove", Button).disabled = not kicks
        self.query_one("#platforms-state", Static).update(", ".join(channels.LABEL[p] for p in app.platforms) or "—")

    def on_button_pressed(self, event):
        app, bid = self.app, event.button.id
        event.stop()
        if bid == "twitch-btn":
            app.action_logout() if app.auth else app.action_login()
        elif bid == "google-btn":
            app.action_google_logout() if app.gauth else app.action_google_login()
        elif bid == "kick-add":
            app.action_add("kick")
        elif bid == "kick-remove":
            ol = self.query_one("#kick-list", OptionList)
            if ol.highlighted is not None:
                app.remove_channel("kick", ol.get_option_at_index(ol.highlighted).id)
        elif bid == "platforms-btn":
            app.action_platforms()
        self.sync()

    def on_switch_changed(self, event):
        key, default = {"set-rewind": ("rewind", True), "set-chat": ("chat_open", False),
                        "set-one": ("one_per_channel", True)}.get(event.switch.id, (None, None))
        if key and bool(event.value) != bool(config.get(key, default)):
            config.save_setting(key, bool(event.value))

    def on_select_changed(self, event):
        sid, v = event.select.id, event.value
        if sid == "set-player" and (v or None) != config.get("player"):
            config.save_setting("player", v or None)
        elif sid == "set-quality" and v != config.get("quality", "best"):
            config.save_setting("quality", None if v == "best" else v)
        elif sid == "set-lang" and v != config.get("lang", i18n.LANG):
            config.save_setting("lang", v)
