"""Palette, constants and formatting helpers."""
import zlib
from datetime import UTC, datetime

from . import i18n

BG, SURF, PANEL, BORDER = "#0f1420", "#141b2a", "#1a2335", "#263044"
FG, BRIGHT, MUTED, DIM = "#d6deeb", "#eef2fa", "#7c879f", "#4b5570"
ACCENT, OK_C, WARN_C, ERR_C, INFO_C = "#f2cc8f", "#a5d68f", "#f2cc8f", "#f28b82", "#9cc8e8"
LIVE_C = "#f28b82"     # the red "live" dot
TWITCH_C = "#b39ddb"   # soft Twitch purple for the brand bits

# one fixed colour per game/category, picked by name so it is the same everywhere and on every run
GAME_COLORS = ("#9cc8e8", "#a5d68f", "#c3a6ff", "#f4a98a", "#63d3c4", "#e8d36a", "#ff9fb2", "#7fb2ff",
               "#b8c4d6", "#d9a6ff", "#8fd6c1", "#f2b880")


def game_color(name):
    if not name:
        return MUTED
    return GAME_COLORS[zlib.crc32(name.lower().encode()) % len(GAME_COLORS)]


def human(n):
    n = int(n or 0)
    if n >= 1_000_000_000: return f"{n / 1e9:.2f}B"
    if n >= 1_000_000: return f"{n / 1e6:.2f}M"
    if n >= 10_000: return f"{n / 1e3:.0f}k"
    if n >= 1_000: return f"{n / 1e3:.1f}k"
    return str(n)


def human_full(n):
    s = f"{int(n or 0):,}"
    return s.replace(",", ".") if i18n.LANG == "es" else s


def parse_time(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def uptime(started_at, now=None):
    """'3h 05m' since the stream started."""
    st = parse_time(started_at)
    if not st:
        return ""
    secs = max(0, int(((now or datetime.now(UTC)) - st).total_seconds()))
    h, m = divmod(secs // 60, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


def uptime_secs(started_at, now=None):
    st = parse_time(started_at)
    return int(((now or datetime.now(UTC)) - st).total_seconds()) if st else 0


def clip(s, n):
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[: max(0, n - 1)] + "…"
