-- openlive's interface for mpv: a control bar with vector icons and a volume slider and a chat sidebar, in openlive's colours.
-- The rewind logic lives in openlive.lua, which shares the session in user-data/openlive.
-- The chat sidebar itself is drawn by openlive's chat bridge (chat.py), which shows it with overlay-add.
local mp = require "mp"

-- palette (same as the TUI)
local function c(hex) return hex:sub(6, 7) .. hex:sub(4, 5) .. hex:sub(2, 3) end
local BG, SURF, BORDER = c("#0f1420"), c("#141b2a"), c("#263044")
local FG, BRIGHT, MUTED, DIM = c("#d6deeb"), c("#eef2fa"), c("#7c879f"), c("#4b5570")
local ACCENT, LIVE, HOVER = c("#f2cc8f"), c("#f28b82"), c("#222c42")
local PLATFORM = { twitch = c("#b39ddb"), kick = c("#a5d68f"), youtube = c("#f28b82") }
local CHAT_RATIO = 0.27

local S = { text = {} }            -- session from openlive.lua
local chat_on = false
local last_move, hover_bar = 0, false
local hits, mouse, dragging, zone_top = {}, nil, nil, nil
local osc = mp.create_osd_overlay("ass-events")
local chat = mp.create_osd_overlay("ass-events")
osc.z, chat.z = 2, 1

local function tr(key, fallback) return (S.text and S.text[key]) or fallback end

-- libass can't draw colour emoji: drop them (and their joiners/variation selectors) instead of showing boxes
local function clean(s)
    s = tostring(s or ""):gsub("[\240-\244][\128-\191]+", ""):gsub("\239\184[\128-\143]", ""):gsub("\226\128\141", "")
    s = s:gsub("%s+", " "):gsub("^ ", ""):gsub(" $", "")
    return s
end

local function esc(s)
    s = tostring(s or ""):gsub("\\", "\\\226\128\139"):gsub("{", "\\{"):gsub("}", "\\}"):gsub("\n", " ")
    return s
end

local function fmt_time(sec)
    sec = math.max(0, math.floor(sec or 0))
    local h, m, s = math.floor(sec / 3600), math.floor(sec / 60) % 60, sec % 60
    if h > 0 then return string.format("%d:%02d:%02d", h, m, s) end
    return string.format("%d:%02d", m, s)
end

-- characters of a UTF-8 string, counting wide ones (CJK, emoji) as two columns
local function chars(s)
    local out = {}
    for ch in s:gmatch("[%z\1-\127\194-\244][\128-\191]*") do
        out[#out + 1] = { ch, (#ch >= 3) and 2 or 1 }
    end
    return out
end

local function rect(x1, y1, x2, y2, color, alpha)
    return string.format("{\\an7\\pos(0,0)\\bord0\\shad0\\1c&H%s&\\1a&H%s&\\p1}m %d %d l %d %d l %d %d l %d %d{\\p0}",
        color, alpha or "00", math.floor(x1), math.floor(y1), math.ceil(x2), math.floor(y1), math.ceil(x2), math.ceil(y2), math.floor(x1), math.ceil(y2))
end

local function text(x, y, an, size, color, s, extra)
    return string.format("{\\an%d\\pos(%d,%d)\\fs%d\\bord0\\shad0\\1c&H%s&%s}%s", an, math.floor(x + 0.5), math.floor(y + 0.5),
        math.floor(size), color, extra or "", s)
end

-- ───────────────────────── chat sidebar ─────────────────────────
-- openlive's chat bridge draws the sidebar itself (as an image, so it can show emoji and emotes) and puts it
-- on screen with overlay-add. This script makes room for it, forwards clicks and the mouse wheel over it, and
-- asks for the text when you write.

local function chat_x()
    local w = mp.get_osd_size()
    return w and (w - math.floor(w * CHAT_RATIO)) or nil
end

local function over_chat(m)
    local x0 = chat_x()
    return chat_on and m and x0 and m.x >= x0
end

local function render_chat()
    local w, h = mp.get_osd_size()
    if not chat_on or not w or w == 0 then
        chat.data = ""
        chat:update()
        return
    end
    -- plain panel shown until the bridge's first image covers it
    chat.res_x, chat.res_y = w, h
    local x0 = chat_x()
    chat.data = rect(x0, 0, w, h, SURF) .. "\n" .. rect(x0, 0, x0 + math.max(1, math.floor(h / 720)), h, BORDER)
    chat:update()
end

local function set_chat(on)
    chat_on = on and S.chat ~= ""
    mp.set_property_number("video-margin-ratio-right", chat_on and CHAT_RATIO or 0)
    mp.set_property_native("user-data/openlive-ui", { chat = chat_on })
    render_chat()
end

local function to_bridge(...)
    mp.commandv("script-message", "openlive-chat-ui", ...)
end

mp.register_script_message("openlive-chat-hide", function() set_chat(false) end)

local ok_input, input = pcall(require, "mp.input")
mp.register_script_message("openlive-chat-prompt", function()
    if not ok_input then
        mp.osd_message(tr("chat_no_input", "Writing needs mpv 0.38 or newer."), 3)
        return
    end
    input.get({
        prompt = tr("say", "Say") .. " › ",
        submit = function(line)
            if line and line:match("%S") then to_bridge("send", line) end
            input.terminate()
        end,
    })
end)

-- ───────────────────────── drawing helpers ─────────────────────────

local function shape(path, color, alpha)
    return string.format("{\\an7\\pos(0,0)\\bord0\\shad0\\1c&H%s&\\1a&H%s&\\p1}%s{\\p0}", color, alpha or "00", path)
end

local function n(v) return string.format("%d", math.floor(v + 0.5)) end

-- rounded rectangle path (r is clamped to half the smaller side, so a square with a big r is a circle)
local function rr_path(x1, y1, x2, y2, r)
    r = math.min(r, (x2 - x1) / 2, (y2 - y1) / 2)
    local k = r * 0.448
    return table.concat({
        "m", n(x1 + r), n(y1), "l", n(x2 - r), n(y1),
        "b", n(x2 - k), n(y1), n(x2), n(y1 + k), n(x2), n(y1 + r), "l", n(x2), n(y2 - r),
        "b", n(x2), n(y2 - k), n(x2 - k), n(y2), n(x2 - r), n(y2), "l", n(x1 + r), n(y2),
        "b", n(x1 + k), n(y2), n(x1), n(y2 - k), n(x1), n(y2 - r), "l", n(x1), n(y1 + r),
        "b", n(x1), n(y1 + k), n(x1 + k), n(y1), n(x1 + r), n(y1),
    }, " ")
end

local function rrect(x1, y1, x2, y2, r, color, alpha) return shape(rr_path(x1, y1, x2, y2, r), color, alpha) end
local function circle(cx, cy, r, color, alpha) return rrect(cx - r, cy - r, cx + r, cy + r, r, color, alpha) end

local function poly(pts)
    local out = { "m", n(pts[1]), n(pts[2]), "l" }
    for i = 3, #pts, 2 do out[#out + 1] = n(pts[i]); out[#out + 1] = n(pts[i + 1]) end
    return table.concat(out, " ")
end

-- vertical gradient made of thin strips that never overlap, from fully transparent at y1 to `alpha` at y2
local function gradient(ev, x1, y1, x2, y2, color, alpha)
    local steps = math.max(1, math.min(48, math.floor(math.abs(y2 - y1) / 3)))
    local lo, hi = math.min(y1, y2), math.max(y1, y2)
    local prev = math.floor(lo)
    for i = 1, steps do
        local nxt = math.floor(lo + (hi - lo) * i / steps + 0.5)
        if nxt > prev then
            local f = ((prev + nxt) / 2 - lo) / (hi - lo)
            if y2 < y1 then f = 1 - f end
            local a = math.floor(255 - (255 - alpha) * f ^ 1.1)
            ev[#ev + 1] = rect(math.floor(x1), prev, math.ceil(x2), nxt, color, string.format("%02X", a))
            prev = nxt
        end
    end
end

local function text_w(s, size) return #s * size * 0.56 end

-- icons, drawn centred on (cx, cy) with half-size s
local icon = {}
function icon.play(cx, cy, s) return poly({ cx - s * 0.55, cy - s * 0.75, cx + s * 0.8, cy, cx - s * 0.55, cy + s * 0.75 }) end
function icon.pause(cx, cy, s)
    local w = s * 0.32
    return rr_path(cx - s * 0.6, cy - s * 0.7, cx - s * 0.6 + w, cy + s * 0.7, w * 0.3) .. " " ..
           rr_path(cx + s * 0.6 - w, cy - s * 0.7, cx + s * 0.6, cy + s * 0.7, w * 0.3)
end
function icon.back(cx, cy, s)
    return poly({ cx + s * 0.05, cy - s * 0.6, cx - s * 0.75, cy, cx + s * 0.05, cy + s * 0.6 }) .. " " ..
           poly({ cx + s * 0.8, cy - s * 0.6, cx, cy, cx + s * 0.8, cy + s * 0.6 })
end
function icon.fwd(cx, cy, s)
    return poly({ cx - s * 0.05, cy - s * 0.6, cx + s * 0.75, cy, cx - s * 0.05, cy + s * 0.6 }) .. " " ..
           poly({ cx - s * 0.8, cy - s * 0.6, cx, cy, cx - s * 0.8, cy + s * 0.6 })
end
local function wave(x, cy, r, t)
    local k = r * 0.75
    return table.concat({ "m", n(x), n(cy - r), "b", n(x + k), n(cy - r * 0.6), n(x + k), n(cy + r * 0.6), n(x), n(cy + r),
        "l", n(x - t), n(cy + r * 0.8), "b", n(x - t + k * 0.7), n(cy + r * 0.45), n(x - t + k * 0.7), n(cy - r * 0.45),
        n(x - t), n(cy - r * 0.8) }, " ")
end
function icon.speaker(cx, cy, s, vol, muted)
    local x = cx - s * 0.35
    local out = { poly({ x - s * 0.55, cy - s * 0.25, x - s * 0.15, cy - s * 0.25, x + s * 0.25, cy - s * 0.65,
                         x + s * 0.25, cy + s * 0.65, x - s * 0.15, cy + s * 0.25, x - s * 0.55, cy + s * 0.25 }) }
    if muted or vol <= 0 then
        local a, b, t = x + s * 0.55, x + s * 1.05, s * 0.11
        out[#out + 1] = poly({ a, cy - s * 0.25 + t, a + t, cy - s * 0.25, b, cy + s * 0.25 - t, b - t, cy + s * 0.25 })
        out[#out + 1] = poly({ b - t, cy - s * 0.25, b, cy - s * 0.25 + t, a + t, cy + s * 0.25, a, cy + s * 0.25 - t })
    else
        out[#out + 1] = wave(x + s * 0.5, cy, s * 0.32, s * 0.14)
        if vol > 50 then out[#out + 1] = wave(x + s * 0.85, cy, s * 0.62, s * 0.15) end
    end
    return table.concat(out, " ")
end
function icon.chat(cx, cy, s)
    return rr_path(cx - s * 0.8, cy - s * 0.65, cx + s * 0.8, cy + s * 0.4, s * 0.3) .. " " ..
           poly({ cx - s * 0.45, cy + s * 0.3, cx - s * 0.05, cy + s * 0.3, cx - s * 0.5, cy + s * 0.8 })
end
function icon.full(cx, cy, s, on)
    local a, t, l = s * 0.75, s * 0.16, s * 0.42
    local out = {}
    for _, q in ipairs({ { -1, -1 }, { 1, -1 }, { 1, 1 }, { -1, 1 } }) do
        local sx, sy = q[1], q[2]
        local x, y = cx + sx * a, cy + sy * a           -- outer corner
        if on then x, y = cx + sx * (a - l), cy + sy * (a - l) end
        local dx, dy = on and sx or -sx, on and sy or -sy -- arms point inwards, or outwards when leaving full screen
        out[#out + 1] = poly({ x, y, x + dx * l, y, x + dx * l, y + dy * t, x + dx * t, y + dy * t,
                               x + dx * t, y + dy * l, x, y + dy * l })
    end
    return table.concat(out, " ")
end

-- ───────────────────────── control bar ─────────────────────────

-- what the timeline spans and how far behind live we are
local function timeline()
    local pos = mp.get_property_number("time-pos")
    if not pos then return nil end
    local dur = mp.get_property_number("duration")
    local a, b
    if mp.get_property_bool("seekable") and dur and dur > 0 then
        a, b = 0, dur
    else
        local st = mp.get_property_native("demuxer-cache-state") or {}
        for _, r in ipairs(st["seekable-ranges"] or {}) do
            if r["start"] <= pos + 1 and pos <= r["end"] + 1 then a, b = r["start"], r["end"] end
        end
        a, b = a or pos, b or pos
    end
    local behind = math.max(0, b - pos)
    if S.mode == "vod" and S.platform == "kick" then behind = behind + (S.lag or 15) end
    return pos, a, b, behind
end

local function visible()
    return dragging or hover_bar or mp.get_property_bool("pause") or (mp.get_time() - last_move < 2.5)
end

local function inside(m, x1, y1, x2, y2) return m and m.x >= x1 and m.x <= x2 and m.y >= y1 and m.y <= y2 end

local function set_volume(v)
    v = math.max(0, math.min(100, math.floor(v + 0.5)))
    mp.set_property_number("volume", v)
    if v > 0 then mp.set_property_bool("mute", false) end
end

local function render_osc()
    local w, h = mp.get_osd_size()
    if not w or w == 0 then return end
    hits = {}
    local ev = {}
    osc.res_x, osc.res_y = w, h
    local u = h / 720
    local vw = chat_on and (w - math.floor(w * CHAT_RATIO)) or w
    local paused = mp.get_property_bool("pause")

    -- buffering note in the middle, shown even with the bar hidden
    if mp.get_property_bool("paused-for-cache") or (mp.get_property_bool("core-idle") and not paused) then
        local fs = math.floor(math.max(14, 16 * u))
        local label = esc(tr("loading", "Loading…"))
        local pw = text_w(tr("loading", "Loading…"), fs) + 32 * u
        ev[#ev + 1] = rrect(vw / 2 - pw / 2, h / 2 - fs, vw / 2 + pw / 2, h / 2 + fs, fs, BG, "40")
        ev[#ev + 1] = text(vw / 2, h / 2, 5, fs, FG, label)
    end

    if not visible() then
        zone_top = nil
        osc.data = table.concat(ev, "\n")
        osc:update()
        return
    end

    local fs = math.floor(math.max(13, 15 * u))
    local pad = math.floor(math.max(12, 20 * u))
    local is = math.max(8, 11 * u)                   -- icon half-size
    local btn = math.floor(is * 1.75)                -- button radius
    local cy = h - pad - btn                         -- buttons row centre
    local ty = cy - btn - math.floor(10 * u)         -- timeline centre
    zone_top = ty - 24 * u

    -- soft shades top and bottom
    gradient(ev, 0, h - (h - ty) * 2.6, vw, h, BG, 0x10)
    gradient(ev, 0, math.floor(120 * u), vw, 0, BG, 0x10)

    -- title at the top: platform, channel, stream title
    local title_x = pad
    local plat = S.platform or ""
    if plat ~= "" and PLATFORM[plat] then
        ev[#ev + 1] = circle(title_x + 4 * u, pad + fs * 0.55, 4 * u, PLATFORM[plat])
        title_x = title_x + 16 * u
    end
    local chan = clean(S.channel ~= "" and S.channel or (mp.get_property("media-title") or ""))
    local fs_big = math.floor(fs * 1.2)
    local shadow = string.format("\\shad%d\\4c&H%s&\\4a&H40&", math.max(1, math.floor(1.5 * u)), BG)
    ev[#ev + 1] = text(title_x, pad, 7, fs_big, BRIGHT, esc(chan), "\\b1" .. shadow)
    if S.channel ~= "" and S.title ~= "" then
        local room = math.floor((vw - title_x - pad) / (fs * 0.5))
        local out, width = "", 0
        for _, cw in ipairs(chars(clean(S.title))) do
            if width + cw[2] > room - 1 then out = out .. "…"; break end
            out, width = out .. cw[1], width + cw[2]
        end
        ev[#ev + 1] = text(title_x, pad + fs_big * 1.35, 7, fs, FG, esc(out), shadow)
    end

    -- big play button in the middle while paused
    if paused then
        local r = math.floor(34 * u)
        local hov = inside(mouse, vw / 2 - r, h / 2 - r, vw / 2 + r, h / 2 + r)
        ev[#ev + 1] = circle(vw / 2, h / 2, r, hov and HOVER or BG, "30")
        ev[#ev + 1] = shape(icon.play(vw / 2 + r * 0.08, h / 2, r * 0.45), hov and ACCENT or BRIGHT)
        hits[#hits + 1] = { vw / 2 - r, h / 2 - r, vw / 2 + r, h / 2 + r, function() mp.set_property_bool("pause", false) end }
    end

    local tips = {}
    local function tip(x, label)
        if label then tips[#tips + 1] = { x, label } end
    end

    -- timeline
    local pos, a, b, behind = timeline()
    local tx1, tx2 = pad, vw - pad
    local over_tl = dragging and dragging.kind == "seek" or inside(mouse, tx1 - 4, ty - 10 * u, tx2 + 4, ty + 10 * u)
    local th = math.max(2, math.floor((over_tl and 6 or 4) * u))
    ev[#ev + 1] = rrect(tx1, ty - th / 2, tx2, ty + th / 2, th / 2, DIM, "50")
    if pos and b > a then
        local f = math.min(1, math.max(0, (pos - a) / (b - a)))
        local fx = tx1 + (tx2 - tx1) * f
        ev[#ev + 1] = rrect(tx1, ty - th / 2, math.max(tx1 + th, fx), ty + th / 2, th / 2, ACCENT)
        if over_tl then
            ev[#ev + 1] = circle(fx, ty, 7 * u, ACCENT)
            local mx = math.max(tx1, math.min(tx2, mouse and mouse.x or fx))
            local t = a + (b - a) * (mx - tx1) / (tx2 - tx1)
            local lag = (S.mode == "vod" and S.platform == "kick") and (S.lag or 15) or 0
            local d = b - t + lag
            tip(mx, d < 3 and tr("live", "LIVE") or ("−" .. fmt_time(d)))
        end
        hits[#hits + 1] = { tx1 - 4, ty - 10 * u, tx2 + 4, ty + 10 * u, function(mx, final)
            local t = a + (b - a) * math.max(0, math.min(1, (mx - tx1) / (tx2 - tx1)))
            mp.commandv("seek", tostring(t), final and "absolute" or "absolute+keyframes")
        end, kind = "seek" }
    end

    -- round icon buttons
    local function button(x, ic, action, label, color, arg1, arg2)
        local hov = inside(mouse, x - btn, cy - btn, x + btn, cy + btn)
        if hov then
            ev[#ev + 1] = circle(x, cy, btn, HOVER, "20")
            tip(x, label)
        end
        ev[#ev + 1] = shape(icon[ic](x, cy, is, arg1, arg2), color or (hov and BRIGHT or FG))
        hits[#hits + 1] = { x - btn, cy - btn, x + btn, cy + btn, action }
        return x + btn * 2 + math.floor(2 * u)
    end

    local x = pad + btn
    x = button(x, paused and "play" or "pause", function() mp.commandv("cycle", "pause") end,
        paused and tr("play", "Play") or tr("pause", "Pause"), BRIGHT)
    x = button(x, "back", function() mp.command("script-binding openlive/back") end, tr("back10", "Back 10 s"))
    x = button(x, "fwd", function() mp.command("script-binding openlive/forward") end, tr("fwd10", "Forward 10 s"))

    -- volume: speaker (click mutes) and a slider (click, drag or wheel)
    local vol = mp.get_property_number("volume") or 100
    local muted = mp.get_property_bool("mute")
    x = button(x, "speaker", function() mp.commandv("cycle", "mute") end,
        muted and tr("unmute", "Unmute") or tr("mute", "Mute"), nil, vol, muted) - btn + math.floor(4 * u)
    local sw = math.floor(84 * u)
    local sx1, sx2 = x, x + sw
    local over_vol = dragging and dragging.kind == "volume" or inside(mouse, sx1 - 6, cy - btn, sx2 + 6, cy + btn)
    local sh = math.max(2, math.floor((over_vol and 5 or 4) * u))
    local vf = muted and 0 or math.min(1, vol / 100)
    ev[#ev + 1] = rrect(sx1, cy - sh / 2, sx2, cy + sh / 2, sh / 2, DIM, "30")
    if vf > 0 then ev[#ev + 1] = rrect(sx1, cy - sh / 2, math.max(sx1 + sh, sx1 + sw * vf), cy + sh / 2, sh / 2, over_vol and ACCENT or FG) end
    ev[#ev + 1] = circle(sx1 + sw * vf, cy, (over_vol and 6.5 or 5) * u, over_vol and ACCENT or BRIGHT)
    if over_vol then tip(sx1 + sw * vf, string.format("%d%%", math.floor(vf * 100 + 0.5))) end
    hits[#hits + 1] = { sx1 - 6, cy - btn, sx2 + 6, cy + btn, function(mx) set_volume(100 * (mx - sx1) / sw) end,
        kind = "volume", wheel = function(d) set_volume((muted and 0 or vol) + d * 5) end }
    x = sx2 + math.floor(18 * u)

    -- live pill
    if behind then
        local live = behind < 12 and S.mode ~= "pipe"
        local label = live and tr("live", "LIVE") or ("−" .. fmt_time(behind))
        local pw = text_w(label, fs) + 30 * u
        local ph = fs * 0.95
        local hov = not live and inside(mouse, x, cy - ph, x + pw, cy + ph)
        ev[#ev + 1] = rrect(x, cy - ph, x + pw, cy + ph, ph, live and LIVE or (hov and HOVER or SURF), live and "00" or "20")
        ev[#ev + 1] = circle(x + 12 * u, cy, 3.5 * u, live and BG or (hov and LIVE or MUTED))
        ev[#ev + 1] = text(x + 20 * u, cy, 4, fs, live and BG or (hov and BRIGHT or FG), esc(label), "\\b1")
        if not live then
            hits[#hits + 1] = { x, cy - ph, x + pw, cy + ph, function() mp.command("script-binding openlive/live") end }
            if hov then tip(x + pw / 2, tr("go_live", "Go live") .. " (L)") end
        end
    end

    -- right side: full screen, chat
    local rx = vw - pad - btn
    local fullscreen = mp.get_property_bool("fullscreen")
    button(rx, "full", function() mp.commandv("cycle", "fullscreen") end, tr("fullscreen", "Full screen") .. " (F)",
        nil, fullscreen)
    if S.chat ~= "" then
        rx = rx - btn * 2 - math.floor(2 * u)
        button(rx, "chat", function() set_chat(not chat_on) end,
            (chat_on and tr("close_chat", "Close chat") or tr("open_chat", "Open chat")) .. " (C)", chat_on and ACCENT or nil)
        if chat_on then ev[#ev + 1] = circle(rx, cy + btn - 3 * u, 2 * u, ACCENT) end
    end

    -- tooltips last, above everything, kept inside the video area
    for _, tp in ipairs(tips) do
        local label = tp[2]
        local tw = text_w(label, fs * 0.9) + 18 * u
        local tx = math.max(pad, math.min(vw - pad - tw, tp[1] - tw / 2))
        local tyy = ty - 22 * u
        ev[#ev + 1] = rrect(tx, tyy - fs * 0.8, tx + tw, tyy + fs * 0.8, 6 * u, SURF, "08")
        ev[#ev + 1] = text(tx + tw / 2, tyy, 5, math.floor(fs * 0.9), BRIGHT, esc(label))
    end

    osc.data = table.concat(ev, "\n")
    osc:update()
end

local function hit_test(mx, my)
    for i = #hits, 1, -1 do
        local hb = hits[i]
        if mx >= hb[1] and mx <= hb[3] and my >= hb[2] and my <= hb[4] then return hb end
    end
end

mp.observe_property("mouse-pos", "native", function(_, m)
    if not m then return end
    mouse = m.hover and m or nil
    last_move = mp.get_time()
    hover_bar = (m.hover and zone_top and m.y > zone_top and not over_chat(m)) or false
    if dragging then dragging[5](m.x) end
    render_osc()
end)

mp.add_forced_key_binding("MBTN_LEFT", "click", function(e)
    local m = mp.get_property_native("mouse-pos")
    if e.event == "up" then
        if dragging and m then dragging[5](m.x, true) end
        dragging = nil
        render_osc()
        return
    end
    if e.event ~= "down" and e.event ~= "press" then return end
    if over_chat(m) then
        to_bridge("click", tostring(m.x), tostring(m.y))
        return
    end
    local hb = m and visible() and hit_test(m.x, m.y)
    if hb then
        hb[5](m.x, e.event == "press")
        if hb.kind and e.event == "down" then dragging = hb end
        render_osc()
    else
        pcall(mp.commandv, "begin-vo-dragging")  -- keep dragging the window by the video
    end
end, { complex = true })

local function wheel(d)
    local m = mp.get_property_native("mouse-pos")
    if over_chat(m) then to_bridge("scroll", tostring(d * 3)); return end
    local hb = m and visible() and hit_test(m.x, m.y)
    if hb and hb.wheel then hb.wheel(d); render_osc(); return end
    mp.command(d > 0 and "script-binding openlive/forward" or "script-binding openlive/back")
end

mp.add_forced_key_binding("c", "toggle-chat", function() set_chat(not chat_on) end)
mp.add_forced_key_binding("WHEEL_UP", "wheel-up", function() wheel(1) end)
mp.add_forced_key_binding("WHEEL_DOWN", "wheel-down", function() wheel(-1) end)
mp.add_forced_key_binding("UP", "volume-up", function() set_volume((mp.get_property_number("volume") or 100) + 5) end, { repeatable = true })
mp.add_forced_key_binding("DOWN", "volume-down", function() set_volume((mp.get_property_number("volume") or 100) - 5) end, { repeatable = true })
mp.add_forced_key_binding("f", "fullscreen", function() mp.commandv("cycle", "fullscreen") end)
mp.add_forced_key_binding("ENTER", "chat-write", function() if chat_on then to_bridge("write") end end)
mp.add_forced_key_binding("PGUP", "chat-up", function() if chat_on then to_bridge("scroll", "10") end end)
mp.add_forced_key_binding("PGDWN", "chat-down", function() if chat_on then to_bridge("scroll", "-10") end end)

-- remember the volume between streams
local vol_file = mp.command_native({ "expand-path", "~~/volume" })
do
    local f = io.open(vol_file, "r")
    local v = f and tonumber(f:read("*l"))
    if f then f:close() end
    if v then mp.set_property_number("volume", math.max(0, math.min(100, v))) end
end
local vol_timer = mp.add_timeout(1, function()
    local f = io.open(vol_file, "w")
    if f then f:write(tostring(math.floor(mp.get_property_number("volume") or 100)), "\n"); f:close() end
end)
vol_timer:kill()

mp.observe_property("volume", "number", function() vol_timer:kill(); vol_timer:resume(); render_osc() end)
mp.observe_property("mute", "bool", function() render_osc() end)
mp.observe_property("fullscreen", "bool", function() render_osc() end)
mp.observe_property("paused-for-cache", "bool", function() render_osc() end)

mp.observe_property("user-data/openlive", "native", function(_, v)
    if type(v) ~= "table" then return end
    local first = S.mode == nil
    S = v
    if first then set_chat(S.chat_on) end
    render_osc()
end)

mp.observe_property("osd-dimensions", "native", function() render_chat(); render_osc() end)
mp.observe_property("pause", "bool", function() render_osc() end)
mp.add_periodic_timer(0.5, function()
    if visible() or osc.data ~= "" then render_osc() end
end)
