# Changelog

## 0.1.0 — unreleased

First public version, rewritten from a personal shell script.

- Terminal dashboard (Textual): Live, Following, Browse and Search tabs.
- Sign in with Twitch by entering a code on twitch.tv/activate. No keys to create or paste.
- Watch in your own player (mpv, IINA or VLC) through streamlink; open the channel or its chat in the browser.
- Favourites on top, filter, click a header to sort, auto refresh.
- Just run `openlive`; `--text`, `--demo` and `--lang` are the only flags.
- Kick and YouTube live streams next to Twitch, each with its own colour; show or hide them with t, k, y.
- Kick / YouTube channel lists you keep in openlive (a adds, x removes); import YouTube subscriptions from Google Takeout.
- Sign in with Google (a code, like Twitch) to bring your YouTube subscriptions; RSS + cheap API checks keep quota low.
- Kick channel search as you type in the add dialog.
- Rewind live streams in mpv, even to before you opened them (Twitch and Kick to the stream start, YouTube up to ~1 h with DVR); End returns to live. openlive runs mpv with its own setup: a control bar in openlive's colours and a Twitch chat sidebar (c hides it).
- The player's chat shows emoji and Twitch emotes, keeps 2000 messages (scroll back with the wheel; it waits and counts new ones), can be paused, and lets you write (Enter). Writing asks Twitch for `user:write:chat`.
- Search covers Twitch, Kick and YouTube at once, one section per platform, and works without a Twitch sign-in.
- New player look: vector icons, volume slider (↑/↓, remembered), live pill, tooltips, draggable timeline, full-screen button. The chat starts closed; c or its button opens it.
- Settings tab (5): accounts, Kick channels, rewind, chat, player, quality, language.
- First-run platform picker (p to change it later). Optional YouTube Data API key.
- English and Spanish.
