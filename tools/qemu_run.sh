#!/usr/bin/env bash
# Run the UltraTiny firmware + a model in QEMU (emulated ESP32), interactively.
#
#   make qemu                                   # starter model
#   make qemu MODEL=training/runs/v1/model.utny
#
# Sets everything up on first use (asks before installing anything):
#   - finds ESP-IDF via $IDF_PATH or ~/esp/esp-idf and loads it (no manual export.sh needed)
#   - installs ESP-IDF v5.4.1 to ~/esp/esp-idf if it is missing (~2 GB download)
#   - installs QEMU for Xtensa via idf_tools.py if it is missing
#   - macOS: installs the required Homebrew packages if they are missing
# Set UT_YES=1 to answer all questions with yes.
#
# Quit QEMU with: Ctrl-A, then X.
# QEMU checks function and output, not speed; timings in /info are not representative.
set -euo pipefail

IDF_VERSION="v5.4.1"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
MODEL="${1:-$REPO/models/starter.utny}"
BUILD="$REPO/firmware/build-qemu"
FLASH="$BUILD/qemu_flash.bin"
IDF_DIR="${IDF_PATH:-$HOME/esp/esp-idf}"
OS="$(uname -s)"

say() { printf '\033[1m==> %s\033[0m\n' "$*"; }
confirm() {
    [ "${UT_YES:-0}" = "1" ] && return 0
    if [ ! -t 0 ]; then
        echo "$1 -> not interactive; re-run with UT_YES=1 to allow." >&2
        return 1
    fi
    read -r -p "$1 [j/N] " reply
    [[ "$reply" =~ ^[jJyY]$ ]]
}

load_idf() {
    # export.sh is not written for `set -u`; also silence its banner.
    set +u
    # shellcheck disable=SC1091
    . "$IDF_DIR/export.sh" >/dev/null 2>&1 || true
    set -u
}

brew_deps() {
    [ "$OS" = "Darwin" ] || return 0
    command -v brew >/dev/null || { echo "Homebrew fehlt: https://brew.sh" >&2; exit 1; }
    local missing=()
    for p in "$@"; do brew list --formula "$p" >/dev/null 2>&1 || missing+=("$p"); done
    [ ${#missing[@]} -eq 0 ] && return 0
    confirm "Fehlende Homebrew-Pakete installieren: ${missing[*]}?" || exit 1
    brew install "${missing[@]}"
}

# 1. ESP-IDF
if ! command -v idf.py >/dev/null; then
    if [ ! -f "$IDF_DIR/export.sh" ]; then
        say "ESP-IDF nicht gefunden (gesucht: $IDF_DIR)."
        confirm "ESP-IDF $IDF_VERSION nach $IDF_DIR installieren (~2 GB, einige Minuten)?" || exit 1
        brew_deps cmake ninja dfu-util python3
        mkdir -p "$(dirname "$IDF_DIR")"
        git clone --depth 1 -b "$IDF_VERSION" --recursive --shallow-submodules \
            https://github.com/espressif/esp-idf.git "$IDF_DIR"
        "$IDF_DIR/install.sh" esp32
    fi
    say "Lade ESP-IDF aus $IDF_DIR"
    load_idf
    command -v idf.py >/dev/null || { echo "ESP-IDF in $IDF_DIR lässt sich nicht laden." >&2; exit 1; }
fi
IDF_DIR="${IDF_PATH:-$IDF_DIR}"

# 2. QEMU for Xtensa
if ! command -v qemu-system-xtensa >/dev/null; then
    say "QEMU für den ESP32 fehlt."
    if [ "$OS" = "Darwin" ]; then
        brew_deps libgcrypt glib pixman sdl2 libslirp
    elif [ "$OS" = "Linux" ]; then
        echo "Hinweis (Linux): QEMU braucht libslirp0 und libsdl2-2.0-0 (apt install ...)."
    fi
    confirm "QEMU (qemu-xtensa) über ESP-IDF installieren?" || exit 1
    python "$IDF_DIR/tools/idf_tools.py" install qemu-xtensa
    load_idf
    command -v qemu-system-xtensa >/dev/null || { echo "QEMU-Installation fehlgeschlagen." >&2; exit 1; }
fi

[ -f "$MODEL" ] || { echo "Modell nicht gefunden: $MODEL" >&2; exit 1; }

# 3. Build (DIO/40 MHz variant, see firmware/sdkconfig.qemu) and flash image with the model
say "Baue Firmware für QEMU (beim ersten Mal dauert das etwas)"
cd "$REPO/firmware"
idf.py -B "$BUILD" -DSDKCONFIG="$BUILD/sdkconfig" \
    -DSDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.qemu" build >"$BUILD.log" 2>&1 \
    || { tail -30 "$BUILD.log"; echo "Build fehlgeschlagen, Log: $BUILD.log" >&2; exit 1; }

python -m esptool --chip esp32 merge_bin --fill-flash-size 4MB -o "$FLASH" \
    --flash_mode dio --flash_freq 40m --flash_size 4MB \
    0x1000 "$BUILD/bootloader/bootloader.bin" \
    0x8000 "$BUILD/partition_table/partition-table.bin" \
    0x10000 "$BUILD/ultratiny.bin" \
    0x110000 "$MODEL" >/dev/null

say "Starte QEMU (ESP32) mit $(basename "$MODEL"). Beenden: Strg-A, dann X."
exec qemu-system-xtensa -nographic -machine esp32 -m 4M \
    -drive "file=$FLASH,if=mtd,format=raw" -serial mon:stdio
