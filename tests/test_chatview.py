from PIL import Image

from openlive import chatview


def test_pieces_split_text_emoji_and_emotes():
    # Twitch counts emote positions in characters; "Kappa" is 5-9 here
    assert chatview.pieces("hola Kappa 😂🔥 ok", "25:5-9") == [
        ("text", "hola "), ("emote", "25"), ("text", " "), ("emoji", "😂"), ("emoji", "🔥"), ("text", " ok")]
    # joined emoji show their first part; skin tones and variation selectors are dropped
    assert chatview.pieces("👩‍💻👍🏽❤️") == [("emoji", "👩"), ("emoji", "👍"), ("emoji", "❤")]
    assert chatview.pieces("🇪🇸") == [("emoji", "🇪🇸")]
    assert chatview.emote_ranges("25:0-4,12-16/bad id:1-2/1902:6-10") == [(0, 4, "25"), (6, 10, "1902"), (12, 16, "25")]


def test_name_colours_stay_readable():
    assert chatview.name_color("a", "#FF0000") == (255, 0, 0, 255)
    assert chatview.name_color("a", "#000010") in chatview.NAME_COLORS  # too dark for the panel


def view_with(n):
    emote = Image.new("RGBA", (56, 56), (200, 100, 50, 255))
    v = chatview.ChatView(emote_image=lambda eid: emote)
    v.channel, v.status = "chan", "joined"
    for i in range(n):
        v.add({"n": f"user{i}", "c": "", "t": f"message {i} Kappa 😂 " + "word " * (i % 7), "e": f"25:{10 + len(str(i))}-{14 + len(str(i))}"})
    return v


def test_render_draws_the_sidebar_and_maps_clicks():
    v = view_with(50)
    img, x0 = v.render(1280, 720)
    assert img.size == (int(1280 * chatview.RATIO), 720) and x0 == 1280 - img.width
    assert {h[4] for h in v.hits} == {"hide", "pause", "write"}
    hide = next(h for h in v.hits if h[4] == "hide")
    assert v.click((hide[0] + hide[2]) / 2, (hide[1] + hide[3]) / 2) == "hide"
    assert v.click(x0 + 5, 700) is None
    long = {"n": "x", "c": "", "t": "a" * 400, "e": ""}  # one huge word is cut, never wider than the panel
    v.add(long)
    v.render(1280, 720)
    _, lines = v._measure(long, v._last_w)
    assert len(lines) > 2 and all(x + a[4] <= v._last_w + 1 for line in lines for x, a in line)


def test_scrolling_up_freezes_the_chat_and_counts_new_messages():
    v = view_with(200)
    v.render(1280, 720)
    v.scroll_by(5)
    assert v.frozen and v.scroll > 0
    before = v.scroll
    v.add({"n": "late", "c": "", "t": "hi", "e": ""})
    assert v.new == 1 and v.scroll > before  # the view stays on the same messages
    v.render(1280, 720)
    assert any(h[4] == "resume" for h in v.hits)
    v.resume()
    assert not v.frozen and v.new == 0
    v.toggle_pause()
    assert v.paused and v.frozen
    v.scroll_by(10_000)  # can't scroll past the oldest message
    v.render(1280, 720)
    assert v.scroll == v.max_scroll


def test_keeps_the_last_2000_messages():
    v = chatview.ChatView()
    for i in range(2100):
        v.add({"n": "a", "c": "", "t": str(i), "e": ""})
    assert len(v.msgs) == 2000 and v.msgs[0]["t"] == "100"
