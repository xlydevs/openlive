"""Command line entry point."""
import argparse
import shutil
import sys
import tempfile

from . import __version__, config, i18n
from .i18n import t


def main(argv=None):
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--lang", choices=i18n.SUPPORTED)
    known, _ = pre.parse_known_args(argv)
    if known.lang:
        i18n.set_lang(known.lang)

    ap = argparse.ArgumentParser(prog="openlive", description=t("Who you follow is live on Twitch, in the terminal."))
    ap.add_argument("channel", nargs="?", help=t("watch this channel right away"))
    ap.add_argument("--text", action="store_true", help=t("print who is live and exit, no TUI"))
    ap.add_argument("--login", action="store_true", help=t("sign in with Twitch from the terminal"))
    ap.add_argument("--logout", action="store_true", help=t("sign out and forget the saved token"))
    ap.add_argument("--demo", action="store_true", help=t("explore with made-up channels (reads nothing, writes nothing)"))
    ap.add_argument("--lang", choices=i18n.SUPPORTED, help=t("interface language"))
    ap.add_argument("-V", "--version", action="version", version=f"openlive {__version__}")
    args = ap.parse_args(argv)

    if args.demo:
        config.set_data_dir(tempfile.mkdtemp(prefix="openlive-demo-"))
        config.OFFLINE = True
    from . import twitch
    if args.logout:
        twitch.logout()
        print(t("Signed out."))
        return 0
    if args.login:
        if not config.client_id():
            print(t("No Twitch Client ID set (client_id in {path}).", path=config.config_path()), file=sys.stderr)
            return 1
        try:
            rec = twitch.run_terminal_login(config.client_id())
        except twitch.TwitchError as e:
            print(f"{t('error')}: {e}", file=sys.stderr)
            return 1
        print(t("Signed in as {login}", login=rec["login"]))
        return 0
    if args.channel:
        from . import player
        ok, why = player.play(args.channel.lower().removeprefix("https://www.twitch.tv/").strip("/"))
        if not ok:
            print(t("No video player found. Install mpv (https://mpv.io), IINA or VLC, or set player in the config.")
                  if why == "no-player" else t("streamlink isn't installed. Reinstall openlive or run: pipx install streamlink"),
                  file=sys.stderr)
            return 1
        return 0
    if args.text or not sys.stdout.isatty():
        from .text import run
        return run(args.demo, out=lambda s: print(s))
    from .tui import make_app
    make_app(args.demo).run()
    if args.demo:
        shutil.rmtree(config.DATA, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
