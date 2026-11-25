"""Textual TUI."""
import time
from datetime import datetime

from rich.text import Text
from textual import events, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.command import Hit, Hits, Provider
from textual.containers import Horizontal, Vertical
from textual.theme import Theme
from textual.widgets import DataTable, Footer, Input, Static, TabbedContent, TabPane

from . import channels, config, demo, google, kick, onboard, player, twitch, youtube
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
TWITCH_ONLY = ("browse", "search")
CACHE = "cache.json"
SHORT = {"twitch": "TW", "kick": "KI", "youtube": "YT"}

CSS = """
Screen { background: #0f1420; }
#topbar { height: 1; background: #141b2a; padding: 0 1; }
#brand { width: auto; color: #f2cc8f; text-style: bold; margin-right: 2; }
.chip { width: auto; margin-right: 2; }
.chip:hover { background: #222c42; }
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
.detail { height: 2; color: #d6deeb; padding: 0 1; background: #141b2a; text-wrap: nowrap; text-overflow: ellipsis; }
.empty { height: auto; color: #7c879f; padding: 1 1; display: none; }
.-narrow #brand, .-narrow #status, .-narrow #who { display: none; }
""" + onboard.CSS


class Commands(Provider):
    async def search(self, query: str) -> Hits:
        app = self.app
        cmds = [(t("Sign in with Twitch"), app.action_login), (t("Sign out of Twitch"), app.action_logout),
                (t("Sign in with Google (YouTube subscriptions)"), app.action_google_login), (t("Sign out of Google"), app.action_google_logout),
                (t("Add Kick or YouTube channels"), app.action_add), (t("Choose platforms"), app.action_platforms),
                (t("Refresh now"), app.action_refresh)]
        matcher = self.matcher(query)
        for name, fn in cmds:
            if (score := matcher.match(name)) > 0:
                yield Hit(score, matcher.highlight(name), fn)


class Chip(Static):
    """● Platform in the top bar; click toggles it."""

    def __init__(self, platform, **kw):
        super().__init__(classes="chip", **kw)
        self.platform = platform

    def paint(self, on):
        c = channels.COLOR[self.platform]
        txt = Text()
        txt.append("● ", style=c if on else DIM)
        txt.append(channels.LABEL[self.platform], style=FG if on else f"{DIM} strike")
        self.update(txt)
        self.tooltip = t("press {key} to show or hide", key=channels.KEY[self.platform])

    def on_click(self, event: events.Click):
        self.app.action_toggle(self.platform)


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
        yield DataTable(id=f"table-{self.kind}", cursor_type="row", zebra_stripes=True)
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
        cols = [("fav", "", 2), ("plat", "", 2), ("name", t("Channel"), 18)]
        if not narrow: cols.append(("game", t("Category"), 22))
        cols.append(("viewers", t("Viewers"), 8))
        if not narrow: cols.append(("uptime", t("Uptime"), 8))
        used = sum(c[2] for c in cols) + 2 * (len(cols) + 1) + 2
        cols.append(("title", t("Title"), max(12, w - used)))
        return cols

    def visible(self):
        q = self.query_one(Input).value.strip().lower() if self.kind != "search" else ""
        on = self.app.platform_on
        rows = [r for r in self.rows if r.get("platform", "twitch") in on and (not q or q in r["login"].lower() or q in r["name"].lower()
                or q in r["game"].lower() or q in r["title"].lower())]
        favs = self.app.favs
        fav = lambda r: channels.row_key(r) in favs
        if self.sort_key:
            key = {"name": lambda r: r["name"].lower(), "game": lambda r: r["game"].lower(), "viewers": lambda r: r["viewers"],
                   "uptime": lambda r: uptime_secs(r["started_at"]), "title": lambda r: r["title"].lower(), "fav": fav,
                   "plat": lambda r: r.get("platform", "")}[self.sort_key]
            rows.sort(key=key, reverse=self.sort_rev)
        elif self.kind == "following":
            rows.sort(key=lambda r: (not fav(r), not r["live"], -r["viewers"], r["name"].lower()))
        elif self.kind != "search":
            rows.sort(key=lambda r: (not fav(r), -r["viewers"]))
        return rows

    def render_rows(self):
        dt = self.table
        cur = channels.row_key(self.shown[dt.cursor_row]) if self.shown and 0 <= dt.cursor_row < len(self.shown) else None
        self.shown = self.visible()
        cols = self.columns()
        dt.clear(columns=True)
        for key, label, width in cols:
            if key == self.sort_key: label = f"{label} {'▼' if self.sort_rev else '▲'}"
            dt.add_column(label, width=width, key=key)
        favs = self.app.favs
        tw = cols[-1][2]
        for r in self.shown:
            p = r.get("platform", "twitch")
            cells = []
            for key, _, _ in cols:
                if key == "fav":
                    cells.append(Text("★", style=ACCENT) if channels.row_key(r) in favs else Text(""))
                elif key == "plat":
                    cells.append(Text(SHORT[p], style=f"bold {channels.COLOR[p]}"))
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
            dt.add_row(*cells, key=channels.row_key(r))
        if cur:
            for i, r in enumerate(self.shown):
                if channels.row_key(r) == cur:
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
            d.update(Text(t("↑↓ move · Enter watch · o open in browser · c chat · f favourite · a add channel · click a header to sort"), style=DIM))
            return
        p = r.get("platform", "twitch")
        out = Text(no_wrap=True, overflow="ellipsis")
        out.append(r["name"], style=f"bold {BRIGHT}")
        out.append(f"  {channels.LABEL[p]}", style=channels.COLOR[p])
        if r["live"]:
            out.append("  ● " + t("live"), style=LIVE_C)
            if r["game"]: out.append(f"  {r['game']}", style=game_color(r["game"]))
            if r["viewers"]: out.append(f"  {human_full(r['viewers'])} {t('viewers')}", style=FG)
            if r["started_at"]: out.append(f"  {t('for {time}', time=uptime(r['started_at']))}", style=MUTED)
            if r["language"]: out.append(f"  {r['language'].upper()}", style=INFO_C)
            out.append("\n" + clip(r["title"], 400), style=FG)
        else:
            out.append("  " + t("offline"), style=DIM)
            hint = t("Enter opens the channel in the browser.")
            if p in channels.LISTED: hint += "  " + t("x removes it from your list.")
            out.append("\n" + hint, style=MUTED)
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
        Binding("o", "web", t("Browser")),
        Binding("c", "chat", t("Chat")),
        Binding("f", "fav", t("Favourite")),
        Binding("a", "add", t("Add")),
        Binding("slash", "filter", t("Search")),
        Binding("r", "refresh", t("Refresh")),
        Binding("x", "remove", t("Remove"), show=False),
        Binding("p", "platforms", t("Platforms"), show=False),
        Binding("l", "login", t("Sign in"), show=False),
        Binding("g", "google_login", "Google", show=False),
        Binding("escape", "unfocus", "", show=False),
        *[Binding(channels.KEY[p], f"toggle('{p}')", "", show=False) for p in channels.ALL],
        *[Binding(str(i + 1), f"tab('{k}')", "", show=False) for i, k in enumerate(TABS)],
    ]

    def __init__(self, demo_mode=False):
        super().__init__()
        self.demo = demo_mode
        self.auth = None
        self.client = None
        self.gauth = None
        self.skipped = set()   # setup steps already offered this session
        self.yt_at = 0.0       # last YouTube check (signed in: every few minutes, it costs API quota)
        self.favs = {"lunacodes", "kick:emberfox"} if demo_mode else config.favourites()
        self.platforms = list(channels.ALL) if demo_mode else (config.enabled_platforms() or [])
        self.platform_on = set(self.platforms)
        self.src = {"twitch": [], "twitch_follow": None, "kick": [], "youtube": []}
        self.loaded = set()
        self.busy = 0
        self.last_ok = None
        self.warning = ""

    def compose(self) -> ComposeResult:
        with Horizontal(id="topbar"):
            yield Static("◈ openlive", id="brand")
            for p in channels.ALL:
                yield Chip(p, id=f"chip-{p}")
            yield Static("", id="who")
            yield Static("", id="status")
        with TabbedContent(initial="live"):
            for k, label in zip(TABS, (t("Live"), t("Following"), t("Browse"), t("Search"))):
                with TabPane(label, id=k):
                    pane = StreamPane(k, classes="box", id=f"pane-{k}")
                    pane.border_title = (label + (" · Twitch" if k in TWITCH_ONLY else "")).upper()
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
            self.src.update(twitch=d["live"], twitch_follow=d["following"], kick=d["kick"], youtube=d["youtube"])
            self.pane("browse").set_rows(d["browse"])
            self.loaded |= {"twitch", "following", "browse", "kick", "youtube"}
            self.rebuild()
            self.last_ok = datetime.now()
            self.update_bar()
            self.pane("live").table.focus()
            return
        cached = config.read_json(CACHE) or {}
        for k in ("twitch", "youtube"):  # Kick playback links expire: never reuse them
            self.src[k] = cached.get(k, []) or []
        self.gauth = google.load_auth()
        self.auth = twitch.load_auth()
        if self.auth:
            self.client = twitch.Client(self.auth)
        self.rebuild()
        self.update_bar()
        self.pane("live").table.focus()
        if not self.platforms:
            self.call_after_refresh(self.action_platforms, True)
        else:
            self.start()

    def start(self):
        """After the platforms are known: load, then offer whatever setup is still missing."""
        self.load_live()
        self.next_setup()

    def next_setup(self):
        """One step at a time: Twitch sign-in, Google sign-in, then channels for empty lists. Each is offered once."""
        if self.demo: return
        lists = channels.load()
        steps = [("twitch", "twitch" in self.platforms and not self.auth, self.action_login),
                 ("google", "youtube" in self.platforms and not self.gauth and not lists["youtube"], self.action_google_login),
                 ("add", any(p in self.platforms and not lists[p] and not (p == "youtube" and self.gauth) for p in channels.LISTED), self.action_add)]
        for name, needed, fn in steps:
            if needed and name not in self.skipped:
                self.skipped.add(name)
                self.call_after_refresh(fn)
                return

    # ── data ──
    def rebuild(self):
        live = list(self.src["twitch"])
        for p in channels.LISTED:
            live += [r for r in self.src[p] if r["live"]]
        follow = []
        if self.src["twitch_follow"] is not None:
            by = {r["login"]: r for r in self.src["twitch"]}
            follow = [by.get(r["login"], r) for r in self.src["twitch_follow"]]
        for p in channels.LISTED:
            follow += self.src[p]
        en = set(self.platforms)
        self.pane("live").set_rows([r for r in live if r.get("platform", "twitch") in en])
        self.pane("following").set_rows([r for r in follow if r.get("platform", "twitch") in en])

    def load_live(self, force=True):
        if self.demo: return
        if "twitch" in self.platforms and self.client:
            self.load_twitch("live")
        lists = channels.load()
        if "kick" in self.platforms and lists["kick"]:
            self.load_listed("kick", lists["kick"])
        elif not lists["kick"]:
            self.src["kick"] = []
        if "youtube" in self.platforms and (lists["youtube"] or self.gauth):
            if force or not self.gauth or time.time() - self.yt_at > 150:
                self.yt_at = time.time()
                self.load_listed("youtube", lists["youtube"])
        elif not lists["youtube"] and not self.gauth:
            self.src["youtube"] = []
        self.rebuild()

    def _save_cache(self):
        config.write_json(CACHE, {"twitch": self.src["twitch"], "youtube": self.src["youtube"]})

    @work(thread=True, group="twitch")
    def load_twitch(self, kind):
        if not self.client: return
        self.call_from_thread(self._busy, 1)
        try:
            if kind == "live":
                rows = [twitch.norm_stream(s) for s in self.client.followed_live()]
                self.call_from_thread(self._set_src, "twitch", rows)
            elif kind == "following":
                rows = [twitch.norm_followed(c) for c in self.client.followed_channels()]
                self.call_from_thread(self._set_src, "twitch_follow", rows, "following")
            elif kind == "browse":
                rows = [twitch.norm_stream(s) for s in self.client.top_streams(config.get("browse_language"))]
                self.call_from_thread(self._loaded, "browse", rows)
        except twitch.NotSignedIn:
            self.call_from_thread(self._signed_out)
        except twitch.TwitchError as e:
            self.call_from_thread(self._warn, f"Twitch: {e}")
        finally:
            self.call_from_thread(self._busy, -1)

    @work(thread=True)
    def load_listed(self, platform, chans):
        self.call_from_thread(self._busy, 1)
        try:
            if platform == "kick":
                rows, errors = kick.check([c["id"] for c in chans])
            else:
                rec, extra = self.gauth, []
                if rec:
                    try:
                        chans = youtube.merge(chans, google.subscriptions(rec))
                    except google.NotSignedIn:
                        rec = None
                        self.call_from_thread(self._google_signed_out)
                    except google.GoogleError as e:
                        extra.append(f"Google: {e}")
                rows, errors = youtube.check(chans, rec)
                errors += extra
            self.call_from_thread(self._set_src, platform, rows)
            if errors:
                self.call_from_thread(self._warn, t("{n} channel(s) couldn't be read", n=len(errors)))
        finally:
            self.call_from_thread(self._busy, -1)

    @work(thread=True, group="search", exclusive=True)
    def run_search(self, query):
        if self.demo:
            self.call_from_thread(self._loaded, "search", demo.search(query))
            return
        if not self.client:
            self.call_from_thread(self._warn, t("Search needs a Twitch sign-in"))
            return
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

    def _set_src(self, key, rows, loaded=None):
        self.src[key] = rows
        self.loaded.add(loaded or key)
        self.rebuild()
        self._save_cache()
        self.warning, self.last_ok = "", datetime.now()
        self.update_bar()

    def _loaded(self, kind, rows):
        self.loaded.add(kind)
        self.pane(kind).set_rows(rows)
        self.warning, self.last_ok = "", datetime.now()
        self.update_bar()

    def _warn(self, msg):
        self.warning = clip(msg, 44)
        self.update_bar()

    def _signed_out(self):
        self.auth, self.client = None, None
        self.src.update(twitch=[], twitch_follow=None)
        self.rebuild()
        self.update_bar()
        self.action_login()

    def auto_refresh(self):
        if self.demo: return
        self.load_live(force=False)
        if self.current == "following" and self.client and "twitch" in self.platforms:
            self.load_twitch("following")
        elif self.current == "browse" and self.client:
            self.load_twitch("browse")

    def repaint_uptimes(self):
        self.pane(self.current).render_rows()

    # ── top bar ──
    def update_bar(self):
        for p in channels.ALL:
            chip = self.query_one(f"#chip-{p}", Chip)
            chip.display = p in self.platforms
            chip.paint(p in self.platform_on)
        who = Text()
        n = sum(1 for r in self.pane("live").shown if r["live"])
        if "twitch" in self.platforms:
            if self.auth:
                who.append(self.auth["login"], style=MUTED)
            else:
                who.append(t("Twitch: not signed in · l"), style=WARN_C)
            who.append("   ")
        if "youtube" in self.platforms and not self.demo:
            if self.gauth:
                who.append("▶ " + self.gauth.get("name", "YouTube"), style=MUTED)
            else:
                who.append(t("YouTube: sign in · g"), style=WARN_C)
            who.append("   ")
        who.append(t("{n} live now", n=n), style=MUTED)
        if self.demo: who.append("   " + t("demo data"), style=WARN_C)
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
            return t("Nothing matches the filter, or its platform is hidden.")
        if kind in TWITCH_ONLY and not self.auth:
            return t("This tab needs a Twitch sign-in (press l).")
        if kind not in TWITCH_ONLY:
            lists = channels.load() if not self.demo else {"kick": [1], "youtube": [1]}
            usable = (self.auth and "twitch" in self.platforms) or (self.gauth and "youtube" in self.platforms) \
                or any(p in self.platforms and lists[p] for p in channels.LISTED)
            if not usable:
                if "twitch" in self.platforms:
                    return t("Sign in with Twitch (l) or add Kick / YouTube channels (a).")
                return t("Add the Kick / YouTube channels you watch with a.")
        if kind == "browse" and kind not in self.loaded:
            return t("Loading…")
        return {"live": t("Nobody you follow is live right now. Browse (3) shows the top streams on Twitch."),
                "following": t("No channels yet. Follow some on Twitch, or press a to add Kick / YouTube channels."),
                "browse": t("No streams found."),
                "search": t("Type a channel or game above and press Enter.")}[kind]

    # ── actions ──
    def on_tabbed_content_tab_activated(self, event):
        kind = event.pane.id
        if kind == "following" and self.client and "twitch" in self.platforms and self.src["twitch_follow"] is None:
            self.load_twitch("following")
        elif kind == "browse" and "browse" not in self.loaded and self.client:
            self.load_twitch("browse")
        p = self.pane(kind)
        (p.query_one(Input) if kind == "search" and not p.rows else p.table).focus()

    def action_tab(self, kind):
        self.query_one(TabbedContent).active = kind

    def action_toggle(self, platform):
        if platform not in self.platforms: return
        self.platform_on ^= {platform}
        for k in TABS:
            self.pane(k).render_rows()
        self.update_bar()

    def action_refresh(self):
        if self.demo:
            self.notify(t("Demo mode: nothing to refresh."), timeout=2)
            return
        self.load_live()
        if self.current == "following" and self.client and "twitch" in self.platforms:
            self.load_twitch("following")
        elif self.current == "browse" and self.client:
            self.load_twitch("browse")

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
            if not self.demo: player.open_web(r)
            return
        if self.demo:
            self.notify(t("Demo mode: would open {name} in your player.", name=r["name"]), timeout=3)
            return
        ok, why = player.play(r, r["title"])
        if ok:
            self.notify(t("Opening {name}…", name=r["name"]), timeout=3)
        elif why == "no-streamlink":
            self.notify(t("streamlink isn't installed. Reinstall openlive or run: pipx install streamlink"), severity="error", timeout=8)
        else:
            self.notify(t("No video player found. Install mpv (https://mpv.io), IINA or VLC, or set player in the config."),
                        severity="error", timeout=8)

    def action_web(self):
        if (r := self.selected()) and not self.demo: player.open_web(r)

    def action_chat(self):
        if (r := self.selected()) and not self.demo: player.open_chat(r)

    def action_fav(self):
        r = self.selected()
        if not r: return
        self.favs ^= {channels.row_key(r)}
        if not self.demo: config.save_favourites(self.favs)
        for k in TABS:
            self.pane(k).render_rows()

    def action_add(self):
        if isinstance(self.screen, onboard.AddChannelScreen): return
        r = self.selected()
        plats = [p for p in (self.platforms if not self.demo else channels.ALL)
                 if p in channels.LISTED and not (p == "youtube" and self.gauth)]  # signed in: YouTube comes from Google
        if not plats:
            self.notify(t("Your YouTube channels come from your Google subscriptions."))
            return
        self.push_screen(onboard.AddChannelScreen(plats, r.get("platform") if r else None), self._after_add)

    def _after_add(self, added):
        if added and not self.demo:
            self.load_live()

    def action_remove(self):
        r = self.selected()
        if not r or r.get("platform") not in channels.LISTED: return
        if self.demo:
            self.notify(t("Demo mode: nothing to remove."), timeout=2)
            return
        lists = channels.load()
        if channels.remove(lists, r["platform"], r["login"]):
            channels.save(lists)
            self.src[r["platform"]] = [x for x in self.src[r["platform"]] if x["login"] != r["login"]]
            self.rebuild()
            self.update_bar()
            self.notify(t("Removed {name} from your {platform} list.", name=r["name"], platform=channels.LABEL[r["platform"]]), timeout=3)
        elif r["platform"] == "youtube" and self.gauth:
            self.notify(t("That channel comes from your YouTube subscriptions."), timeout=3)

    def action_platforms(self, first_run=False):
        if self.demo or isinstance(self.screen, onboard.PlatformsScreen): return
        self.push_screen(onboard.PlatformsScreen(self.platforms or ["twitch"], first_run), self._after_platforms)

    def _after_platforms(self, chosen):
        if not chosen:
            return
        first = not self.platforms
        self.platforms = chosen
        self.platform_on = set(chosen)
        config.save_platforms(chosen)
        self.rebuild()
        self.update_bar()
        if first:
            self.start()
        else:
            self.load_live()

    def action_login(self):
        if self.demo or isinstance(self.screen, onboard.LoginScreen): return
        self.push_screen(onboard.LoginScreen(), self._after_login)

    def _after_login(self, rec):
        if rec:
            self.auth, self.client = rec, twitch.Client(rec)
            self.loaded.discard("browse")
            self.src["twitch_follow"] = None
            self.notify(t("Signed in as {login}", login=rec["login"]), timeout=3)
            if "twitch" not in self.platforms:
                self._after_platforms([*self.platforms, "twitch"])
            self.load_twitch("live")
            if self.current == "following":
                self.load_twitch("following")
        self.update_bar()
        self.next_setup()

    def action_google_login(self):
        if self.demo or isinstance(self.screen, onboard.LoginScreen): return
        self.push_screen(onboard.LoginScreen("google"), self._after_google_login)

    def _after_google_login(self, rec):
        if rec:
            self.gauth = rec
            self.notify(t("Signed in as {login}", login=rec.get("name", "YouTube")), timeout=3)
            if "youtube" not in self.platforms:
                self._after_platforms([*self.platforms, "youtube"])
            self.yt_at = time.time()
            self.load_listed("youtube", channels.load()["youtube"])
        self.update_bar()
        self.next_setup()

    def _google_signed_out(self):
        self.gauth = None
        self.update_bar()

    def action_google_logout(self):
        if self.demo: return
        google.logout()
        self.gauth = None
        self.load_live()
        self.update_bar()

    def action_logout(self):
        if self.demo: return
        twitch.logout()
        self.auth, self.client = None, None
        self.src.update(twitch=[], twitch_follow=None)
        self.loaded.discard("browse")
        self._save_cache()
        for k in TWITCH_ONLY:
            self.pane(k).set_rows([])
        self.rebuild()
        self.update_bar()


def make_app(demo_mode=False):
    return OpenLive(demo_mode)
