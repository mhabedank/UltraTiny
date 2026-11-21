# Feature Specification: Switch Controller Board from ESP32 to NodeMCU

**Feature Branch**: `claude/keen-feynman-z2sszl`

**Created**: 2026-11-21

**Status**: Draft

**Input**: User description: "we want to switch from esp32 to nodeMCU"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Device works the same on the new board (Priority: P1)

A person who uses an UltraTiny device gets one built on a NodeMCU board instead of an ESP32 board. They power it up, connect it to their Wi-Fi network and use it exactly as before: the same functions, the same way of interacting with it, the same results.

**Why this priority**: This is the whole point of the switch. If the device doesn't do what it did before, nothing else matters.

**Independent Test**: Build one device on a NodeMCU board, run every function on the current ESP32 feature list against it, and compare the results with an ESP32 reference device.

**Acceptance Scenarios**:

1. **Given** a newly built NodeMCU device, **When** it is powered on for the first time, **Then** it starts up and offers the same first-time setup as the ESP32 device.
2. **Given** a NodeMCU device with Wi-Fi configured, **When** the user runs any function on the ESP32 feature list, **Then** the result matches what the ESP32 device produces under the same conditions.
3. **Given** a NodeMCU device that loses power, **When** power returns, **Then** it recovers on its own with its settings still in place, as the ESP32 device does.

---

### User Story 2 - A maker can build and flash the new board (Priority: P2)

A maintainer or hobbyist uses the project's instructions to wire up a NodeMCU board with the required peripherals, load the firmware onto it and confirm that it runs.

**Why this priority**: The switch only lasts if other people can repeat the build. Without clear build and flash steps, every new device depends on the original author.

**Independent Test**: Give the documentation and parts to someone who hasn't seen the project before, and check whether they get a working device without outside help.

**Acceptance Scenarios**:

1. **Given** a blank NodeMCU board and the parts list, **When** a maker follows the documented wiring and flashing steps, **Then** the device boots and reports that it is ready.
2. **Given** a wiring mistake, such as a peripheral on the wrong pin, **When** the device boots, **Then** it reports which peripheral it can't reach instead of failing silently.

---

### User Story 3 - Existing ESP32 devices are handled deliberately (Priority: P3)

People who already own ESP32-based devices know what the switch means for them: whether their devices keep working, keep receiving updates, or should be replaced.

**Why this priority**: It matters for existing users but doesn't block building new devices.

**Independent Test**: Check that the documentation states the support status of ESP32 devices, and that an ESP32 device behaves the way that statement says.

**Acceptance Scenarios**:

1. **Given** an existing ESP32 device, **When** its owner reads the project documentation, **Then** they find a clear statement of its support status and of any steps they need to take.
2. **Given** the support model chosen in FR-009, **When** a firmware update is released, **Then** ESP32 devices receive it or not, as that model says.

---

### Edge Cases

- A function relies on a capability the NodeMCU board lacks or has less of, such as Bluetooth, several analog inputs, many usable pins or extra memory. Each such function is either replaced, reduced in a documented way, or dropped with the decision recorded (FR-004).
- A peripheral needs 5 V logic levels or a higher current than the NodeMCU pins can safely supply.
- Some NodeMCU pins affect booting when pulled high or low at power-on, so a peripheral wired to one of them can stop the board from starting.
- The device runs out of memory under peak load, for example during a firmware update or while serving several requests at once.
- Wi-Fi is unavailable, or only a 5 GHz network is available, which the NodeMCU board can't join.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The project MUST support the NodeMCU board as a target controller for UltraTiny devices.
- **FR-002**: Before the migration starts, the project MUST record an inventory of every function the ESP32 device provides and every peripheral it connects to. This inventory is the parity baseline.
- **FR-003**: Every function in the parity baseline MUST work on the NodeMCU device, except for those documented under FR-004.
- **FR-004**: For each function that relies on a capability the NodeMCU board lacks, the project MUST record whether it is replaced, reduced or dropped, and why.
- **FR-005**: The NodeMCU device MUST keep user settings, including Wi-Fi credentials, across reboots and power loss.
- **FR-006**: The NodeMCU device MUST provide the same first-time setup and network connection experience as the ESP32 device.
- **FR-007**: The project MUST include a pin map and a wiring guide for the NodeMCU board that keeps clear of pins that interfere with booting.
- **FR-008**: The project MUST include step-by-step instructions for loading firmware onto a NodeMCU board and confirming that it works.
- **FR-009**: Existing ESP32 devices MUST be handled as follows: [NEEDS CLARIFICATION: Is ESP32 dropped completely, kept as a second supported board, or frozen at its current firmware with no further updates?]
- **FR-010**: The NodeMCU device MUST report a clear error when an expected peripheral isn't detected at startup.
- **FR-011**: The NodeMCU device MUST be able to receive firmware updates in the same way the ESP32 device can, or the parity baseline MUST record that update method as out of scope.

### Key Entities

- **Parity baseline**: The list of functions and peripherals of the current ESP32 device. Each entry gets a status on NodeMCU: supported, replaced, reduced or dropped.
- **Pin map**: Which peripheral connects to which NodeMCU pin, with voltage and boot-safety notes for each pin.
- **Device settings**: The user configuration (network credentials and device preferences) that must survive reboots.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of the functions in the parity baseline are either working on the NodeMCU device or carry a documented decision under FR-004.
- **SC-002**: A maker who hasn't seen the project before builds, flashes and verifies a working NodeMCU device in under 60 minutes, using only the project documentation.
- **SC-003**: A NodeMCU device runs continuously for 72 hours under normal use without an unplanned restart or loss of function.
- **SC-004**: After a power cut, the device is usable again within 30 seconds of power returning, with no user action needed.
- **SC-005**: The parts cost of one device goes down compared with the ESP32 build. [NEEDS CLARIFICATION: What is the main reason for the switch, for example cost, parts you already have, power use or something else? It decides which success measure matters most.]

## Assumptions

- "NodeMCU" means the common ESP8266-based NodeMCU development board (v2 or v3, with a USB-serial chip and 4 MB of flash). The firmware toolchain and language are chosen during planning, not here.
- The ESP32 firmware and hardware design that serve as the parity baseline will be added to this repository or made available to the project. The repository doesn't contain them yet. [NEEDS CLARIFICATION: Where does the current ESP32 firmware or design live, and what does the device do? Without it, the parity baseline in FR-002 can't be built.]
- The NodeMCU device connects only to 2.4 GHz Wi-Fi networks. This matches typical ESP32 deployments.
- Existing peripherals (sensors, actuators, displays) are reused wherever they're electrically compatible with the NodeMCU board's 3.3 V logic.
- The device's enclosure and power supply may need small adjustments for the new board's size and mounting holes. A full enclosure redesign is out of scope.
