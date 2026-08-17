#!/usr/bin/env python3
from __future__ import annotations

import os
import sys

# Force Qt Quick Controls to use a deterministic non-native visual style.
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

# The smoke test is used by GitHub Actions to prove that both the source tree
# and the frozen .app can create the QML engine, instantiate every locked page,
# and exercise the calibration overlay without requiring an interactive desktop.
SMOKE_TEST = "--smoke-test" in sys.argv
if SMOKE_TEST:
    try:
        sys.argv.remove("--smoke-test")
    except ValueError:
        pass
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

# Import these explicitly. Besides documenting what the QML frontend needs,
# it gives deployment tools an unambiguous dependency path for the Qt Quick /
# Qt Quick Controls runtime modules.
import PySide6.QtQuick  # noqa: F401
import PySide6.QtQuickControls2  # noqa: F401

from backend import HVP2PBackend

APP_VERSION = "26.08.17.08"


def _exercise_qml(app: QGuiApplication, engine: QQmlApplicationEngine, backend: HVP2PBackend) -> bool:
    """Non-interactive source/frozen smoke test used by CI."""
    roots = engine.rootObjects()
    if not roots:
        print("SMOKE FAIL: no QML root object", file=sys.stderr)
        return False

    root = roots[0]
    try:
        # Exercise all primary pages.
        for page in range(4):
            root.setProperty("page", page)
            app.processEvents()

        # Exercise all four Shortcuts sub-tabs on the Run page.
        root.setProperty("page", 0)
        for tab in range(4):
            root.setProperty("shortcutTab", tab)
            app.processEvents()

        # Exercise the locked Limit Calibration popup, including step changes.
        backend.openLimitCalibration()
        app.processEvents()
        backend.calibrationNext()
        app.processEvents()
        backend.calibrationBack()
        app.processEvents()
        backend.cancelCalibration()
        app.processEvents()

        # Exercise the editable Run/System controls that previously appeared
        # visually correct but behaved read-only in the first Qt test builds.
        backend.state.near_limit.position_m = 0.0
        backend.state.far_limit.position_m = 100.0
        backend.setPresetName(0, "Smoke Preset")
        backend.setPresetPosition(0, 12.34)
        if backend.presets[0]["name"] != "Smoke Preset" or abs(float(backend.presets[0]["position"]) - 12.34) > 1e-6:
            raise RuntimeError("editable preset fields failed")
        backend.renameDriveMode(0, "Smoke Mode")
        if backend.driveMode1Name != "Smoke Mode":
            raise RuntimeError("editable drive-mode name failed")
        backend.setRamping("Near", "Distance", 20.0)
        backend.changeRampingMode("Near", "Percentage")
        if backend.nearRampMode != "Percentage" or abs(float(backend.nearRampValue) - 20.0) > 1e-6:
            raise RuntimeError("ramp Distance->Percentage conversion failed")
        backend.changeRampingMode("Near", "Distance")
        if abs(float(backend.nearRampValue) - 20.0) > 1e-6:
            raise RuntimeError("ramp Percentage->Distance conversion failed")

        # Exercise staged Free-D editing plus Apply/Reset.
        backend.setFreeDNetwork("Output", "IP", "172.20.1.30")
        backend.setFreeDNetwork("Output", "Port", "5002")
        backend.setFreeDNetwork("Output", "FPS", "50")
        backend.setFreeDOffset("Input", "Pan", 1.25)
        backend.setFreeDInvert("Output", "Y", True)
        backend.setGeometryPoint(1, "x", 25.0)
        backend.setGeometryPoint(1, "y", 5.0)
        backend.setWeightUnit("Static", "lbs")
        backend.setLensType("u16")
        backend.setLensScale("Auto")
        backend.applyFreeDSettings()
        backend.setFreeDNetwork("Output", "IP", "10.0.0.99")
        backend.resetFreeDSettings()
        if backend.freeDOutputIp != "172.20.1.30":
            raise RuntimeError("Free-D Apply/Reset failed")

        # The shared status banner must retain the legacy SRVR software E-stop
        # action without affecting other independent safety sources.
        before = bool(backend._srvr_estop)
        backend.toggleSrvrEStop()
        backend.toggleSrvrEStop()
        if bool(backend._srvr_estop) != before:
            raise RuntimeError("SRVR E-stop toggle failed")
        app.processEvents()
    except Exception as exc:
        print(f"SMOKE FAIL: {exc}", file=sys.stderr)
        return False

    print("SMOKE PASS: QML pages, editable controls, Free-D Apply/Reset, shortcuts and calibration overlay instantiated")
    return True


def main() -> int:
    app = QGuiApplication(sys.argv)
    app.setApplicationName("HV P2P SRVR")
    app.setOrganizationName("H-V")
    app.setOrganizationDomain("h-v.au")

    # resources.qrc is compiled by pyside6-rcc to rc_resources.py in CI.
    # Qt's project tooling expects this rc_<qrc-name>.py naming convention.
    import rc_resources  # noqa: F401

    backend = HVP2PBackend(version=APP_VERSION, smoke_test=SMOKE_TEST)
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("backend", backend)
    engine.rootContext().setContextProperty("appVersion", APP_VERSION)
    engine.load(QUrl("qrc:/qml/Main.qml"))

    if not engine.rootObjects():
        backend.shutdown()
        return 2

    app.aboutToQuit.connect(backend.shutdown)

    if SMOKE_TEST:
        ok = _exercise_qml(app, engine, backend)
        backend.shutdown()
        # A short event-loop turn catches deferred QML/component errors while
        # still guaranteeing that the CI step terminates.
        QTimer.singleShot(80, app.quit)
        app.exec()
        return 0 if ok else 3

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
