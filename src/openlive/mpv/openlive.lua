-- openlive: rewind a live stream and jump back to live, in mpv.
--
-- openlive writes a small JSON "session" file and passes its path in --script-opts=openlive-session=<path>.
--   mode "vod"  (Twitch)  the recording Twitch keeps of the live stream: it grows as the stream goes on, so the
--                         whole stream can be seeked and playing on reaches live. Nothing to switch.
--   mode "live" (Kick)    plays live; going back further than mpv's own cache switches to Kick's recording
--                         ("vod" url), which is a snapshot, so reaching its end switches back to live.
--   mode "live" (YouTube) plays live; going back further than the cache reloads the live playlist starting
--                         earlier (ffmpeg's live_start_index), up to the DVR window the channel allows.
--   mode "pipe"           streamlink feeds mpv: only mpv's cache can be rewound.
local mp = require "mp"
local utils = require "mp.utils"
local options = require "mp.options"

local opts = { session = "" }
options.read_options(opts, "openlive")
if opts.session == "" then return end
local f = io.open(opts.session, "r")
if not f then return end
local s = utils.parse_json(f:read("*a")) or {}
f:close()
os.remove(opts.session)

local T = s.text or {}
local mode = s.mode or "pipe"          -- what is playing now: "vod", "live", "dvr" (YouTube rewound) or "pipe"
local yt_back = 0                      -- YouTube: seconds before live the playlist was reloaded at
local seg = tonumber(s.seg) or 5       -- YouTube segment length
local dvr = tonumber(s.dvr) or 0       -- YouTube: how far back the channel lets you go (seconds)
local lag = tonumber(s.lag) or 15      -- Kick: how far behind live its recording is
local quality = s.quality or ""        -- name of the quality playing ("1080p60"); s.qualities lists them, best first

local function say(text) if text then mp.osd_message(text, 2.5) end end

local function url_of(list, name)
    for _, q in ipairs(list or {}) do
        if q.name == name then return q.url end
    end
end

local function names()
    local out = {}
    for _, q in ipairs(s.qualities or {}) do out[#out + 1] = q.name end
    return out
end

-- the interface script (openlive_ui.lua) reads the session and the current mode from here
local function publish()
    mp.set_property_native("user-data/openlive", {
        platform = s.platform or "", mode = mode, lag = lag, title = s.title or "", channel = s.channel or "",
        chat = s.chat or "", chat_on = s.chat_on ~= false, text = T, quality = quality, qualities = names(),
    })
end
publish()

-- seconds that can be rewound inside mpv's own cache
local function cached_back()
    local st = mp.get_property_native("demuxer-cache-state")
    local pos = mp.get_property_number("time-pos")
    if not st or not pos or not st["seekable-ranges"] then return 0 end
    for _, r in ipairs(st["seekable-ranges"]) do
        if r["start"] <= pos and pos <= r["end"] + 1 then return pos - r["start"] end
    end
    return 0
end

local function load(url, start, lavf, new_mode)
    mp.set_property("start", start or "none")
    mp.set_property("demuxer-lavf-o", lavf or "")
    mode = new_mode
    publish()
    mp.commandv("loadfile", url, "replace")
end

-- after a load, later files (and reloads) start normally again
mp.register_event("file-loaded", function()
    mp.set_property("start", "none")
end)

local function back(sec)
    if mode == "vod" or mode == "pipe" or cached_back() >= sec then
        mp.commandv("seek", tostring(-sec), "relative")
        return
    end
    if s.platform == "kick" and mode == "live" and s.vod then
        say(T.rewind)
        load(s.vod, tostring(-(sec + lag)), nil, "vod")
    elseif s.platform == "youtube" and (mode == "live" or mode == "dvr") then
        if dvr < 60 or yt_back >= dvr - seg then
            say(T.no_more)
            return
        end
        local behind = yt_back + math.max(sec, 30)
        if mode == "dvr" then behind = behind + cached_back() end
        yt_back = math.min(behind, dvr - seg)
        say(T.rewind)
        load(s.live, nil, "live_start_index=" .. tostring(-math.floor(yt_back / seg + 0.5)), "dvr")
    else
        say(T.no_more)
    end
end

local function forward(sec)
    mp.commandv("seek", tostring(sec), "relative")
end

-- the newest moment mpv has: the end of its cache
local function cache_end()
    local st = mp.get_property_native("demuxer-cache-state") or {}
    local e
    for _, r in ipairs(st["seekable-ranges"] or {}) do e = math.max(e or r["end"], r["end"]) end
    return e
end

local function go_live()
    if mode == "vod" and s.platform ~= "kick" then
        mp.commandv("seek", "-4", "absolute")  -- Twitch: the end of the growing recording is live
    elseif mode == "live" or mode == "pipe" then
        local e = cache_end()                  -- rewound inside the cache: back to its end
        if e then mp.commandv("seek", tostring(e - 1), "absolute") end
    elseif s.live then
        yt_back = 0
        load(s.live, nil, nil, "live")
    end
    say(T.live)
end

-- another quality: the same stream from another playlist, carrying on where it was
local function set_quality(name)
    local url = url_of(s.qualities, name)
    if not url or name == quality then return end
    quality = name
    local pos = mp.get_property_number("time-pos")
    if s.platform == "twitch" and mode == "vod" then
        load(url, pos and tostring(pos) or nil, nil, "vod")  -- every quality of the recording has the same timeline
    else
        s.live = url
        if mode == "live" then
            load(url, nil, nil, "live")
        elseif mode == "dvr" then
            load(url, nil, mp.get_property("demuxer-lavf-o"), "dvr")
        elseif mode == "vod" then                 -- Kick's recording: its own playlists, same names
            local vod = url_of(s.vod_qualities, name)
            if vod then
                s.vod = vod
                load(vod, pos and tostring(pos) or nil, nil, "vod")
            end
        end
    end
    publish()
    say((T.quality_set or "Quality: {q}"):gsub("{q}", name))
end
mp.register_script_message("openlive-quality", set_quality)

-- Kick's recording is a snapshot: at its end, carry on live
mp.observe_property("eof-reached", "bool", function(_, eof)
    if eof and mode == "vod" and s.platform == "kick" and s.live then
        load(s.live, nil, nil, "live")
        say(T.live)
    end
end)

mp.add_forced_key_binding("LEFT", "back", function() back(10) end, { repeatable = true })
mp.add_forced_key_binding("RIGHT", "forward", function() forward(10) end, { repeatable = true })
mp.add_forced_key_binding("Shift+LEFT", "back-more", function() back(300) end)
mp.add_forced_key_binding("Shift+RIGHT", "forward-more", function() forward(300) end)
mp.add_forced_key_binding("END", "live", go_live)
mp.add_forced_key_binding("l", "live-l", go_live)
