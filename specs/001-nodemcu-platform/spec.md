# Feature Specification: NodeMCU as the UltraTiny Hardware Platform

**Feature Branch**: `claude/keen-feynman-z2sszl`

**Created**: 2026-11-21

**Status**: Draft

**Input**: User description: "we want to switch from esp32 to nodeMCU"

**Clarifications (2026-11-21)**:
- ESP32 is dropped completely. There are no existing ESP32 devices to support or migrate.
- The reason for the switch is that NodeMCU boards are already on hand. The platform must work with the boards that are there; parts cost is not a goal.
- No ESP32 firmware or design exists yet. This is a new project on NodeMCU, not a migration.

## Overview

UltraTiny targets the NodeMCU board as its only controller. This feature lays the foundation every later device feature builds on: a NodeMCU board from the existing stock can be flashed, connected to Wi-Fi, keeps its settings, and reports its own health and attached peripherals. The device's specific functions (what it measures, shows or switches) are out of scope here and will be specified as separate features.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Flash a board from stock and see it come alive (Priority: P1)

A maker takes a NodeMCU board from the boards already on hand, connects it to a computer, follows the project instructions to load the firmware, and sees the board confirm that it is running.

**Why this priority**: Nothing else is possible until boards from the existing stock can be brought up reliably and repeatably.

**Independent Test**: Take a board that has never been used for the project, follow only the written instructions, and check that it reports a running state.

**Acceptance Scenarios**:

1. **Given** a blank NodeMCU board from stock and a computer, **When** the maker follows the documented flashing steps, **Then** the board starts and signals that it is running (visible indicator plus a readable status message).
2. **Given** a board that already runs an older UltraTiny firmware, **When** the maker flashes the current version, **Then** the board runs the new version and reports its version number.
3. **Given** a board that cannot be flashed (faulty USB connection or defective board), **When** the maker follows the steps, **Then** the instructions help them recognise the fault and set that board aside.

---

### User Story 2 - Connect the device to Wi-Fi without editing firmware (Priority: P2)

A user powers on a freshly flashed device, enters their Wi-Fi details through a simple setup flow, and the device joins the network and stays connected across restarts.

**Why this priority**: Network access is the basis for nearly every later device function, and putting credentials into the firmware itself would mean reflashing for every network.

**Independent Test**: Flash a board, complete setup on a phone or laptop, cut power, restore it, and confirm the device reconnects by itself.

**Acceptance Scenarios**:

1. **Given** a device without saved Wi-Fi settings, **When** it is powered on, **Then** it offers a setup mode a phone or laptop can connect to in order to enter network details.
2. **Given** valid network details have been entered, **When** setup is completed, **Then** the device joins the network and leaves setup mode.
3. **Given** a configured device, **When** power is cut and restored, **Then** it reconnects with the saved settings without user action.
4. **Given** saved settings that no longer work (password changed, network gone), **When** the device cannot connect for a set period, **Then** it returns to setup mode so the user can enter new details.
5. **Given** a configured device, **When** the user triggers a documented reset action, **Then** saved settings are erased and the device starts in setup mode.

---

### User Story 3 - Wire peripherals safely and know when one is missing (Priority: P3)

A maker connects sensors or other parts to the board using the project's pin map. When the device starts, it reports which expected peripherals it found and which it did not.

**Why this priority**: Later device features depend on peripherals. A shared pin map and startup check prevent boot failures and wasted debugging time.

**Independent Test**: Wire the board per the pin map with one peripheral deliberately disconnected, and check that the device starts normally and names the missing part.

**Acceptance Scenarios**:

1. **Given** the pin map, **When** a maker wires peripherals to the recommended pins, **Then** the board still starts normally.
2. **Given** an expected peripheral is disconnected, **When** the device starts, **Then** it reports that peripheral as missing and keeps running everything else.

---

### Edge Cases

- A board from stock turns out to be a different NodeMCU variant (different USB-serial chip, board revision or flash size); the instructions identify the supported variants and how to tell them apart.
- A peripheral is wired to a pin that affects booting, and the board fails to start; the pin map marks such pins clearly.
- Only a 5 GHz network is available, which the board can't join; setup tells the user that no usable network was found.
- The device runs low on memory; it restarts cleanly instead of hanging, and reports that a restart happened.
- Power is cut while settings are being saved; on the next start the device has either the old or the new settings, never corrupted ones.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The NodeMCU board MUST be the only supported controller for UltraTiny; no other controller board is supported.
- **FR-002**: The project MUST document which NodeMCU variants are supported and how a maker identifies the variant of a board on hand.
- **FR-003**: The project MUST provide step-by-step instructions to load firmware onto a supported board and confirm it runs.
- **FR-004**: The device MUST signal its running state at startup through a visible indicator and a readable status message, including its firmware version.
- **FR-005**: The device MUST offer a setup mode for entering Wi-Fi details from a phone or laptop, without changing the firmware.
- **FR-006**: The device MUST store its settings so they survive restarts and power loss, and MUST never be left with corrupted settings after an interrupted save.
- **FR-007**: The device MUST reconnect automatically to the saved network after a restart or a network outage.
- **FR-008**: The device MUST return to setup mode when it cannot connect with the saved settings for 5 minutes.
- **FR-009**: The device MUST provide a documented way to erase saved settings and return to setup mode.
- **FR-010**: The project MUST provide a pin map for the supported boards that marks pins reserved for booting, pins that are safe for peripherals, and the board's voltage limits.
- **FR-011**: The device MUST check for its expected peripherals at startup, report each missing one by name, and keep running the rest.
- **FR-012**: The device MUST restart itself cleanly when it stops responding, and report after the restart that one occurred.

### Key Entities

- **Device settings**: The user configuration kept on the board: network details and device preferences.
- **Pin map**: Which pins may be used for peripherals, which are reserved or affect booting, and their voltage limits.
- **Device status**: What the device reports about itself: firmware version, network state, peripherals found or missing, and whether the last start followed an unplanned restart.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every working board in the existing stock can be flashed and brought to a running state using only the project instructions.
- **SC-002**: A maker new to the project goes from a blank board to a running device in under 30 minutes.
- **SC-003**: A new user completes Wi-Fi setup in under 3 minutes on their first attempt.
- **SC-004**: After a power cut, the device is back online within 30 seconds of power returning, with no user action.
- **SC-005**: A device runs for 72 hours without an unplanned restart or loss of network connection while the network is available.

## Assumptions

- "NodeMCU" means the ESP8266-based NodeMCU development board (v2 or v3 with 4 MB flash), which is what the boards on hand are assumed to be. The firmware toolchain and language are chosen during planning.
- The device's specific functions and peripherals are not yet defined and will be specified as separate features on top of this platform.
- The device joins only 2.4 GHz Wi-Fi networks.
- Peripherals added later work with the board's 3.3 V logic, or get level shifting that is documented with the feature that adds them.
- Settings are entered by someone with physical access to the device; securing setup mode against nearby strangers beyond a standard Wi-Fi password is out of scope for this feature.
