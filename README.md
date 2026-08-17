# HV P2P SRVR v26.08.17.05 — Qt Quick macOS Intel test build

This is the next Qt Quick development build of HV P2P SRVR. The visible interface is PySide6 + Qt Quick/QML only; Tkinter/ttk is not used by the application UI.

## What v26.08.17.05 fixes

The v26.08.17.04 failure was caused by `pyside6-deploy`/Nuitka seeing the checked-out GitHub repository and copying `.github` into the generated `.app`. This revision does not deploy from the repository at all. GitHub Actions creates a clean directory under `$RUNNER_TEMP`, copies only `main.py`, `backend.py`, `resources.qrc`, `HV_P2P_SRVR.pyproject`, and `qml/`, and runs every Qt/Nuitka deployment command from that isolated directory. `.github` therefore does not exist in the deployment source tree.

The Qt resource compiler now generates the expected `rc_resources.py` file for `resources.qrc`, removing the previous resource-name mismatch.

The GitHub build pins `PySide6==6.11.1` so a newer Qt/PySide release cannot silently change the deployment behaviour between test builds.

The workflow now performs multiple preflight gates before publishing anything:

- Python syntax and static project validation.
- Backend safety/calibration regression tests.
- `pyside6-qmllint` against all QML files, with warnings reported but only real lint errors blocking the build.
- Source-tree Qt Quick smoke test that creates all four pages, every Shortcuts tab, and the calibration overlay.
- `pyside6-deploy --dry-run` inspection from the isolated tree plus an audit of the generated `pysidedeploy.spec`.
- Completed `.app` scan for leaked repository metadata.
- x86_64 executable verification.
- Preserve Qt/Nuitka’s existing signature when valid; otherwise apply and verify a development ad-hoc signature.
- Frozen `.app` smoke test using the real macOS Cocoa platform plugin before packaging.
- Final ZIP content verification.

## Backend corrections found during the deep scan

The Qt Quick port keeps the Python engine separate internally but packages it into the same macOS application. During the v26.08.17.05 audit, several important behaviours were corrected to match the proven v26.06.26.25 control contract:

- Cable Slip uses `SYNC_POS`, not `SET_POSITION`.
- Not Calibrated is a reduced-speed service state rather than an E-stop, allowing Limit Calibration to be performed.
- Service movement is limited to 5 km/h.
- `SERVICE_MODE` is synchronised to W1P for Not Calibrated, calibration and Battery Change operation.
- Battery Change auto-cancel is restored after travelling outside a limit and returning safely inside.
- Limit Calibration establishes Near as 0.00 m, Far as a positive span distance, then Reference; normal calibrated state is restored only after Reference is saved.
- The ADS1115 controller fault bit is treated as a fail-safe source.
- W1P position feedback now rejects implausible jumps outside a short deliberate `SYNC_POS` grace window.
- Preset positions remain operator distances relative to Near and are converted back to absolute W1P positions for Recall.

## Run UI geometry

The bottom Run row remains explicitly fixed to:

- Drive — 20%
- Speed — 25%
- Position — 25%
- Shortcuts — 30%

No automatic content sizing is allowed to change those ratios.

## GitHub output

The workflow is deliberately macOS Intel only for development. It does not use Apple Developer ID signing or notarisation.

At the bottom of the completed Actions run, download the artifact:

`HV-P2P-SRVR-v26.08.17.05-macOS-Intel`

GitHub wraps the artifact for transport. Inside it is:

`HV P2P SRVR v26.08.17.05 macOS Intel.zip`

and that inner ZIP contains only:

`HV P2P SRVR.app`
