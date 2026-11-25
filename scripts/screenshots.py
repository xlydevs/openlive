"""Regenerate docs/screenshots/*.svg from --demo data: python scripts/screenshots.py"""
import asyncio
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from openlive import config, i18n  # noqa: E402

config.set_data_dir(tempfile.mkdtemp(prefix="openlive-shots-"))
config.OFFLINE = True
OUT = ROOT / "docs" / "screenshots"


async def shoot(lang, keys, name, size=(140, 36)):
    i18n.set_lang(lang)
    from openlive.tui import make_app
    app = make_app(demo_mode=True)
    async with app.run_test(size=size) as pilot:
        await pilot.pause(0.3)
        for k in keys:
            await pilot.press(k)
            await pilot.pause(0.05)
        await pilot.pause(0.3)
        app.save_screenshot(str(OUT / f"{name}.svg"))


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    await shoot("en", ["down", "down"], "live")
    await shoot("en", ["2", "down"], "following")
    await shoot("en", ["3"], "browse")
    await shoot("en", ["4", "slash", *"lantern", "enter"], "search")
    await shoot("es", ["down"], "live-es")
    await shoot("en", ["down"], "narrow", size=(80, 24))
    await shoot("en", ["a"], "add-channels")


asyncio.run(main())
