#!/usr/bin/env python3
from __future__ import annotations

# The hidden legacy worker still uses Tk internally to preserve the proven
# v26.06.26.25 control implementation.  Tell Nuitka to bundle Tcl/Tk when the
# Qt application is compiled into a self-contained desktop binary.
# nuitka-project: --enable-plugin=tk-inter
# nuitka-project-if: {OS} == "Windows":
#    nuitka-project: --windows-console-mode=disable

import os
import sys
from pathlib import Path

APP_VERSION = "v26.08.15.06"


def _run_backend_mode() -> int:
    from backend_worker import run_backend_worker
    return run_backend_worker()


def _run_frontend() -> int:
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from bridge import BackendBridge

    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    app = QGuiApplication(sys.argv)
    app.setApplicationName("HV P2P SRVR")
    app.setApplicationDisplayName("HV P2P SRVR")
    app.setOrganizationName("H-V")
    app.setOrganizationDomain("h-v.au")
    app.setApplicationVersion(APP_VERSION)

    bridge = BackendBridge()
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("backend", bridge)
    qml_file = Path(__file__).resolve().parent / "qml" / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml_file)))
    if not engine.rootObjects():
        bridge.shutdown()
        return 2

    app.aboutToQuit.connect(bridge.shutdown)
    return app.exec()


def main() -> int:
    if "--backend-worker" in sys.argv:
        return _run_backend_mode()
    return _run_frontend()


if __name__ == "__main__":
    raise SystemExit(main())
