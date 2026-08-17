# HV P2P SRVR v26.08.17.09 — Qt Quick macOS Intel test build

This revision keeps the proven v26.08.17.07/v08 Qt Quick deployment path and fixes the six Run/Free-D issues reported after testing v26.08.17.08. The visible application remains PySide6 + Qt Quick/QML only; Tkinter/ttk is not used.

## v26.08.17.09 changes

### 1. Preset edit isolation

- Preset 1–5 and Preset 6–10 now use separate QML delegates with fixed indices.
- The old dynamic expression that changed a row's preset index when `shortcutTab` changed has been removed.
- Switching Shortcuts tabs or primary pages explicitly moves focus away from the current editor before changing the tab/page, so an in-progress edit commits to the field that was actually being edited.
- This specifically prevents an edit to P6/P7/etc. being written into P1/P2/etc. when switching back to Preset 1–5.

### 2. One calculated cable profile for Run and Free-D

- Run Top View, Run Side View, Free-D Top View and Free-D Side View now all use the exact same `SpanDiagram` component and the same backend `cableProfile` data.
- Run overlays Preset positions, REF and the live Skate.
- Free-D overlays P1/P2/P3/P4/P5 geometry points instead.
- The Side View cable line is no longer drawn as straight segments between P1–P5. The backend creates a smooth reference-height curve and then applies the physical whole-span sag calculation.
- Sag calculation includes cable self-weight, cable tension, static/skate weight, live skate position and Single/Dual Highline mode.
- The same calculation now drives both the diagrams and the actual Free-D Y output, avoiding UI/output disagreement.
- Top View uses P1 and P5 Z values and interpolates the complete cable line through P2/P3/P4 X positions.

### 3. Run camera guide removed / endpoint label clearance

- The old dashed camera/FOV guide lines have been removed completely from the Run Top/Side diagrams.
- Only the Skate marker/camera icon remains.
- When the Skate is close to Near or Far, the green `SKATE` text is moved away from the `NEAR LIMIT` / `FAR LIMIT` labels so they do not overlap.

### 4. Operator E-Stop source wording

The top banner now rolls lower-level faults into the system node names used by the operator:

- CTRL connection / CTRL E-stop / ADS1115 fault → `E-Stop | CTRL`
- W1P connection / W1P E-stop / RS485/config/feedback fault → `E-Stop | W1P`
- CTRL + W1P problems → `E-Stop | CTRL & W1P`
- SRVR software E-stop remains `SRVR` and can combine with the other sources when appropriate.

Low-level `RS485` and `ADS1115` labels are no longer added to the top safety banner.

### 5. Live Free-D sag preview and units

- Cable Tension now updates the staged calculated cable profile while the operator types a valid number, rather than waiting for an unrelated action.
- Geometry X/Y/Z and Static/Cable Weight values also live-preview the staged diagram calculation while being edited.
- Free-D Apply/Reset semantics remain unchanged: the diagram previews staged edits immediately, while the outgoing Free-D stream continues to use the last Applied snapshot.
- The Cable Weight unit selector has been widened so `kg/100m` and `lbs/100m` are displayed in full.
- Cable Tension remains correctly expressed as `kg` / `lbs`.

### 6. Free-D Top View restored

- The Free-D Top View now uses the same shared cable renderer as Run.
- The physical cable line is always drawn.
- P1–P5 are always plotted along the X span; P2/P3/P4 Z positions are derived from the P1→P5 Z interpolation because only P1/P5 have editable Z fields.

## Existing locked behaviour retained

- Run bottom cards remain mathematically fixed at **Drive 20% / Speed 25% / Position 25% / Shortcuts 30%** after gutters.
- Shortcuts remains Preset 1–5 / Preset 6–10 / Limits / System.
- Preset names and cable positions are editable; Save / Recall / Show-Hide remain active for all ten presets.
- Near/Far/Reference Save / Recall / Slip remain active.
- Ramping Distance ↔ Percentage converts the same physical ramp distance rather than reinterpreting the number.
- Drive Mode names remain editable.
- Limit Calibration popup design/flow is unchanged.
- Free-D Input/Output tables remain complete and editable.
- P1–P5 geometry retains Z only on P1/P5.
- Static Weight kg/lbs, Cable Weight kg/100m or lbs/100m, Cable Tension kg/lbs and Single/Dual Highline remain active.
- Lens Data Type remains i16/u16/i24/u24 and Data Scale remains Auto/Manual/Full Scale.
- No Wide/Tele/Narrow FOV value fields are present.

## Regression/build checks

Automated backend tests now additionally verify:

- exact CTRL-only, W1P-only and CTRL+W1P banner source wording;
- lower cable tension produces more calculated sag than higher cable tension;
- the Top View profile contains the full P1→P5 Z line, including the interpolated midpoint;
- the shared cable profile remains the same backend source used by the four diagrams;
- preset list QML uses fixed P1–5 and P6–10 indices rather than a tab-dependent index.

The existing CI gates remain: Python/static preflight, backend regression tests, isolated Qt deployment tree, QML lint, source smoke test, Intel Nuitka build, metadata-leak scan, x86_64 check, signature verification, frozen Cocoa smoke test, ZIP round-trip verification and a second extracted-app smoke test before artifact upload.

This remains a development build: **macOS Intel only**, without Apple Developer ID signing or notarisation.

## GitHub output

Download the Actions artifact:

`HV-P2P-SRVR-v26.08.17.09-macOS-Intel`

Inside GitHub's transport ZIP is:

`HV P2P SRVR v26.08.17.09 macOS Intel.zip`

and that inner ZIP contains only:

`HV P2P SRVR.app`
