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

    ap = argparse.ArgumentParser(prog="openlive", description=t("Who you watch is live on Twitch, Kick and YouTube, in the terminal."))
    ap.add_argument("--text", action="store_true", help=t("print who is live and exit, no TUI"))
    ap.add_argument("--demo", action="store_true", help=t("explore with made-up channels (reads nothing, writes nothing)"))
    ap.add_argument("--lang", choices=i18n.SUPPORTED, help=t("interface language"))
    ap.add_argument("-V", "--version", action="version", version=f"openlive {__version__}")
    args = ap.parse_args(argv)

    if args.demo:
        config.set_data_dir(tempfile.mkdtemp(prefix="openlive-demo-"))
        config.OFFLINE = True
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
