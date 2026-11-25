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


def _rows(items, rng, now):
    out = []
    for login, name, game, viewers, title, lang in items:
        out.append({"login": login, "name": name, "game": game, "viewers": viewers + rng.randint(-viewers // 20, viewers // 20),
                    "title": title, "language": lang, "tags": [lang.upper(), game.split()[0]], "live": True,
                    "started_at": (now - timedelta(minutes=rng.randint(12, 520))).isoformat().replace("+00:00", "Z")})
    return out


def data(seed=7):
    rng = random.Random(seed)
    now = datetime.now(UTC)
    live = _rows(_LIVE, rng, now)
    following = live + [{"login": o, "name": o.capitalize(), "game": "", "viewers": 0, "title": "", "started_at": "",
                         "language": "", "tags": [], "live": False} for o in _OFF]
    browse = sorted(_rows(_BROWSE, rng, now) + live, key=lambda r: -r["viewers"])
    return {"live": live, "following": following, "browse": browse}


def search(query):
    q = query.lower()
    return [r for r in data()["following"] if q in r["login"] or q in r["game"].lower()]
