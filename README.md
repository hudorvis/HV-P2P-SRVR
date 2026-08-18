# HV P2P SRVR v26.08.17.15 — Qt Quick macOS Intel test build

This is a narrow Free-D geometry/sag correction from the approved **v26.08.17.14** Qt Quick build. The locked Run, Setup, Free-D and Log page design, shared shell, colour/style system and existing control architecture remain unchanged except for the Free-D span/sag behaviour described below.

## v26.08.17.15 changes

- Corrects the Free-D geometry model so **Near Limit and Far Limit are the actual cable-span endpoints**. P1, P2, P3, P4 and P5 are now independent geometry/reference points that may be positioned anywhere within that calibrated span.
- Removes the old internal `P1 (Near)` / `P5 (Far)` semantics. Existing configurations are normalised to the neutral `P1` ... `P5` labels when loaded.
- The Top View now extends the P1/P5 Z reference line through the complete Near-to-Far span instead of clamping the line at P1 and P5. P2-P4 Z remains intentionally disabled.
- The Side View calculated profile is now the **loaded skate/camera path across the whole run**. At every X sample, the skate point load is evaluated at that X. This matches the Free-D Y calculation at the live skate position and allows the full-run preview to be meaningful even while the rig is offline or parked at a support.
- The sag calculation uses all four operator inputs in one model:
  - **Skate Weight** is the suspended skate/camera package mass.
  - **Cable Weight** is cable mass per 100 m, per individual highline cable.
  - **Cable Tension** is treated as per-cable horizontal tension in kgf/lbf-equivalent units for the existing small-sag model.
  - **Dual Highline** shares the skate package 50/50 between the two cables; each cable retains its own self-weight and entered per-cable tension.
- The Free-D diagram vertical scale is now anchored to the entered geometry/reference points and Near/Far support heights. It no longer automatically zooms around ordinary sag changes, which previously made different Skate Weight / Cable Weight / Cable Tension / Highline Mode values look almost identical. Extreme profiles can still expand the scale to avoid severe clipping.
- Free-D Apply/Reset behaviour remains unchanged: all of the above changes are previewed from `freeDDraft`, while the live Free-D output continues using the last-applied configuration until **Apply** is selected.

Everything else remains locked to the approved v26.08.17.14 design and functionality.

## Compatibility and safety notes

The previous immediate-write backend slots are retained for compatibility with older internal callers, but the Setup QML no longer calls them. The operator-facing Setup page uses only staged `setSetup*` methods.

Joystick calibration retains the v26.08.17.13 motion interlock: winch velocity is forced to zero while the wizard is open, and after Done or Cancel motion remains inhibited until the joystick has returned to Centre/deadband. Completing the wizard only stages the calibration; Setup Apply performs the live/persistent commit.

No new unverified AUX hardware protocol has been invented in this revision. The requested Preset Save names are available for assignment/persistence through the existing AUX assignment mechanism.

## Deep preflight / regression coverage

Before packaging this source tree, the local gates verify:

- Python syntax and Qt Quick-only architecture; no visible Tkinter/ttk regression.
- QML/backend property and slot coverage.
- Locked four-page heading/style and Run/Free-D geometry contracts.
- All ten Preset Save AUX assignment options and both AUX panels using the same staged list.
- Setup draft isolation, page-navigation persistence, Apply commit and Reset rollback.
- Free-D draft isolation, staged preview, page-navigation persistence, Apply commit and Reset rollback.
- Transferable config export/import, including QML-style `file://` URLs, applied-only export and staged import.
- Joystick Left/Centre/Right staged calibration, invalid-range rejection, electrical reversal, forced-zero motion and neutral-return safety interlock.
- Existing CTRL packet handling, ADS1115 safety, hard limits, service-speed behaviour, presets, ramp conversion, logging filters and canonical cable-sag calculations.
- Existing W1P command contract including `SYNC_POS`, `SERVICE_MODE`, acceleration/deceleration/crossover/stop-deceleration settings and the 5 km/h service limit.
- Source packaging hygiene and GitHub Actions deployment guards.

Qt's authoritative `pyside6-qmllint`, source Qt Quick smoke test and frozen macOS `.app` smoke tests remain GitHub Actions gates because the development target is macOS Intel.

## Build output

The workflow builds macOS Intel (`x86_64`) only. Development builds remain unsigned by Apple Developer ID and are not notarised; the finished test bundle receives the existing ad-hoc development signature.

After a successful GitHub Actions run, download:

`HV-P2P-SRVR-v26.08.17.15-macOS-Intel`

The artifact contains:

`HV P2P SRVR v26.08.17.15 macOS Intel.zip`

That ZIP contains the single `HV P2P SRVR.app` bundle with the existing P2P SRVR icon and bundle/display metadata.

## GitHub Actions gates

The workflow must pass all of these before publishing the artifact:

1. Python/static project preflight.
2. Backend safety/calibration/Apply-Reset/config-transfer regression tests.
3. Isolated deployment staging so repository metadata cannot enter the app.
4. `pyside6-rcc` resource generation.
5. Qt `pyside6-qmllint` validation for every QML file, including Setup and Log.
6. Source Qt Quick smoke test across all pages, Shortcuts tabs and calibration popups.
7. PySide6/Nuitka deployment.
8. Finished `.app` metadata-leak, Intel architecture and code-signature checks.
9. Frozen Cocoa `.app` smoke test.
10. Distribution ZIP CRC/layout checks.
11. ZIP round-trip extraction, signature verification and a second frozen Cocoa smoke test.
