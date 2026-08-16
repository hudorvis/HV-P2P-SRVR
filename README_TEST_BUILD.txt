HV P2P SRVR v26.08.17.01 - macOS Intel TEST BUILD

This is an unsigned / non-notarised development build intended for the current
visual and functional test cycle.

Locked/tested in this revision:
- Shared grey/charcoal shell, header/status cards, system banner, navigation and footer.
- Run page using the approved 20% / 25% / 25% / 30% fixed bottom split:
    Drive 20% | Speed 25% | Position 25% | Shortcuts 30%
- 10 programmable presets with editable names and positions, Save, Recall and Show/Hide.
- Limits tab with Near/Far Save, Recall, Slip and Ramping; Reference Save, Recall, Slip.
- System tab with Acceleration Mode, Battery Change Mode, Drive Mode names/modes and calibration entry.
- Locked Limit Calibration popup: Set Near -> Set Far -> Set Ref -> Done, without extra Confirm steps.
- Locked Free-D page layout and controls, including 3-decimal FPS display.
- Existing v26.06.26.25 CTRL/W1P/RS485/Free-D networking and safety backend retained as the functional baseline.

Not yet visually locked:
- Setup page final design.
- Log page final design.
These pages remain functional/interim and use the same overall grey theme for this test build.

macOS Gatekeeper (development build):
If macOS blocks the unsigned app, right-click the app and choose Open, or allow it
from System Settings > Privacy & Security. No Apple Developer ID signing or
notarisation is used in this development workflow.
