# HV P2P SRVR v26.08.17.10 — Qt Quick macOS Intel test build

This revision carries forward all v26.08.17.09 Run/Free-D/backend fixes and corrects the QML syntax/lint failure that stopped v09 before deployment. The visible application remains PySide6 + Qt Quick/QML only; Tkinter/ttk is not used.

## v26.08.17.10 changes

- Fixes the six `Unexpected token ';'` qmllint errors in `qml/Main.qml`. These came from JavaScript-style semicolons placed between adjacent QML signal-handler attributes (`onTextEdited` and `onCommit`). The affected geometry and Static/Cable/Tension editors have been rewritten as explicit multi-line QML objects using normal QML handler syntax.
- Removes the qmllint warnings reported by the custom combo-box delegate by using `pragma ComponentBehavior: Bound`, explicitly declared delegate roles, and qualified delegate-property access.
- Removes the reusable `SpanDiagram.qml` component's direct reference to the global `backend` context property. The diagram now repaints from changes to its own bound properties, which is cleaner, reusable and lint-safe.
- Adds a pre-dependency static guard that rejects the exact illegal `}; on...:` handler pattern that broke v09 before GitHub even installs Qt.
- Expands local QML structural checks to balance `{}`, `()` and `[]`, rather than braces only.
- Preserves all v09 requested behaviour: fixed Preset 1–5 / 6–10 edit isolation, shared Run/Free-D cable profile, smooth calculated Side View sag, no Run camera/FOV guide line, endpoint-safe SKATE label, simplified CTRL/W1P E-Stop banner naming, live cable-tension sag preview, full `kg/100m` selector, and complete Free-D Top View cable/geometry display.
- No intentional visual redesign has been made relative to v09.

## Build output

The workflow builds macOS Intel (`x86_64`) only. It does not perform Apple Developer ID signing or notarisation during this development/test phase.

After a successful GitHub Actions run, download the artifact:

`HV-P2P-SRVR-v26.08.17.10-macOS-Intel`

The GitHub artifact contains one transport ZIP:

`HV P2P SRVR v26.08.17.10 macOS Intel.zip`

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
