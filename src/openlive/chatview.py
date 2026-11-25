"""Draws the chat sidebar as an image (Pillow), so it can show colour emoji and Twitch emotes, which mpv's own
text renderer can't. The chat bridge hands each frame to mpv with overlay-add.

ChatView keeps up to 2000 messages, a scroll position and a paused state; render() returns the panel and
click() maps a click on it to an action.
"""
import glob
import os
import re
import sys
from collections import deque

from PIL import Image, ImageDraw, ImageFont

RATIO = 0.27  # share of the window the sidebar takes (same as openlive_ui.lua)
KEEP = 2000


def _rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5)) + (255,)


BG, SURF, PANEL, BORDER = _rgb("#0f1420"), _rgb("#141b2a"), _rgb("#1a2335"), _rgb("#263044")
FG, BRIGHT, MUTED, DIM = _rgb("#d6deeb"), _rgb("#eef2fa"), _rgb("#7c879f"), _rgb("#4b5570")
ACCENT, INFO = _rgb("#f2cc8f"), _rgb("#9cc8e8")
NAME_COLORS = [_rgb(h) for h in ("#9cc8e8", "#a5d68f", "#c3a6ff", "#f4a98a", "#63d3c4", "#e8d36a", "#ff9fb2", "#7fb2ff")]


# ───────────────────────── fonts ─────────────────────────

def _first(*patterns):
    for p in patterns:
        hits = sorted(glob.glob(p, recursive=True))
        if hits:
            return hits[0]
    return None


def font_files():
    """(regular, bold, fallback for other scripts, colour emoji) font paths for this system; any may be None."""
    if sys.platform == "darwin":
        return (("/System/Library/Fonts/HelveticaNeue.ttc", 0), ("/System/Library/Fonts/HelveticaNeue.ttc", 1),
                (_first("/System/Library/Fonts/Supplemental/Arial Unicode.ttf", "/Library/Fonts/Arial Unicode.ttf"), 0),
                (_first("/System/Library/Fonts/Apple Color Emoji.ttc"), 0))
    if sys.platform == "win32":
        f = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
        return ((os.path.join(f, "segoeui.ttf"), 0), (os.path.join(f, "segoeuib.ttf"), 0),
                (_first(os.path.join(f, "seguisym.ttf"), os.path.join(f, "msyh.ttc")), 0), (os.path.join(f, "seguiemj.ttf"), 0))
    roots = ["/usr/share/fonts/**/", "/usr/local/share/fonts/**/", os.path.expanduser("~/.local/share/fonts/**/")]
    find = lambda *names: _first(*[r + n for r in roots for n in names])
    return ((find("NotoSans-Regular.ttf", "DejaVuSans.ttf"), 0), (find("NotoSans-Bold.ttf", "DejaVuSans-Bold.ttf"), 0),
            (find("NotoSansCJK-Regular.ttc", "DejaVuSans.ttf"), 0), (find("NotoColorEmoji.ttf"), 0))


class Fonts:
    def __init__(self, size, files=None):
        reg, bold, other, emoji = files or font_files()
        self.size = size
        self.reg = self._load(reg, size)
        self.bold = self._load(bold, size) if bold and bold[0] else self.reg
        self.other = self._load(other, size) if other and other[0] else None
        self.emoji_path = emoji[0] if emoji and emoji[0] and os.path.exists(emoji[0]) else None
        self._emoji_font, self._emoji_cache = None, {}

    @staticmethod
    def _load(spec, size):
        if spec and spec[0]:
            try:
                return ImageFont.truetype(spec[0], size, index=spec[1])
            except OSError:
                pass
        return ImageFont.load_default(size)

    def emoji(self, cluster, height):
        """A colour emoji scaled to height px, or None when the system has no emoji font."""
        key = (cluster, height)
        if key in self._emoji_cache:
            return self._emoji_cache[key]
        img = None
        if self.emoji_path:
            if self._emoji_font is None:  # bitmap emoji fonts only come in a few sizes
                for s in (64, 109, 96, 160, 48, 40, 32):
                    try:
                        self._emoji_font = ImageFont.truetype(self.emoji_path, s)
                        break
                    except OSError:
                        continue
            if self._emoji_font:
                s = self._emoji_font.size
                canvas = Image.new("RGBA", (s * 2, s * 2))
                try:
                    ImageDraw.Draw(canvas).text((0, 0), cluster, font=self._emoji_font, embedded_color=True)
                except (OSError, ValueError):
                    canvas = None
                box = canvas.getbbox() if canvas else None
                if box:
                    g = canvas.crop(box)
                    img = g.resize((max(1, round(g.width * height / g.height)), height), Image.LANCZOS)
        self._emoji_cache[key] = img
        return img


# ───────────────────────── text → pieces ─────────────────────────

def _is_emoji(cp):
    return cp >= 0x1F000 and cp <= 0x1FAFF or 0x2600 <= cp <= 0x27BF or 0x2300 <= cp <= 0x23FF or 0x2B00 <= cp <= 0x2BFF


def _skip(cp):
    """Joiners, variation selectors, skin tones and tags: without text shaping they'd draw as boxes."""
    return (cp in (0x200D, 0xFE0F, 0xFE0E, 0x20E3, 0x034F, 0x00AD) or 0x1F3FB <= cp <= 0x1F3FF or 0xE0000 <= cp <= 0xE0FFF
            or 0x200B <= cp <= 0x200F or 0x2060 <= cp <= 0x2064)  # chatters add U+E0000 to dodge the duplicate filter


def emote_ranges(tag):
    """Twitch's emotes tag ("25:0-4,12-16/1902:6-10") → [(start, end, id)] sorted by position."""
    out = []
    for part in (tag or "").split("/"):
        eid, _, spans = part.partition(":")
        if not re.fullmatch(r"[A-Za-z0-9_]+", eid or ""):
            continue
        for sp in spans.split(","):
            a, _, b = sp.partition("-")
            if a.isdigit() and b.isdigit():
                out.append((int(a), int(b), eid))
    return sorted(out)


def pieces(text, emotes=""):
    """Split a message into ("text", s), ("emoji", s) and ("emote", id) pieces."""
    out, buf = [], []

    def flush():
        if buf:
            out.append(("text", "".join(buf)))
            buf.clear()

    ranges = {a: (b, eid) for a, b, eid in emote_ranges(emotes)}
    i, after_zwj = 0, False
    while i < len(text):
        if i in ranges:
            b, eid = ranges[i]
            flush()
            out.append(("emote", eid))
            i = b + 1
            continue
        ch = text[i]
        cp = ord(ch)
        if _skip(cp):
            after_zwj = cp == 0x200D
        elif _is_emoji(cp):
            if not after_zwj:  # a joined emoji (👩‍💻) shows its first part only
                flush()
                if 0x1F1E6 <= cp <= 0x1F1FF and i + 1 < len(text) and 0x1F1E6 <= ord(text[i + 1]) <= 0x1F1FF:
                    out.append(("emoji", text[i:i + 2]))  # a flag
                    i += 1
                else:
                    out.append(("emoji", ch))
            after_zwj = False
        else:
            after_zwj = False
            buf.append(ch)
        i += 1
    flush()
    return out


def name_color(name, color):
    if color and re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        r, g, b, _ = _rgb(color)
        if r * 0.3 + g * 0.59 + b * 0.11 > 70:  # very dark name colours are unreadable on the panel
            return _rgb(color)
    h = 0
    for ch in name or "":
        h = (h * 31 + ord(ch)) % 1000003
    return NAME_COLORS[h % len(NAME_COLORS)]


# ───────────────────────── the panel ─────────────────────────

class ChatView:
    def __init__(self, emote_image=None, files=None):
        self.msgs = deque(maxlen=KEEP)
        self.status = None        # None (connecting) / "joined" / "offline"
        self.text = {}            # localized strings from the session
        self.channel = ""
        self.can_write = False
        self.paused = False
        self.scroll = 0           # px scrolled up from the newest message
        self.new = 0              # messages that arrived while paused or scrolled up
        self.emote_image = emote_image or (lambda eid: None)
        self.files = files
        self._fonts = {}
        self._layout = {}         # id(msg) → (width, height, lines)
        self.hits = []
        self.max_scroll = None

    def tr(self, key, fallback):
        return self.text.get(key) or fallback

    @property
    def frozen(self):
        return self.paused or self.scroll > 0

    def add(self, msg):
        if len(self.msgs) == self.msgs.maxlen:
            self._layout.pop(id(self.msgs[0]), None)
        self.msgs.append(msg)
        if self.frozen:
            self.new += 1
            if self._last_w:  # keep the same messages in view
                self.scroll += self._measure(msg, self._last_w)[0] + self._gap
        return True

    _last_w, _gap = 0, 0

    def forget_layouts(self):
        """An emote image arrived: sizes change."""
        self._layout.clear()

    def scroll_by(self, lines):
        step = lines * (self._fonts_for(self._last_h).size * 1.45 if self._last_h else 20)
        self.scroll = max(0, round(self.scroll + step))
        if self.max_scroll is not None:
            self.scroll = min(self.scroll, self.max_scroll)
        if self.scroll == 0 and not self.paused:
            self.new = 0

    def resume(self):
        self.paused, self.scroll, self.new = False, 0, 0

    def toggle_pause(self):
        if self.frozen:
            self.resume()
        else:
            self.paused = True

    # geometry
    _last_h = 0

    def _fonts_for(self, h):
        fs = max(14, round(17 * h / 720))
        if fs not in self._fonts:
            self._fonts = {fs: Fonts(fs, self.files)}
            self._layout.clear()
        return self._fonts[fs]

    def _atoms(self, m, f):
        """Drawable units of a message: (kind, payload, font, colour, width, is_space)."""
        lh = round(f.size * 1.45)
        out = []

        def add_text(s, font, color):
            for word in re.findall(r"\S+|\s+", s):
                if word.isspace():
                    out.append(("text", " ", font, color, font.getlength(" "), True))
                    continue
                run, run_font = "", None
                for ch in word:  # characters the main font lacks go to the fallback font
                    use = f.other if f.other and ord(ch) > 0x24F else font
                    if run and use is not run_font:
                        out.append(("text", run, run_font, color, run_font.getlength(run), False))
                        run = ""
                    run, run_font = run + ch, use
                if run:
                    out.append(("text", run, run_font, color, run_font.getlength(run), False))

        if m.get("note"):
            add_text(m["note"], f.reg, INFO)
            return out
        nc = name_color(m.get("n", ""), m.get("c", ""))
        add_text(m.get("n", ""), f.bold, nc)
        if not m.get("me"):
            add_text(":", f.bold, nc)
        out.append(("text", " ", f.reg, FG, f.reg.getlength(" "), True))
        body = nc if m.get("me") else FG
        for kind, val in pieces(m.get("t", ""), m.get("e", "")):
            if kind == "text":
                add_text(val, f.reg, body)
            elif kind == "emoji":
                img = f.emoji(val, round(f.size * 1.15))
                if img:
                    out.append(("img", img, None, None, img.width, False))
            else:
                img = self.emote_image(val)
                w = round(img.width * lh / img.height) if img else lh
                out.append(("emote", val, None, None, w, False))
        return out

    def _measure(self, m, width):
        """(height, lines) of a message wrapped to width; lines = [[(x, atom), …], …]."""
        f = self._fonts_for(self._last_h)
        cached = self._layout.get(id(m))
        if cached and cached[0] == width:
            return cached[1], cached[2]
        lh = round(f.size * 1.45)
        lines, line, x = [], [], 0
        words, word = [], []
        for a in self._atoms(m, f):
            word.append(a)
            if a[5]:
                words.append(word)
                word = []
        if word:
            words.append(word)
        for word in words:
            ww = sum(a[4] for a in word if not a[5])
            if x + ww > width and line:
                lines.append(line)
                line, x = [], 0
            for a in word:
                if a[5] and not line:
                    continue  # no space at the start of a line
                if a[4] > width - x and not a[5] and (line or a[4] > width):  # doesn't fit: cut it or wrap
                    if a[0] == "text" and len(a[1]) > 1 and a[4] > width:
                        for ch in a[1]:
                            cw = a[2].getlength(ch)
                            if x + cw > width and line:
                                lines.append(line)
                                line, x = [], 0
                            line.append((x, ("text", ch, a[2], a[3], cw, False)))
                            x += cw
                        continue
                    if line:
                        lines.append(line)
                        line, x = [], 0
                line.append((x, a))
                x += a[4]
        if line:
            lines.append(line)
        h = max(1, len(lines)) * lh
        self._layout[id(m)] = (width, h, lines)
        return h, lines

    def _draw_msg(self, img, d, lines, x0, y0, f):
        lh = round(f.size * 1.45)
        for i, line in enumerate(lines):
            y = y0 + i * lh
            for x, a in line:
                kind = a[0]
                if kind == "text":
                    d.text((x0 + x, y + lh / 2), a[1], font=a[2], fill=a[3], anchor="lm")
                elif kind == "img":
                    im = a[1]
                    img.alpha_composite(im, (round(x0 + x), round(y + (lh - im.height) / 2)))
                else:
                    em = self.emote_image(a[1])
                    if em:
                        em = em.resize((max(1, round(a[4])), lh), Image.LANCZOS) if em.size != (round(a[4]), lh) else em
                        img.alpha_composite(em.convert("RGBA"), (round(x0 + x), round(y)))

    def render(self, w, h):
        """The sidebar for a w×h window: (RGBA image, its x position)."""
        pw, x0 = int(w * RATIO), w - int(w * RATIO)
        self._last_h = h
        f = self._fonts_for(h)
        u = h / 720
        pad = max(6, round(12 * u))
        head = round(f.size * 2.6)
        lh = round(f.size * 1.45)
        self._gap = gap = round(lh * 0.25)
        inner = pw - 2 * pad
        self._last_w = inner
        img = Image.new("RGBA", (pw, h), SURF)
        d = ImageDraw.Draw(img)
        line_w = max(1, round(u))
        self.hits = []

        # messages, newest at the bottom
        top, bottom = head + pad // 2, h - pad
        if not self.msgs:
            status = {"offline": self.tr("chat_offline", "Can't reach the chat, retrying…"),
                      "joined": self.tr("chat_quiet", "Nobody has written yet.")}.get(
                self.status, self.tr("chat_connecting", "Connecting to the chat…"))
            d.text((pad, top + pad), status, font=f.reg, fill=DIM)
        y = bottom + self.scroll
        total = 0
        self.max_scroll = None  # known only once the oldest message is reached
        for m in reversed(self.msgs):
            mh, lines = self._measure(m, inner)
            y -= mh
            if y < bottom and y + mh > top:
                self._draw_msg(img, d, lines, pad, y, f)
            total += mh + gap
            if y < top and total > self.scroll + (bottom - top):
                break
            y -= gap
        else:  # reached the oldest message: that's as far as scrolling goes
            self.max_scroll = max(0, total - (bottom - top))
            if self.scroll > self.max_scroll:
                self.scroll = self.max_scroll
        d.rectangle((0, 0, pw, top - 1), fill=SURF)  # nothing scrolls over the header
        d.rectangle((0, 0, line_w - 1, h), fill=BORDER)
        d.rectangle((0, head - line_w, pw, head), fill=BORDER)

        # header: title, then buttons from the right: hide, pause, write
        bh = round(head * 0.62)
        bx = pw - pad
        by = (head - bh) // 2

        def button(width, action, draw):
            nonlocal bx
            box = (bx - width, by, bx, by + bh)
            d.rounded_rectangle(box, radius=max(3, bh // 4), fill=PANEL)
            draw(box)
            self.hits.append((x0 + box[0], box[1], x0 + box[2], box[3], action))
            bx -= width + round(6 * u)

        def x_icon(b):
            cx, cy, r = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2, bh * 0.2
            for s in (1, -1):
                d.line((cx - r, cy - r * s, cx + r, cy + r * s), fill=MUTED, width=max(2, round(2 * u)))

        def pause_icon(b):
            cx, cy, r = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2, bh * 0.2
            if self.frozen:  # play triangle: back to the live chat
                d.polygon([(cx - r * 0.8, cy - r), (cx - r * 0.8, cy + r), (cx + r, cy)], fill=ACCENT)
            else:
                bw = max(2, round(r * 0.55))
                d.rectangle((cx - r * 0.75, cy - r, cx - r * 0.75 + bw, cy + r), fill=FG)
                d.rectangle((cx + r * 0.75 - bw, cy - r, cx + r * 0.75, cy + r), fill=FG)

        button(bh, "hide", x_icon)
        button(bh, "pause", pause_icon)
        label = self.tr("write", "Write")
        lw = round(f.reg.getlength(label)) + 2 * pad
        button(lw, "write", lambda b: d.text(((b[0] + b[2]) / 2, (b[1] + b[3]) / 2), label, font=f.reg,
                                             fill=FG if self.can_write else DIM, anchor="mm"))
        title_room = bx - pad
        d.text((pad, head / 2), self.tr("chat", "Chat"), font=f.bold, fill=MUTED, anchor="lm")
        tx = pad + f.bold.getlength(self.tr("chat", "Chat")) + f.size * 0.6
        name = self.channel
        while name and tx + f.bold.getlength(name) > title_room:
            name = name[:-2] + "…" if len(name) > 2 else ""
        d.text((tx, head / 2), name, font=f.bold, fill=FG, anchor="lm")

        # "N new messages" / "back to the live chat" pill
        if self.frozen:
            label = self.tr("new_msgs", "{n} new messages").replace("{n}", str(self.new)) if self.new \
                else self.tr("paused", "Chat paused")
            pw_ = round(f.bold.getlength(label) + f.size * 2.8)
            ph = round(f.size * 2)
            px, py = (pw - pw_) // 2, h - pad - ph
            d.rounded_rectangle((px, py, px + pw_, py + ph), radius=ph // 2, fill=ACCENT)
            d.text((px + f.size * 0.9, py + ph / 2), label, font=f.bold, fill=BG, anchor="lm")
            ax, ay, r = px + pw_ - f.size * 0.9, py + ph / 2, f.size * 0.3
            d.polygon([(ax - r, ay - r * 0.5), (ax + r, ay - r * 0.5), (ax, ay + r * 0.6)], fill=BG)
            self.hits.append((x0 + px, py, x0 + px + pw_, py + ph, "resume"))
        return img, x0

    def click(self, x, y):
        """What a click at window position (x, y) does: an action name or None."""
        for x1, y1, x2, y2, action in self.hits:
            if x1 <= x <= x2 and y1 <= y <= y2:
                return action
        return None
