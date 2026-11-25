-- openlive's interface for mpv: a slim control bar and a chat sidebar, in openlive's colours.
-- The rewind logic lives in openlive.lua, which shares the session in user-data/openlive.
-- Chat messages arrive as "script-message openlive-chat <json>" from openlive's chat bridge.
local mp = require "mp"
local utils = require "mp.utils"

-- palette (same as the TUI)
local function c(hex) return hex:sub(6, 7) .. hex:sub(4, 5) .. hex:sub(2, 3) end
local BG, SURF, BORDER = c("#0f1420"), c("#141b2a"), c("#263044")
local FG, BRIGHT, MUTED, DIM = c("#d6deeb"), c("#eef2fa"), c("#7c879f"), c("#4b5570")
local ACCENT, LIVE = c("#f2cc8f"), c("#f28b82")
local NAME_COLORS = { "#9cc8e8", "#a5d68f", "#c3a6ff", "#f4a98a", "#63d3c4", "#e8d36a", "#ff9fb2", "#7fb2ff" }
local CHAT_RATIO = 0.27

local S = { text = {} }            -- session from openlive.lua
local msgs = {}                    -- chat messages {n, c, t} or {sys}
local chat_status = nil            -- "joined" / "offline"
local chat_on = false
local last_move, hover_bar = 0, false
local hits = {}
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

local function wrap(s, cols)
    local lines, line, width, word, wwidth = {}, "", 0, "", 0
    local function push_word()
        if word == "" then return end
        if width + wwidth > cols and width > 0 then
            lines[#lines + 1] = line
            line, width = (word:gsub("^ ", "")), wwidth
        else
            line, width = line .. word, width + wwidth
        end
        word, wwidth = "", 0
    end
    for _, cw in ipairs(chars(s)) do
        if cw[1] == " " then push_word() end
        word, wwidth = word .. cw[1], wwidth + cw[2]
        if wwidth > cols then  -- a very long word: cut it
            push_word()
        end
    end
    push_word()
    lines[#lines + 1] = line
    return lines
end

local function rect(x1, y1, x2, y2, color, alpha)
    return string.format("{\\an7\\pos(0,0)\\bord0\\shad0\\1c&H%s&\\1a&H%s&\\p1}m %d %d l %d %d l %d %d l %d %d{\\p0}",
        color, alpha or "00", x1, y1, x2, y1, x2, y2, x1, y2)
end

local function text(x, y, an, size, color, s, extra)
    return string.format("{\\an%d\\pos(%d,%d)\\fs%d\\bord0\\shad0\\1c&H%s&%s}%s", an, x, y, size, color, extra or "", s)
end

local function name_color(m)
    if m.c and m.c:match("^#%x%x%x%x%x%x$") then
        -- very dark name colours are unreadable on the panel: fall back to the palette
        local r, g, b = tonumber(m.c:sub(2, 3), 16), tonumber(m.c:sub(4, 5), 16), tonumber(m.c:sub(6, 7), 16)
        if r * 0.3 + g * 0.59 + b * 0.11 > 70 then return c(m.c) end
    end
    local h = 0
    for i = 1, #(m.n or "") do h = (h * 31 + m.n:byte(i)) % 1000003 end
    return c(NAME_COLORS[h % #NAME_COLORS + 1])
end

-- ───────────────────────── chat sidebar ─────────────────────────

local function render_chat()
    local w, h = mp.get_osd_size()
    if not chat_on or not w or w == 0 then
        chat.data = ""
        chat:update()
        return
    end
    chat.res_x, chat.res_y = w, h
    local u = h / 720
    local fs = math.floor(math.max(14, 17 * u))
    local pad = math.floor(12 * u)
    local x0 = w - math.floor(w * CHAT_RATIO)
    local ev = {}
    ev[#ev + 1] = rect(x0, 0, w, h, SURF)
    ev[#ev + 1] = rect(x0, 0, x0 + math.max(1, math.floor(u)), h, BORDER)
    local head = math.floor(fs * 2.6)
    ev[#ev + 1] = rect(x0, head - math.max(1, math.floor(u)), w, head, BORDER)
    ev[#ev + 1] = text(x0 + pad, head / 2, 4, fs, MUTED, esc(tr("chat", "Chat")) .. "  {\\1c&H" .. FG .. "&}" .. esc(S.channel), "\\b1")
    ev[#ev + 1] = text(w - pad, head / 2, 6, math.floor(fs * 0.85), DIM, "c " .. esc(tr("hide", "hide")))
    local cols = math.max(10, math.floor((w - x0 - 2 * pad) / (fs * 0.47)))
    local lh = math.floor(fs * 1.3)
    local y = h - pad
    if #msgs == 0 then
        local status = chat_status == "offline" and tr("chat_offline", "Can't reach the chat, retrying…")
            or chat_status == "joined" and tr("chat_quiet", "Nobody has written yet.")
            or tr("chat_connecting", "Connecting to the chat…")
        ev[#ev + 1] = text(x0 + pad, head + pad, 7, fs, DIM, esc(status))
    end
    for i = #msgs, 1, -1 do
        local m = msgs[i]
        local lines = wrap((m.n or "") .. ": " .. clean(m.t), cols)
        y = y - #lines * lh
        if y < head + pad / 2 then break end
        local first = lines[1]
        local name = m.n or ""
        local body = first:sub(#name + 1)
        local out = "{\\1c&H" .. name_color(m) .. "&\\b1}" .. esc(name) .. "{\\b0\\1c&H" .. FG .. "&}" .. esc(body)
        for j = 2, #lines do out = out .. "\\N" .. esc(lines[j]) end
        ev[#ev + 1] = string.format("{\\an7\\pos(%d,%d)\\fs%d\\bord0\\shad0\\q2}", x0 + pad, y, fs) .. out
        y = y - math.floor(lh * 0.25)
    end
    chat.data = table.concat(ev, "\n")
    chat:update()
end

local function set_chat(on)
    chat_on = on and S.chat ~= ""
    mp.set_property_number("video-margin-ratio-right", chat_on and CHAT_RATIO or 0)
    render_chat()
end

mp.register_script_message("openlive-chat", function(json)
    local m = utils.parse_json(json)
    if not m then return end
    if m.sys then
        chat_status = m.sys
    else
        msgs[#msgs + 1] = m
        if #msgs > 150 then table.remove(msgs, 1) end
    end
    if chat_on then render_chat() end
end)

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
    return hover_bar or mp.get_property_bool("pause") or (mp.get_time() - last_move < 2.5)
end

local function render_osc()
    local w, h = mp.get_osd_size()
    if not w or w == 0 then return end
    hits = {}
    if not visible() then
        osc.data = ""
        osc:update()
        return
    end
    osc.res_x, osc.res_y = w, h
    local u = h / 720
    local fs = math.floor(math.max(14, 17 * u))
    local vw = chat_on and (w - math.floor(w * CHAT_RATIO)) or w
    local bh = math.floor(fs * 3.4)
    local top = h - bh
    local pad = math.floor(14 * u)
    local ev = {}
    ev[#ev + 1] = rect(0, top, vw, h, BG, "30")
    -- timeline
    local pos, a, b, behind = timeline()
    local ty, th = top + math.floor(6 * u), math.max(2, math.floor((hover_bar and 5 or 3) * u))
    local tx1, tx2 = pad, vw - pad
    ev[#ev + 1] = rect(tx1, ty, tx2, ty + th, BORDER)
    if pos and b > a then
        local f = math.min(1, math.max(0, (pos - a) / (b - a)))
        ev[#ev + 1] = rect(tx1, ty, tx1 + math.floor((tx2 - tx1) * f), ty + th, ACCENT)
        hits[#hits + 1] = { tx1, ty - 8 * u, tx2, ty + th + 8 * u, function(mx)
            local t = a + (b - a) * (mx - tx1) / (tx2 - tx1)
            mp.commandv("seek", tostring(t), "absolute")
        end }
    end
    -- buttons row
    local cy = top + math.floor(bh * 0.6)
    local x = pad
    local function button(label, action, color)
        local bw = math.floor(fs * 0.62 * #label) + math.floor(16 * u)
        ev[#ev + 1] = text(x + bw / 2, cy, 5, fs, color or FG, label)
        hits[#hits + 1] = { x, cy - fs, x + bw, cy + fs, action }
        x = x + bw + math.floor(4 * u)
    end
    local paused = mp.get_property_bool("pause")
    button(paused and "▶" or "❚❚", function() mp.commandv("cycle", "pause") end, BRIGHT)
    button("« 10", function() mp.command("script-binding openlive/back") end)
    button("10 »", function() mp.command("script-binding openlive/forward") end)
    -- right side: live badge, chat toggle
    local rx = vw - pad
    local function rbutton(label, action, color, bold)
        local bw = math.floor(fs * 0.58 * #label) + math.floor(16 * u)
        ev[#ev + 1] = text(rx - bw / 2, cy, 5, fs, color, label, bold and "\\b1" or "")
        hits[#hits + 1] = { rx - bw, cy - fs, rx, cy + fs, action }
        rx = rx - bw - math.floor(8 * u)
    end
    if S.chat ~= "" then
        rbutton(esc(tr("chat", "Chat")), function() set_chat(not chat_on) end, chat_on and ACCENT or MUTED, chat_on)
    end
    local is_live = behind and behind < 12 and S.mode ~= "pipe"
    if is_live then
        rbutton("● " .. esc(tr("live", "LIVE")), function() end, LIVE, true)
    elseif behind then
        rbutton("● −" .. fmt_time(behind), function() mp.command("script-binding openlive/live") end, MUTED)
    end
    -- title in the middle, cut to fit
    local room = math.floor((rx - x - pad) / (fs * 0.55))
    local title = clean(S.channel ~= "" and (S.channel .. (S.title ~= "" and "  ·  " .. S.title or "")) or (mp.get_property("media-title") or ""))
    if room > 4 then
        local cs, out, width = chars(title), "", 0
        for _, cw in ipairs(cs) do
            if width + cw[2] > room - 1 then out = out .. "…"; break end
            out, width = out .. cw[1], width + cw[2]
        end
        ev[#ev + 1] = text(x + pad, cy, 4, fs, MUTED, esc(out))
    end
    osc.data = table.concat(ev, "\n")
    osc:update()
end

local function hit_test(mx, my)
    for _, hb in ipairs(hits) do
        if mx >= hb[1] and mx <= hb[3] and my >= hb[2] and my <= hb[4] then return hb end
    end
end

mp.observe_property("mouse-pos", "native", function(_, m)
    if not m then return end
    last_move = mp.get_time()
    local w, h = mp.get_osd_size()
    hover_bar = m.hover and h and m.y > h - (math.max(14, 17 * h / 720) * 3.4) or false
    render_osc()
end)

mp.add_forced_key_binding("MBTN_LEFT", "click", function(e)
    if e.event ~= "down" then return end
    local m = mp.get_property_native("mouse-pos")
    local hb = m and visible() and hit_test(m.x, m.y)
    if hb then
        hb[5](m.x)
    else
        pcall(mp.commandv, "begin-vo-dragging")  -- keep dragging the window by the video
    end
end, { complex = true })

mp.add_forced_key_binding("c", "toggle-chat", function() set_chat(not chat_on) end)

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
