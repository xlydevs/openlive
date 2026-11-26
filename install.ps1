# openlive installer for Windows. Nothing needs to be installed first. In PowerShell:
#   irm https://raw.githubusercontent.com/xlydevs/openlive/main/install.ps1 | iex
# It installs uv (a single program that brings its own Python), then openlive, then mpv if it's missing.
# Uninstall with: uv tool uninstall openlive

# "Continue": in Windows PowerShell 5, "Stop" turns any text a program writes to stderr into a fatal error
$ErrorActionPreference = "Continue"
$src = "https://github.com/xlydevs/openlive/archive/refs/heads/main.zip"

function Say($msg) { Write-Host "==> $msg" -ForegroundColor Yellow }
function Warn($msg) { Write-Host "==> $msg" -ForegroundColor Red }
function Have($name) { [bool](Get-Command $name -ErrorAction SilentlyContinue) }

# 1. uv
if (-not (Have "uv")) {
    Say "Installing uv (it brings its own Python, nothing else is needed)..."
    powershell -NoProfile -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

# 2. openlive
Say "Installing openlive..."
uv tool install --force --python 3.12 "openlive @ $src"
if ($LASTEXITCODE -ne 0) { Warn "openlive couldn't be installed (see the message above)."; return }
try { uv tool update-shell *> $null } catch { }

# 3. mpv, the video player openlive sets up for rewind and chat
$mpvPaths = @(
    "$env:LOCALAPPDATA\Microsoft\WinGet\Links\mpv.exe",
    "$env:LOCALAPPDATA\Programs\mpv\mpv.exe",
    "$env:ProgramFiles\mpv\mpv.exe",
    "$env:USERPROFILE\scoop\shims\mpv.exe"
)
if ((Have "mpv") -or ($mpvPaths | Where-Object { Test-Path $_ })) {
    Say "mpv is already installed."
} elseif (Have "winget") {
    Say "Installing mpv with winget..."
    winget install --id shinchiro.mpv --exact --source winget --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { Warn "Couldn't install mpv. Try later: winget install --id shinchiro.mpv --exact" }
} else {
    Warn "openlive plays streams in mpv. Install it from https://mpv.io/installation/"
}

Say "Done. Open a new terminal and run: openlive"
Say "Just looking? Try: openlive --demo"
