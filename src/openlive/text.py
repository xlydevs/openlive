"""Plain-text output (--text, or when stdout is not a terminal)."""
from . import twitch
from .common import clip, human, uptime
from .i18n import t


def render(rows, out=print, width=100):
    live = sorted((r for r in rows if r["live"]), key=lambda r: -r["viewers"])
    if not live:
        out(t("Nobody you follow is live right now."))
        return
    nw = max(len(r["name"]) for r in live)
    gw = min(24, max(len(r["game"]) for r in live))
    for r in live:
        head = f"{r['name']:<{nw}}  {clip(r['game'], gw):<{gw}}  {human(r['viewers']):>6}  {uptime(r['started_at']):>7}  "
        out(head + clip(r["title"], max(10, width - len(head))))


def run(demo_mode=False, out=print):
    if demo_mode:
        from . import demo
        render(demo.data()["live"], out)
        return 0
    auth = twitch.load_auth()
    if not auth:
        out(t("Not signed in. Run openlive (or openlive --login) to sign in with Twitch."))
        return 1
    try:
        rows = [twitch.norm_stream(s) for s in twitch.Client(auth).followed_live()]
    except twitch.TwitchError as e:
        out(f"{t('error')}: {e}")
        return 1
    render(rows, out)
    return 0
