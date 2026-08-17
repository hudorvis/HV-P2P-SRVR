#!/usr/bin/env python3
"""Static preflight for the HV P2P SRVR Qt Quick source tree.

This deliberately avoids importing PySide6 so it can run before dependencies are
installed and can also be run locally on any Python 3.12 machine.
"""
from __future__ import annotations

import ast
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "26.08.17.05"
ERRORS: list[str] = []


def require(condition: bool, message: str) -> None:
    if not condition:
        ERRORS.append(message)


def read(rel: str) -> str:
    p = ROOT / rel
    require(p.is_file(), f"missing required file: {rel}")
    return p.read_text(encoding="utf-8") if p.is_file() else ""


main = read("main.py")
backend = read("backend.py")
qml_main = read("qml/Main.qml")
workflow = read(".github/workflows/build-macos-intel.yml")
project_text = read("HV_P2P_SRVR.pyproject")
qrc_text = read("resources.qrc")
requirements = read("requirements.txt")

# Python syntax.
for rel in ("main.py", "backend.py"):
    try:
        ast.parse(read(rel), filename=rel)
    except SyntaxError as exc:
        ERRORS.append(f"{rel} syntax error: {exc}")

# Architecture guard: the new visible app must never regress to Tkinter/ttk.
for rel, text in (("main.py", main), ("backend.py", backend)):
    require(not re.search(r"(?m)^\s*(?:import\s+tkinter\b|from\s+tkinter\b|import\s+ttk\b|from\s+ttk\b)", text, re.I),
            f"{rel} imports Tkinter/ttk")

# Version consistency.
require(f'APP_VERSION = "{VERSION}"' in main, "main.py version mismatch")
require(f"APP_VERSION: '{VERSION}'" in workflow, "workflow version mismatch")
require(f"v{VERSION}" in workflow, "artifact version mismatch")

# Pin the Qt/PySide toolchain so a later PyPI release cannot silently change deployment behaviour.
require(requirements.strip() == "PySide6==6.11.1", "PySide6 must be pinned to 6.11.1 for reproducible CI")

# The Qt resource compiler output and import name must match exactly.
require("import rc_resources" in main, "main.py must import rc_resources")
require("pyside6-rcc resources.qrc -o rc_resources.py" in workflow,
        "workflow must generate rc_resources.py")
require("resources_rc.py" not in main + workflow, "stale resources_rc.py name found")

# Validate .pyproject. It must never list repository/build metadata.
try:
    project = json.loads(project_text)
    files = project.get("files", [])
    require(isinstance(files, list) and files, "HV_P2P_SRVR.pyproject has no files")
    forbidden_prefixes = (".git", ".github", "assets", "build", "release", "tools")
    for f in files:
        require((ROOT / f).is_file(), f"project manifest missing file: {f}")
        require(not str(f).startswith(forbidden_prefixes), f"forbidden manifest entry: {f}")
except Exception as exc:
    ERRORS.append(f"invalid HV_P2P_SRVR.pyproject: {exc}")

# Validate qrc XML and every resource target.
try:
    qroot = ET.fromstring(qrc_text)
    qfiles = [n.text.strip() for n in qroot.findall(".//file") if n.text]
    require("qml/Main.qml" in qfiles, "resources.qrc does not contain qml/Main.qml")
    for f in qfiles:
        require((ROOT / f).is_file(), f"resources.qrc missing file: {f}")
except Exception as exc:
    ERRORS.append(f"invalid resources.qrc: {exc}")

# Basic QML structural check, ignoring comments/quoted strings. qmllint in CI is
# authoritative; this catches accidental unmatched braces before that step.
def strip_qml_strings_comments(s: str) -> str:
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.S)
    s = re.sub(r"//[^\n]*", "", s)
    s = re.sub(r'"(?:\\.|[^"\\])*"', '""', s)
    s = re.sub(r"'(?:\\.|[^'\\])*'", "''", s)
    return s

for p in sorted((ROOT / "qml").rglob("*.qml")):
    text = strip_qml_strings_comments(p.read_text(encoding="utf-8"))
    require(text.count("{") == text.count("}"), f"unbalanced braces in {p.relative_to(ROOT)}")

# Every backend.<name> reference in QML must be present on HVP2PBackend.
try:
    tree = ast.parse(backend)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "HVP2PBackend")
    exposed = {n.name for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    refs: set[str] = set()
    for p in (ROOT / "qml").rglob("*.qml"):
        refs.update(re.findall(r"\bbackend\.([A-Za-z_][A-Za-z0-9_]*)", p.read_text(encoding="utf-8")))
    missing = sorted(refs - exposed)
    require(not missing, "QML references missing backend members: " + ", ".join(missing))
except Exception as exc:
    ERRORS.append(f"backend/QML interface scan failed: {exc}")

# Locked Run geometry and Shortcuts tabs.
for ratio in ("0.20", "0.25", "0.30"):
    require(ratio in qml_main, f"Run fixed geometry ratio missing: {ratio}")
require(qml_main.count("parent.parent.avail*0.25") >= 2, "Speed/Position 25% widths not both fixed")
require("parent.parent.avail*0.20" in qml_main, "Drive 20% width not fixed")
require("parent.parent.avail*0.30" in qml_main, "Shortcuts 30% width not fixed")
require('["Preset 1-5","Preset 6-10","Limits","System"]' in qml_main,
        "Shortcuts tab order changed")
require("height:parent.height*0.58" in qml_main,
        "Free-D upper/lower split regression detected")

# Critical proven W1P/CTRL contract. SET_POSITION is specifically wrong for
# cable-slip re-referencing on this system; the working backend uses SYNC_POS.
for token in (
    "SYNC_POS", "SERVICE_MODE", "SET_UNITS_PER_M", "SET_MOTOR_REVERSE",
    "SET_ACCEL", "SET_DECEL", "SET_CROSSOVER", "SET_STOP_DECEL",
    "SET_ACCEL_MODE", "SET_SPAN", "SET_LIMIT_NEAR", "SET_LIMIT_FAR", "VEL ",
    "HEARTBEAT_CODE = 0xA5", "CONTROL_PACKET_CODE = 0xA6",
    "FLAG_ESTOP_PRESSED = 0x10", "FLAG_ADS1115_FAULT = 0x0200",
):
    require(token in backend, f"critical protocol token missing: {token}")
require("SET_POSITION" not in backend, "invalid SET_POSITION command has returned")
require("5.0 / 3.6" in backend, "5 km/h calibration/service speed limit missing")
require("_not_calibrated\n            or self.battery_change_mode" in backend,
        "service-mode Not Calibrated path missing")

# Exact v04 failure must be structurally impossible in v05: deploy from a clean
# RUNNER_TEMP staging directory containing an explicit allow-list.
require("$RUNNER_TEMP/hvp2p-stage" in workflow, "workflow is not deploying from isolated staging")
require("cp main.py backend.py resources.qrc HV_P2P_SRVR.pyproject" in workflow,
        "workflow staging allow-list missing core files")
require("cp -R qml \"$STAGE/\"" in workflow, "workflow staging allow-list missing qml directory")
require("cd \"$STAGE\"" in workflow, "deployment does not cd into isolated staging")
require("--smoke-test" in workflow, "CI frozen/source smoke tests missing")
require("pyside6-qmllint --max-warnings -1" in workflow, "QML syntax lint step missing or warning threshold not stabilized")
require("pyside6-deploy main.py --init" in workflow, "explicit deployment spec initialization missing")
require("test -s pysidedeploy.spec" in workflow, "generated deployment spec audit missing")
require("QT_QPA_PLATFORM=cocoa" in workflow, "frozen app is not smoke-tested with the real Cocoa platform plugin")

if ERRORS:
    print("HV P2P SRVR preflight FAILED:", file=sys.stderr)
    for e in ERRORS:
        print(f"  - {e}", file=sys.stderr)
    raise SystemExit(1)

print("HV P2P SRVR preflight PASS")
print("  Python syntax: OK")
print("  Qt Quick only / no Tkinter: OK")
print("  QML/backend interface: OK")
print("  QRC/project manifest: OK")
print("  Run 20/25/25/30 geometry: OK")
print("  Proven W1P/CTRL critical command contract: OK")
print("  Isolated deployment staging + smoke checks: OK")
