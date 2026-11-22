# UltraTiny convenience targets. NodeMCU (ESP8266, current target): specs/005-nodemcu-port/quickstart.md.
# Legacy ESP32 targets (flash-model, monitor, qemu): specs/001-esp32-tiny-lm/quickstart.md.
PORT        ?= /dev/ttyUSB0
MODEL       ?= models/starter.utny
BUILD_DIR   ?= build
MODEL_MAX   := 2097152

# NodeMCU (contracts/flash-layout.md); keep in sync with firmware-nodemcu/include/layout.h
NODEMCU_MODEL      ?= models/nodemcu.utny
NODEMCU_MODEL_ADDR := 0x58000
NODEMCU_MODEL_MAX  := 688128
ESPTOOL            ?= esptool.py
PIO_BUILD          := firmware-nodemcu/.pio/build/nodemcuv2
BOARD              ?= nodemcu

.PHONY: test test-python test-runtime flash-model monitor budget starter nodemcu qemu observe \
	observe-host nodemcu-build nodemcu-flash nodemcu-flash-model nodemcu-monitor spark-loss

test: test-python test-runtime

test-python:
	cd training && uv run ruff check . && uv run pytest -q

test-runtime:
	cmake -S runtime -B $(BUILD_DIR) && cmake --build $(BUILD_DIR) -j && ctest --test-dir $(BUILD_DIR) --output-on-failure

# Train the starter model end to end (Foundational, T035).
starter:
	cd training && uv run ut pipeline --config configs/starter.toml --out runs/starter

# Train the NodeMCU PoC model (specs/005-nodemcu-port): starter architecture, context 104.
nodemcu:
	cd training && uv run ut pipeline --config configs/nodemcu.toml --out runs/nodemcu --device cpu

# Live loss chart of training runs on the Spark (tools/loss_viewer.py, opens the browser).
SPARK         ?= dienstollama@cst-ai-02
SPARK_PATTERN ?= *-s*.log
spark-loss:
	python3 tools/loss_viewer.py --ssh $(SPARK) --pattern '$(SPARK_PATTERN)'

# --- NodeMCU (ESP8266) firmware, specs/005-nodemcu-port/contracts/flash-layout.md ---
nodemcu-build:
	cd firmware-nodemcu && pio run

nodemcu-flash:
	cd firmware-nodemcu && pio run -t upload --upload-port $(PORT)

# Flash only the model area (0x58000); firmware stays untouched. NODEMCU_MODEL=... picks the file.
nodemcu-flash-model:
	@test -f "$(NODEMCU_MODEL)" || { echo "Model file not found: $(NODEMCU_MODEL)"; exit 1; }
	@size=$$(wc -c < "$(NODEMCU_MODEL)"); if [ $$size -gt $(NODEMCU_MODEL_MAX) ]; then \
		echo "Model too large for the NodeMCU model area: $$size > $(NODEMCU_MODEL_MAX) bytes"; exit 1; fi
	@magic=$$(head -c 4 "$(NODEMCU_MODEL)"); if [ "$$magic" != "UTNY" ]; then \
		echo "Not a UTNY model file (magic '$$magic')"; exit 1; fi
	$(ESPTOOL) --port $(PORT) write_flash $(NODEMCU_MODEL_ADDR) "$(NODEMCU_MODEL)"

nodemcu-monitor:
	cd firmware-nodemcu && pio device monitor -p $(PORT) -b 115200

# --- Legacy ESP32 (specs/001-esp32-tiny-lm) ---
# Flash only the model partition; firmware stays untouched (User Story 3).
flash-model:
	@test -f "$(MODEL)" || { echo "Model file not found: $(MODEL)"; exit 1; }
	@size=$$(wc -c < "$(MODEL)"); if [ $$size -gt $(MODEL_MAX) ]; then \
		echo "Model too large: $$size bytes > $(MODEL_MAX)"; exit 1; fi
	@magic=$$(head -c 4 "$(MODEL)"); if [ "$$magic" != "UTNY" ]; then \
		echo "Not a UTNY model file (magic '$$magic')"; exit 1; fi
	parttool.py --port $(PORT) --partition-table-file firmware/partitions.csv \
		write_partition --partition-name model --input "$(MODEL)"

monitor:
	cd firmware && idf.py -p $(PORT) monitor

# Constitution I budget gate, default board nodemcu (model: NODEMCU_MODEL, firmware sizes when
# built). Legacy: make budget BOARD=esp32 (model: MODEL, firmware sizes from firmware/build).
ifeq ($(BOARD),esp32)
BUDGET_ARGS = --board esp32 --model ../$(MODEL) $(if $(wildcard firmware/build),--idf-build ../firmware/build)
else
BUDGET_ARGS = --board nodemcu --model ../$(NODEMCU_MODEL) $(if $(wildcard $(PIO_BUILD)/firmware.bin),--pio-build ../$(PIO_BUILD))
endif
budget:
	cd training && uv run python ../tools/budget_report.py $(BUDGET_ARGS)

# Run firmware + model in QEMU (emulated ESP32, interactive). Quit: Ctrl-A, then X.
qemu:
	tools/qemu_run.sh $(abspath $(MODEL))

# Observability viewer (specs/002-observability): starts QEMU with the console on TCP, sends the
# demo prompts with /trace json, shows probabilities, timings, profile and /stats; stops QEMU.
# Real board: make observe OBSERVE_SRC="--port /dev/ttyUSB0"
# Every run writes a JSONL log to logs/ (OBSERVE_LOG= disables it).
OBSERVE_SRC  ?= --qemu
OBSERVE_ARGS ?= --demo 5
OBSERVE_LOG  ?= logs/observe-$(shell date +%Y%m%d-%H%M%S).jsonl
OBSERVE_LOGARG = $(if $(OBSERVE_LOG),--log $(abspath $(OBSERVE_LOG)))
observe:
	cd training && uv run python ../tools/observe.py $(OBSERVE_SRC) --model $(abspath $(MODEL)) $(OBSERVE_LOGARG) $(OBSERVE_ARGS)

# Same viewer against the PC runtime (build/utiny-host --console), no emulator needed.
observe-host: test-runtime
	cd training && uv run python ../tools/observe.py --host --model $(abspath $(MODEL)) $(OBSERVE_LOGARG) $(OBSERVE_ARGS)
