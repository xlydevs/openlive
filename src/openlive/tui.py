"""Textual TUI."""
from datetime import datetime

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.command import Hit, Hits, Provider
from textual.containers import Horizontal, Vertical
from textual.theme import Theme
from textual.widgets import DataTable, Footer, Input, Static, TabbedContent, TabPane

from . import config, demo, onboard, player, twitch
from .common import (
    ACCENT,
    BG,
    BRIGHT,
    DIM,
    ERR_C,
    FG,
    INFO_C,
    LIVE_C,
    MUTED,
    OK_C,
    PANEL,
    SURF,
    WARN_C,
    clip,
    game_color,
    human,
    human_full,
    uptime,
    uptime_secs,
)
from .i18n import t

THEME = Theme(name="openlive", primary=ACCENT, secondary="#c3a6ff", accent=ACCENT, foreground=FG,
              background=BG, surface=SURF, panel=PANEL, success=OK_C, warning=WARN_C, error=ERR_C, dark=True,
              variables={"block-cursor-background": "#2a3754", "block-cursor-foreground": BRIGHT,
                         "block-cursor-text-style": "none", "block-cursor-blurred-background": "#202a40",
                         "block-cursor-blurred-foreground": FG, "block-hover-background": "#1c2538",
                         "footer-key-foreground": ACCENT, "input-selection-background": "#33415f"})

TABS = ("live", "following", "browse", "search")
CACHE = "cache.json"

CSS = """
Screen { background: #0f1420; }
#topbar { height: 1; background: #141b2a; padding: 0 1; }
#brand { width: auto; color: #f2cc8f; text-style: bold; margin-right: 2; }
#who { width: 1fr; color: #7c879f; }
#status { width: auto; color: #7c879f; }
TabbedContent { height: 1fr; }
Tabs { background: #0f1420; }
Tab { color: #7c879f; }
Tab.-active { color: #f2cc8f; text-style: bold; }
Underline > .underline--bar { color: #f2cc8f; background: #263044; }
TabPane { padding: 0; }
.box { border: round #263044; border-title-color: #7c879f; border-title-style: bold; padding: 0 1; height: 1fr; background: #0f1420; }
.filter { height: 1; border: none; background: #141b2a; color: #d6deeb; padding: 0 1; margin-bottom: 1; }
.filter:focus { background: #1a2335; }
DataTable { height: 1fr; background: #0f1420; scrollbar-size-vertical: 1; }
DataTable > .datatable--header { background: #141b2a; color: #7c879f; text-style: bold; }
DataTable > .datatable--even-row { background: #121826; }
DataTable > .datatable--odd-row { background: #0f1420; }
DataTable > .datatable--header-hover { background: #222c42; }
.detail { height: 2; color: #d6deeb; padding: 0 1; background: #141b2a; }
.empty { height: auto; color: #7c879f; padding: 1 1; display: none; }
.-narrow #brand, .-narrow #status { display: none; }
""" + onboard.CSS


class Commands(Provider):
    async def search(self, query: str) -> Hits:
        app = self.app
        cmds = [(t("Sign in with Twitch"), app.action_login), (t("Sign out"), app.action_logout),
                (t("Refresh now"), app.action_refresh)]
        matcher = self.matcher(query)
        for name, fn in cmds:
            if (score := matcher.match(name)) > 0:
                yield Hit(score, matcher.highlight(name), fn)


class StreamPane(Vertical):
    """A filter/search line, the table of channels and a detail line for the selected one."""

    def __init__(self, kind, **kw):
        super().__init__(**kw)
        self.kind = kind
        self.rows, self.shown = [], []
        self.sort_key, self.sort_rev = (None, False)

    def compose(self) -> ComposeResult:
        ph = t("search any channel or game on Twitch, then Enter") if self.kind == "search" else t("filter by channel, game or title")
        yield Input(placeholder="/ " + ph, classes="filter", id=f"filter-{self.kind}")
        yield Static("", classes="empty", id=f"empty-{self.kind}")
        dt = DataTable(id=f"table-{self.kind}", cursor_type="row", zebra_stripes=True)
        yield dt
        yield Static("", classes="detail", id=f"detail-{self.kind}")

    @property
    def table(self) -> DataTable:
        return self.query_one(DataTable)

    def set_rows(self, rows):
        self.rows = rows
        self.render_rows()

    def columns(self):
        w = self.table.size.width or self.size.width or 100
        narrow = w < 90
        cols = [("fav", "", 2), ("name", t("Channel"), 18)]
        if not narrow: cols.append(("game", t("Category"), 22))
        cols.append(("viewers", t("Viewers"), 8))
        if not narrow: cols.append(("uptime", t("Uptime"), 8))
        used = sum(c[2] for c in cols) + 2 * (len(cols) + 1) + 2
        cols.append(("title", t("Title"), max(12, w - used)))
        return cols

    def visible(self):
        q = self.query_one(Input).value.strip().lower() if self.kind != "search" else ""
        rows = [r for r in self.rows if not q or q in r["login"] or q in r["name"].lower()
                or q in r["game"].lower() or q in r["title"].lower()]
        favs = self.app.favs
        if self.sort_key:
            k = self.sort_key
            key = {"name": lambda r: r["login"], "game": lambda r: r["game"].lower(), "viewers": lambda r: r["viewers"],
                   "uptime": lambda r: uptime_secs(r["started_at"]), "title": lambda r: r["title"].lower(),
                   "fav": lambda r: r["login"] in favs}[k]
            rows.sort(key=key, reverse=self.sort_rev)
        elif self.kind == "following":
            rows.sort(key=lambda r: (r["login"] not in favs, not r["live"], -r["viewers"], r["login"]))
        elif self.kind != "search":
            rows.sort(key=lambda r: (r["login"] not in favs, -r["viewers"]))
        return rows

    def render_rows(self):
        dt = self.table
        cur = self.shown[dt.cursor_row]["login"] if self.shown and 0 <= dt.cursor_row < len(self.shown) else None
        self.shown = self.visible()
        cols = self.columns()
        dt.clear(columns=True)
        for key, label, width in cols:
            if key == self.sort_key: label = f"{label} {'▼' if self.sort_rev else '▲'}"
            dt.add_column(label, width=width, key=key)
        favs = self.app.favs
        tw = cols[-1][2]
        for r in self.shown:
            cells = []
            for key, _, _ in cols:
                if key == "fav":
                    cells.append(Text("★", style=ACCENT) if r["login"] in favs else Text(""))
                elif key == "name":
                    c = Text("● ", style=LIVE_C if r["live"] else DIM)
                    c.append(r["name"], style=BRIGHT if r["live"] else MUTED)
                    cells.append(c)
                elif key == "game":
                    cells.append(Text(clip(r["game"], 22), style=game_color(r["game"])))
                elif key == "viewers":
                    cells.append(Text(human(r["viewers"]) if r["live"] and r["viewers"] else ("" if r["live"] else t("offline")),
                                      style=FG if r["live"] else DIM, justify="right"))
                elif key == "uptime":
                    cells.append(Text(uptime(r["started_at"]) if r["live"] else "", style=MUTED, justify="right"))
                elif key == "title":
                    cells.append(Text(clip(r["title"], tw), style=FG))
            dt.add_row(*cells, key=r["login"])
        if cur:
            for i, r in enumerate(self.shown):
                if r["login"] == cur:
                    dt.move_cursor(row=i)
                    break
        empty = self.query_one(".empty")
        empty.display = not self.shown
        empty.update(self.app.empty_message(self.kind, bool(self.rows)))
        self.update_detail()

    def selected(self):
        dt = self.table
        if self.shown and 0 <= dt.cursor_row < len(self.shown):
            return self.shown[dt.cursor_row]
        return None

    def update_detail(self):
        r = self.selected()
        d = self.query_one(".detail")
        if not r:
            d.update(Text(t("↑↓ move · Enter watch · o open on Twitch · c chat · f favourite · click a header to sort"), style=DIM))
            return
        out = Text(no_wrap=True, overflow="ellipsis")
        out.append(r["name"], style=f"bold {BRIGHT}")
        if r["live"]:
            out.append("  ● " + t("live"), style=LIVE_C)
            if r["game"]: out.append(f"  {r['game']}", style=game_color(r["game"]))
            if r["viewers"]: out.append(f"  {human_full(r['viewers'])} {t('viewers')}", style=FG)
            if r["started_at"]: out.append(f"  {t('for {time}', time=uptime(r['started_at']))}", style=MUTED)
            if r["language"]: out.append(f"  {r['language'].upper()}", style=INFO_C)
            out.append("\n" + clip(r["title"], 400), style=FG)
        else:
            out.append("  " + t("offline"), style=DIM)
            out.append("\n" + t("Enter opens the channel on Twitch."), style=MUTED)
        d.update(out)

    def on_data_table_row_highlighted(self, event):
        self.update_detail()

    def on_data_table_header_selected(self, event):
        k = str(event.column_key.value)
        if self.sort_key == k:
            if self.sort_rev == (k not in ("viewers", "uptime", "fav")):  # second click: back to default order
                self.sort_key, self.sort_rev = None, False
            else:
                self.sort_rev = not self.sort_rev
        else:
            self.sort_key, self.sort_rev = k, k in ("viewers", "uptime", "fav")
        self.render_rows()

    def on_data_table_row_selected(self, event):
        self.app.action_watch()

    def on_input_changed(self, event):
        if self.kind != "search":
            self.render_rows()

    def on_input_submitted(self, event):
        query = event.value.strip().lstrip("/").strip()
        if self.kind == "search" and query:
            self.app.run_search(query)
        self.table.focus()

    def on_resize(self, event):
        self.render_rows()


class OpenLive(App):
    TITLE = "openlive"
    CSS = CSS
    COMMANDS = App.COMMANDS | {Commands}
    HORIZONTAL_BREAKPOINTS = [(0, "-narrow"), (96, "-medium"), (150, "-wide")]
    BINDINGS = [
        Binding("q", "quit", t("Quit")),
        Binding("enter", "watch", t("Watch"), show=True, priority=False),
        Binding("o", "web", t("Open on Twitch")),
        Binding("c", "chat", t("Chat")),
        Binding("f", "fav", t("Favourite")),
        Binding("slash", "filter", t("Search")),
        Binding("r", "refresh", t("Refresh")),
        Binding("l", "login", t("Sign in"), show=False),
        Binding("escape", "unfocus", "", show=False),
        *[Binding(str(i + 1), f"tab('{k}')", "", show=False) for i, k in enumerate(TABS)],
    ]

    def __init__(self, demo_mode=False):
        super().__init__()
        self.demo = demo_mode
        self.auth = None
        self.client = None
        self.favs = set() if demo_mode else config.favourites()
        if demo_mode: self.favs = {"lunacodes", "quietfox"}
        self.loaded = set()
        self.busy = 0
        self.last_ok = None
        self.warning = ""

    def compose(self) -> ComposeResult:
        with Horizontal(id="topbar"):
            yield Static("◈ openlive", id="brand")
            yield Static("", id="who")
            yield Static("", id="status")
        with TabbedContent(initial="live"):
            for k, label in zip(TABS, (t("Live"), t("Following"), t("Browse"), t("Search"))):
                with TabPane(label, id=k):
                    pane = StreamPane(k, classes="box", id=f"pane-{k}")
                    pane.border_title = label.upper()
                    yield pane
        yield Footer()

    def pane(self, kind) -> StreamPane:
        return self.query_one(f"#pane-{kind}", StreamPane)

    @property
    def current(self):
        return self.query_one(TabbedContent).active or "live"

    def on_mount(self):
        self.register_theme(THEME)
        self.theme = "openlive"
        self.set_interval(config.refresh_seconds(), self.auto_refresh)
        self.set_interval(30, self.repaint_uptimes)
        if self.demo:
            self.auth = {"login": demo.LOGIN}
            d = demo.data()
            for k in ("live", "following", "browse"):
                self.pane(k).set_rows(d[k])
                self.loaded.add(k)
            self.last_ok = datetime.now()
            self.update_bar()
            self.pane("live").table.focus()
            return
        cached = config.read_json(CACHE) or {}
        if cached.get("live"):
            self.pane("live").set_rows(cached["live"])
        self.auth = twitch.load_auth()
        self.update_bar()
        if self.auth:
            self.client = twitch.Client(self.auth)
            self.load("live")
        else:
            self.call_after_refresh(self.action_login)
        self.pane("live").table.focus()

    # ── top bar ──
    def update_bar(self):
        who = Text()
        if self.auth:
            who.append("● ", style=OK_C)
            who.append(self.auth["login"], style=FG)
            n = sum(1 for r in self.pane("live").rows if r["live"])
            who.append(f"   {t('{n} live now', n=n)}", style=MUTED)
            if self.demo: who.append("   " + t("demo data"), style=WARN_C)
        else:
            who.append("○ " + t("not signed in · press l"), style=WARN_C)
        self.query_one("#who").update(who)
        st = Text()
        if self.busy:
            st.append("⟳ " + t("loading…"), style=INFO_C)
        elif self.warning:
            st.append("⚠ " + self.warning, style=WARN_C)
        elif self.last_ok:
            st.append(f"✓ {self.last_ok:%H:%M}", style=OK_C)
        self.query_one("#status").update(st)

    def empty_message(self, kind, has_rows):
        if has_rows:
            return t("Nothing matches the filter.")
        if not self.auth:
            return t("Sign in with Twitch to see who you follow (press l).")
        if kind not in self.loaded and kind != "search":
            return t("Loading…")
        return {"live": t("Nobody you follow is live right now. Browse (3) shows the top streams."),
                "following": t("You don't follow any channel yet."),
                "browse": t("No streams found."),
                "search": t("Type a channel or game above and press Enter.")}[kind]

    # ── loading ──
    @work(thread=True, group="load")
    def load(self, kind):
        if not self.client: return
        self.call_from_thread(self._busy, 1)
        try:
            if kind == "live":
                rows = [twitch.norm_stream(s) for s in self.client.followed_live()]
                config.write_json(CACHE, {"live": rows})
            elif kind == "following":
                live = {r["login"]: r for r in self.pane("live").rows}
                if "live" not in self.loaded:
                    live = {s["user_login"]: twitch.norm_stream(s) for s in self.client.followed_live()}
                rows = [live.get(c["broadcaster_login"]) or twitch.norm_followed(c) for c in self.client.followed_channels()]
            elif kind == "browse":
                rows = [twitch.norm_stream(s) for s in self.client.top_streams(config.get("browse_language"))]
            else:
                return
            self.call_from_thread(self._loaded, kind, rows)
        except twitch.NotSignedIn:
            self.call_from_thread(self._signed_out)
        except twitch.TwitchError as e:
            self.call_from_thread(self._warn, str(e))
        finally:
            self.call_from_thread(self._busy, -1)

    @work(thread=True, group="search", exclusive=True)
    def run_search(self, query):
        if self.demo:
            self.call_from_thread(self._loaded, "search", demo.search(query))
            return
        if not self.client: return
        self.call_from_thread(self._busy, 1)
        try:
            found = [twitch.norm_search(c) for c in self.client.search(query)]
            live = [r["login"] for r in found if r["live"]]
            if live:  # search results have no viewer counts: ask for them
                by = {s["user_login"]: twitch.norm_stream(s) for s in self.client.streams_by_login(live)}
                found = [by.get(r["login"], r) for r in found]
            self.call_from_thread(self._loaded, "search", found)
        except twitch.NotSignedIn:
            self.call_from_thread(self._signed_out)
        except twitch.TwitchError as e:
            self.call_from_thread(self._warn, str(e))
        finally:
            self.call_from_thread(self._busy, -1)

    def _busy(self, d):
        self.busy = max(0, self.busy + d)
        self.update_bar()

    def _loaded(self, kind, rows):
        self.loaded.add(kind)
        self.pane(kind).set_rows(rows)
        self.warning, self.last_ok = "", datetime.now()
        self.update_bar()

    def _warn(self, msg):
        self.warning = clip(msg, 40)
        self.update_bar()

    def _signed_out(self):
        self.auth, self.client = None, None
        self.update_bar()
        self.action_login()

    def auto_refresh(self):
        if self.demo or not self.client: return
        self.load("live")
        if self.current in ("following", "browse"):
            self.load(self.current)

    def repaint_uptimes(self):
        self.pane(self.current).render_rows()

    # ── actions ──
    def on_tabbed_content_tab_activated(self, event):
        kind = event.pane.id
        if kind not in self.loaded and kind != "search":
            self.load(kind)
        p = self.pane(kind)
        (p.query_one(Input) if kind == "search" and not p.rows else p.table).focus()

    def action_tab(self, kind):
        self.query_one(TabbedContent).active = kind

    def action_refresh(self):
        if self.demo:
            self.notify(t("Demo mode: nothing to refresh."), timeout=2)
            return
        if not self.client:
            self.action_login()
            return
        self.load(self.current if self.current != "search" else "live")

    def action_filter(self):
        self.pane(self.current).query_one(Input).focus()

    def action_unfocus(self):
        p = self.pane(self.current)
        inp = p.query_one(Input)
        if self.focused is inp and inp.value and self.current != "search":
            inp.value = ""
        p.table.focus()

    def selected(self):
        return self.pane(self.current).selected()

    def action_watch(self):
        if isinstance(self.focused, Input): return
        r = self.selected()
        if not r: return
        if not r["live"]:
            player.open_web(r["login"])
            return
        if self.demo:
            self.notify(t("Demo mode: would open {name} in your player.", name=r["name"]), timeout=3)
            return
        ok, why = player.play(r["login"], r["title"])
        if ok:
            self.notify(t("Opening {name}…", name=r["name"]), timeout=3)
        elif why == "no-streamlink":
            self.notify(t("streamlink isn't installed. Reinstall openlive or run: pipx install streamlink"), severity="error", timeout=8)
        else:
            self.notify(t("No video player found. Install mpv (https://mpv.io), IINA or VLC, or set player in the config."),
                        severity="error", timeout=8)

    def action_web(self):
        if (r := self.selected()) and not self.demo: player.open_web(r["login"])

    def action_chat(self):
        if (r := self.selected()) and not self.demo: player.open_chat(r["login"])

    def action_fav(self):
        r = self.selected()
        if not r: return
        self.favs ^= {r["login"]}
        if not self.demo: config.save_favourites(self.favs)
        for k in TABS:
            self.pane(k).render_rows()

    def action_login(self):
        if self.demo or isinstance(self.screen, onboard.LoginScreen): return
        self.push_screen(onboard.LoginScreen(), self._after_login)

    def _after_login(self, rec):
        if not rec:
            self.update_bar()
            return
        self.auth, self.client = rec, twitch.Client(rec)
        self.loaded.clear()
        self.notify(t("Signed in as {login}", login=rec["login"]), timeout=3)
        self.update_bar()
        self.load("live")
        if self.current in ("following", "browse"):
            self.load(self.current)

    def action_logout(self):
        if self.demo: return
        twitch.logout()
        config.delete(CACHE)
        self.auth, self.client = None, None
        self.loaded.clear()
        for k in TABS:
            self.pane(k).set_rows([])
        self.update_bar()


def make_app(demo_mode=False):
    return OpenLive(demo_mode)
