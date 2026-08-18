# HV P2P SRVR v26.08.17.16 — Qt Quick macOS Intel test build

This is the final controller/interface validation revision from the approved **v26.08.17.15** Qt Quick build. The locked Run, Setup, Free-D and Log layouts, shared shell, colour/style system and existing motion/safety architecture remain unchanged. The only visible UI change is the requested Free-D Side View geometry-marker correction; the remaining changes restore proven CTRL/W1P integration paths that were present in the stable pre-Qt SRVR backend but had not been carried into the Qt migration.

## v26.08.17.16 changes

- **Free-D Side View P1-P5 markers now stay on the calculated cable path.** Each marker keeps its entered X coordinate but its displayed Y coordinate is sampled from the same calculated sagged profile used to draw the cable. The underlying editable geometry Y values are not overwritten. Top View P1/P5 Z behaviour is unchanged.
- Restores the proven **CTRL `HMI_STATUS|...` parser** so Setup can independently report CTRL-TS and ADS1115 health instead of aliasing those indicators to the parent CTRL link.
- Restores the proven **W1P `W1P_HMI_STATUS|...` parser** so Setup can independently report W1P-TS health.
- Restores **physical AUX execution**:
  - CTRL AUX1-AUX4 are handled as rising-edge inputs, so holding a button does not retrigger its action every 50 ms.
  - W1P-TS `W1PTS_AUX N` events execute the currently applied W1P-TS AUX assignment.
  - The current Setup action vocabulary is supported, including Drive Mode, Acceleration Mode, Battery Change Mode, Near/Far/Reference Save/Recall/Slip, and Preset 1-10 Save/Recall/Slip.
- Restores the proven **SRVR -> CTRL `DSP1|...` display/status packet** on UDP port 5000. The CTRL firmware relays that packet to CTRL-TS as `HMI1|...`. This is a secondary display/status path only; joystick and safety control remain on the existing binary CTRL packet path.
- The locked Setup UI still contains five stored AUX assignment rows. The currently proven CTRL firmware and current CTRL-TS interface expose **four physical AUX inputs**, and the stable W1P-TS event path likewise emits AUX1-AUX4. AUX5 therefore remains a stored/future assignment until matching controller firmware provides a fifth physical/event input.

## Control-path audit

The core motion and safety functions are unchanged from v26.08.17.15 in this revision. The final audit specifically verifies that these established paths remain intact:

- CTRL A6/A7 packet decoding and UDP/5000 heartbeat handling.
- Two-packet/0.75 s CTRL fail-safe connection qualification.
- Physical CTRL E-stop, ADS1115 fault, CTRL loss, W1P loss and W1P/RS485 fault aggregation.
- Joystick calibration/deadband, Mode and Battery Change controls, service-mode 5 km/h limit and post-calibration neutral-return interlock.
- W1P `STATUS` parsing, position-jump sanity filtering and RS485/Leadshine health classification.
- W1P commands: `SET_UNITS_PER_M`, `SET_MOTOR_REVERSE`, `SET_ACCEL`, `SET_DECEL`, `SET_CROSSOVER`, `SET_STOP_DECEL`, `SET_ACCEL_MODE`, `SET_SPAN`, `SET_LIMIT_NEAR`, `SET_LIMIT_FAR`, `SERVICE_MODE`, `VEL`, `SYNC_POS`, `STOP` and `SW_SRVON`.
- Hard Near/Far limit enforcement, ramp zones, Goto target clamping/creep behaviour and live feedback speed.

## Operator/UI audit

The final static interface audit checks every `backend.*` QML reference against the Python backend and currently finds no unresolved property/slot names. The existing contracts remain in place:

- Setup and Free-D are staged **Apply / Reset** pages; edits do not change live control or Free-D output until Apply.
- Run retains immediate operator actions for presets, limits, Drive Mode and other run-time controls.
- Setup and Run share the same applied Mode 1 / Mode 2 objects and names.
- Save Config exports applied settings only; Load Config stages imported Setup and Free-D values until their respective Apply buttons are pressed.
- Joystick calibration remains Left -> Centre -> Right, with zero-motion and neutral-return safety interlocks.
- Run / Setup / Free-D / Log keep the locked shell, heading palette and page geometry.

## Deep preflight / regression coverage

Before packaging this source tree, the local gates verify:

- Python syntax and Qt Quick-only architecture; no visible Tkinter/ttk regression.
- QML/backend reference coverage: every `backend.*` QML reference resolves to the backend.
- Locked four-page heading/style, panel geometry and clipping guards.
- Free-D Side View P1-P5 marker sampling from the calculated cable profile while Top View Z remains unchanged.
- Setup and Free-D staged Apply/Reset isolation and transferable config behaviour.
- Joystick Left/Centre/Right calibration, invalid-range rejection, electrical reversal, forced-zero motion and neutral-return interlock.
- CTRL A6/A7 packet decoding, HMI status parsing and physical AUX rising-edge behaviour.
- W1P status parsing, W1P-TS status/AUX events and the established motion/safety command vocabulary.
- Exact simulated UDP/W1P emission for the W1P settings/velocity/sync/E-stop commands and the CTRL `DSP1` packet to the configured CTRL IP on UDP/5000.
- Existing hard limits, service-mode speed cap, presets, ramp conversion, logging filters and Free-D sag calculations.
- Workflow YAML parsing, source packaging hygiene and GitHub Actions deployment guards.

The local Linux audit cannot run the native macOS PySide6/Cocoa runtime. Qt's authoritative `pyside6-qmllint`, source Qt Quick smoke test and frozen macOS `.app` smoke tests therefore remain mandatory GitHub Actions gates.

## Build output

The workflow builds macOS Intel (`x86_64`) only. Development builds remain unsigned by Apple Developer ID and are not notarised; the finished test bundle receives the existing ad-hoc development signature.

After a successful GitHub Actions run, download:

`HV-P2P-SRVR-v26.08.17.16-macOS-Intel`

The artifact contains:

`HV P2P SRVR v26.08.17.16 macOS Intel.zip`

That ZIP contains the single `HV P2P SRVR.app` bundle with the existing P2P SRVR icon and bundle/display metadata.

## GitHub Actions gates

The workflow must pass all of these before publishing the artifact:

1. Python/static project preflight.
2. Backend safety/calibration/Apply-Reset/config-transfer/controller-protocol regression tests.
3. Isolated deployment staging so repository metadata cannot enter the app.
4. `pyside6-rcc` resource generation.
5. Qt `pyside6-qmllint` validation for every QML file, including Setup and Log.
6. Source Qt Quick smoke test across all pages, Shortcuts tabs and calibration popups.
7. PySide6/Nuitka deployment.
8. Finished `.app` metadata-leak, Intel architecture and code-signature checks.
9. Frozen Cocoa `.app` smoke test.
10. Distribution ZIP CRC/layout checks.
11. ZIP round-trip extraction, signature verification and a second frozen Cocoa smoke test.
