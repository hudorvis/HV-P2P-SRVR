# HV P2P SRVR v26.08.19.01 — Qt Quick macOS Intel test build

This is the controller/interface integration revision from the approved **v26.08.17.15** Qt Quick build. The locked Run, Setup, Free-D and Log layouts, shared shell and colour/style system remain the visual baseline. Visible integration changes are limited to the requested Free-D Side View geometry-marker correction and the CTRL-TS five-AUX top row; the remaining changes restore or strengthen proven CTRL/W1P protocol, configuration, motion and safety paths that were present in the stable pre-Qt system but had not been fully carried into the Qt migration.

## v26.08.19.01 changes

- **Five CTRL AUX actions end-to-end.** The existing A7 packet keeps its 16-bit flag field and adds AUX5 as bit `0x0400`. SRVR now accepts five CTRL AUX assignments, CTRL forwards touchscreen `AUX5`, and CTRL-TS renders five equal AUX tiles across the top row. Existing stored CTRL `main4` layouts are migrated to `main5` without losing their saved labels.
- **State-aware CTRL-TS AUX labels restored.** SRVR again publishes operator-facing labels such as `Accel Mode | Speed`, `Drive Mode | <custom name>` and `Battery Change | On/Off`, plus calibration/preset action labels.
- **Safety STOP / Servo Enable semantics strengthened.** Any SRVR-resolved safety source (SRVR E-stop, CTRL E-stop/loss, ADS1115 fault, W1P loss/E-stop or RS485/drive fault) requests the hard W1P `STOP` path plus `SW_SRVON 0`, rate-limited while the fault remains. After all sources clear, the joystick must pass through neutral before SRVR requests `SW_SRVON 1`; this prevents a held stick from restarting motion.
- **Calibrated state is persistent.** `not_calibrated_mode` is now saved/restored so an already calibrated system does not return to service/un-calibrated mode after every SRVR restart.
- **v26.06.26.25 config migration.** Legacy IP, joystick calibration, Mode A/B names and motion parameters, Accel Mode, AUX assignments, units-per-metre, limits/ramping, presets and relevant Free-D fields are migrated into schema version 2.
- **Goto anti-hunt behaviour restored.** The proven approach-direction latch, stop-before-reverse rule, early deceleration and low-speed creep logic are restored so a small target crossing does not immediately create full-direction reversal/hunting.
- **W1P diagnostics extended for software Servo Enable and the EL7 output map.** The integration SRVR parses `SW_SRVON*` plus DO2 Ready/SRDY, DO3 Enabled/SRV-ST, DO4 Brake/BRK-OFF and DO5 Fault/ALARM assignment/state fields from the matching v26.08.19.01 W1P firmware.
- **EL7 output/brake assignment safety check.** Matching W1P firmware verifies/configures DO2=SRDY, DO3=SRV-ST, DO4=BRK-OFF and DO5=ALARM while motion is locked. If software SRV-ON is already active it is first dropped during migration, and is restored only after the full map is verified. The physical EL7 DO4 still has to be wired to the external 24 V brake relay/circuit.
- **Free-D Side View P1-P5 markers remain locked to the calculated cable path.** Each marker keeps its entered X coordinate while its displayed Y coordinate is sampled from the same sagged profile used to draw the cable.

## Control-path audit

The core `.25` control contracts are retained, with the safety, calibration-direction, Goto and status fixes listed above. The final audit specifically verifies:

- CTRL A6/A7 packet decoding and UDP/5000 heartbeat handling.
- Two-packet/0.75 s CTRL fail-safe connection qualification.
- Physical CTRL E-stop, ADS1115 fault, CTRL loss, W1P loss and W1P/RS485 fault aggregation, hard STOP + software Servo Enable inhibit, and neutral-return re-arm.
- Joystick calibration/deadband, Mode and Battery Change controls, service-mode 5 km/h limit and post-calibration neutral-return interlock.
- W1P `STATUS` parsing, position-jump sanity filtering and RS485/Leadshine health classification.
- W1P commands: `SET_UNITS_PER_M`, `SET_MOTOR_REVERSE`, `SET_ACCEL`, `SET_DECEL`, `SET_CROSSOVER`, `SET_STOP_DECEL`, `SET_ACCEL_MODE`, `SET_SPAN`, `SET_LIMIT_NEAR`, `SET_LIMIT_FAR`, `SERVICE_MODE`, `VEL`, `SYNC_POS`, `STOP` and `SW_SRVON`.
- Hard Near/Far limit enforcement, ramp zones, Goto target clamping/creep behaviour, live feedback speed and Limit Calibration auto-correction of Winch Invert when physical Near-to-Far travel initially reads negative.

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

`HV-P2P-SRVR-v26.08.19.01-macOS-Intel`

The artifact contains:

`HV P2P SRVR v26.08.19.01 macOS Intel.zip`

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
