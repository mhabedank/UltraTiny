# Contract: Budget report with board profiles

Extends `tools/budget_report.py` (standard library only, as today).

```text
python tools/budget_report.py --model <file.utny> [--board nodemcu|esp32]
                              [--pio-build firmware-nodemcu/.pio/build/nodemcuv2]
                              [--idf-build firmware/build] [--json out.json]
```

- `--board` defaults to `nodemcu` (constitution v2.0.0). Profiles: see
  [data-model.md](../data-model.md#board-budget-profile-toolsbudget_reportpy).
- `--pio-build`: reads `firmware.bin` size and static RAM (`.data` + `.bss` + `.rodata` in DRAM)
  from the linker map / `firmware.elf` via `xtensa-lx106-elf-size` when available, else from the
  map file.
- Output: one line per budget, as today, e.g.

  ```text
  model            601,884 / 688,128 B  (87.5 %)  OK
  arena             35,520 /  40,960 B  (86.7 %)  OK
  firmware         289,000 / 360,448 B  (80.2 %)  OK
  mapped window    1,048,576 / 1,048,576 B  firmware area + model area  OK
  ```

- Exit code 1 if any budget has < 10 % headroom, the two areas don't fit the mapped window, or the
  model's arena is larger than the firmware's `UT_ARENA_MAX`.
- `--json` adds `"board"` to the existing JSON object; other keys unchanged.
