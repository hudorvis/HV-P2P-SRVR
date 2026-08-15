#!/usr/bin/env python3
"""Hidden legacy backend worker for HV P2P SRVR v26.08.15.05.

The proven v26.06.26.25 Tk backend runs in this *separate process* with its
window withdrawn.  The visible application is Qt Quick/QML.  JSON lines on
stdin/stdout are used as a deliberately small process boundary so Qt and Tk do
not compete for the same macOS/Windows GUI event loop.
"""
from __future__ import annotations

import json
import os
import queue
import sys
import threading
import time
import traceback
from pathlib import Path

# stdout is reserved for the frontend protocol.  Anything printed by the legacy
# module is redirected to stderr so it can never corrupt a JSON protocol line.
_PROTOCOL_OUT = sys.stdout
sys.stdout = sys.stderr

import tkinter as tk
import hv_p2p_legacy_core as legacy

APP_VERSION = "v26.08.15.05"

def _user_config_path() -> str:
    if sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support" / "HV P2P SRVR"
    elif os.name == "nt":
        root = Path(os.environ.get("APPDATA", str(Path.home()))) / "HV P2P SRVR"
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "HV P2P SRVR"
    root.mkdir(parents=True, exist_ok=True)
    return str(root / "config.json")


class WorkerApp(legacy.HVP2PServerApp):
    """Legacy control engine with writable packaged-app configuration storage."""
    def _prepare_config(self):
        desired = _user_config_path()
        self.config_path = desired
        self.default_config_path = desired

    def _load_config(self):
        self._prepare_config()
        return super()._load_config()

    def _save_config(self, path=None):
        if path is None:
            self._prepare_config()
        return super()._save_config(path)


_COMMANDS: "queue.Queue[dict]" = queue.Queue()
_STOP = threading.Event()


def _send(payload: dict) -> None:
    try:
        _PROTOCOL_OUT.write(json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n")
        _PROTOCOL_OUT.flush()
    except Exception:
        pass


def _stdin_reader() -> None:
    while not _STOP.is_set():
        try:
            line = sys.stdin.readline()
        except Exception:
            break
        if not line:
            break
        try:
            msg = json.loads(line)
            if isinstance(msg, dict):
                _COMMANDS.put(msg)
        except Exception:
            continue
    _STOP.set()


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return int(default)


def _drive_mode_name(app) -> str:
    try:
        idx = int(getattr(app, "active_drive_mode", 0))
        modes = list(getattr(app, "drive_modes", []) or [])
        if 0 <= idx < len(modes):
            name = str(modes[idx].get("name", f"Mode {idx+1}") or "").strip()
            return name or f"Mode {idx+1}"
    except Exception:
        pass
    return "Mode 1"


def _connection_snapshot(app) -> dict:
    now = time.time()
    try:
        cs = legacy.get_controller_status()
        ctrl = bool(cs.get("connected", False))
    except Exception:
        cs = {}
        ctrl = False
    try:
        last = _safe_float(getattr(app.arduino_status, "last_seen", 0.0), 0.0)
        w1p = bool(getattr(app.arduino_status, "connected", False)) and last > 0 and (now - last) <= legacy.WINCH_STATUS_TIMEOUT_S
    except Exception:
        w1p = False
    try:
        input_recent = bool(app._freed_input_recent()) if bool(getattr(app, "freed_input_enabled", False)) else False
    except Exception:
        input_recent = False
    # Output is connectionless UDP.  When output is enabled there is no remote
    # ACK to prove reachability, so the status means the Free-D path is active;
    # input freshness still takes precedence when input is enabled.
    try:
        output_active = bool(getattr(app, "freed_output_enabled", False))
    except Exception:
        output_active = False
    freed = input_recent or output_active
    return {"ctrl": ctrl, "w1p": w1p, "freeD": freed, "ctrlDetails": cs}


def _safety_snapshot(app) -> dict:
    try:
        is_red, red_text, sources = app._safety_status_summary()
    except Exception:
        is_red, red_text, sources = True, "SRVR Fault", ["SRVR"]
    if is_red:
        return {"level": "fault", "text": str(red_text or "E-STOP"), "sources": list(sources or [])}
    if bool(getattr(app, "battery_change_mode", False)):
        return {"level": "warning", "text": "BATTERY CHANGE", "sources": []}
    if bool(getattr(app, "system_calibration_mode", False)):
        return {"level": "warning", "text": "LIMIT CALIBRATION", "sources": []}
    if bool(getattr(app, "winch_calibration_mode", False)):
        return {"level": "warning", "text": "WINCH CALIBRATION", "sources": []}
    if bool(getattr(app, "not_calibrated_mode", False)):
        return {"level": "warning", "text": "UN-CALIBRATED", "sources": []}
    return {"level": "ready", "text": "SYSTEM READY", "sources": []}


def _setup_snapshot(app) -> dict:
    modes = list(getattr(app, "drive_modes", []) or [])
    while len(modes) < 2:
        modes.append({})
    def mode(i):
        m = modes[i] if isinstance(modes[i], dict) else {}
        return {
            "name": str(m.get("name", f"Mode {i+1}") or f"Mode {i+1}"),
            "maxSpeed": _safe_float(m.get("max_speed_mps", 0.0)),
            "gotoSpeed": _safe_float(m.get("max_goto_speed_mps", 0.0)),
            "accel": _safe_float(m.get("max_accel_mps2", 0.0)),
            "decel": _safe_float(m.get("max_decel_mps2", 0.0)),
            "crossover": _safe_float(m.get("max_crossover_mps2", 0.0)),
            "stopDecel": _safe_float(m.get("max_stop_decel_mps2", 0.0)),
        }
    return {
        "controllerIp": str(getattr(app, "controller_ip_ref", "") or ""),
        "controllerDirection": "Inverted" if bool(getattr(app, "reverse_joystick", False)) else "Normal",
        "ctrlTsConnected": bool(getattr(legacy.controller_state, "get", lambda *_: False)("hmi_connected_reported", False)) if hasattr(legacy, "controller_state") else False,
        "adsConnected": bool(getattr(legacy.controller_state, "get", lambda *_: False)("ads1115_connected_reported", False)) if hasattr(legacy, "controller_state") else False,
        "winchIp": str(getattr(app, "winch_host", "") or ""),
        "winchDirection": "Inverted" if bool(getattr(app, "reverse_motor", False)) else "Normal",
        "w1pTsConnected": bool(getattr(app, "w1pts_connected_reported", False)),
        "rs485": str(getattr(app, "winch_rs_status", "--") or "--"),
        "positionSource": str(getattr(app, "winch_pos_source", "--") or "--"),
        "unitsPerM": _safe_float(getattr(app, "winch_units_per_m", 0.0)),
        "mode1": mode(0),
        "mode2": mode(1),
        "auxCtrl": [str(getattr(app, f"aux{i}_action", "None") or "None") for i in range(1, 5)],
        "auxW1pts": [str(getattr(app, f"w1pts_aux{i}_action", "None") or "None") for i in range(1, 5)],
        "joy": {
            "current": _safe_float(legacy.controller_state.get("joystick_raw", 0.0)),
            "center": _safe_float(legacy.controller_state.get("joy_center", 0.0)),
            "min": _safe_float(legacy.controller_state.get("joy_min", -1.0)),
            "max": _safe_float(legacy.controller_state.get("joy_max", 1.0)),
        },
        "limitCalibrationLabel": str(app._setup_direct_action_label("Limit Calibration")),
        "winchCalibrationLabel": str(app._setup_direct_action_label("Winch Calibration")),
    }


def _freed_snapshot(app) -> dict:
    try:
        x, y, z = app._current_freed_xyz()
    except Exception:
        x, y, z = 0.0, 0.0, 0.0
    raw = {
        "camId": _safe_int(getattr(app, "freed_in_raw_camera_id", 0)),
        "pan": _safe_int(getattr(app, "freed_in_raw_pan", 0)),
        "tilt": _safe_int(getattr(app, "freed_in_raw_tilt", 0)),
        "roll": _safe_int(getattr(app, "freed_in_raw_roll", 0)),
        "zoom": _safe_int(getattr(app, "freed_in_raw_zoom", 0)),
        "focus": _safe_int(getattr(app, "freed_in_raw_focus", 0)),
    }
    decoded = {
        "camId": _safe_int(getattr(app, "freed_in_camera_id", 0)),
        "pan": _safe_float(getattr(app, "freed_in_pan", 0.0)),
        "tilt": _safe_float(getattr(app, "freed_in_tilt", 0.0)),
        "roll": _safe_float(getattr(app, "freed_in_roll", 0.0)),
        "zoom": _safe_int(getattr(app, "freed_in_zoom", 0)),
        "focus": _safe_int(getattr(app, "freed_in_focus", 0)),
        "fps": _safe_float(getattr(app, "freed_in_fps", 0.0)),
    }
    pts = []
    for idx, p in enumerate(list(getattr(app, "freed_height_points", []) or [])[:5]):
        if not isinstance(p, dict):
            p = {}
        pts.append({
            "enabled": bool(p.get("enabled", False)),
            "name": f"P{idx+1}",
            "x": _safe_float(p.get("y_m", 0.0)),
            "y": _safe_float(p.get("z_m", 0.0)),
            "z": _safe_float(p.get("z_offset_m", 0.0)),
        })
    while len(pts) < 5:
        idx = len(pts)
        pts.append({"enabled": False, "name": f"P{idx+1}", "x": idx * 25.0, "y": 0.0, "z": 0.0})
    return {
        "inputEnabled": bool(getattr(app, "freed_input_enabled", False)),
        "inputIp": str(getattr(app, "freed_input_bind_ip", "0.0.0.0") or "0.0.0.0"),
        "inputPort": _safe_int(getattr(app, "freed_input_port", 40001)),
        "inputRaw": raw,
        "inputDecoded": decoded,
        "inputOffsets": dict(getattr(app, "freed_input_offsets", {}) or {}),
        "inputInverts": dict(getattr(app, "freed_input_inverts", {}) or {}),
        "outputEnabled": bool(getattr(app, "freed_output_enabled", False)),
        "outputIp": str(getattr(app, "freed_target_ip", "") or ""),
        "outputPort": _safe_int(getattr(app, "freed_target_port", 40000)),
        "outputRate": _safe_float(getattr(app, "freed_rate_hz", 25.0)),
        "outputFps": _safe_float(getattr(app, "freed_out_fps", 0.0)),
        "xyz": {"x": x, "y": y, "z": z},
        "outputOffsets": dict(getattr(app, "freed_output_offsets", {}) or {}),
        "outputInverts": dict(getattr(app, "freed_output_inverts", {}) or {}),
        "points": pts,
        "skateKg": _safe_float(getattr(app, "freed_skate_weight_kg", 35.0)),
        "cableKg100m": _safe_float(getattr(app, "freed_weight_per_100m_kg", 4.8)),
        "tensionKg": _safe_float(getattr(app, "freed_sag_tension_kgf", 1200.0)),
        "highlineMode": str(getattr(app, "freed_highline_mode", "Single Highline") or "Single Highline"),
        "lensType": str(getattr(app, "freed_lens_type", "i24") or "i24"),
        "lensScale": str(getattr(app, "freed_lens_scale_mode", "Auto") or "Auto"),
        "lensCal": dict(getattr(app, "freed_lens_cal", {}) or {}),
        "zoomLive": _safe_float(app._current_lens_value("zoom")),
        "focusLive": _safe_float(app._current_lens_value("focus")),
    }


def _log_snapshot(app) -> list[str]:
    try:
        text = app.log_text.get("1.0", "end-1c") if hasattr(app, "log_text") else ""
        lines = str(text).splitlines()
        return lines[-350:]
    except Exception:
        return []


def _snapshot(app) -> dict:
    conn = _connection_snapshot(app)
    safety = _safety_snapshot(app)
    try:
        span = max(0.001, _safe_float(app._limit_display_position_m(app.state.far_limit), 100.0))
    except Exception:
        span = max(0.001, _safe_float(getattr(app.state, "total_length_m", 100.0), 100.0))
    try:
        pos = _safe_float(app._display_position_relative_m(), 0.0)
    except Exception:
        pos = 0.0
    try:
        ref = _safe_float(app._limit_display_position_m(app.state.ref_point), 0.0)
    except Exception:
        ref = 0.0
    presets = []
    names = list(getattr(app, "preset_names", []) or [])
    positions = list(getattr(app, "preset_positions", []) or [])
    visible = list(getattr(app, "preset_visible", []) or [])
    for i in range(6):
        p = positions[i] if i < len(positions) else None
        presets.append({
            "name": str(names[i] if i < len(names) else f"P{i+1}"),
            "position": None if p is None else _safe_float(p),
            "visible": bool(visible[i]) if i < len(visible) else True,
        })
    try:
        z0 = _safe_float(app._freed_z_offset_for_x(0.0), 0.0) + _safe_float(app._freed_output_offset_value("Z"), 0.0)
        z1 = _safe_float(app._freed_z_offset_for_x(span), 0.0) + _safe_float(app._freed_output_offset_value("Z"), 0.0)
    except Exception:
        z0 = z1 = 0.0
    side_samples = []
    try:
        yoff = _safe_float(app._freed_output_offset_value("Y"), 0.0)
        for i in range(61):
            x = span * i / 60.0
            side_samples.append([x, _safe_float(app._freed_z_for_y(x), 0.0) + yoff])
    except Exception:
        side_samples = [[0.0, 0.0], [span, 0.0]]
    try:
        _cid, pan, tilt, roll, zoom, focus = app._freed_motion_for_display()
    except Exception:
        pan = tilt = roll = 0.0; zoom = focus = 0
    try:
        max_speed, _ = app._current_max_speed_info()
    except Exception:
        max_speed = _safe_float(getattr(app, "max_speed_mps", 0.0))
    mode_idx = _safe_int(getattr(app, "active_drive_mode", 0), 0)
    snapshot = {
        "version": APP_VERSION,
        "connections": conn,
        "safety": safety,
        "run": {
            "speed": _safe_float(getattr(app, "display_speed_mps", getattr(app, "current_speed_mps", 0.0))),
            "maxSpeed": _safe_float(max_speed),
            "driveMode": _drive_mode_name(app),
            "driveModeIndex": mode_idx,
            "accelMode": str(app._display_accel_type()),
            "batteryChange": bool(getattr(app, "battery_change_mode", False)),
            "position": pos,
            "span": span,
            "toNear": abs(pos),
            "toFar": abs(span - pos),
            "reference": ref,
            "nearRamp": max(0.0, _safe_float(getattr(app.state, "ramp_zone_near", 0.0))),
            "farRamp": max(0.0, _safe_float(getattr(app.state, "ramp_zone_far", 0.0))),
            "presets": presets,
            "zNear": z0,
            "zFar": z1,
            "sideSamples": side_samples,
            "camera": {"pan": pan, "tilt": tilt, "roll": roll, "zoom": zoom, "focus": focus},
            "auxLabels": [str(app._aux_action_label(i) or f"AUX{i+1}") for i in range(4)],
        },
        "setup": _setup_snapshot(app),
        "freeD": _freed_snapshot(app),
        "log": _log_snapshot(app),
        "statusMessage": str(getattr(getattr(app, "status_var", None), "get", lambda: "")() or ""),
    }
    return snapshot


def _set_mode_values(app, idx: int, data: dict) -> None:
    modes = list(getattr(app, "drive_modes", []) or [])
    while len(modes) < 2:
        modes.append({})
    m = dict(modes[idx] if isinstance(modes[idx], dict) else {})
    m.update({
        "name": str(data.get("name", m.get("name", f"Mode {idx+1}")) or f"Mode {idx+1}"),
        "max_speed_mps": max(0.01, _safe_float(data.get("maxSpeed", m.get("max_speed_mps", 1.0)), 1.0)),
        "max_goto_speed_mps": max(0.01, _safe_float(data.get("gotoSpeed", m.get("max_goto_speed_mps", 1.0)), 1.0)),
        "max_accel_mps2": max(0.01, _safe_float(data.get("accel", m.get("max_accel_mps2", 1.0)), 1.0)),
        "max_decel_mps2": max(0.01, _safe_float(data.get("decel", m.get("max_decel_mps2", 1.0)), 1.0)),
        "max_crossover_mps2": max(0.01, _safe_float(data.get("crossover", m.get("max_crossover_mps2", 1.0)), 1.0)),
        "max_stop_decel_mps2": max(0.01, _safe_float(data.get("stopDecel", m.get("max_stop_decel_mps2", 1.0)), 1.0)),
    })
    modes[idx] = m
    app.drive_modes = modes


def _apply_setup(app, d: dict) -> None:
    old_winch = str(getattr(app, "winch_host", "") or "")
    app._apply_controller_ip_change(str(d.get("controllerIp", getattr(app, "controller_ip_ref", "")) or "").strip())
    app.reverse_joystick = str(d.get("controllerDirection", "Normal")) == "Inverted"
    app.winch_host = str(d.get("winchIp", old_winch) or "").strip()
    app.reverse_motor = str(d.get("winchDirection", "Normal")) == "Inverted"
    app.winch_units_per_m = max(1.0, _safe_float(d.get("unitsPerM", getattr(app, "winch_units_per_m", 1.0)), 1.0))
    _set_mode_values(app, 0, dict(d.get("mode1", {}) or {}))
    _set_mode_values(app, 1, dict(d.get("mode2", {}) or {}))
    aux = list(d.get("auxCtrl", []) or [])
    for i in range(4):
        if i < len(aux): setattr(app, f"aux{i+1}_action", str(aux[i] or "None"))
    auxw = list(d.get("auxW1pts", []) or [])
    for i in range(4):
        if i < len(auxw): setattr(app, f"w1pts_aux{i+1}_action", str(auxw[i] or "None"))
    joy = dict(d.get("joy", {}) or {})
    try:
        legacy.controller_state["joy_center"] = _safe_float(joy.get("center", legacy.controller_state.get("joy_center", 0.0)))
        legacy.controller_state["joy_min"] = _safe_float(joy.get("min", legacy.controller_state.get("joy_min", -1.0)))
        legacy.controller_state["joy_max"] = _safe_float(joy.get("max", legacy.controller_state.get("joy_max", 1.0)))
    except Exception:
        pass
    try:
        if app.winch_host != old_winch:
            app.arduino_client.reconfigure(app.winch_host, app.winch_port)
        app.arduino_client.send(f"SET_UNITS_PER_M {app.winch_units_per_m:.1f}")
        app.arduino_client.send(f"SET_MOTOR_REVERSE {1 if app.reverse_motor else 0}")
    except Exception:
        pass
    app._set_active_drive_mode(_safe_int(getattr(app, "active_drive_mode", 0), 0), save_config=False)
    app._sync_motion_profile_to_winch(force=True)
    app._save_config()
    app._set_status("Setup settings saved")


def _apply_freed(app, d: dict) -> None:
    app.freed_input_enabled = bool(d.get("inputEnabled", getattr(app, "freed_input_enabled", False)))
    app.freed_input_bind_ip = str(d.get("inputIp", getattr(app, "freed_input_bind_ip", "0.0.0.0")) or "0.0.0.0")
    app.freed_input_port = max(1, min(65535, _safe_int(d.get("inputPort", getattr(app, "freed_input_port", 40001)), 40001)))
    app.freed_output_enabled = bool(d.get("outputEnabled", getattr(app, "freed_output_enabled", False)))
    app.freed_target_ip = str(d.get("outputIp", getattr(app, "freed_target_ip", "")) or "")
    app.freed_target_port = max(1, min(65535, _safe_int(d.get("outputPort", getattr(app, "freed_target_port", 40000)), 40000)))
    app.freed_rate_hz = max(1.0, min(100.0, _safe_float(d.get("outputRate", getattr(app, "freed_rate_hz", 25.0)), 25.0)))
    app.freed_input_offsets = dict(d.get("inputOffsets", getattr(app, "freed_input_offsets", {})) or {})
    app.freed_input_inverts = dict(d.get("inputInverts", getattr(app, "freed_input_inverts", {})) or {})
    app.freed_output_offsets = dict(d.get("outputOffsets", getattr(app, "freed_output_offsets", {})) or {})
    app.freed_output_inverts = dict(d.get("outputInverts", getattr(app, "freed_output_inverts", {})) or {})
    pts = []
    for p in list(d.get("points", []) or [])[:5]:
        p = dict(p or {})
        pts.append({
            "enabled": bool(p.get("enabled", False)),
            "y_m": _safe_float(p.get("x", 0.0)),
            "z_m": _safe_float(p.get("y", 0.0)),
            "z_offset_m": _safe_float(p.get("z", 0.0)),
        })
    if pts:
        while len(pts) < 5: pts.append({"enabled": False, "y_m": 0.0, "z_m": 0.0, "z_offset_m": 0.0})
        app.freed_height_points = pts
    app.freed_skate_weight_kg = max(0.0, _safe_float(d.get("skateKg", getattr(app, "freed_skate_weight_kg", 35.0)), 35.0))
    app.freed_weight_per_100m_kg = max(0.0, _safe_float(d.get("cableKg100m", getattr(app, "freed_weight_per_100m_kg", 4.8)), 4.8))
    app.freed_sag_tension_kgf = max(1.0, _safe_float(d.get("tensionKg", getattr(app, "freed_sag_tension_kgf", 1200.0)), 1200.0))
    app.freed_highline_mode = "Dual Highline" if str(d.get("highlineMode", "Single Highline")).lower().startswith("dual") else "Single Highline"
    app.freed_lens_type = str(d.get("lensType", getattr(app, "freed_lens_type", "i24")) or "i24")
    app.freed_lens_scale_mode = str(d.get("lensScale", getattr(app, "freed_lens_scale_mode", "Auto")) or "Auto")
    cal = dict(d.get("lensCal", {}) or {})
    if cal:
        app.freed_lens_cal = {k: _safe_float(v) for k, v in cal.items()}
    app._save_config()
    app._ensure_freed_input_listener()
    app._ensure_freed_output_thread()
    app._set_status("Free-D settings saved")


def _goto_preset(app, idx: int) -> None:
    idx = _safe_int(idx, -1)
    try:
        target = app._preset_absolute_position_m(idx)
    except Exception:
        target = None
    if target is None:
        app._set_status(f"Preset P{idx+1} is not set")
        return
    name = app.preset_names[idx] if 0 <= idx < len(app.preset_names) else f"P{idx+1}"
    app._start_goto_target(float(target), f"Goto {name} {float(target):0.2f} m")


def _goto_limit(app, which: str) -> None:
    which = str(which or "").lower()
    if which == "near": lp = app.state.near_limit
    elif which == "far": lp = app.state.far_limit
    else: lp = app.state.ref_point
    pos = getattr(lp, "position_m", None)
    if pos is None:
        app._set_status(f"{getattr(lp, 'name', 'Target')} is not set")
        return
    app._start_goto_target(float(pos), f"Goto {getattr(lp, 'name', which.title())} {float(pos):0.2f} m")



def _limit_obj(app, which: str):
    w=str(which or "").lower()
    if w=="near": return app.state.near_limit
    if w=="far": return app.state.far_limit
    return app.state.ref_point


def _preset_set_direct(app, idx: int) -> None:
    idx=_safe_int(idx,-1)
    if not (0 <= idx < len(app.preset_positions)): return
    rel=app._current_position_relative_m()
    app.preset_positions[idx]=float(rel)
    app._save_config(); app._set_status(f"Preset {app.preset_names[idx]} set to {rel:0.2f} m")


def _preset_update(app, idx: int, name, position, visible) -> None:
    idx=_safe_int(idx,-1)
    if not (0 <= idx < len(app.preset_positions)): return
    if name is not None and str(name).strip(): app.preset_names[idx]=str(name).strip()
    if position is None or str(position).strip()=="": app.preset_positions[idx]=None
    else: app.preset_positions[idx]=_safe_float(position,0.0)
    if idx < len(app.preset_visible): app.preset_visible[idx]=bool(visible)
    app._save_config(); app._set_status(f"Preset {app.preset_names[idx]} updated")


def _set_ramp_direct(app, which: str, mode: str, value) -> None:
    lp=_limit_obj(app,which)
    if lp not in (app.state.near_limit,app.state.far_limit): return
    mode="Percentage" if str(mode).lower().startswith("percent") else "Distance"
    v=max(0.0,_safe_float(value,0.0)); lp.ramp_mode=mode
    span=max(0.1,_safe_float(getattr(app.state,"total_length_m",100.0),100.0))
    if mode=="Percentage":
        lp.ramp_percentage=v; lp.ramp_distance_m=None; dist=span*v/100.0
    else:
        lp.ramp_distance_m=v; lp.ramp_percentage=None; dist=v
    if lp is app.state.near_limit: app.state.ramp_zone_near=dist
    else: app.state.ramp_zone_far=dist
    app._sync_limits_to_winch(); app._save_config(); app._set_status(f"{lp.name} ramping set to {v:0.2f} {'%' if mode=='Percentage' else 'm'}")


def _load_config_path(app, path: str) -> None:
    try:
        with open(path,"r",encoding="utf-8") as f: cfg=json.load(f)
        app._apply_config_dict(cfg)
        app.config_path=app.default_config_path
        app._save_config(app.config_path)
        app._sync_limits_to_winch(); app._sync_motion_profile_to_winch(force=True)
        app._ensure_freed_input_listener(); app._ensure_freed_output_thread()
        app._set_status(f"Configuration loaded: {Path(path).name}")
    except Exception as exc:
        app._set_status(f"Configuration load failed: {exc}")

def _execute(app, msg: dict) -> None:
    name = str(msg.get("name", ""))
    args = dict(msg.get("args", {}) or {})
    if name == "shutdown":
        _STOP.set(); return
    if name == "estop": app._toggle_estop(); return
    if name == "goto_preset": _goto_preset(app, args.get("index", -1)); return
    if name == "goto_limit": _goto_limit(app, args.get("which", "ref")); return
    if name == "aux": app._handle_aux_action(_safe_int(args.get("index", 0))); return
    if name == "drive_mode": app._set_active_drive_mode(0 if _safe_int(args.get("index", 0)) <= 0 else 1); return
    if name == "accel_toggle": app._toggle_accel_type(save_config=True); return
    if name == "battery_change": app._set_battery_change_mode(bool(args.get("enabled", False)), save_config=True); return
    if name == "cancel_motion": app._cancel_motion(); return
    if name == "setup_action": app._execute_setup_direct_action(str(args.get("action", ""))); return
    if name == "apply_setup": _apply_setup(app, args); return
    if name == "apply_freed": _apply_freed(app, args); return
    if name == "capture_lens": app._capture_lens_endpoint(str(args.get("endpoint", ""))); return
    if name == "reset_lens": app._reset_lens_calibration(); return
    if name == "clear_log": app._clear_log_tab(); return
    if name == "save_log": app._save_log_tab(); return
    if name == "reload_config": app._load_config(); app._set_status("Configuration reloaded"); return
    if name == "save_config": app._save_config(); app._set_status("Configuration saved"); return
    if name == "save_config_path": app._save_config(str(args.get("path", ""))); app._set_status("Configuration backup saved"); return
    if name == "load_config_path": _load_config_path(app, str(args.get("path", ""))); return
    if name == "limit_set": app.on_set_point(_limit_obj(app,args.get("which","ref")), require_popup=False); app._set_status("Limit point set"); return
    if name == "limit_slip": app.on_set_slip(_limit_obj(app,args.get("which","ref")), require_popup=False, show_info=False); return
    if name == "ramp_set": _set_ramp_direct(app,args.get("which","near"),args.get("mode","Distance"),args.get("value",0)); return
    if name == "preset_set": _preset_set_direct(app,args.get("index",-1)); return
    if name == "preset_update": _preset_update(app,args.get("index",-1),args.get("presetName"),args.get("position"),args.get("visible",True)); return


def run_backend_worker() -> int:
    root = tk.Tk()
    root.withdraw()
    # Prevent the legacy constructor from deiconifying/maximising its hidden UI.
    original_state = root.state
    original_attributes = root.attributes
    def hidden_state(*args):
        if args:
            return None
        return original_state()
    def hidden_attributes(*args):
        if args and args[0] in ("-zoomed", "-fullscreen"):
            return None
        return original_attributes(*args)
    root.state = hidden_state  # type: ignore[method-assign]
    root.attributes = hidden_attributes  # type: ignore[method-assign]

    try:
        app = WorkerApp(root)
    except Exception as exc:
        _send({"type": "fatal", "message": f"Legacy backend startup failed: {exc}", "traceback": traceback.format_exc()})
        try: root.destroy()
        except Exception: pass
        return 2

    try:
        root.withdraw()
    except Exception:
        pass

    threading.Thread(target=_stdin_reader, daemon=True).start()
    _send({"type": "ready", "version": APP_VERSION})

    last_snapshot = 0.0
    def service():
        nonlocal last_snapshot
        if _STOP.is_set():
            try:
                app._on_close()
            except Exception:
                try: root.destroy()
                except Exception: pass
            return
        for _ in range(25):
            try: msg = _COMMANDS.get_nowait()
            except queue.Empty: break
            try:
                _execute(app, msg)
            except Exception as exc:
                legacy._app_log(f"[QT-BRIDGE] command {msg.get('name')} failed: {exc}")
                _send({"type": "command_error", "name": msg.get("name"), "message": str(exc)})
        now = time.time()
        if now - last_snapshot >= 0.10:
            last_snapshot = now
            try:
                _send({"type": "snapshot", "data": _snapshot(app)})
            except Exception as exc:
                _send({"type": "snapshot_error", "message": str(exc)})
        try:
            root.after(20, service)
        except Exception:
            pass

    root.after(20, service)
    try:
        root.mainloop()
    finally:
        _STOP.set()
    return 0


if __name__ == "__main__":
    raise SystemExit(run_backend_worker())
