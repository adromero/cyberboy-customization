#!/usr/bin/env bash
# Piper TTS wrapper. Reads text from -t/--text or stdin, speaks it.
# Language picked via -l (en, es, de, fr, nl, ru, el). Defaults to en.

set -euo pipefail

PIPER_DIR="$HOME/piper"
PIPER_BIN="$PIPER_DIR/piper/piper"
VOICES_DIR="$PIPER_DIR/voices"
LOCK="/tmp/cyberboy-speak.lock"

declare -A VOICES=(
    [en]="en_US-amy-medium.onnx"
    [es]="es_ES-sharvard-medium.onnx"
    [de]="de_DE-thorsten-medium.onnx"
    [fr]="fr_FR-siwis-medium.onnx"
    [nl]="nl_NL-mls-medium.onnx"
    [ru]="ru_RU-dmitri-medium.onnx"
    [el]="el_GR-rapunzelina-low.onnx"
)

lang="en"
text=""
length_scale="1.0"
stop_flag=0

usage() {
    echo "Usage: speak [-l LANG] [-s SPEED] [-t TEXT | --stop]"
    echo "  -l LANG    en|es|de|fr|nl|ru|el  (default: en)"
    echo "  -s SPEED   length scale, 1.0 = normal, <1 faster, >1 slower"
    echo "  -t TEXT    text to speak (otherwise reads stdin)"
    echo "  --stop     kill any running speech"
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -l) lang="$2"; shift 2 ;;
        -s) length_scale="$2"; shift 2 ;;
        -t) text="$2"; shift 2 ;;
        --stop) stop_flag=1; shift ;;
        -h|--help) usage ;;
        *) echo "Unknown arg: $1"; usage ;;
    esac
done

if [[ $stop_flag -eq 1 ]]; then
    pkill -f "$PIPER_BIN" 2>/dev/null || true
    pkill -f "aplay.*cyberboy-speak" 2>/dev/null || true
    rm -f "$LOCK"
    exit 0
fi

voice="${VOICES[$lang]:-}"
if [[ -z "$voice" ]]; then
    echo "Unknown language: $lang" >&2
    exit 2
fi
model="$VOICES_DIR/$voice"
if [[ ! -f "$model" ]]; then
    echo "Voice model missing: $model" >&2
    exit 3
fi

if [[ -z "$text" ]]; then
    text="$(cat)"
fi
text="$(echo "$text" | tr -d '\000' | sed 's/[[:space:]]\+/ /g')"
if [[ -z "${text// }" ]]; then
    exit 0
fi

# Single-instance: kill any in-flight speech before starting new one
if [[ -f "$LOCK" ]]; then
    old=$(cat "$LOCK" 2>/dev/null || true)
    if [[ -n "$old" ]]; then
        kill "$old" 2>/dev/null || true
    fi
    pkill -f "$PIPER_BIN" 2>/dev/null || true
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

wav="/tmp/cyberboy-speak-$$.wav"
echo "$text" | "$PIPER_BIN" \
    --model "$model" \
    --length_scale "$length_scale" \
    --output_file "$wav" \
    --quiet 2>/dev/null

aplay -q "$wav" 2>/dev/null || true
rm -f "$wav"
