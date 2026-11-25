"""Plain-text output (--text, or when stdout is not a terminal)."""
from . import channels, config, google, kick, twitch, youtube
from .common import clip, human, uptime
from .i18n import t


def render(rows, out=print, width=100):
    live = sorted((r for r in rows if r["live"]), key=lambda r: -r["viewers"])
    if not live:
        out(t("Nobody on your lists is live right now."))
        return
    multi = len({r.get("platform", "twitch") for r in live}) > 1
    nw = max(len(r["name"]) for r in live)
    gw = min(24, max(len(r["game"]) for r in live))
    for r in live:
        tag = f"{channels.LABEL[r.get('platform', 'twitch')]:<8}" if multi else ""
        head = f"{tag}{r['name']:<{nw}}  {clip(r['game'], gw):<{gw}}  {human(r['viewers']):>6}  {uptime(r['started_at']):>7}  "
        out(head + clip(r["title"], max(10, width - len(head))))


def run(demo_mode=False, out=print):
    if demo_mode:
        from . import demo
        d = demo.data()
        render(d["live"] + d["kick"] + d["youtube"], out)
        return 0
    platforms = config.enabled_platforms() or list(channels.ALL)
    rows, problems = [], []
    auth = twitch.load_auth()
    if "twitch" in platforms:
        if not auth:
            problems.append(t("Twitch: not signed in. Open openlive and press l to sign in."))
        else:
            try:
                rows += [twitch.norm_stream(s) for s in twitch.Client(auth).followed_live()]
            except twitch.TwitchError as e:
                problems.append(f"Twitch: {e}")
    lists = channels.load()
    if "kick" in platforms and lists["kick"]:
        r, err = kick.check([c["id"] for c in lists["kick"]])
        rows += r; problems += err
    grec = google.load_auth()
    if "youtube" in platforms and (lists["youtube"] or grec):
        chans = lists["youtube"]
        if grec:
            try:
                chans = youtube.merge(chans, google.subscriptions(grec))
            except google.GoogleError as e:
                problems.append(f"Google: {e}")
                grec = None
        r, err = youtube.check(chans, grec)
        rows += r; problems += err
    render(rows, out)
    for p in problems:
        out(f"  {t('error')}: {p}" if ":" not in p[:8] else f"  {p}")
    return 1 if problems and not rows else 0
