#!/bin/bash
# CyberRAG popup - wofi + zenity interface for local RAG queries

CYBERRAG="$HOME/customization/cyberrag"
STYLE="$HOME/.config/wofi/cyberrag.css"

# Duplicate instance guard
if pgrep -f "cyberrag_popup\.sh" | grep -v "$$" >/dev/null 2>&1; then
    exit 0
fi

show_results() {
    local title="$1"
    local result="$2"
    local source_label="$3"

    # Copy to clipboard
    echo -n "$result" | wl-copy

    display_text="═══ $source_label ═══

$result

(Copied to clipboard)"

    again=$(echo "$display_text" | zenity --text-info \
        --title="CyberRAG: $title" \
        --width=750 \
        --height=450 \
        --font="JetBrains Mono 16" \
        --ok-label="Close" \
        --extra-button="Ask Again" \
        2>&1)

    echo "$again"
}

# Run a cyberrag command with a visible pulsating progress bar.
# User can cancel. Returns 0 on success (result in $QUERY_RESULT), 1 on failure/cancel.
run_with_progress() {
    local label="$1"
    shift
    # remaining args are the command

    local tmp_out=$(mktemp)
    local tmp_err=$(mktemp)

    # Start query in background
    "$@" >"$tmp_out" 2>"$tmp_err" &
    local query_pid=$!

    # Pulsating progress dialog - shows stderr status updates
    (
        while kill -0 $query_pid 2>/dev/null; do
            status=$(tail -1 "$tmp_err" 2>/dev/null)
            if [ -n "$status" ]; then
                echo "# $status"
            else
                echo "# $label"
            fi
            sleep 1
        done
    ) | zenity --progress \
        --title="CyberRAG" \
        --text="$label" \
        --pulsate \
        --auto-close \
        --width=450 \
        2>/dev/null

    local zenity_exit=$?

    # If user cancelled, kill the query
    if kill -0 $query_pid 2>/dev/null; then
        kill $query_pid 2>/dev/null
        wait $query_pid 2>/dev/null
        rm -f "$tmp_out" "$tmp_err"
        QUERY_RESULT=""
        return 1
    fi

    wait $query_pid
    local exit_code=$?

    QUERY_RESULT=$(cat "$tmp_out")
    local err_msg=$(cat "$tmp_err")
    rm -f "$tmp_out" "$tmp_err"

    if [ $exit_code -ne 0 ] || [ -z "$QUERY_RESULT" ]; then
        notify-send "CyberRAG" "Failed: ${err_msg:-no results}"
        return 1
    fi

    return 0
}

query_flow() {
    local mode="$1"  # "ask" or "search"

    while true; do
        # Source picker
        source=$(echo -e "All Sources\nMedical/First Aid\nCode\nLogs\nWiki" | wofi --dmenu --prompt "Source" --width 350 --height 350 --style "$STYLE")
        [ -z "$source" ] && return

        # Map source selection to flag
        local src_flags=()
        case "$source" in
            "All Sources")       ;;
            "Medical/First Aid") src_flags=(--sources docs,wiki) ;;
            "Code")              src_flags=(--sources code) ;;
            "Logs")              src_flags=(--sources logs) ;;
            "Wiki")              src_flags=(--sources wiki) ;;
        esac

        # Question input
        if [ "$mode" = "ask" ]; then
            prompt_title="Ask CyberRAG"
        else
            prompt_title="Search (raw)"
        fi

        question=$(zenity --entry \
            --title="$prompt_title" \
            --text="Enter your question:" \
            --width=700 \
            2>/dev/null)
        [ -z "$question" ] && return

        # Build command and run with progress bar
        if [ "$mode" = "ask" ]; then
            run_with_progress "Thinking... (this may take a minute)" \
                $CYBERRAG query "${src_flags[@]}" "$question"
        else
            run_with_progress "Searching documents..." \
                $CYBERRAG query --raw "${src_flags[@]}" "$question"
        fi

        # Skip to next iteration if cancelled/failed
        [ $? -ne 0 ] && continue

        # Show results
        local label="QUERY: $question"
        again=$(show_results "$question" "$QUERY_RESULT" "$label")

        if [ "$again" = "Ask Again" ]; then
            continue
        else
            return
        fi
    done
}

reindex_flow() {
    run_with_progress "Reindexing documents..." $CYBERRAG index
    [ $? -ne 0 ] && return

    echo "$QUERY_RESULT" | zenity --text-info \
        --title="CyberRAG: Reindex Complete" \
        --width=700 \
        --height=400 \
        --font="JetBrains Mono 16" \
        2>/dev/null
}

status_flow() {
    run_with_progress "Loading status..." $CYBERRAG status
    [ $? -ne 0 ] && return

    echo "$QUERY_RESULT" | zenity --text-info \
        --title="CyberRAG: Status" \
        --width=700 \
        --height=400 \
        --font="JetBrains Mono 16" \
        2>/dev/null
}

# Main menu
main_menu() {
    while true; do
        action=$(echo -e "Ask Question\nSearch (raw)\nReindex\nStatus" | wofi --dmenu --prompt "CyberRAG" --width 400 --height 300 --style "$STYLE")
        [ -z "$action" ] && exit 0

        case "$action" in
            "Ask Question")  query_flow "ask" ;;
            "Search (raw)")  query_flow "search" ;;
            "Reindex")       reindex_flow ;;
            "Status")        status_flow ;;
        esac
    done
}

main_menu
