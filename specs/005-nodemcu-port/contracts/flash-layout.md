# Contract: NodeMCU flash layout and flashing

Board: NodeMCU v2/v3, ESP8266EX, 4 MB flash. Only flash offsets `0x000000`–`0x0FFFFF` are
memory-mapped (at `0x40200000`), so firmware and model share this window.

| Region | Flash offset | Size | Mapped address | Content |
|--------|--------------|------|----------------|---------|
| Firmware area | `0x000000`–`0x057FFF` | 352 KB | `0x40200000` | bootloader + firmware image (linker script `firmware-nodemcu/ld/eagle.flash.4m.ultratiny.ld`) |
| Model area | `0x058000`–`0x0FFFFF` | 672 KB | `0x40258000` | UTNY v1 model file, unchanged format |
| Rest | `0x100000`–`0x3FFFFF` | 3 MB | not mapped | unused (SDK config sectors at the end of flash, as the core expects) |

Rules:

- `UT_MODEL_FLASH_OFFSET = 0x58000` is defined once (`firmware-nodemcu/include/layout.h`) and used
  by the linker script, the firmware and `make nodemcu-flash-model`. The numbers are provisional;
  the boundary may move in 16 KB steps if the budget report shows the firmware needs it, as long
  as both areas keep ≥ 10 % headroom.
- The firmware never writes to the model area.
- An erased model area (`0xFF…`) or a bad image gives the existing `HALT_ERROR` messages
  (001 serial-console contract), not a reboot loop.

## Commands (from the repository root)

| Purpose | Command |
|---------|---------|
| Build firmware | `make nodemcu-build` → `cd firmware-nodemcu && pio run` |
| Flash firmware | `make nodemcu-flash PORT=/dev/ttyUSB0` → `pio run -t upload --upload-port $(PORT)` |
| Flash model only | `make nodemcu-flash-model PORT=… NODEMCU_MODEL=models/nodemcu.utny` → checks magic `UTNY` and size ≤ 688,128 B, then `esptool.py --port $(PORT) write_flash 0x58000 $(NODEMCU_MODEL)` |
| Serial console | `make nodemcu-monitor PORT=…` → `pio device monitor -p $(PORT) -b 115200` |
| Identify board | `esptool.py --port $(PORT) flash_id` → expect `ESP8266EX`, `Detected flash size: 4MB` |
