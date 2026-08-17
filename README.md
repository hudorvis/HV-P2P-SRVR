# HV P2P SRVR v26.08.17.03 — Qt Quick macOS Intel test build

Qt Quick / PySide6 development build of HV P2P SRVR.

## GitHub build

Run **HV P2P SRVR - Qt Quick macOS Intel Test Build** under GitHub Actions.
The development workflow builds macOS Intel only and does not use Apple Developer ID signing or notarisation.

The final app is ad-hoc signed after all bundle modifications so its internal code signature is self-consistent for development testing.

## Download format

GitHub Actions always wraps an uploaded artifact in its own ZIP. To preserve the executable permissions and macOS bundle metadata of the `.app`, this workflow deliberately transports the app inside a permission-safe ZIP.

Download the GitHub artifact:

`HV-P2P-SRVR-v26.08.17.03-macOS-Intel.zip`

Inside it is exactly one file:

`HV P2P SRVR v26.08.17.03 macOS Intel.zip`

Inside that is exactly one application:

`HV P2P SRVR.app`

No `.py` or `.txt` files are included in the application ZIP.
