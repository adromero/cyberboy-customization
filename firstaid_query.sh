#!/bin/bash
# First Aid quick query - goes straight to medical docs search via CyberRAG

CYBERRAG="$HOME/customization/cyberrag"

# Duplicate instance guard
if pgrep -f "firstaid_query\.sh" | grep -v "$$" >/dev/null 2>&1; then
    exit 0
fi

while true; do
    question=$(zenity --entry \
        --title="First Aid / Medical" \
        --text="Describe the situation or injury:" \
        --width=700 \
        2>/dev/null)
    [ -z "$question" ] && exit 0

    tmp_out=$(mktemp)
    tmp_err=$(mktemp)

    $CYBERRAG query --sources docs,wiki --raw "$question" >"$tmp_out" 2>"$tmp_err" &
    query_pid=$!

    (
        while kill -0 $query_pid 2>/dev/null; do
            status=$(tail -1 "$tmp_err" 2>/dev/null)
            echo "# ${status:-Searching medical references...}"
            sleep 1
        done
    ) | zenity --progress \
        --title="First Aid" \
        --text="Searching medical references..." \
        --pulsate \
        --auto-close \
        --width=450 \
        2>/dev/null

    if kill -0 $query_pid 2>/dev/null; then
        kill $query_pid 2>/dev/null
        wait $query_pid 2>/dev/null
        rm -f "$tmp_out" "$tmp_err"
        continue
    fi

    wait $query_pid
    result=$(cat "$tmp_out")
    rm -f "$tmp_out" "$tmp_err"

    if [ -z "$result" ]; then
        notify-send "First Aid" "No results found"
        continue
    fi

    echo -n "$result" | wl-copy

    again=$(echo "$result" | zenity --text-info \
        --title="First Aid: $question" \
        --width=750 \
        --height=450 \
        --font="JetBrains Mono 16" \
        --ok-label="Close" \
        --extra-button="Ask Again" \
        2>&1)

    [ "$again" != "Ask Again" ] && exit 0
done
