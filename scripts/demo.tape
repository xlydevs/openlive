# Records docs/demo.gif with made-up data:  vhs scripts/demo.tape
Output docs/demo.gif

Require openlive
Set Shell "bash"
Set FontSize 14
Set Width 1400
Set Height 820
Set Padding 12
Set Framerate 20
Set TypingSpeed 70ms
Set Theme { "background": "#0f1420", "foreground": "#d6deeb", "cursor": "#f2cc8f", "black": "#0f1420", "brightBlack": "#4b5570", "red": "#f28b82", "brightRed": "#f28b82", "green": "#a5d68f", "brightGreen": "#a5d68f", "yellow": "#f2cc8f", "brightYellow": "#f2cc8f", "blue": "#9cc8e8", "brightBlue": "#9cc8e8", "magenta": "#c3a6ff", "brightMagenta": "#c3a6ff", "cyan": "#63d3c4", "brightCyan": "#63d3c4", "white": "#d6deeb", "brightWhite": "#eef2fa" }

Hide
Type "clear && COLORTERM=truecolor openlive --demo --lang en" Enter
Sleep 3s
Show

# Live: Twitch, Kick and YouTube together, favourites on top
Sleep 3s
Down Sleep 0.8s
Down Sleep 0.8s
Down Sleep 1.5s
# mark a favourite
Type "f" Sleep 2s
# filter
Type "/" Sleep 0.5s
Type "chess" Sleep 2.5s
Escape Sleep 1.5s
# hide Kick and YouTube for a moment, then bring them back
Type "k" Sleep 1.5s
Type "y" Sleep 2s
Type "k" Sleep 0.6s
Type "y" Sleep 1.5s

# add a Kick or YouTube channel (no sign-in)
Type "a" Sleep 2s
Type "kick.com/emberfox" Sleep 2s
Escape Sleep 1.2s

# Following: everyone you follow, live first
Type "2" Sleep 3s
Down Sleep 0.6s
Down Sleep 1.5s

# Browse: the top streams on Twitch
Type "3" Sleep 3s

# Search any channel
Type "4" Sleep 1.2s
Type "pixel" Sleep 0.8s
Enter Sleep 3s

# back to Live and "watch" (demo shows what would open)
Type "1" Sleep 1.2s
Enter Sleep 3s

Hide
Type "q"
