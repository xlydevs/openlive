"""Made-up channels for --demo (nothing is read from or sent to Twitch)."""
import random
from datetime import UTC, datetime, timedelta

LOGIN = "demo_viewer"

_LIVE = [
    ("pixelharbor", "PixelHarbor", "Minecraft", 18400, "hardcore day 212 · building the sky bridge", "en"),
    ("lunacodes", "LunaCodes", "Software and Game Development", 2300, "writing a tiny game engine in Rust, chill vibes", "en"),
    ("noctua_gg", "Noctua_GG", "League of Legends", 41200, "climbing to challenger · !duo !setup", "es"),
    ("riverbard", "RiverBard", "Music", 960, "lofi piano requests 🎹", "en"),
    ("tacticalmoth", "TacticalMoth", "Counter-Strike", 27650, "FACEIT level 10 grind, road to 4k elo", "en"),
    ("saltyspoon", "SaltySpoon", "Just Chatting", 73100, "reacting to your worst kitchen fails", "es"),
    ("quietfox", "QuietFox", "Chess", 5400, "blitz with viewers · rated 2300+", "en"),
    ("vantablock", "Vantablock", "Speedrunning", 3100, "any% WR attempts — 2 seconds off", "en"),
    ("marrowmage", "MarrowMage", "Elden Ring", 12900, "no-hit run, boss 7 of 12", "es"),
    ("orbitalpanda", "OrbitalPanda", "Kerbal Space Program", 640, "landing on every moon, part 3", "en"),
    ("drift_kana", "Drift_Kana", "Art", 1800, "painting your pets · commissions open", "ja"),
    ("cloudlantern", "CloudLantern", "Valorant", 8700, "ranked with the squad", "es"),
]
_OFF = ["amberkite", "basaltbeat", "cometcrumb", "duskwalker", "emberowl", "frostbyte_tv", "glimmerjack", "hollowpine",
        "irisrune", "junipersky", "kelpknight", "mossbyte"]
_BROWSE = [
    ("megastreamz", "MegaStreamz", "Just Chatting", 182000, "IRL in Tokyo with chat", "en"),
    ("goalcast", "GoalCast", "EA Sports FC", 96500, "weekend league finals", "es"),
    ("arenaone", "ArenaOne", "Dota 2", 74100, "major qualifiers day 2", "en"),
]


_KICK = [
    ("emberfox", "EmberFox", "Just Chatting", 6400, "late night talk show · call-ins open", "en"),
    ("ruta_libre", "RutaLibre", "IRL", 2100, "caminando por Lisboa en directo", "es"),
]
_KICK_OFF = ["neonpike", "slatewren"]
_YT = [
    ("@cozybeatsradio", "Cozy Beats Radio", "Music", 9800, "lofi radio 24/7 — beats to study to", "en"),
    ("@starwatchlive", "StarWatch Live", "Science & Technology", 3300, "rocket launch coverage — T-minus 40 min", "en"),
]
_YT_OFF = ["@gardengrid", "@pocketkitchen"]


def _rows(items, rng, now, platform="twitch"):
    out = []
    for login, name, game, viewers, title, lang in items:
        out.append({"platform": platform, "login": login, "name": name, "game": game, "viewers": viewers + rng.randint(-viewers // 20, viewers // 20),
                    "title": title, "language": lang, "tags": [lang.upper(), game.split()[0]], "live": True,
                    "started_at": (now - timedelta(minutes=rng.randint(12, 520))).isoformat().replace("+00:00", "Z")})
    return out


def data(seed=7):
    rng = random.Random(seed)
    now = datetime.now(UTC)
    live = _rows(_LIVE, rng, now)
    following = live + [{"platform": "twitch", "login": o, "name": o.capitalize(), "game": "", "viewers": 0, "title": "", "started_at": "",
                         "language": "", "tags": [], "live": False} for o in _OFF]
    browse = sorted(_rows(_BROWSE, rng, now) + live, key=lambda r: -r["viewers"])
    kick = _rows(_KICK, rng, now, "kick") + [_off("kick", o, o.capitalize()) for o in _KICK_OFF]
    yt = _rows(_YT, rng, now, "youtube") + [_off("youtube", o, o.lstrip("@").capitalize()) for o in _YT_OFF]
    return {"live": live, "following": following, "browse": browse, "kick": kick, "youtube": yt}


def _off(platform, login, name):
    return {"platform": platform, "login": login, "name": name, "game": "", "viewers": 0, "title": "", "started_at": "",
            "language": "", "tags": [], "live": False}


def search(query):
    q = query.lower()
    return [r for r in data()["following"] if q in r["login"] or q in r["game"].lower()]


def kick_search(query):
    q = query.lower()
    rows = [(login, name, viewers) for login, name, _g, viewers, _t, _l in _KICK] + [(o, o.capitalize(), 0) for o in _KICK_OFF]
    rows += [("emberfox_clips", "EmberFoxClips", 0), ("embertalks", "EmberTalks", 0)]
    return [{"id": lo, "name": na, "followers": 1000 + v * 37, "live": v > 0} for lo, na, v in rows if q in lo][:8]
