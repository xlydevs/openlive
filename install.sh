#!/bin/sh
# openlive installer for macOS and Linux. Nothing needs to be installed first:
#   curl -LsSf https://raw.githubusercontent.com/xlydevs/openlive/main/install.sh | sh
# It installs uv (a single program that brings its own Python), then openlive, then mpv if it's missing.
# Uninstall with: uv tool uninstall openlive
set -eu

SRC="https://github.com/xlydevs/openlive/archive/refs/heads/main.tar.gz"

say() { printf '\033[1;33m==>\033[0m %s\n' "$1"; }
warn() { printf '\033[1;31m==>\033[0m %s\n' "$1"; }
have() { command -v "$1" >/dev/null 2>&1; }

if ! have curl; then
    warn "curl is needed to install openlive. Install it with your system's package manager and run this again."
    exit 1
fi

# 1. uv
if ! have uv; then
    say "Installing uv (it brings its own Python, nothing else is needed)…"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    export PATH
fi

# 2. openlive
say "Installing openlive…"
uv tool install --force --python 3.12 "openlive @ $SRC"
uv tool update-shell >/dev/null 2>&1 || true

# 3. mpv, the video player openlive sets up for rewind and chat
if have mpv || [ -x /Applications/mpv.app/Contents/MacOS/mpv ]; then
    say "mpv is already installed."
elif [ "$(uname)" = "Darwin" ]; then
    BREW=""
    for b in brew /opt/homebrew/bin/brew /usr/local/bin/brew; do
        if have "$b" || [ -x "$b" ]; then BREW="$b"; break; fi
    done
    if [ -n "$BREW" ]; then
        say "Installing mpv with Homebrew…"
        "$BREW" install mpv || warn "Couldn't install mpv. Try later: brew install mpv"
    else
        warn "openlive plays streams in mpv. Install it from https://mpv.io/installation/"
        warn "(or install Homebrew from https://brew.sh, then run: brew install mpv)"
    fi
else
    CMD=""
    if have apt-get; then CMD="apt-get install -y mpv"
    elif have dnf; then CMD="dnf install -y mpv"
    elif have pacman; then CMD="pacman -S --noconfirm mpv"
    elif have zypper; then CMD="zypper --non-interactive install mpv"
    elif have apk; then CMD="apk add mpv"
    fi
    if [ -n "$CMD" ] && have sudo; then
        say "Installing mpv (sudo asks for your password)…"
        # shellcheck disable=SC2086
        sudo $CMD </dev/tty || warn "Couldn't install mpv. Try later: sudo $CMD"
    else
        warn "openlive plays streams in mpv. Install it from https://mpv.io/installation/"
    fi
fi

say "Done. Open a new terminal and run: openlive"
say "Just looking? Try: openlive --demo"
