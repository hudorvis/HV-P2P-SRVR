# HV P2P SRVR v26.08.15.07

Fast-development GitHub Actions revision of the Qt Quick / QML HV P2P SRVR.

## Functional and visual baseline

- Stable backend remains the preserved `HV P2P SRVR v26.06.26.25` implementation in `source/hv_p2p_legacy_core.py`.
- Visible application remains PySide6 / Qt Quick / QML rather than Tkinter.
- Approved Run design remains in `Approved Run Design Reference.png`.
- Bottom Run cards remain **Drive / Speed / Position / Quick Actions**.
- Top status connections remain **CTRL / W1P / Free-D**.
- Top View uses straight rigging-line geometry with Z offset.
- Side View uses the existing sag calculation.
- Both views retain limits, ramp zones, Ref, presets, skate and camera FOV.
- Coordinate wording remains **X (Tracking) / Y (Sag) / Z (Offset)**.

## What is new in v26.08.15.07

This revision intentionally changes the GitHub build pipeline for faster development testing.

A push to `main` now builds only:

**macOS Intel — self-contained unsigned test application**

The development workflow does **not**:

- import the Developer ID certificate;
- contact Apple's notarisation service;
- wait for notarisation;
- staple a notarisation ticket;
- build Apple Silicon;
- build Windows x64.

Those release steps will be restored after the SRVR UI and behaviour are approved.

No Apple signing/notarisation GitHub Secrets are required by this test workflow.

## Normal test cycle

Use the same cloned repository in GitHub Desktop.

1. Extract this ZIP.
2. Copy the contents into the existing local `HV-P2P-SRVR` repository, replacing the previous revision files.
3. Do **not** delete the repository's hidden `.git` folder.
4. Open GitHub Desktop.
5. Commit the changes to `main`.
6. Push origin.
7. GitHub Actions starts **Build HV P2P SRVR — macOS Intel Test** automatically.
8. When it finishes, download the `HV-P2P-SRVR-v26.08.15.07-macOS-Intel-Test` artifact.
9. Unzip it and open `HV P2P SRVR v26.08.15.07.app`.

Because this is intentionally an unsigned/unnotarised development build, macOS Gatekeeper may require manual approval through **System Settings → Privacy & Security → Open Anyway**.

## Artifact retention

Development artifacts are retained for **3 days** to avoid old Qt test builds accumulating in GitHub Actions storage. Keep any test build you want to retain locally.

## Local diagnostics

A local build remains available if required:

```bash
./build/build_macos.sh
```

For normal iterative testing, use the GitHub Actions artifact so the build environment stays repeatable.
