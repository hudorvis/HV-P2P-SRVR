# HV P2P SRVR v26.08.17.13 — Qt Quick macOS Intel test build

This revision is a narrow update from the working **v26.08.17.12** Qt Quick build. The locked Run, Setup, Free-D and Log layouts remain in place; only the specifically requested colour standardisation, visible text-clipping corrections and Joystick Calibration implementation have been added.

## v26.08.17.13 changes

- Standardises one heading accent, **`#26d5ff`**, across all four pages.
  - Run: Top/Side View headings and subtitles, Drive, Speed, Position and Shortcuts.
  - Setup: all main headings and section/subheadings.
  - Free-D: Input, Output, Geometry, Lens Calibration, diagram headings and section/subheadings.
  - Log: all main headings and tab accents.
- Keeps green for operational/positive state such as selected operating controls, live speed/distance values and healthy status. It is no longer used as a Run section-heading colour.
- Corrects the clipping visible in the supplied v26.08.17.12 screenshots without changing panel allocation:
  - Run > Shortcuts > System Mode 1 / Mode 2 controls and editable mode names.
  - Free-D Input/Output `Parameter` table headers.
  - Free-D Lens Calibration decoded percentage values such as `100.00 %`.
- Implements the Setup **Joystick Calibration** button as a real three-step popup wizard:
  1. `Set Joystick Left`
  2. `Set Joystick Centre`
  3. `Set Joystick Right`
- Captures the raw CTRL joystick endpoints/centre, validates that Left and Right are on opposite sides of Centre, normalises the live joystick axis around the captured centre, and saves the calibration in the existing configuration file.
- Supports electrically reversed joystick axes while preserving the existing independent CTRL Direction setting.
- Adds a calibration safety interlock: winch velocity is forced to zero for the complete joystick wizard, and after Done or Cancel motion remains inhibited until the stick is returned to the configured centre/deadband. This prevents the final full-Right capture from becoming an immediate motion command.
- Keeps the existing proven CTRL, W1P, RS485, safety, hard-limit, Goto, calibration, Free-D, networking, logging and configuration command paths intact.
- Retains the shared Setup/Run `drive_modes` backend state and the common shell/footer contract: `SRVR Time` left, `Uptime` right, Apply/Reset on Setup and Free-D only.

## Deep preflight / regression coverage

Before packaging this source tree, the local static and backend regression gates verify:

- Python syntax and Qt Quick-only architecture (no Tkinter/ttk visible UI).
- QML/backend property and slot coverage.
- One shared heading-blue style contract across Run, Setup, Free-D and Log.
- The screenshot-derived clipping fixes above while preserving the locked 20/25/25/30 Run panel split and Free-D page split.
- Joystick Left/Centre/Right capture, invalid-range rejection, persisted calibration, electrical reversal, Cancel behaviour, forced-zero motion during calibration and the post-calibration neutral-return interlock.
- Existing CTRL packet handling, ADS1115 safety, hard limits, service-speed behaviour, presets, ramp conversion, Setup Apply/Reset, shared drive-mode state, logging filters, Free-D staging and shared sag calculations.
- The existing W1P command contract, including `SYNC_POS`, `SERVICE_MODE`, acceleration/deceleration/crossover/stop-deceleration settings and the 5 km/h service limit.

Qt's authoritative `pyside6-qmllint`, source Qt Quick smoke test and frozen macOS `.app` smoke tests remain GitHub Actions gates because the development target is macOS Intel.

## Build output

The workflow builds macOS Intel (`x86_64`) only. Development builds remain unsigned by Apple Developer ID and are not notarised; the finished test bundle receives the existing ad-hoc development signature.

After a successful GitHub Actions run, download:

`HV-P2P-SRVR-v26.08.17.13-macOS-Intel`

The artifact contains:

`HV P2P SRVR v26.08.17.13 macOS Intel.zip`

That ZIP contains the single `HV P2P SRVR.app` bundle with the existing P2P SRVR icon and bundle/display metadata.

## GitHub Actions gates

The workflow must pass all of these before publishing the artifact:

1. Python/static project preflight.
2. Backend safety/calibration/interaction regression tests.
3. Isolated deployment staging so repository metadata cannot enter the app.
4. `pyside6-rcc` resource generation.
5. Qt `pyside6-qmllint` validation for every QML file.
6. Source Qt Quick smoke test across all pages, Shortcuts tabs and calibration popups.
7. PySide6/Nuitka deployment.
8. Finished `.app` metadata-leak, Intel architecture and code-signature checks.
9. Frozen Cocoa `.app` smoke test.
10. Distribution ZIP CRC/layout checks.
11. ZIP round-trip extraction, signature verification and a second frozen Cocoa smoke test.
