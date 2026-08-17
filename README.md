# HV P2P SRVR v26.08.17.12 — Qt Quick macOS Intel test build

This revision uses the supplied working v26.08.17.11 application/source as the functional baseline and integrates the final locked Setup and Log designs without changing the locked Run or Free-D page bodies.

## v26.08.17.12 changes

- Integrates the final locked **Setup** page as a dedicated Qt Quick component, including CTRL/W1P link status, joystick deadband display/editing, both shared motion profiles, Drive Behaviour, AUX assignment panels, Actions, and Calibration summary.
- Integrates the final locked **Log** page with Log View, Severity, Search, Save/Clear actions, structured live table, and the final System Summary using round status lights.
- Keeps **Run** and **Free-D** page QML unchanged from the supplied v26.08.17.11 working source; only their shared shell now loads the new Setup/Log components.
- Uses the same backend `drive_modes` objects for Setup and Run, so Mode 1/Mode 2 names and profile values cannot diverge between pages.
- Adds Setup Apply/Reset to the common footer while preserving Free-D Apply/Reset; Run and Log continue to have no Apply/Reset buttons. `SRVR Time` remains left and `Uptime` right on all pages.
- Preserves the proven CTRL/W1P safety, motion, calibration, Free-D, networking and configuration command paths. AUX assignments are persisted in configuration but this revision deliberately does not invent unverified AUX hardware commands.
- Adds a parallel structured logging model for the final Log filters/table while preserving the existing plain-text log and Save Log output.
- Extends source/frozen smoke checks and backend tests for shared Setup state, Setup Apply/Reset, Log filtering and final Setup/Log QML resources.
- Corrects the macOS packaging path so the finished bundle explicitly uses the existing **P2P SRVR** icon and `HV P2P SRVR` display/name metadata before the final ad-hoc development signature.

## Build output

The workflow builds macOS Intel (`x86_64`) only. It does not perform Apple Developer ID signing or notarisation during this development/test phase.

After a successful GitHub Actions run, download the artifact:

`HV-P2P-SRVR-v26.08.17.12-macOS-Intel`

The GitHub artifact contains one transport ZIP:

`HV P2P SRVR v26.08.17.12 macOS Intel.zip`

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
