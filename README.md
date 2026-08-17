# HV P2P SRVR v26.08.17.11 — Qt Quick macOS Intel test build

This revision carries forward the working Qt Quick build/deployment path and applies the requested Run/Free-D refinements without changing the locked overall visual language.

## v26.08.17.11 changes

- Renames the Free-D **Static Weight** control to **Skate Weight** throughout the visible Qt Quick interface.
- Makes **Skate Weight / Cable Weight / Cable Tension / Highline Mode** explicit inputs to the single canonical cable-sag model used by:
  - Run Side View,
  - Free-D Side View,
  - the live Free-D Y value, and
  - transmitted Free-D Y after Apply.
- Preserves the legacy engineering rule from the previous SRVR backend: Cable Weight and Cable Tension are entered **per individual highline cable**. Dual Highline shares the suspended Skate Weight between the two cables; each cable still carries its own self-weight at its entered tension.
- Keeps backward configuration compatibility with older `static_weight_kg` / `static_weight_unit` keys while saving the new `skate_weight_kg` / `skate_weight_unit` names.
- Aligns the **Drive Mode** controls in Shortcuts > System to the same 150 px control start used by Acceleration Mode, Battery Change Mode and Calibration Mode. The Mode 1 button therefore starts directly under the Battery Change `Off` button column.
- Removes the `SKATE` text label from both shared Top View / Side View diagrams. The green downward arrow and moving skate/camera icon remain.
- Expands regression/smoke tests so Skate Weight, Cable Weight, Cable Tension and Single/Dual Highline are each proven to change the calculated sag as expected, and verifies Free-D Y uses the exact same sag function as the displayed cable profile.

## Build output

The workflow builds macOS Intel (`x86_64`) only. It does not perform Apple Developer ID signing or notarisation during this development/test phase.

After a successful GitHub Actions run, download the artifact:

`HV-P2P-SRVR-v26.08.17.11-macOS-Intel`

The GitHub artifact contains one transport ZIP:

`HV P2P SRVR v26.08.17.11 macOS Intel.zip`

That inner ZIP contains the single `HV P2P SRVR.app` bundle and preserves the macOS executable permissions/bundle structure.

## CI gates before an artifact is published

The workflow must pass all of these before upload:

1. Python/static project preflight.
2. Backend safety/calibration/interaction regression tests.
3. Isolated deployment staging so repository metadata cannot enter the app.
4. `pyside6-rcc` resource generation.
5. Qt `pyside6-qmllint` syntax/type validation for every QML file.
6. Source Qt Quick smoke test.
7. PySide6/Nuitka deployment.
8. Finished `.app` metadata-leak, Intel architecture and code-signature checks.
9. Frozen Cocoa `.app` smoke test.
10. Distribution ZIP CRC/layout checks.
11. ZIP round-trip extraction, signature verification and a second frozen Cocoa smoke test.
