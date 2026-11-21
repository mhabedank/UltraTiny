# UltraTiny convenience targets. See specs/001-esp32-tiny-lm/quickstart.md.
PORT        ?= /dev/ttyUSB0
MODEL       ?= models/starter.utny
BUILD_DIR   ?= build
MODEL_MAX   := 2097152

.PHONY: test test-python test-runtime flash-model monitor budget starter qemu observe observe-host

test: test-python test-runtime

test-python:
	cd training && uv run ruff check . && uv run pytest -q

test-runtime:
	cmake -S runtime -B $(BUILD_DIR) && cmake --build $(BUILD_DIR) -j && ctest --test-dir $(BUILD_DIR) --output-on-failure

# Train the starter model end to end (Foundational, T035).
starter:
	cd training && uv run ut pipeline --config configs/starter.toml --out runs/starter

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

# Constitution I budget gate. Includes firmware sizes when firmware/build exists.
budget:
	cd training && uv run python ../tools/budget_report.py --model ../$(MODEL) \
		$$( [ -d ../firmware/build ] && echo --idf-build ../firmware/build )

# Run firmware + model in QEMU (emulated ESP32, interactive). Quit: Ctrl-A, then X.
qemu:
	tools/qemu_run.sh $(abspath $(MODEL))

# Observability viewer (specs/002-observability): starts QEMU with the console on TCP, sends the
# demo prompts with /trace json, shows probabilities, timings, profile and /stats; stops QEMU.
# Real board: make observe OBSERVE_SRC="--port /dev/ttyUSB0"
OBSERVE_SRC  ?= --qemu
OBSERVE_ARGS ?= --demo 5
observe:
	cd training && uv run python ../tools/observe.py $(OBSERVE_SRC) --model $(abspath $(MODEL)) $(OBSERVE_ARGS)

# Same viewer against the PC runtime (build/utiny-host --console), no emulator needed.
observe-host: test-runtime
	cd training && uv run python ../tools/observe.py --host --model $(abspath $(MODEL)) $(OBSERVE_ARGS)
