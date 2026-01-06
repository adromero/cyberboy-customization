#!/bin/bash
# RetroArch launcher for Cyberboy
# Presents a menu to choose system, then ROM

ROMS_DIR="$HOME/ROMs"

# Define systems and their cores
declare -A CORES
CORES["nes"]="/usr/lib/aarch64-linux-gnu/libretro/nestopia_libretro.so"
CORES["snes"]="/usr/lib/aarch64-linux-gnu/libretro/snes9x_libretro.so"
CORES["gb"]="/usr/lib/aarch64-linux-gnu/libretro/gambatte_libretro.so"
CORES["gbc"]="/usr/lib/aarch64-linux-gnu/libretro/gambatte_libretro.so"
CORES["gba"]="/usr/lib/aarch64-linux-gnu/libretro/mgba_libretro.so"
CORES["genesis"]="/usr/lib/aarch64-linux-gnu/libretro/genesis_plus_gx_libretro.so"

declare -A NAMES
NAMES["nes"]="Nintendo NES"
NAMES["snes"]="Super Nintendo"
NAMES["gb"]="Game Boy"
NAMES["gbc"]="Game Boy Color"
NAMES["gba"]="Game Boy Advance"
NAMES["genesis"]="Sega Genesis"

# Build system menu
systems=""
for sys in nes snes gb gbc gba genesis; do
    count=$(find "$ROMS_DIR/$sys" -maxdepth 1 -type f \( -iname "*.nes" -o -iname "*.smc" -o -iname "*.sfc" -o -iname "*.gb" -o -iname "*.gbc" -o -iname "*.gba" -o -iname "*.md" -o -iname "*.bin" -o -iname "*.zip" \) 2>/dev/null | wc -l)
    systems+="${NAMES[$sys]} ($count ROMs)\n"
done

# Add option to open RetroArch directly
systems+="Open RetroArch Menu"

# Show system selection
choice=$(echo -e "$systems" | wofi --dmenu --prompt "Select System" --width 400 --height 300)

[ -z "$choice" ] && exit 0

# Open RetroArch directly if selected
if [[ "$choice" == "Open RetroArch Menu" ]]; then
    retroarch
    exit 0
fi

# Find which system was selected
selected_sys=""
for sys in nes snes gb gbc gba genesis; do
    if [[ "$choice" == "${NAMES[$sys]}"* ]]; then
        selected_sys="$sys"
        break
    fi
done

[ -z "$selected_sys" ] && exit 0

# List ROMs for selected system
rom_list=$(find "$ROMS_DIR/$selected_sys" -maxdepth 1 -type f \( -iname "*.nes" -o -iname "*.smc" -o -iname "*.sfc" -o -iname "*.gb" -o -iname "*.gbc" -o -iname "*.gba" -o -iname "*.md" -o -iname "*.bin" -o -iname "*.zip" \) 2>/dev/null | sort)

if [ -z "$rom_list" ]; then
    notify-send "No ROMs" "No ROMs found in ~/ROMs/$selected_sys"
    exit 0
fi

# Show ROM selection
rom_names=$(echo "$rom_list" | xargs -I{} basename "{}")
selected_rom=$(echo "$rom_names" | wofi --dmenu --prompt "Select Game" --width 500 --height 400)

[ -z "$selected_rom" ] && exit 0

# Get full path
full_path="$ROMS_DIR/$selected_sys/$selected_rom"

# Launch with appropriate core
retroarch -L "${CORES[$selected_sys]}" "$full_path"
