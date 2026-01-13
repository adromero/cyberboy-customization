#!/bin/bash
# Check status of offline content downloads

echo "╔══════════════════════════════════════════╗"
echo "║     OFFLINE CONTENT DOWNLOAD STATUS      ║"
echo "╚══════════════════════════════════════════╝"
echo

# Kiwix content
echo "═══ KIWIX (Wiki/StackOverflow) ═══"
KIWIX_DIR=~/offline-library/kiwix
if [ -d "$KIWIX_DIR" ]; then
    shopt -s nullglob
    zim_files=("$KIWIX_DIR"/*.zim)
    shopt -u nullglob

    if [ ${#zim_files[@]} -gt 0 ]; then
        for zim in "${zim_files[@]}"; do
            name=$(basename "$zim")
            size=$(du -h "$zim" 2>/dev/null | cut -f1)
            # Check if still downloading
            if lsof "$zim" 2>/dev/null | grep -q aria2c; then
                echo "  ⟳ $name: $size (downloading...)"
            else
                echo "  ✓ $name: $size"
            fi
        done
    else
        echo "  No content yet"
    fi

    # Check for partial downloads
    shopt -s nullglob
    aria2_files=("$KIWIX_DIR"/*.aria2)
    shopt -u nullglob

    for part in "${aria2_files[@]}"; do
        name=$(basename "$part" .aria2)
        echo "  ⟳ $name: (in progress)"
    done
else
    echo "  Directory not found"
fi
echo

# Map tiles
echo "═══ MAP TILES (GNOME Maps cache) ═══"
CACHE_DIR=~/.cache/shumate/osm-mapnik
if [ -d "$CACHE_DIR" ]; then
    count=$(find "$CACHE_DIR" -name "*.png" 2>/dev/null | wc -l)
    size=$(du -sh "$CACHE_DIR" 2>/dev/null | cut -f1)
    echo "  Tiles: $count"
    echo "  Size: $size"

    # Check if downloader is running
    if pgrep -f "download_us_tiles" >/dev/null; then
        echo "  Status: ⟳ Download in progress..."
    else
        echo "  Status: ✓ Ready"
    fi
else
    echo "  No tiles cached yet"
fi
echo

# Disk usage summary
echo "═══ DISK USAGE ═══"
df -h / | tail -1 | awk '{print "  Used: "$3" / "$2" ("$5" full)"}'
echo "  Offline content: $(du -sh ~/offline-library 2>/dev/null | cut -f1)"
echo

echo "Press Enter to close..."
read
