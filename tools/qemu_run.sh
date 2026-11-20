#!/usr/bin/env bash
# Run the UltraTiny firmware + a model in QEMU (emulated ESP32), interactively.
#
#   make qemu                       # starter model
#   make qemu MODEL=training/runs/v1/model.utny
#
# Requires an exported ESP-IDF v5.4 (. $IDF_PATH/export.sh) and QEMU for Xtensa:
#   python $IDF_PATH/tools/idf_tools.py install qemu-xtensa && . $IDF_PATH/export.sh
# macOS additionally: brew install libgcrypt glib pixman sdl2 libslirp
# Linux (Debian/Ubuntu) additionally: apt install libslirp0 libsdl2-2.0-0
#
# Quit QEMU with: Ctrl-A, then X.
# Note: QEMU checks function and output, not speed; timings in /info are not representative.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
MODEL="${1:-$REPO/models/starter.utny}"
BUILD="$REPO/firmware/build-qemu"
FLASH="$BUILD/qemu_flash.bin"

command -v idf.py >/dev/null || { echo "ESP-IDF not exported (. \$IDF_PATH/export.sh)"; exit 1; }
command -v qemu-system-xtensa >/dev/null || {
    echo "qemu-system-xtensa not found. Install: python \$IDF_PATH/tools/idf_tools.py install qemu-xtensa"
    echo "then re-run: . \$IDF_PATH/export.sh"; exit 1; }
[ -f "$MODEL" ] || { echo "Model not found: $MODEL"; exit 1; }

cd "$REPO/firmware"
idf.py -B "$BUILD" -DSDKCONFIG="$BUILD/sdkconfig" \
    -DSDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.qemu" build >/dev/null

python -m esptool --chip esp32 merge_bin --fill-flash-size 4MB -o "$FLASH" \
    --flash_mode dio --flash_freq 40m --flash_size 4MB \
    0x1000 "$BUILD/bootloader/bootloader.bin" \
    0x8000 "$BUILD/partition_table/partition-table.bin" \
    0x10000 "$BUILD/ultratiny.bin" \
    0x110000 "$MODEL" >/dev/null

echo "Starting QEMU (esp32) with $(basename "$MODEL"). Quit: Ctrl-A, then X."
exec qemu-system-xtensa -nographic -machine esp32 -m 4M \
    -drive "file=$FLASH,if=mtd,format=raw" -serial mon:stdio
