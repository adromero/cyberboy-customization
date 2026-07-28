#!/usr/bin/env bash
# Read clipboard contents aloud (English voice).
# Toggle: if speech is currently running, stop it instead.

if pgrep -f "$HOME/piper/piper/piper" >/dev/null 2>&1 \
   || pgrep -f "cyberboy-speak" >/dev/null 2>&1; then
    "$HOME/customization/speak.sh" --stop
    notify-send -t 1500 "Speech" "Stopped" 2>/dev/null || true
    exit 0
fi

text="$(wl-paste --no-newline 2>/dev/null || true)"
if [[ -z "${text// }" ]]; then
    notify-send -t 2000 "Speech" "Clipboard is empty" 2>/dev/null || true
    exit 0
fi

# Cap absurdly long pastes to avoid runaway speech
if [[ ${#text} -gt 4000 ]]; then
    text="${text:0:4000} . Truncated."
fi

notify-send -t 1500 "Speech" "Reading clipboard" 2>/dev/null || true
echo "$text" | "$HOME/customization/speak.sh" -l en
