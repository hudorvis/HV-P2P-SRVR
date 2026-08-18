# HV P2P SRVR v26.08.17.14 — Qt Quick macOS Intel test build

This is a narrow maintenance revision from the approved **v26.08.17.13** Qt Quick build. The locked Run, Setup, Free-D and Log page design, shared shell, heading palette and existing control architecture remain unchanged except for the four requested fixes below.

## v26.08.17.14 changes

- Adds the missing AUX assignment choices **Preset 1 Save** through **Preset 10 Save** to the same shared list used by both CTRL-TS AUX Assign and W1P-TS AUX Assign.
- Makes Setup **Save Config** and **Load Config** functional with native Qt file dialogs:
  - Save Config exports the currently **applied** complete configuration to a transferable `.hvp2p.json` / `.json` file.
  - Load Config reads a transfer file into the Setup and Free-D **drafts** without silently changing live operation.
  - Imported Setup/Run configuration is committed only by **Setup → Apply**; imported Free-D configuration is committed only by **Free-D → Apply**.
- Enforces true Apply/Reset editing on Setup and Free-D:
  - Setup fields edit `setupDraft` only. Run/motion/network values do not change merely because text was edited or the page was changed.
  - Free-D fields edit `freeDDraft` only. Live Free-D network output continues to use the last-applied settings until Apply.
  - Page navigation preserves unapplied draft edits.
  - **Apply** atomically commits that page's draft and saves it.
  - **Reset** discards the page's unapplied draft and restores the latest applied/saved values.
  - The Joystick Left/Centre/Right wizard now stages its accepted calibration in Setup as well; it is not committed until Setup Apply.
  - Save Config deliberately exports applied values only, never un-applied drafts.
- Corrects the Setup Motion Profiles vertical containment so the divider above **DRIVE BEHAVIOUR** no longer overlaps the **Stop Deceleration** row.

Everything else remains locked to the approved v26.08.17.13 design and functionality, including the common blue `#26d5ff` heading treatment, Run page geometry, Free-D layout, Log page, shared shell/footer, CTRL/W1P safety and motion behaviour, calibration flows, Free-D calculations and logging.

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

`HV-P2P-SRVR-v26.08.17.14-macOS-Intel`

The artifact contains:

`HV P2P SRVR v26.08.17.14 macOS Intel.zip`

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
