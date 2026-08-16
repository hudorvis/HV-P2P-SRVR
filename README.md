# HV P2P SRVR v26.08.17.02 — Qt Quick test build

This revision replaces the visible Tkinter/ttk user interface with **PySide6 + Qt Quick/QML**. There are no Tkinter imports in the application.

The source is organised into a Python control engine (`backend.py`) and QML visual resources, but GitHub compiles them into **one macOS application bundle**.

## GitHub build

The workflow builds **macOS Intel only** on `macos-15-intel`. It does not use Apple Developer ID signing or notarisation during this test phase.

The workflow publishes a GitHub **Prerelease** asset named:

`HV P2P SRVR v26.08.17.02 macOS Intel.zip`

That ZIP contains only:

`HV P2P SRVR.app`

It deliberately does not use `actions/upload-artifact`, avoiding the previous ZIP-inside-a-ZIP download.

## UI status

Locked/final visual references implemented in Qt Quick:
- shared header/status/navigation/footer shell
- Run page
- Preset 1–5
- Preset 6–10
- Limits
- System
- Limit Calibration popup
- Free-D page

Setup and Log remain functional/interim until their visual designs are separately reviewed and locked.
