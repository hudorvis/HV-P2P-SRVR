#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import QObject, Property, QProcess, QProcessEnvironment, QUrl, Signal, Slot


class BackendBridge(QObject):
    snapshotChanged = Signal()
    backendReadyChanged = Signal()
    backendErrorChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._snapshot = {
            "version": "v26.08.15.05",
            "connections": {"ctrl": False, "w1p": False, "freeD": False},
            "safety": {"level": "warning", "text": "STARTING", "sources": []},
            "run": {"speed": 0.0, "maxSpeed": 0.0, "driveMode": "Mode 1", "driveModeIndex": 0,
                    "accelMode": "Speed", "batteryChange": False, "position": 0.0, "span": 100.0,
                    "toNear": 0.0, "toFar": 100.0, "reference": 50.0, "nearRamp": 5.0, "farRamp": 5.0,
                    "presets": [], "zNear": 0.0, "zFar": 0.0, "sideSamples": [[0,0],[100,0]],
                    "camera": {}, "auxLabels": ["AUX1","AUX2","AUX3","AUX4"]},
            "setup": {}, "freeD": {}, "log": [], "statusMessage": "Starting backend…"
        }
        self._ready = False
        self._error = ""
        self._buffer = b""
        self._proc = QProcess(self)
        self._proc.setProcessChannelMode(QProcess.SeparateChannels)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONUNBUFFERED", "1")
        self._proc.setProcessEnvironment(env)
        self._proc.readyReadStandardOutput.connect(self._read_stdout)
        self._proc.readyReadStandardError.connect(self._read_stderr)
        self._proc.errorOccurred.connect(self._process_error)
        self._proc.finished.connect(self._process_finished)
        self._start_backend()

    def _start_backend(self):
        source_dir = Path(__file__).resolve().parent
        compiled = "__compiled__" in globals()
        if compiled:
            program = sys.executable
            args = ["--backend-worker"]
        else:
            program = sys.executable
            args = [str(source_dir / "main.py"), "--backend-worker"]
        self._proc.setWorkingDirectory(str(source_dir))
        self._proc.start(program, args)
        if not self._proc.waitForStarted(5000):
            self._set_error("Could not start the SRVR backend process.")

    def _read_stdout(self):
        self._buffer += bytes(self._proc.readAllStandardOutput())
        while b"\n" in self._buffer:
            line, self._buffer = self._buffer.split(b"\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line.decode("utf-8", errors="replace"))
            except Exception:
                continue
            typ = msg.get("type")
            if typ == "ready":
                if not self._ready:
                    self._ready = True
                    self.backendReadyChanged.emit()
            elif typ == "snapshot":
                data = msg.get("data")
                if isinstance(data, dict):
                    self._snapshot = data
                    self.snapshotChanged.emit()
            elif typ == "fatal":
                self._set_error(str(msg.get("message", "Backend failed")))
            elif typ in ("command_error", "snapshot_error"):
                self._set_error(str(msg.get("message", "Backend error")))

    def _read_stderr(self):
        # Keep stderr available for a future diagnostics file, but do not mirror
        # routine legacy debug output into the visible operator UI.
        _ = bytes(self._proc.readAllStandardError())

    def _process_error(self, _err):
        self._set_error(self._proc.errorString() or "Backend process error")

    def _process_finished(self, code, _status):
        if not self._closing and code != 0:
            self._set_error(f"SRVR backend stopped unexpectedly (exit {code}).")
        if self._ready:
            self._ready = False
            self.backendReadyChanged.emit()

    _closing = False

    def _set_error(self, text: str):
        if text != self._error:
            self._error = text
            self.backendErrorChanged.emit()

    def _send(self, name: str, **args):
        if self._proc.state() != QProcess.Running:
            self._set_error("SRVR backend is not running.")
            return
        payload = json.dumps({"name": name, "args": args}, separators=(",", ":")) + "\n"
        self._proc.write(payload.encode("utf-8"))

    def get_snapshot(self): return self._snapshot
    snapshot = Property("QVariantMap", get_snapshot, notify=snapshotChanged)

    def get_ready(self): return self._ready
    backendReady = Property(bool, get_ready, notify=backendReadyChanged)

    def get_error(self): return self._error
    backendError = Property(str, get_error, notify=backendErrorChanged)

    @Slot()
    def toggleEstop(self): self._send("estop")

    @Slot(int)
    def gotoPreset(self, index): self._send("goto_preset", index=int(index))

    @Slot(str)
    def gotoLimit(self, which): self._send("goto_limit", which=str(which))

    @Slot(int)
    def runAux(self, index): self._send("aux", index=int(index))

    @Slot(int)
    def setDriveMode(self, index): self._send("drive_mode", index=int(index))

    @Slot()
    def toggleAccelMode(self): self._send("accel_toggle")

    @Slot(bool)
    def setBatteryChange(self, enabled): self._send("battery_change", enabled=bool(enabled))

    @Slot()
    def cancelMotion(self): self._send("cancel_motion")

    @Slot(str)
    def setupAction(self, action): self._send("setup_action", action=str(action))

    @Slot("QVariantMap")
    def applySetup(self, data): self._send("apply_setup", **dict(data))

    @Slot("QVariantMap")
    def applyFreeD(self, data): self._send("apply_freed", **dict(data))

    @Slot(str)
    def captureLens(self, endpoint): self._send("capture_lens", endpoint=str(endpoint))

    @Slot()
    def resetLens(self): self._send("reset_lens")

    @Slot()
    def clearLog(self): self._send("clear_log")

    @Slot()
    def saveLog(self): self._send("save_log")

    @Slot()
    def reloadConfig(self): self._send("reload_config")

    @Slot()
    def saveConfig(self): self._send("save_config")


    @Slot(str)
    def saveConfigPath(self, url):
        path = QUrl(str(url)).toLocalFile() or str(url)
        self._send("save_config_path", path=path)

    @Slot(str)
    def loadConfigPath(self, url):
        path = QUrl(str(url)).toLocalFile() or str(url)
        self._send("load_config_path", path=path)

    @Slot(str)
    def setLimitPoint(self, which): self._send("limit_set", which=str(which))

    @Slot(str)
    def slipLimit(self, which): self._send("limit_slip", which=str(which))

    @Slot(str, str, float)
    def setRamp(self, which, mode, value): self._send("ramp_set", which=str(which), mode=str(mode), value=float(value))

    @Slot(int)
    def setPresetHere(self, index): self._send("preset_set", index=int(index))

    @Slot(int, str, str, bool)
    def updatePreset(self, index, name, position, visible):
        self._send("preset_update", index=int(index), presetName=str(name), position=str(position), visible=bool(visible))

    @Slot()
    def shutdown(self):
        self._closing = True
        try:
            self._send("shutdown")
            self._proc.closeWriteChannel()
            if not self._proc.waitForFinished(1800):
                self._proc.terminate()
                if not self._proc.waitForFinished(800):
                    self._proc.kill()
        except Exception:
            pass
