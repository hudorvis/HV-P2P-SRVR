# HV P2P SRVR v26.08.17.04 — Qt Quick macOS Intel test build

Development test package for the PySide6 + Qt Quick/QML frontend.

This revision fixes the v26.08.17.03 macOS build failure where pyside6-deploy had no Qt/PySide project manifest and copied repository metadata (`.github`) into the generated `.app` bundle. The project now has an explicit `HV_P2P_SRVR.pyproject` file and the workflow separately ignores repository/build directories.

The visible application remains Qt Quick/QML; Tkinter/ttk is not used.

## GitHub build

Upload the contents of this folder to the repository root and run:

**Actions → HV P2P SRVR - Qt Quick macOS Intel Test Build**

The workflow builds macOS Intel only. Development builds are not Developer ID signed or notarised.

The Actions artifact is named:

`HV-P2P-SRVR-v26.08.17.04-macOS-Intel`

GitHub downloads that artifact as a ZIP. Inside it is one permission-safe application ZIP:

`HV P2P SRVR v26.08.17.04 macOS Intel.zip`

That inner ZIP contains only:

`HV P2P SRVR.app`
