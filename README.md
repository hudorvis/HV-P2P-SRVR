# HV P2P SRVR v26.08.17.08 — Qt Quick macOS Intel test build

This revision keeps the proven v26.08.17.07 Qt Quick build/deployment path and concentrates on the user-requested Run/Free-D interaction and visual-completeness pass. The visible application is PySide6 + Qt Quick/QML only; Tkinter/ttk is not used.

## v26.08.17.08 changes

### Run page

- Keeps the bottom cards mathematically fixed at **Drive 20% / Speed 25% / Position 25% / Shortcuts 30%** after fixed gutters are removed.
- Restores the locked two-row Shortcuts heading/tab arrangement so the tabs sit below the `SHORTCUTS` heading.
- Preset 1–10 name fields are genuinely editable and persist.
- Preset cable-distance fields are genuinely editable, persist, and are constrained to the current cable span.
- Save / Recall / Show-Hide are wired for all ten presets.
- Near/Far/Reference Save / Recall / Slip remain wired.
- Near/Far Ramping numeric fields are editable.
- Changing Ramping **Distance ↔ Percentage converts the existing physical ramp point** instead of reinterpreting the same number. The value field immediately shows `m` or `%`.
- Drive Mode 1 / Mode 2 names are editable in the System tab and persist.
- Acceleration Mode, Battery Change Mode, Drive Mode selection, Limit Calibration and Winch Calibration are active controls.
- The shared safety/status banner retains the legacy SRVR software E-stop action while independent CTRL/W1P/RS485 safety sources remain authoritative.
- Top/Side diagrams keep the requested clean ramp-zone visual treatment and contain no lens FOV values.

### Free-D page

- The locked four-card upper layout is preserved and made taller to match the approved Free-D reference more closely.
- Free-D Input restores the complete boxed `Parameter / Raw / Decoded / Offset / Invert` table for Cam ID, Pan, Tilt, Roll, Zoom, Focus and FPS.
- Free-D Output restores the complete boxed `Parameter / Raw / Decoded / Offset / Invert` table for X, Y, Z and FPS.
- Input/Output enable, IP, port, offsets, inversion and output FPS controls are editable.
- Geometry P1–P5 X/Y values are editable; Z remains editable only on P1/P5.
- Static Weight supports kg/lbs with automatic conversion.
- Cable Weight supports kg/100m or lbs/100m with automatic conversion.
- Cable Tension supports kg/lbs with automatic conversion.
- Single Highline / Dual Highline remains selectable and now materially affects the camera-package point-load sag calculation; Static Weight is part of the live Y calculation rather than a display-only field.
- Lens Data Type supports `i16 / u16 / i24 / u24`.
- Lens Data Scale supports `Auto / Manual / Full Scale`.
- Live Zoom/Focus and Wide/Tele + Near/Far calibration fields/buttons are wired.
- **Wide FOV / Tele FOV / Narrow FOV fields and FOV-value displays are removed** as requested.
- Apply stores the current Free-D configuration; Reset restores the last applied Free-D configuration. The live outgoing Free-D stream uses the last-applied snapshot, so staged edits do not alter transmission before Apply.

### Editability fix

Earlier Qt test builds bound text editors directly to frequently-changing backend state. That allowed refresh notifications to overwrite an edit while the operator was typing, making fields feel read-only. `HVField` now uses a focus-safe model binding: backend values refresh the field only while it is not being edited, and the user's value is committed on Return or focus loss.

Fast live telemetry uses `stateChanged`; operator configuration uses the separate `configChanged` signal, so 20 Hz telemetry cannot recreate editable models while a field has focus.

## Control/backend checks

The Qt frontend still packages with the Python control engine in one `.app`. Regression checks cover:

- CTRL A6/A7 packet parsing and E-stop/ADS1115 safety handling.
- W1P command contract including `SYNC_POS`, service mode, motion profile, span/limits and velocity commands.
- 5 km/h service-speed restriction while Not Calibrated / calibrating / Battery Change.
- predictive hard-limit and ramp-zone enforcement.
- preset save/recall/edit behaviour.
- SRVR software E-stop toggle.
- Slip/SYNC re-reference.
- Battery Change auto-cancel after returning inside limits.
- Limit Calibration Near → Far → Ref → Done flow.
- position-jump rejection.
- ramp Distance/Percentage conversion.
- Free-D editable network/offset/invert/geometry/lens/weight settings.
- Free-D kg/lbs conversions and Apply/Reset staging persistence.

## GitHub build gates

The already-working v26.08.17.07 macOS Intel deployment path is retained:

1. static Python/QML/backend interface validation;
2. Python backend regression suite;
3. isolated `$RUNNER_TEMP` Qt deployment source tree;
4. `pyside6-rcc` and `pyside6-qmllint`;
5. source Qt Quick smoke test;
6. `pyside6-deploy` / Nuitka Intel build;
7. repository-metadata leak scan;
8. x86_64 verification;
9. code-signature verification / development ad-hoc fallback;
10. frozen Cocoa `.app` smoke test;
11. permission-safe ZIP packaging;
12. ZIP round-trip extraction, signature verification and a second frozen-app smoke test;
13. GitHub Actions artifact upload only after all gates pass.

This remains a development build: macOS Intel only, with no Apple Developer ID signing or notarisation.

## GitHub output

Download the Actions artifact:

`HV-P2P-SRVR-v26.08.17.08-macOS-Intel`

Inside GitHub's transport ZIP is:

`HV P2P SRVR v26.08.17.08 macOS Intel.zip`

and that inner ZIP contains only:

`HV P2P SRVR.app`
