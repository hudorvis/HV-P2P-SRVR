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
VERSION = "26.08.17.12"
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
qml_setup = read("qml/pages/SetupPage.qml")
qml_log = read("qml/pages/LogPage.qml")
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
    require("qml/pages/SetupPage.qml" in qfiles, "resources.qrc does not contain final SetupPage.qml")
    require("qml/pages/LogPage.qml" in qfiles, "resources.qrc does not contain final LogPage.qml")
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
    raw = p.read_text(encoding="utf-8")
    text = strip_qml_strings_comments(raw)

    # Balanced QML/JavaScript delimiters. This is intentionally a small static
    # guard rather than a replacement for Qt's authoritative qmllint in CI.
    stack: list[tuple[str, int]] = []
    pairs = {"}": "{", ")": "(", "]": "["}
    for pos, ch in enumerate(text):
        if ch in "{([":
            stack.append((ch, pos))
        elif ch in "})]":
            if not stack or stack[-1][0] != pairs[ch]:
                require(False, f"mismatched delimiter {ch!r} in {p.relative_to(ROOT)} at character {pos}")
                break
            stack.pop()
    require(not stack, f"unclosed delimiter(s) in {p.relative_to(ROOT)}: {stack[-3:] if stack else []}")

    # QML object attributes are not JavaScript statements. A semicolon after a
    # signal-handler block (for example `onTextEdited: {...}; onCommit: ...`) is
    # rejected by qmllint as an Unexpected token. v26.08.17.09 failed CI for
    # exactly this pattern, so make it impossible to reintroduce silently.
    require(re.search(r"}\s*;\s*on[A-Z][A-Za-z0-9_]*\s*:", text) is None,
            f"illegal semicolon between QML signal handlers in {p.relative_to(ROOT)}")

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
require("height:parent.height*0.66" in qml_main,
        "Free-D upper/lower split regression detected")

# Requested v08 interaction/design contract.
require("Wide FOV" not in qml_main and "Narrow FOV" not in qml_main and "Tele FOV" not in qml_main,
        "lens FOV fields/labels must be removed from the Qt Quick UI")
require('height:f(27)' in qml_main and qml_main.find('text:"▱  SHORTCUTS"') < qml_main.find('model:["Preset 1-5","Preset 6-10","Limits","System"]'),
        "Shortcuts heading/tab two-row layout missing")
require('backend.toggleSrvrEStop()' in qml_main and 'def toggleSrvrEStop' in backend,
        "SRVR status banner E-stop action is not wired")
require('(backend.nearRampMode==="Percentage"?" %":" m")' in qml_main and
        '(backend.farRampMode==="Percentage"?" %":" m")' in qml_main,
        "ramp value field unit feedback missing")
require("changeRampingMode" in backend and "backend.changeRampingMode" in qml_main,
        "Distance/Percentage ramp conversion is not wired end-to-end")
require("bindModel:true" in qml_main and "signal commit(string value)" in read("qml/components/HVField.qml"),
        "focus-safe editable field binding is missing")
for token in (
    'backend.setPresetName', 'backend.setPresetPosition', 'backend.renameDriveMode',
    'backend.setFreeDNetwork', 'backend.setFreeDOffset', 'backend.setFreeDInvert',
    'backend.setGeometryPoint', 'backend.setWeightValue', 'backend.setWeightUnit',
    'backend.setLensCalibration', 'backend.captureLens',
    'backend.applyFreeDSettings', 'backend.resetFreeDSettings',
):
    require(token in qml_main, f"editable UI action not wired: {token}")
for token in ("Parameter", "Raw", "Decoded", "Offset", "Invert", "Input Rate", "Output Rate"):
    require(token in qml_main, f"Free-D Input/Output table content missing: {token}")
require('model:["Cam ID","Pan","Tilt","Roll","Zoom","Focus","FPS"]' in qml_main,
        "Free-D Input seven-row table is incomplete")
require('model:["X","Y","Z","FPS"]' in qml_main,
        "Free-D Output four-row table is incomplete")
require("HVReadout.qml" in qrc_text and "HVCheck.qml" in qrc_text and "SpanDiagram.qml" in qrc_text,
        "required deterministic Qt Quick components are missing from resources.qrc")
require("FreeDGeometryDiagram" not in qml_main and "FreeDGeometryDiagram.qml" not in qrc_text,
        "Run and Free-D must use the same SpanDiagram component")
require("@Property('QVariantList', notify=configChanged)" in backend,
        "editable list models still use the fast telemetry signal")
require("self._saved_freed_snapshot" in backend and "resetFreeDSettings" in backend,
        "Free-D Apply/Reset staging support missing")
require("_kg_to_lb" in backend and "_lb_to_kg" in backend,
        "kg/lbs automatic conversion support missing")
require("skate_per_line" in backend and "point_drop" in backend and "highline_mode" in backend,
        "Skate Weight / Dual Highline sag model is not active in Free-D calculation")
require('getattr(self, "_saved_freed_snapshot"' in backend and 'def _send_freed' in backend,
        "live Free-D output is not using the last-applied settings snapshot")

# Requested v09 fixes: preset tab commit isolation, one shared calculated cable
# profile, simplified safety source naming, and fully visible cable-weight unit.
span_qml = read("qml/components/SpanDiagram.qml")
require('property int pi:index+(window.shortcutTab' not in qml_main,
        "preset delegate index still changes when switching Shortcuts tabs")
require('property int pi:index' in qml_main and 'property int pi:index+5' in qml_main,
        "Preset 1-5 and Preset 6-10 do not have fixed delegate indices")
require(qml_main.count('cableProfile:backend.cableProfile') >= 4,
        "Run and Free-D are not all using the same calculated cable profile")
require(qml_main.count('showGeometryPoints:true') >= 2 and qml_main.count('showPresets:true') >= 2,
        "Run/Free-D marker overlays are not separated correctly")
require('property var cableProfile' in span_qml and 'Canonical calculated cable line' in span_qml,
        "shared SpanDiagram calculated profile rendering is missing")
require('c.moveTo(sx,sy+8)' not in span_qml and 'fov' not in span_qml.lower(),
        "Run diagram still contains camera/FOV guide drawing")
require('def _cable_profile' in backend and 'def _cable_y_at' in backend and 'def _smooth_geometry_y' in backend,
        "canonical smooth cable sag model is missing from backend")
require('def cableProfile' in backend, "QML cableProfile property missing")
require('or (self.winch_rs_status != "Connected")' in backend and 'parts.append("W1P")' in backend,
        "RS485/W1P failures are not rolled up to W1P in the operator banner")
require('parts.append("RS485")' not in backend and 'parts.append("ADS1115")' not in backend,
        "low-level RS485/ADS1115 names leaked back into top E-stop banner")
require(re.search(r'model\s*:\s*\[\s*"kg/100m"\s*,\s*"lbs/100m"\s*\]', qml_main) is not None and
        re.search(r'width\s*:\s*f\(108\)', qml_main) is not None,
        "Cable Weight kg/100m unit control is missing or too narrow")
require(re.search(r'onTextEdited\s*:\s*\{[\s\S]{0,300}?setWeightValue\(\s*"Tension"\s*,\s*n\s*\)', qml_main) is not None,
        "Cable Tension does not live-preview the calculated sag while editing")
require('editCommitSink.forceActiveFocus()' in qml_main and 'function changeShortcutTab' in qml_main,
        "page/tab changes do not explicitly commit the active editor first")

# v10 QML-lint regression guard. v09 reached Qt's authoritative qmllint but
# failed on six `}; onCommit:` separators. Keep the corrected handler syntax
# and the two reusable components that produced the remaining lint warnings.
hvcombo_qml = read("qml/components/HVCombo.qml")
require('pragma ComponentBehavior: Bound' in hvcombo_qml,
        "HVCombo must use bound component behavior for its popup delegate")
require('required property int index' in hvcombo_qml and 'required property var modelData' in hvcombo_qml,
        "HVCombo delegate roles are not explicitly declared")
require('delegateItem.highlighted' in hvcombo_qml and 'delegateItem.modelData' in hvcombo_qml,
        "HVCombo delegate still contains unqualified role/property access")
require('target: backend' not in span_qml and 'backend.' not in span_qml,
        "SpanDiagram reusable component must repaint from bound properties, not an unqualified backend context reference")
require('onCableProfileChanged: canvas.requestPaint()' in span_qml and
        'onCurrentPositionChanged: canvas.requestPaint()' in span_qml,
        "SpanDiagram property-driven repaint hooks are missing")

# Final locked Setup / Log integration contract. Run and Free-D remain in Main.qml
# and are guarded separately above; Setup/Log are isolated components so their
# integration cannot accidentally rewrite those locked bodies.
require('import "pages"' in qml_main and 'SetupPage {' in qml_main and 'LogPage {' in qml_main,
        "final Setup/Log page components are not integrated into the shared shell")
require("functional interim visual" not in qml_main and "final Setup visual design has not yet been locked" not in qml_main,
        "interim Setup implementation remains in Main.qml")
for token in (
    "CTRL-TS Link", "ADS1115 Link", "JOYSTICK CALIBRATION", "W1P-TS Link", "RS485 Link",
    "MOTION PROFILES", "DRIVE BEHAVIOUR", "CTRL-TS AUX ASSIGN", "W1P-TS AUX ASSIGN",
    "LIMIT CALIBRATION", "WINCH CALIBRATION", "SAVE CONFIG", "LOAD CONFIG",
):
    require(token in qml_setup, f"final Setup content missing: {token}")
for token in ("LOG VIEW", "SEVERITY", "SEARCH", "ACTIONS", "LIVE LOG", "SYSTEM SUMMARY", "Backend State", "System Uptime"):
    require(token in qml_log, f"final Log content missing: {token}")
require('width:(parent.width-root.f(10))*0.245' in qml_log and 'width:(parent.width-root.f(30))*0.245' in qml_log,
        "Log System Summary is not aligned to the Actions panel width ratio")
require('visible:window.page===1 || window.page===2' in qml_main,
        "footer Apply/Reset must be visible on Setup and Free-D only")
require('SRVR Time:' in qml_main and 'Uptime:' in qml_main,
        "shared footer time/uptime placement missing")
for token in (
    "def driveModes", "def setDriveModeValue", "def beginSetupEdit", "def applySetupSettings", "def resetSetupSettings",
    "def ctrlAuxAssignments", "def w1pAuxAssignments", "def calibrationSummary",
    "def filteredLogEntries", "def logRevision", "def logCount",
):
    require(token in backend, f"final Setup/Log backend surface missing: {token}")
require('pyside6-qmllint --max-warnings -1 qml/Main.qml qml/components/*.qml qml/pages/*.qml' in workflow,
        "CI qmllint does not include final Setup/Log pages")

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
require("python -m tools.test_backend_logic" in workflow, "backend tests are not run as an import-safe module")
require("sys.path.insert(0, str(ROOT))" in read("tools/test_backend_logic.py"), "backend test does not add repository root to sys.path")
require(not re.search(r"(?m)^\s*ditto\s+.*--sequesterRsrc", workflow),
        "software-distribution ZIP command must not use --sequesterRsrc")
require('ditto -c -k --keepParent "release/HV P2P SRVR.app" "$ZIP"' in workflow,
        "release ZIP is not created with the expected ditto command")
require('ditto -x -k "$ZIP" "$VERIFY_DIR"' in workflow,
        "release ZIP round-trip extraction validation missing")
require('codesign --verify --deep --strict --verbose=2 "$ROUNDTRIP_APP"' in workflow,
        "round-trip extracted app signature verification missing")
require('xattr -cr "$APP_PATH" || true' in workflow,
        "extended-attribute cleanup before final app signature is missing")
require('cp assets/HV_P2P_SRVR_icon.png "$STAGE/HV_P2P_SRVR_icon.png"' in workflow and
        'iconutil -c icns' in workflow and 'CFBundleIconFile' in workflow,
        "P2P SRVR bundle icon is not restored during packaging")
require('CFBundleDisplayName' in workflow and "HV P2P SRVR'" in workflow,
        "HV P2P SRVR bundle display metadata is not enforced")
require('QT_QPA_PLATFORM=cocoa "$ROUNDTRIP_EXE" --smoke-test' in workflow,
        "round-trip extracted app smoke test missing")

require('text: "Skate Weight:"' in qml_main, "Free-D must label the suspended package as Skate Weight")
require('text: "Static Weight:"' not in qml_main, "obsolete Static Weight label remains in Free-D")
require('backend.skateWeightValue' in qml_main and 'setWeightValue("Skate", n)' in qml_main,
        "Skate Weight editor is not wired to the backend")
require('Text { width:f(150); anchors.verticalCenter:parent.verticalCenter; text:"Drive Mode"' in qml_main,
        "System Drive Mode row is not aligned to the common 150px control column")
require('fillText("SKATE"' not in span_qml, "Top/Side span diagrams still draw the SKATE text label")

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
