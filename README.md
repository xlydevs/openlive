# openlive

**Who you watch is live right now?** `openlive` is a terminal dashboard of the Twitch, Kick and YouTube channels you watch that are streaming at this moment. Pick one and it plays in your own video player (mpv, IINA or VLC), not in a browser tab.

It runs on your computer and talks only to those sites. Twitch sign-in takes a code, not keys: you open twitch.tv/activate, check the code and press Activate. Kick and YouTube need no account at all.

[Español](README.es.md)

![openlive demo](docs/demo.gif)

## Features

- **Live first, every platform in one list.** The channels you watch that are live, with category, viewers, uptime and title, tagged `TW`, `KI` or `YT`. It refreshes on its own every minute.
- **Watch without the browser.** `Enter` opens the stream through streamlink in mpv, IINA or VLC. `o` opens the channel in the browser, `c` pops out its chat.
- **Twitch follows, no keys.** Sign in once with a code; your follows come from your account. No developer account, no Client ID, no secret to copy.
- **Kick and YouTube lists.** Add channels by name or link with `a`, remove them with `x`. Import your YouTube subscriptions from Google Takeout. YouTube shows live streams only, never videos.
- **Show or hide a platform.** Click its chip in the top bar, or press `t`, `k` or `y`.
- **Following, Browse and Search.** Everyone you watch (live first), the top streams on Twitch, and a search for any Twitch channel or game.
- **Favourites on top.** `f` pins a channel to the top of every list.
- **Mouse and keyboard.** Click a header to sort, `/` to filter. Works from 80 columns up.
- **English and Spanish.**

| Following | Add Kick / YouTube channels |
|---|---|
| ![Following](docs/screenshots/following.svg) | ![Add channels](docs/screenshots/add-channels.svg) |

## Install

You need Python 3.11+ and a video player: [mpv](https://mpv.io) (recommended), [IINA](https://iina.io) on macOS, or [VLC](https://www.videolan.org/vlc/). streamlink is installed with openlive.

```bash
pipx install openlive        # or: uv tool install openlive
openlive
```

On macOS, `brew install mpv` gets you a player.

The first time, openlive asks which platforms you watch. Twitch then asks you to sign in; Kick and YouTube ask for a few channels.

Try it without any account. The demo uses made-up channels and reads and writes nothing:

```bash
openlive --demo
```

From source:

```bash
git clone https://github.com/xlydevs/openlive && cd openlive
uv venv && uv pip install -e ".[dev]"
.venv/bin/openlive
```

## Usage

```text
openlive               open the dashboard (first run: pick platforms, sign in)
openlive <channel>     watch a Twitch channel right away
openlive --text        print who is live and exit (also used when piping: openlive | less)
openlive --login       sign in to Twitch from the terminal, without the dashboard
openlive --logout      sign out of Twitch and delete the saved token
openlive --demo        made-up channels
openlive --lang es     interface language (default: system locale)
```

**Keys:**
- `1`–`4` switch tabs: Live, Following, Browse, Search.
- `↑`/`↓` move, `Enter` watch (offline channels open in the browser).
- `o` open in the browser, `c` chat, `f` favourite.
- `a` add Kick / YouTube channels, `x` remove the selected one from your list.
- `t`, `k`, `y` show or hide Twitch, Kick, YouTube; `p` choose platforms.
- `/` filter the list (in Search: type a channel or game and press `Enter`), `Esc` clear it.
- `r` refresh, `l` sign in to Twitch, `Ctrl+P` command palette (sign out is there), `q` quit.
- Click a column header to sort; click again to reverse.

**YouTube subscriptions:** in [Google Takeout](https://takeout.google.com/takeout/custom/youtube) pick only YouTube → subscriptions, export, unzip, and paste the path of `subscriptions.csv` in the `a` dialog.

## How it works

Twitch uses its [device code flow](https://dev.twitch.tv/docs/authentication/getting-tokens-oauth/#device-code-grant-flow) and asks for one permission, `user:read:follows`, so it can read who you follow and nothing else. It can't chat, follow or change anything on your account.

Kick and YouTube have no public way for an app like this to read who you follow, so openlive keeps its own list of channels and checks each one.

| Platform | What | Where it comes from |
|---|---|---|
| Twitch | Live, Following | Helix `streams/followed`, `channels/followed` |
| Twitch | Browse, Search | Helix `streams` (top by viewers; `browse_language` filters it), `search/channels` |
| Kick | live check | `kick.com/api/v2/channels/<slug>` (public, no key) |
| YouTube | live check | the channel's `/live` page, or with an API key: RSS feed + `videos.list` |
| All | playback | `streamlink <url> best --player <yours>` |

**Honest note:** Kick's channel API and YouTube's `/live` page are not official, documented APIs. They work today and need no keys, but either site can change them and break the check until openlive is updated. With a [YouTube Data API key](https://console.cloud.google.com/apis/library/youtube.googleapis.com) (`[youtube] api_key` in the config, free quota is plenty) YouTube uses the official API instead.

Files it keeps:

| File | What |
|---|---|
| `~/.config/openlive/config.toml` | optional settings: platforms, player, quality, language, YouTube key… see [config.example.toml](config.example.toml) |
| `~/.local/share/openlive/auth.json` | your Twitch sign-in token (only readable by you) |
| `~/.local/share/openlive/channels.json` | your Kick and YouTube channels |
| `~/.local/share/openlive/favourites.json` | your favourites |
| `~/.local/share/openlive/cache.json` | last Live list, so the app opens instantly |

On Windows they live in `%APPDATA%\openlive` and `%LOCALAPPDATA%\openlive`. `$OPENLIVE_CONFIG` and `$OPENLIVE_DATA_DIR` override them.

**Not supported:** chat inside the terminal, VODs, clips and regular YouTube videos, Browse and Search on Kick or YouTube (no public API for it), `openlive <channel>` for Kick or YouTube. Ads and sub-only streams behave as they do in streamlink.

**Privacy:** nothing is sent anywhere but Twitch, Kick and YouTube. No analytics.

## Development

```bash
uv venv && uv pip install -e ".[dev]"
.venv/bin/python -m pytest -q        # tests never touch the network or your real token
uvx ruff check .
.venv/bin/python scripts/screenshots.py   # docs/screenshots/*.svg from demo data
vhs scripts/demo.tape                     # docs/demo.gif
```

Using your own Twitch app: create a **Public** app at [dev.twitch.tv](https://dev.twitch.tv/console/apps/create) (redirect `http://localhost`), then set `client_id` in the config or `$OPENLIVE_CLIENT_ID`.

openlive is not affiliated with or endorsed by Twitch, Kick or YouTube.

## License

[MIT](LICENSE)
