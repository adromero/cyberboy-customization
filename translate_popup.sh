#!/bin/bash
# Translate popup - wofi + zenity interface for offline translation

TRANSLATE="$HOME/customization/translate.py"
STYLE="$HOME/.config/wofi/translate.css"

# Language options (name:code)
LANGUAGES=(
    "Spanish:es"
    "German:de"
    "French:fr"
    "Chinese:zh"
    "Dutch:nl"
    "Russian:ru"
    "Greek:el"
)

# Uses cyberpunk GTK theme from ~/.config/gtk-4.0/gtk.css

translate_loop() {
    while true; do
        # Step 1: To or From English?
        direction=$(echo -e "English → Other\nOther → English" | wofi --dmenu --prompt "Direction" --width 400 --height 280 --style "$STYLE")
        [ -z "$direction" ] && exit 0

        # Step 2: Pick language
        lang_menu=""
        for lang in "${LANGUAGES[@]}"; do
            name=$(echo "$lang" | cut -d: -f1)
            lang_menu+="$name\n"
        done

        chosen_lang=$(echo -e "$lang_menu" | wofi --dmenu --prompt "Language" --width 350 --height 340 --style "$STYLE")
        [ -z "$chosen_lang" ] && exit 0

        # Get language code
        lang_code=""
        for lang in "${LANGUAGES[@]}"; do
            name=$(echo "$lang" | cut -d: -f1)
            if [ "$name" = "$chosen_lang" ]; then
                lang_code=$(echo "$lang" | cut -d: -f2)
                break
            fi
        done

        # Build flag and display name; remember target lang for TTS
        if [ "$direction" = "English → Other" ]; then
            flag="-$lang_code"
            chosen_dir="English → $chosen_lang"
            speak_lang="$lang_code"
        else
            flag="-${lang_code}-en"
            chosen_dir="$chosen_lang → English"
            speak_lang="en"
        fi

        # Voices available in piper (no zh voice installed)
        case "$speak_lang" in
            en|es|de|fr|nl|ru|el) speak_ok=1 ;;
            *) speak_ok=0 ;;
        esac

        # Step 3: Choose input mode
        mode=$(echo -e "Type text\nClipboard\nSelection" | wofi --dmenu --prompt "Input" --width 350 --height 320 --style "$STYLE")
        [ -z "$mode" ] && exit 0

        # Step 4: Get text based on mode
        case "$mode" in
            "Type text")
                text=$(zenity --text-info \
                    --title="Translate: $chosen_dir" \
                    --editable \
                    --width=700 \
                    --height=350 \
                    --font="JetBrains Mono 18" \
                    2>/dev/null)
                ;;
            "Clipboard")
                text=$(wl-paste 2>/dev/null)
                ;;
            "Selection")
                text=$(wl-paste --primary 2>/dev/null)
                ;;
        esac

        [ -z "$text" ] && { notify-send "Translate" "No text provided"; continue; }

        # Step 5: Translate
        result=$(python3 "$TRANSLATE" $flag "$text" 2>&1)

        if [ -z "$result" ]; then
            notify-send "Translate" "Translation failed"
            continue
        fi

        # Step 6: Copy to clipboard
        echo -n "$result" | wl-copy

        # Step 7: Show result in scrollable text area
        display_text="═══ ORIGINAL ═══

$text

═══ TRANSLATION ═══

$result

(Copied to clipboard)"

        # Build zenity buttons; only offer Speak if voice is available
        zenity_args=(--text-info \
            --title="$chosen_dir" \
            --width=750 \
            --height=450 \
            --font="JetBrains Mono 18" \
            --ok-label="Close" \
            --extra-button="Translate Again")
        if [ "$speak_ok" = "1" ]; then
            zenity_args+=(--extra-button="Speak")
        fi

        again=$(echo "$display_text" | zenity "${zenity_args[@]}" 2>&1)

        case "$again" in
            "Translate Again") continue ;;
            "Speak")
                "$HOME/customization/speak.sh" -l "$speak_lang" -t "$result" &
                continue
                ;;
            *) exit 0 ;;
        esac
    done
}

translate_loop
