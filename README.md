# HV P2P SRVR v26.08.15.06

First **GitHub Actions release-build revision** of the Qt Quick / QML HV P2P SRVR.

## Functional and visual baseline

- Stable backend remains the preserved `HV P2P SRVR v26.06.26.25` implementation in `source/hv_p2p_legacy_core.py`.
- Visible application is PySide6 / Qt Quick / QML rather than Tkinter.
- Approved Run design is retained in `Approved Run Design Reference.png`.
- Bottom Run cards remain **Drive / Speed / Position / Quick Actions**.
- Top status connections remain **CTRL / W1P / Free-D**.
- Top View uses a straight rigging-line geometry with Z offset.
- Side View uses the existing sag calculation.
- Both views retain limits, ramp zones, Ref, presets, skate and camera FOV.
- Coordinate wording remains **X (Tracking) / Y (Sag) / Z (Offset)**.

## What is new in v26.08.15.06

This revision is prepared so GitHub Actions is the normal build machine.

A commit to `main` automatically starts one workflow which creates:

1. **macOS Apple Silicon — Developer ID signed + Apple notarised + stapled**
2. **macOS Intel — Developer ID signed + Apple notarised + stapled**
3. **Windows x64 — self-contained executable**

The macOS workflow uses a temporary Keychain on the GitHub runner, imports the Developer ID certificate from encrypted GitHub Secrets, signs the complete Qt/Nuitka app with Hardened Runtime, authenticates to Apple's notary service with the App Store Connect API key, staples the accepted ticket, runs Gatekeeper verification, and then uploads the finished ZIP as a GitHub Actions artifact.

## Required GitHub Actions Secrets

The workflow expects the exact secret names below:

- `MACOS_CERTIFICATE_P12` — Base64-encoded Developer ID `.p12`
- `MACOS_CERTIFICATE_PASSWORD` — password used when exporting the `.p12`
- `MACOS_SIGNING_IDENTITY` — exact full `Developer ID Application: ...` identity
- `APPLE_NOTARY_KEY` — Base64-encoded App Store Connect `.p8` key
- `APPLE_NOTARY_KEY_ID` — App Store Connect API Key ID
- `APPLE_NOTARY_ISSUER_ID` — App Store Connect API Issuer ID

Never put `.p12`, `.p8`, passwords or Base64 private-key material in the repository. `.gitignore` explicitly excludes common signing file extensions as an additional safeguard.

## First GitHub build

1. Extract this ZIP.
2. Open your `HV-P2P-SRVR` GitHub repository.
3. Upload/commit the **contents** of this folder to the root of the repository. The root should contain `source/`, `build/`, `.github/`, `.gitignore`, `README.md`, and the design reference image.
4. Commit to the `main` branch.
5. Open the repository's **Actions** tab.
6. Select **Build Signed HV P2P SRVR v26.08.15.06**.
7. The push to `main` should start it automatically. You can also use **Run workflow** manually.
8. Wait for the desired job to turn green.
9. Open the completed workflow run and download the artifact from the **Artifacts** section.

Expected macOS artifacts:

- `HV-P2P-SRVR-v26.08.15.06-macOS-Apple-Silicon-Signed`
- `HV-P2P-SRVR-v26.08.15.06-macOS-Intel-Signed`

Expected Windows artifact:

- `HV-P2P-SRVR-v26.08.15.06-Windows-x64`

The macOS artifact contains a self-contained `.app`; the Mac does not need Python installed to run the built application.

## Build implementation

Qt for Python's `pyside6-deploy` is used to create the platform-native application through Nuitka. The legacy worker still imports Tk internally during this migration, so Nuitka's Tk plugin remains enabled even though the visible UI is entirely Qt/QML.

The earlier `pyside6-project qmllint`/`metaobjectdump` pre-build pass remains intentionally disabled because this project exposes the bridge to QML through `QQmlContext.setContextProperty()` rather than Python QML type registration.

## Local build scripts

Local builds remain available for diagnostics:

```bash
./build/build_macos.sh
```

and on Windows:

```powershell
./build/build_windows.ps1
```

For normal testing from this revision onward, prefer the GitHub Actions artifacts so the build environment is repeatable and macOS packages are signed/notarised before download.
