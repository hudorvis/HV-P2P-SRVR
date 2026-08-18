#!/usr/bin/env python3
"""HV P2P SRVR Qt Quick backend.

This is deliberately UI-free: no Tkinter/ttk imports and no GUI widgets.
The transport/protocol constants and safety/motion behaviours are carried
forward from the supplied HV P2P SRVR v26.06.26.25 backend.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from datetime import datetime
import copy, json, math, os, queue, socket, struct, threading, time
from urllib.parse import unquote, urlparse

from PySide6.QtCore import QObject, Property, Signal, Slot, QTimer

# Proven controller protocol / timing carried forward from v26.06.26.25
SERVER_BIND_PORT = 5000
HEARTBEAT_CODE = 0xA5
HEARTBEAT_ACK = 0x5A
CONTROL_PACKET_CODE = 0xA6
FLAG_ESTOP_PRESSED = 0x10
FLAG_CANCEL_PRESSED = 0x01
FLAG_MODE_TOGGLE = 0x02
FLAG_BATT_CHANGE_TOGGLE = 0x04
FLAG_AUX1 = 0x20
FLAG_AUX2 = 0x40
FLAG_AUX3 = 0x80
FLAG_AUX4 = 0x0100
FLAG_ADS1115_FAULT = 0x0200
CTRL_RX_WINDOW_S = 0.75
CTRL_RX_MIN_PKTS = 2
JOY_DEADBAND_PCT = 5.0
WINCH_STATUS_TIMEOUT_S = 0.75
WINCH_PROBE_INTERVAL_S = 0.05


def _s24_to_int(b: bytes) -> int:
    if len(b) < 3: return 0
    v = (b[0] << 16) | (b[1] << 8) | b[2]
    return v - 0x1000000 if v & 0x800000 else v


def _u24_to_int(b: bytes) -> int:
    if len(b) < 3: return 0
    return (b[0] << 16) | (b[1] << 8) | b[2]


def _s24be(value: int) -> bytes:
    value = max(-8388608, min(8388607, int(value)))
    if value < 0: value += 1 << 24
    return bytes(((value >> 16) & 0xff, (value >> 8) & 0xff, value & 0xff))


@dataclass
class LimitPoint:
    name: str
    position_m: Optional[float] = None
    ramp_mode: str = "Distance"
    ramp_distance_m: float = 2.0
    ramp_percentage: float = 10.0

@dataclass
class WinchState:
    pos_m: Optional[float] = 0.0
    total_length_m: float = 100.0
    near_limit: LimitPoint = field(default_factory=lambda: LimitPoint("Near Limit", 0.0))
    ref_point: LimitPoint = field(default_factory=lambda: LimitPoint("Reference Point", 50.0))
    far_limit: LimitPoint = field(default_factory=lambda: LimitPoint("Far Limit", 100.0))
    estop_active: bool = True


class W1PClient(threading.Thread):
    def __init__(self, host: str, port: int, rxq: queue.Queue, log):
        super().__init__(daemon=True)
        self.host, self.port, self.rxq, self.log = host, port, rxq, log
        self.stop_evt = threading.Event()
        self.txq: queue.Queue[str] = queue.Queue(maxsize=500)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setblocking(False)
        self.last_seen = 0.0
        self.last_probe = 0.0

    @property
    def connected(self):
        return self.last_seen > 0 and time.time() - self.last_seen <= WINCH_STATUS_TIMEOUT_S

    def send(self, text: str):
        try: self.txq.put_nowait(str(text))
        except queue.Full: pass

    def reconfigure(self, host: str, port: int):
        self.host, self.port, self.last_seen = host, port, 0.0

    def run(self):
        while not self.stop_evt.is_set():
            try:
                while True:
                    text = self.txq.get_nowait()
                    payload = text if text.endswith("\n") else text + "\n"
                    self.sock.sendto(payload.encode("ascii", "ignore"), (self.host, self.port))
            except queue.Empty: pass
            except Exception as exc: self.log(f"[W1P TX] {exc}")
            now = time.time()
            if now - self.last_probe >= WINCH_PROBE_INTERVAL_S:
                self.last_probe = now
                try: self.sock.sendto(b"STATUS\n", (self.host, self.port))
                except Exception: pass
            try:
                while True:
                    data, addr = self.sock.recvfrom(4096)
                    if addr[0] != self.host: continue
                    for raw in data.decode("ascii", "ignore").splitlines():
                        line = raw.strip()
                        if line.startswith(("STATUS", "HELLO", "PONG", "OK", "ERR", "W1PTS_AUX", "W1P_HMI_STATUS")):
                            self.last_seen = time.time()
                            try: self.rxq.put_nowait(line)
                            except queue.Full: pass
            except BlockingIOError: pass
            except Exception: pass
            time.sleep(0.015)

    def close(self):
        self.stop_evt.set()
        try: self.sock.close()
        except Exception: pass


class HVP2PBackend(QObject):
    stateChanged = Signal()          # fast live telemetry / safety updates
    configChanged = Signal()         # operator-editable configuration updates
    logChanged = Signal()
    calibrationChanged = Signal()
    joystickCalibrationChanged = Signal()

    def __init__(self, version="26.08.17.14", smoke_test: bool = False):
        super().__init__()
        self.version = version
        self.smoke_test = bool(smoke_test)
        self.started = time.time()
        self._lock = threading.RLock()
        self._logs = deque(maxlen=1200)
        # Keep the proven plain-text log untouched for disk export while also
        # maintaining structured entries for the locked Log page filters/table.
        self._log_entries = deque(maxlen=1200)
        self._log_revision = 0
        self.state = WinchState()
        self.ctrl_ip = "172.20.1.101"
        self.w1p_ip = "172.20.1.102"
        self.w1p_port = 5000
        self.reverse_joystick = False
        self.reverse_motor = False
        self.joystick_deadband_pct = JOY_DEADBAND_PCT
        # Joystick calibration maps the CTRL raw -1..+1 value onto a corrected
        # -1..+1 operator axis. Defaults are identity so existing systems behave
        # exactly as before until the wizard is completed.
        self.joystick_cal_left = -1.0
        self.joystick_cal_centre = 0.0
        self.joystick_cal_right = 1.0
        self.position_source = "Encoder"
        self.ctrl_aux_assignments = [
            "Drive Mode", "Near Limit Save", "Preset 5 Recall",
            "Battery Change Mode", "Ref Point Slip",
        ]
        self.w1p_aux_assignments = [
            "Acceleration Mode", "Far Limit Recall", "Preset 2 Slip",
            "Ref Point Save", "Preset 10 Recall",
        ]
        self._limit_raw = {"near": None, "ref": None, "far": None}
        self.winch_units_per_m = 21220.7
        self.max_speed_mps = 25.0
        self.goto_speed_mps = 7.5
        self.max_accel_mps2 = 5.0
        self.max_decel_mps2 = 5.0
        self.max_crossover_mps2 = 10.0
        self.max_stop_decel_mps2 = 7.5
        self.drive_modes = [
            {"name":"Mode 1", "max_speed_mps":25.0, "goto_speed_mps":7.5, "accel_mps2":5.0, "decel_mps2":5.0, "crossover_mps2":10.0, "stop_decel_mps2":7.5},
            {"name":"Mode 2", "max_speed_mps":25.0, "goto_speed_mps":7.5, "accel_mps2":5.0, "decel_mps2":5.0, "crossover_mps2":10.0, "stop_decel_mps2":7.5},
        ]
        self.active_drive_mode = 0
        self.acceleration_mode = "Speed"
        self.battery_change_mode = False
        self._battery_change_went_outside_limits = False
        self._last_service_mode_sent = None
        self.current_speed_mps = 0.0
        self.requested_speed_mps = 0.0
        self.goto_target_m = None
        self.last_sent_vel = 0.0
        self.last_winch_output = 0.0
        self._winch_position_accept_jump_until = 0.0
        self._winch_last_pos_accept_t = 0.0
        self._winch_last_pos_reject_log_t = 0.0
        self.winch_rs_status = "Disconnected"
        self.winch_drive_writes_enabled = False
        self._w1p_estop = False
        self._ctrl_estop = False
        self._srvr_estop = False
        self._not_calibrated = True
        self._ctrl_rx_times = deque(maxlen=200)
        self._ctrl_last_seen = 0.0
        self._ctrl_flags = 0
        self._ctrl_axis = 0.0
        self._mode_last = self._batt_last = False
        self._stop_evt = threading.Event()
        self._w1p_rx: queue.Queue[str] = queue.Queue(maxsize=1000)
        self.w1p = W1PClient(self.w1p_ip, self.w1p_port, self._w1p_rx, self._log)

        self.preset_names = [f"P{i}" for i in range(1,11)]
        self.preset_positions = [None] * 10
        self.preset_visible = [True] * 10

        # Free-D
        self.freed_input_enabled = True
        self.freed_input_bind_ip = "0.0.0.0"
        self.freed_input_port = 40001
        self.freed_output_enabled = False
        self.freed_target_ip = "172.20.1.120"
        self.freed_target_port = 40000
        self.freed_rate_hz = 50.0
        self.freed_out_fps = 0.0
        self.freed_in_fps = 0.0
        self.freed_input_last_rx = 0.0
        self.freed_in_camera_id = 1
        self.freed_in_raw = {"Cam ID":1,"Pan":0,"Tilt":0,"Roll":0,"Zoom":0,"Focus":0}
        self.freed_in = {"Cam ID":1,"Pan":0.0,"Tilt":0.0,"Roll":0.0,"Zoom":0,"Focus":0}
        self.freed_input_offsets = {"Pan":0.0,"Tilt":0.0,"Roll":0.0}
        self.freed_input_inverts = {"Pan":False,"Tilt":False,"Roll":False,"Zoom":False,"Focus":False}
        self.freed_output_offsets = {"X":0.0,"Y":0.0,"Z":0.0}
        self.freed_output_inverts = {"X":False,"Y":False,"Z":False}
        self.freed_pos_scale = 640.0
        self.freed_lens_type = "u16"
        self.freed_lens_scale_mode = "Auto"
        self.freed_lens_cal = {"zoom_wide":0.0,"zoom_tele":32767.0,"focus_near":0.0,"focus_far":32767.0}
        self._freed_lens_auto_seen = {"zoom_min":None,"zoom_max":None,"focus_min":None,"focus_max":None}
        self.geometry = [
            {"name":"P1 (Near)","x":0.0,"y":0.0,"z":0.0},
            {"name":"P2","x":25.0,"y":5.0,"z":None},
            {"name":"P3","x":50.0,"y":8.0,"z":None},
            {"name":"P4","x":75.0,"y":5.0,"z":None},
            {"name":"P5 (Far)","x":100.0,"y":0.0,"z":0.0},
        ]
        self.skate_weight_kg = 25.0
        self.cable_weight_kg100m = 4.5
        self.cable_tension_kg = 100.0
        self.skate_weight_unit = "kg"
        self.cable_weight_unit = "kg/100m"
        self.cable_tension_unit = "kg"
        self.highline_mode = "Single Highline"
        self._freed_in_stop = threading.Event()
        self._freed_in_sock = None
        self._freed_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._freed_out_times = deque(maxlen=240)
        self._freed_in_times = deque(maxlen=120)
        self._last_freed_tx = 0.0

        # Calibration popup state
        self.calibration_open = False
        self.calibration_type = "Limit"
        self.calibration_step = 0
        self.calibration_title = "Set Near Limit"

        # Three-step joystick calibration wizard. Temporary captures are kept
        # separate until Right is accepted, so Cancel never alters calibration.
        self.joystick_calibration_open = False
        self.joystick_calibration_step = 0
        self.joystick_calibration_title = "Set Joystick Left"
        self.joystick_calibration_error = ""
        self._joystick_cal_pending = {"left": None, "centre": None, "right": None}
        # After a joystick-calibration wizard closes, motion stays inhibited until
        # the operator releases the stick back into the configured deadband. This
        # prevents the final full-Right capture (or a Cancel while displaced) from
        # immediately becoming a live motion command on the next 50 ms tick.
        self._joystick_neutral_required = False

        self._config_path = self._config_file_path()
        self._load_config()
        self._saved_freed_snapshot = self._freed_snapshot()
        self._saved_setup_snapshot = self._setup_snapshot()
        # Setup and Free-D are explicit Apply/Reset pages. Their editable values
        # live in independent drafts so typing never changes the live motion,
        # networking or Free-D state until Apply is deliberately pressed.
        self._setup_draft = copy.deepcopy(self._saved_setup_snapshot)
        self._freed_draft = copy.deepcopy(self._saved_freed_snapshot)
        self._pending_import_config = None
        self._pending_import_setup_handled = True
        self._pending_import_freed_handled = True
        self._setup_draft_dirty = False
        self._freed_draft_dirty = False
        self.w1p.reconfigure(self.w1p_ip, self.w1p_port)
        if not self.smoke_test:
            self.w1p.start()
            self._start_controller_listener()
            self._start_freed_input()
            self._sync_w1p_settings()

        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self._tick)
        self.timer.start()
        self._log("[SRVR] Qt Quick backend ready")

    def _config_file_path(self):
        home = Path.home() / "Library" / "Application Support" / "HV P2P SRVR"
        try: home.mkdir(parents=True, exist_ok=True)
        except Exception: home = Path.home()
        return home / "config.json"

    @staticmethod
    def _classify_log_message(msg: str):
        """Return (level, source, view, clean_message) without changing saved logs."""
        text = str(msg).strip()
        source = "SYSTEM"
        clean = text
        if text.startswith("[") and "]" in text:
            tag, clean = text[1:].split("]", 1)
            clean = clean.strip()
            tag_u = tag.upper()
            if "FREE-D" in tag_u:
                source = "FREE-D"
            elif "W1P" in tag_u:
                source = "W1P"
            elif "CTRL" in tag_u or "ADS1115" in tag_u:
                source = "CTRL"
            elif "CALIBRATION" in tag_u:
                source = "CAL"
            elif "CONFIG" in tag_u:
                source = "CONFIG"
            else:
                source = "SYSTEM"

        hay = (text + " " + clean).lower()
        if any(k in hay for k in ("fault", "failed", "failure", "error", "estop", "e-stop", "overcurrent")):
            level = "FAULT"
        elif any(k in hay for k in ("warn", "warning", "rejected", "timeout", "mismatch", "disconnected")):
            level = "WARN"
        else:
            level = "INFO"

        if source == "FREE-D":
            view = "Free-D"
        elif source in ("CTRL", "W1P") or any(k in hay for k in ("udp", "network", "rs485", "connected", "link")):
            view = "Network"
        elif any(k in hay for k in ("estop", "e-stop", "fault", "safety", "limit", "servo", "brake")):
            view = "Safety"
        else:
            view = "Live"
        return level, source, view, clean

    def _log(self, msg):
        raw = str(msg).strip()
        line = f"{time.strftime('%H:%M:%S')}  {raw}"
        level, source, view, clean = self._classify_log_message(raw)
        entry = {
            "time": datetime.now().strftime("%H:%M:%S.%f")[:-3],
            "level": level,
            "source": source,
            "view": view,
            "message": clean or raw,
        }
        with self._lock:
            self._logs.append(line)
            self._log_entries.append(entry)
            self._log_revision += 1
        self.logChanged.emit()

    # --- controller ---
    def _start_controller_listener(self):
        threading.Thread(target=self._controller_worker, daemon=True).start()

    def _controller_worker(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("0.0.0.0", SERVER_BIND_PORT))
            sock.settimeout(0.25)
        except OSError as exc:
            self._log(f"[SRVR] Controller UDP bind failed 0.0.0.0:{SERVER_BIND_PORT} -> {exc}")
            return
        while not self._stop_evt.is_set():
            try: data, addr = sock.recvfrom(2048)
            except socket.timeout: continue
            except OSError: break
            if not data or (self.ctrl_ip and addr[0] != self.ctrl_ip): continue
            if data[0] == HEARTBEAT_CODE:
                try: sock.sendto(bytes([HEARTBEAT_ACK]), addr)
                except Exception: pass
                continue
            msg = self._parse_control_packet(data)
            if not msg: continue
            now = time.time()
            with self._lock:
                self._ctrl_last_seen = now
                self._ctrl_rx_times.append(now)
                self._ctrl_flags = msg[0]
                self._ctrl_axis = msg[1]
        try: sock.close()
        except Exception: pass

    @staticmethod
    def _parse_control_packet(data):
        try:
            if data[0] == CONTROL_PACKET_CODE and len(data) >= 8:
                flags = int(data[1]); joy = struct.unpack("!f", data[2:6])[0]
            elif data[0] == 0xA7 and len(data) >= 10:
                flags = (int(data[1]) << 8) | int(data[2]); joy = struct.unpack("!f", data[3:7])[0]
            else: return None
            return flags, max(-1.0, min(1.0, float(joy)))
        except Exception: return None

    def _calibrated_joystick(self, raw: float) -> float:
        """Piecewise-normalise a raw joystick sample around the captured centre.

        The mapping deliberately supports controllers whose electrical direction
        is reversed: the physical Left capture always maps to -1 and Right to +1.
        The separate CTRL Direction setting is then applied afterwards.
        """
        raw = max(-1.0, min(1.0, float(raw)))
        left = float(self.joystick_cal_left)
        centre = float(self.joystick_cal_centre)
        right = float(self.joystick_cal_right)
        lspan = left - centre
        rspan = right - centre
        if abs(lspan) < 1e-6 or abs(rspan) < 1e-6 or lspan * rspan >= 0.0:
            return raw
        # Select the physical Left or Right half by which side of centre the raw
        # sample occupies. This works whether Left is electrically low or high.
        if (raw - centre) * lspan >= 0.0:
            value = -((raw - centre) / lspan)
        else:
            value = (raw - centre) / rspan
        return max(-1.0, min(1.0, float(value)))

    def _ctrl_connected(self):
        now = time.time()
        while self._ctrl_rx_times and now - self._ctrl_rx_times[0] > CTRL_RX_WINDOW_S:
            self._ctrl_rx_times.popleft()
        return len(self._ctrl_rx_times) >= CTRL_RX_MIN_PKTS

    # --- W1P parsing / motion ---
    def _parse_w1p(self, line):
        if line.startswith("ERR"):
            self._log(f"[W1P] {line}"); return
        if not line.startswith("STATUS"): return
        fields = {}
        for p in line.split()[1:]:
            if "=" in p:
                k,v = p.split("=",1); fields[k]=v
        try:
            if "POS_M" in fields:
                new_pos = float(fields["POS_M"])
                if self._sanity_accept_winch_position(new_pos, fields):
                    self.state.pos_m = new_pos
            if "RAW_POS" in fields: self._last_raw_pos = int(float(fields["RAW_POS"]))
            if "SPAN_M" in fields: self.state.total_length_m = float(fields["SPAN_M"])
            if "NL" in fields: self.state.near_limit.position_m = float(fields["NL"])
            if "FL" in fields: self.state.far_limit.position_m = float(fields["FL"])
            if "VEL_MPS" in fields: self.current_speed_mps = float(fields["VEL_MPS"])
            if "WRITE_EN" in fields: self.winch_drive_writes_enabled = fields["WRITE_EN"].lower() in ("1","true","on")
            if "UPM" in fields: self.winch_units_per_m = float(fields["UPM"])
            estop = fields.get("ESTOP","0").lower() not in ("0","false","off")
            src = fields.get("ESTOP_SRC","").upper()
            self._w1p_estop = bool(estop and src in ("","W1P","LOCAL"))
            rs = fields.get("RS_STAT", fields.get("MODBUS","0")).upper()
            cfg = fields.get("LEAD_CFG","MISMATCH").upper()
            fb_ok = fields.get("MODBUS","0").upper() in ("1","OK","CONNECTED","TRUE","ON")
            ready = fields.get("READY","0").upper() in ("1","OK","READY","TRUE","ON")
            pos_ok = fields.get("POS_READ","0").upper() in ("1","OK","TRUE","ON")
            io_ok = fields.get("IO_READ","0").upper() in ("1","OK","TRUE","ON")
            do_ok = fields.get("DO1_CFG","0").upper() in ("1","OK","TRUE","ON")
            srdy = fields.get("SRDY","0").upper() in ("1","OK","READY","TRUE","ON")
            if rs in ("1","OK","CONNECTED") and cfg == "OK" and fb_ok and ready and pos_ok and io_ok and do_ok and srdy:
                self.winch_rs_status = "Connected"
            elif rs in ("1","OK","CONNECTED") and cfg != "OK": self.winch_rs_status = "Configuration Fault"
            elif rs in ("1","OK","CONNECTED"): self.winch_rs_status = "Feedback Fault"
            else: self.winch_rs_status = "Disconnected"
        except Exception: pass

    def _sanity_accept_winch_position(self, new_pos_m: float, fields: dict) -> bool:
        """Fail closed on implausible W1P position jumps.

        Ported from the proven v26.06.26.25 backend. A deliberate Slip/SYNC_POS
        opens a short grace window so the new reference is accepted; otherwise
        stationary feedback is strict and active-motion feedback is bounded by
        the configured maximum speed and elapsed status interval.
        """
        try:
            new_pos = float(new_pos_m)
            if not math.isfinite(new_pos):
                return False
            old_pos = self.state.pos_m
            now = time.time()
            if old_pos is None:
                self._winch_last_pos_accept_t = now
                return True
            if now <= float(self._winch_position_accept_jump_until or 0.0):
                self._winch_last_pos_accept_t = now
                return True
            old_pos = float(old_pos)
            dt = now - float(self._winch_last_pos_accept_t or now)
            if dt <= 0.0 or dt > 1.0:
                dt = 0.075
            jump = abs(new_pos - old_pos)
            commanded = abs(float(self.last_winch_output or 0.0))
            max_speed = abs(float(self.max_speed_mps or 20.0))
            if commanded < 0.05 and self.goto_target_m is None:
                allowed_jump = 0.35
            else:
                allowed_jump = max(0.35, (max_speed + 2.0) * max(dt, 0.05) * 2.5)
            if not self._service_override_active():
                nl = float(self.state.near_limit.position_m or 0.0)
                fl = float(self.state.far_limit.position_m if self.state.far_limit.position_m is not None else nl + self.state.total_length_m)
                lo, hi = (nl, fl) if nl <= fl else (fl, nl)
                if new_pos < lo - 0.5 or new_pos > hi + 0.5:
                    jump = max(jump, allowed_jump + 1.0)
            if jump <= allowed_jump:
                self._winch_last_pos_accept_t = now
                return True
            if now - float(self._winch_last_pos_reject_log_t or 0.0) >= 2.0:
                self._winch_last_pos_reject_log_t = now
                self._log(f"[W1P-POS] Rejected implausible position jump {old_pos:.3f} -> {new_pos:.3f} m")
            return False
        except Exception as exc:
            self._log(f"[W1P-POS] Position validation failed closed: {exc}")
            return False

    def _sync_w1p_settings(self):
        """Synchronise the W1P command contract carried forward from v26.06.26.25."""
        if self.smoke_test:
            return
        self.w1p.send(f"SET_UNITS_PER_M {self.winch_units_per_m:.1f}")
        self.w1p.send(f"SET_MOTOR_REVERSE {1 if self.reverse_motor else 0}")
        self.w1p.send(f"SET_ACCEL {self.max_accel_mps2:.3f}")
        self.w1p.send(f"SET_DECEL {self.max_decel_mps2:.3f}")
        self.w1p.send(f"SET_CROSSOVER {self.max_crossover_mps2:.3f}")
        self.w1p.send(f"SET_STOP_DECEL {self.max_stop_decel_mps2:.3f}")
        self.w1p.send(f"SET_ACCEL_MODE {'DYNAMIC' if self.acceleration_mode == 'Speed' else 'TRADITIONAL'}")
        nl = float(self.state.near_limit.position_m or 0.0)
        fl = float(self.state.far_limit.position_m if self.state.far_limit.position_m is not None else 100.0)
        if fl < nl:
            nl, fl = fl, nl
        self.w1p.send(f"SET_SPAN {max(.1, fl-nl):.3f}")
        self.w1p.send(f"SET_LIMIT_NEAR {nl:.3f}")
        self.w1p.send(f"SET_LIMIT_FAR {fl:.3f}")
        self._sync_service_mode_to_winch(force=True)

    def _service_override_active(self) -> bool:
        """Service movement is allowed at reduced speed during calibration/battery work.

        This mirrors the working v26.06.26.25 behaviour: Not Calibrated is not an
        E-stop. It is a low-speed service state so the operator can actually move
        the skate to establish Near/Far/Reference positions.
        """
        return bool(
            self._not_calibrated
            or self.battery_change_mode
            or (self.calibration_open and self.calibration_type in ("Limit", "Winch"))
        )

    @staticmethod
    def _service_speed_limit_mps() -> float:
        # Proven service limit: 5 km/h.
        return 5.0 / 3.6

    def _sync_service_mode_to_winch(self, force: bool = False):
        enabled = 1 if self._service_override_active() else 0
        if (not force) and self._last_service_mode_sent == enabled:
            return
        self._last_service_mode_sent = enabled
        if not self.smoke_test:
            self.w1p.send(f"SERVICE_MODE {enabled}")

    def _update_battery_change_auto_cancel(self):
        if not self.battery_change_mode or self.state.pos_m is None:
            return
        if self._not_calibrated or self.calibration_open:
            return
        try:
            pos = float(self.state.pos_m)
            nl = float(self.state.near_limit.position_m or 0.0)
            fl = float(self.state.far_limit.position_m if self.state.far_limit.position_m is not None else self.state.total_length_m)
            lo, hi = (nl, fl) if nl <= fl else (fl, nl)
            if pos < lo - 0.05 or pos > hi + 0.05:
                self._battery_change_went_outside_limits = True
                return
            if self._battery_change_went_outside_limits and (lo + 0.02) <= pos <= (hi - 0.02):
                self.battery_change_mode = False
                self._battery_change_went_outside_limits = False
                self._sync_service_mode_to_winch(force=True)
                self._save_config()
                self.configChanged.emit()
                self._log("[SRVR] Battery Change auto-cancelled: skate returned inside limits")
        except Exception:
            pass

    def _hard_limit_velocity(self, pos, req):
        nl = float(self.state.near_limit.position_m or 0.0)
        fl = float(self.state.far_limit.position_m if self.state.far_limit.position_m is not None else self.state.total_length_m)
        if fl < nl:
            nl, fl = fl, nl
        if req == 0:
            return 0.0
        a = max(.1, float(self.max_stop_decel_mps2))
        fb = abs(self.current_speed_mps)
        guard = max(.03, min(.35, .03 + .12 * fb))
        if req < 0:
            rem = pos - nl
            if rem <= guard:
                return 0.0
            allow = math.sqrt(max(0, 2*a*(rem-guard)))
            ramp = self._ramp_distance(self.state.near_limit, fl-nl)
            if ramp > 0 and pos < nl+ramp:
                allow = min(allow, abs(req)*max(0, min(1, rem/ramp)))
            return -min(abs(req), allow)
        rem = fl-pos
        if rem <= guard:
            return 0.0
        allow = math.sqrt(max(0, 2*a*(rem-guard)))
        ramp = self._ramp_distance(self.state.far_limit, fl-nl)
        if ramp > 0 and pos > fl-ramp:
            allow = min(allow, abs(req)*max(0, min(1, rem/ramp)))
        return min(abs(req), allow)

    @staticmethod
    def _ramp_distance(lp, span):
        return max(0.0, span*(lp.ramp_percentage/100.0)) if lp.ramp_mode == "Percentage" else max(0.0, lp.ramp_distance_m)

    def _clamp_goto_target_inside_limits(self, target: float) -> float:
        if self._service_override_active():
            return float(target)
        nl = self.state.near_limit.position_m
        fl = self.state.far_limit.position_m
        if nl is None or fl is None:
            return float(target)
        lo, hi = (float(nl), float(fl)) if nl <= fl else (float(fl), float(nl))
        stand_off = 0.03
        if hi-lo <= 2*stand_off:
            return max(lo, min(hi, float(target)))
        return max(lo+stand_off, min(hi-stand_off, float(target)))

    def _goto_velocity(self, diff):
        d = abs(diff)
        fb = abs(self.current_speed_mps)
        if d <= .01 and fb <= .03:
            return 0.0, True
        direction = 1 if diff >= 0 else -1
        if d <= 2.0:
            allowed = min(.38, max(.025, .18*d+.025))
            if fb > max(.12, allowed*1.8):
                return 0.0, False
            return direction*min(self.goto_speed_mps, allowed), False
        plan = max(.08, self.max_stop_decel_mps2*.10)
        guard = max(.08, min(.9, .1+.06*fb))
        allowed = min(self.goto_speed_mps, math.sqrt(max(0, 2*plan*max(0, d-guard))))
        return direction*max(.10, allowed), False

    def _send_velocity(self, vel: float, force: bool = False):
        vel = float(vel)
        now = time.time()
        same = abs(vel-self.last_sent_vel) < .01
        if not force and same:
            if abs(vel) < .001 or (now-getattr(self, "_last_vel_tx", 0.0)) < .25:
                return
        self.last_sent_vel = vel
        self.requested_speed_mps = vel
        self.last_winch_output = vel
        self._last_vel_tx = now
        if self.smoke_test:
            return
        self.w1p.send("VEL 0" if abs(vel) < .001 else f"VEL {vel:.3f}")

    def _motion_tick(self):
        connected = self._ctrl_connected()
        flags = self._ctrl_flags
        self._ctrl_estop = bool(flags & FLAG_ESTOP_PRESSED)

        # Fail-safe sources are real connection / physical E-stop / RS485 faults.
        # Not-calibrated and calibration are SERVICE states, not E-stop states.
        safety = bool(
            self._srvr_estop
            or self._ctrl_estop
            or self._w1p_estop
            or bool(flags & FLAG_ADS1115_FAULT)
            or (not connected)
            or (not self.w1p.connected)
            or (self.winch_rs_status != "Connected")
        )
        self.state.estop_active = safety

        if flags & FLAG_CANCEL_PRESSED:
            self.goto_target_m = None
        mode_pressed = bool(flags & FLAG_MODE_TOGGLE)
        if mode_pressed and not self._mode_last:
            self.setDriveMode(1-self.active_drive_mode)
        self._mode_last = mode_pressed
        batt_pressed = bool(flags & FLAG_BATT_CHANGE_TOGGLE)
        if batt_pressed and not self._batt_last:
            self.setBatteryChange(not self.battery_change_mode)
        self._batt_last = batt_pressed

        self._sync_service_mode_to_winch()
        self._update_battery_change_auto_cancel()

        if safety:
            self.goto_target_m = None
            self._send_velocity(0.0, force=abs(self.last_sent_vel) > .0001)
            return
        if self.state.pos_m is None:
            self._send_velocity(0.0, force=True)
            return

        # Moving the stick is required by the calibration wizard. Never allow
        # those movements to command the winch while the overlay is open.
        if self.joystick_calibration_open:
            self.goto_target_m = None
            self._send_velocity(0.0, force=abs(self.last_sent_vel) > .0001)
            return

        axis = self._calibrated_joystick(self._ctrl_axis) * (-1 if self.reverse_joystick else 1)
        deadband = max(0.0, min(25.0, float(self.joystick_deadband_pct)))
        if self._joystick_neutral_required:
            # A zero-percent operating deadband is valid, but the post-wizard
            # release interlock still needs a small practical neutral window so
            # ADC/joystick noise cannot latch motion off forever.
            neutral_band = max(1.0, deadband)
            if abs(axis*100) <= neutral_band:
                self._joystick_neutral_required = False
            self.goto_target_m = None
            self._send_velocity(0.0, force=abs(self.last_sent_vel) > .0001)
            return
        if abs(axis*100) < deadband:
            axis = 0.0
        if self.goto_target_m is not None and abs(axis*100) >= deadband:
            self.goto_target_m = None

        service = self._service_override_active()
        if self.goto_target_m is not None:
            vel, reached = self._goto_velocity(self.goto_target_m-self.state.pos_m)
            if reached:
                self.goto_target_m = None
                vel = 0.0
            if service:
                limit = self._service_speed_limit_mps()
                vel = max(-limit, min(limit, vel))
        else:
            vmax = self._service_speed_limit_mps() if service else self.max_speed_mps
            vel = axis*vmax

        # Service mode intentionally permits travel outside saved Near/Far limits
        # for calibration and battery-change work. Normal operation always uses
        # the predictive hard-limit envelope and programmed ramp zones.
        if not service:
            vel = self._hard_limit_velocity(float(self.state.pos_m), vel)
        self._send_velocity(vel)

    # --- Free-D ---
    def _start_freed_input(self):
        self._freed_in_stop.set()
        try:
            if self._freed_in_sock: self._freed_in_sock.close()
        except Exception: pass
        self._freed_in_sock=None
        if not self.freed_input_enabled: return
        self._freed_in_stop=threading.Event()
        try:
            sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            sock.bind((self.freed_input_bind_ip,self.freed_input_port)); sock.settimeout(.25); self._freed_in_sock=sock
            threading.Thread(target=self._freed_input_worker,args=(sock,),daemon=True).start()
        except Exception as exc: self._log(f"[Free-D] input bind failed: {exc}")

    def _freed_input_worker(self,sock):
        while not self._freed_in_stop.is_set():
            try: data,addr=sock.recvfrom(2048)
            except socket.timeout: continue
            except OSError: break
            if not data or len(data)<29 or data[0]!=0xD1: continue
            now=time.time(); raw_pan=_s24_to_int(data[2:5]); raw_tilt=_s24_to_int(data[5:8]); raw_roll=_s24_to_int(data[8:11])
            rz=_u24_to_int(data[20:23]); rf=_u24_to_int(data[23:26])
            zoom_dec = self._decode_lens(rz)
            focus_dec = self._decode_lens(rf)
            self._remember_lens_auto("zoom", zoom_dec)
            self._remember_lens_auto("focus", focus_dec)
            with self._lock:
                self.freed_in_raw={"Cam ID":int(data[1]),"Pan":raw_pan,"Tilt":raw_tilt,"Roll":raw_roll,"Zoom":rz,"Focus":rf}
                self.freed_in={"Cam ID":int(data[1]),"Pan":raw_pan/32768.0,"Tilt":raw_tilt/32768.0,"Roll":raw_roll/32768.0,"Zoom":zoom_dec,"Focus":focus_dec}
                self.freed_input_last_rx=now; self._freed_in_times.append(now)
                recent=[t for t in self._freed_in_times if t>=now-1]
                self.freed_in_fps=(len(recent)-1)/(recent[-1]-recent[0]) if len(recent)>1 and recent[-1]>recent[0] else float(len(recent))

    @staticmethod
    def _decode_lens_for_type(u24, lens_type: str):
        t = str(lens_type).lower()
        u24 = int(u24) & 0xFFFFFF
        if t == "u24": return u24
        if t == "u16": return u24 & 0xffff
        if t == "i16":
            v = u24 & 0xffff
            return v - 0x10000 if v & 0x8000 else v
        return u24 - 0x1000000 if u24 & 0x800000 else u24

    def _input_sign(self, name: str, inverts=None) -> int:
        # Preserve the proven v26.06.26.25 native Focus correction while
        # keeping the visible user Invert checkbox OFF by default.
        native = -1 if str(name).strip().lower() == "focus" else 1
        inv = self.freed_input_inverts if inverts is None else dict(inverts)
        user = -1 if bool(inv.get(str(name), False)) else 1
        return native * user

    def _output_sign(self, name: str, inverts=None) -> int:
        inv = self.freed_output_inverts if inverts is None else dict(inverts)
        return -1 if bool(inv.get(str(name), False)) else 1

    def _decode_lens(self, u24):
        return self._decode_lens_for_type(u24, self.freed_lens_type)

    @staticmethod
    def _normalised_geometry(geometry):
        """Return sorted, de-duplicated geometry points with numeric X/Y/Z values."""
        pts = []
        for raw in list(geometry or []):
            if not isinstance(raw, dict):
                continue
            try:
                x = float(raw.get("x", 0.0))
                y = float(raw.get("y", 0.0))
            except Exception:
                continue
            z_raw = raw.get("z", None)
            try:
                z = None if z_raw is None else float(z_raw)
            except Exception:
                z = None
            pts.append({"x": x, "y": y, "z": z, "name": str(raw.get("name", ""))})
        pts.sort(key=lambda p: p["x"])
        dedup = []
        for point in pts:
            if dedup and abs(point["x"] - dedup[-1]["x"]) < 1e-9:
                dedup[-1] = point
            else:
                dedup.append(point)
        return dedup

    @classmethod
    def _smooth_geometry_y(cls, x, geometry):
        """Smooth C1 reference-height interpolation through P1..P5.

        The geometry points are operator-entered reference heights, not straight
        cable segments.  A cubic Hermite interpolation creates a smooth reference
        profile, then the physical whole-span sag model is applied separately.
        """
        pts = cls._normalised_geometry(geometry)
        if not pts:
            return 0.0
        if len(pts) == 1:
            return float(pts[0]["y"])
        xv = float(x)
        if xv <= pts[0]["x"]:
            return float(pts[0]["y"])
        if xv >= pts[-1]["x"]:
            return float(pts[-1]["y"])

        # Finite-difference tangents for a smooth, continuous curve.
        slopes = []
        for i, p in enumerate(pts):
            if i == 0:
                dx = max(1e-9, pts[1]["x"] - p["x"])
                slopes.append((pts[1]["y"] - p["y"]) / dx)
            elif i == len(pts) - 1:
                dx = max(1e-9, p["x"] - pts[i-1]["x"])
                slopes.append((p["y"] - pts[i-1]["y"]) / dx)
            else:
                dx = max(1e-9, pts[i+1]["x"] - pts[i-1]["x"])
                slopes.append((pts[i+1]["y"] - pts[i-1]["y"]) / dx)

        for i in range(len(pts) - 1):
            p0, p1 = pts[i], pts[i+1]
            if p0["x"] <= xv <= p1["x"]:
                h = max(1e-9, p1["x"] - p0["x"])
                t = max(0.0, min(1.0, (xv - p0["x"]) / h))
                t2, t3 = t*t, t*t*t
                h00 = 2*t3 - 3*t2 + 1
                h10 = t3 - 2*t2 + t
                h01 = -2*t3 + 3*t2
                h11 = t3 - t2
                return (h00*p0["y"] + h10*h*slopes[i] +
                        h01*p1["y"] + h11*h*slopes[i+1])
        return float(pts[-1]["y"])

    @classmethod
    def _geometry_z(cls, x, geometry):
        """Top-view Z uses only P1 and P5, with P2..P4 lying on that line."""
        pts = cls._normalised_geometry(geometry)
        if not pts:
            return 0.0
        p0, p1 = pts[0], pts[-1]
        z0 = float(p0["z"] or 0.0)
        z1 = float(p1["z"] or 0.0)
        span = max(1e-9, p1["x"] - p0["x"])
        t = max(0.0, min(1.0, (float(x) - p0["x"]) / span))
        return z0 + (z1-z0)*t

    def _cable_y_at(self, x, geometry, cable_weight, tension, skate_weight, highline, skate_x):
        """Physical side-view cable height at X.

        The single canonical sag model deliberately uses *all four* operator
        inputs from the Free-D Geometry card:
          - Skate Weight: suspended camera/skate package mass.
          - Cable Weight: kg per 100 m, per individual highline cable.
          - Cable Tension: kgf, per individual highline cable (legacy SRVR rule).
          - Highline Mode: Single carries all Skate Weight; Dual shares it 50/50.

        Cable self-weight is represented by the standard small-sag parabolic
        horizontal-tension approximation.  The skate is a moving point load.
        With kg mass values and kgf tension, gravitational acceleration cancels
        in the load/tension ratio.  The result is subtracted from the smooth
        operator-entered P1..P5 reference-height profile.

        This exact function is used by both Run/Free-D Side View and by Free-D Y,
        so the visual arc and transmitted sag value cannot use different models.
        """
        pts = self._normalised_geometry(geometry)
        if len(pts) < 2:
            return self._smooth_geometry_y(x, pts)
        support0, support1 = pts[0]["x"], pts[-1]["x"]
        span = max(0.1, support1-support0)
        xv = max(support0, min(support1, float(x)))
        rel_x = xv-support0
        left = rel_x
        right = span-rel_x

        rope_kg_m = max(0.0, float(cable_weight))/100.0
        # Cable weight and cable tension are entered per individual highline.
        # Dual Highline therefore does not halve the self-weight/tension ratio of
        # either cable; it only shares the suspended skate package between them.
        tension_per_line = max(0.01, float(tension))
        line_count = 2.0 if str(highline).strip().lower().startswith("dual") else 1.0
        skate_per_line = max(0.0, float(skate_weight)) / line_count

        # Uniform cable load: continuous parabola with zero drop at both ends.
        cable_drop = (rope_kg_m * left * right) / (2.0 * tension_per_line)

        # Point load at the LIVE skate position.  This is piecewise-linear in
        # horizontal-tension approximation and remains continuous at the skate.
        a = max(0.0, min(span, float(skate_x)-support0))
        if rel_x <= a:
            point_drop = (skate_per_line * rel_x * (span-a)) / (tension_per_line * span)
        else:
            point_drop = (skate_per_line * a * (span-rel_x)) / (tension_per_line * span)

        return self._smooth_geometry_y(xv, pts) - max(0.0, cable_drop + point_drop)

    def _cable_profile(self, snap=None, samples=121):
        """Return the single canonical cable profile used by Run and Free-D."""
        cfg = snap if isinstance(snap, dict) else None
        geometry = [dict(p) for p in (cfg.get("geometry", self.geometry) if cfg else self.geometry)]
        cable_weight = float(cfg.get("cable_weight_kg100m", self.cable_weight_kg100m) if cfg else self.cable_weight_kg100m)
        tension = float(cfg.get("cable_tension_kg", self.cable_tension_kg) if cfg else self.cable_tension_kg)
        skate_weight = float(cfg.get("skate_weight_kg", cfg.get("static_weight_kg", self.skate_weight_kg)) if cfg else self.skate_weight_kg)
        highline = str(cfg.get("highline_mode", self.highline_mode) if cfg else self.highline_mode)
        pts = self._normalised_geometry(geometry)
        if len(pts) < 2:
            return []
        x0, x1 = pts[0]["x"], pts[-1]["x"]
        span = max(0.1, x1-x0)
        skate_x = float(self.state.pos_m or 0.0) - float(self.state.near_limit.position_m or 0.0)
        count = max(16, int(samples))
        result = []
        for i in range(count):
            x = x0 + span * i / max(1, count-1)
            result.append({
                "x": float(x),
                "y": float(self._cable_y_at(x, pts, cable_weight, tension, skate_weight, highline, skate_x)),
                "z": float(self._geometry_z(x, pts)),
            })
        return result

    def _xyz(self, snap=None):
        """Calculate Free-D X/Y/Z from the same physical profile shown in the UI."""
        cfg = snap if isinstance(snap, dict) else None
        geometry = [dict(p) for p in (cfg.get("geometry", self.geometry) if cfg else self.geometry)]
        output_offsets = dict(cfg.get("output_offsets", self.freed_output_offsets) if cfg else self.freed_output_offsets)
        cable_weight = float(cfg.get("cable_weight_kg100m", self.cable_weight_kg100m) if cfg else self.cable_weight_kg100m)
        tension = float(cfg.get("cable_tension_kg", self.cable_tension_kg) if cfg else self.cable_tension_kg)
        skate_weight = float(cfg.get("skate_weight_kg", cfg.get("static_weight_kg", self.skate_weight_kg)) if cfg else self.skate_weight_kg)
        highline = str(cfg.get("highline_mode", self.highline_mode) if cfg else self.highline_mode)

        x = float(self.state.pos_m or 0.0) - float(self.state.near_limit.position_m or 0.0)
        pts = self._normalised_geometry(geometry)
        if len(pts) >= 2:
            x = max(pts[0]["x"], min(pts[-1]["x"], x))
        y = self._cable_y_at(x, pts, cable_weight, tension, skate_weight, highline, x)
        z = self._geometry_z(x, pts)
        return (
            x + float(output_offsets.get("X",0.0)),
            y + float(output_offsets.get("Y",0.0)),
            z + float(output_offsets.get("Z",0.0)),
        )

    def _send_freed(self):
        # The Free-D page has explicit Apply/Reset controls. Network output uses
        # the last-applied snapshot so staged edits cannot alter the live packet
        # stream until Apply is pressed.
        applied = dict(getattr(self, "_saved_freed_snapshot", {}) or self._freed_snapshot())
        if not bool(applied.get("output_enabled", self.freed_output_enabled)):
            return
        now = time.perf_counter()
        hz = max(1.0, min(100.0, float(applied.get("rate_hz", self.freed_rate_hz))))
        if now-self._last_freed_tx < 1.0/hz:
            return
        self._last_freed_tx = now
        x,y,z = self._xyz(applied)
        raw = self.freed_in_raw
        in_offsets = dict(applied.get("input_offsets", self.freed_input_offsets))
        in_inverts = dict(applied.get("input_inverts", self.freed_input_inverts))
        out_inverts = dict(applied.get("output_inverts", self.freed_output_inverts))
        lens_type = str(applied.get("lens_type", self.freed_lens_type))

        pan = float(self.freed_in.get("Pan",0.0)) * self._input_sign("Pan", in_inverts) + float(in_offsets.get("Pan",0.0))
        tilt = float(self.freed_in.get("Tilt",0.0)) * self._input_sign("Tilt", in_inverts) + float(in_offsets.get("Tilt",0.0))
        roll = float(self.freed_in.get("Roll",0.0)) * self._input_sign("Roll", in_inverts) + float(in_offsets.get("Roll",0.0))
        zoom_dec = self._decode_lens_for_type(int(raw.get("Zoom",0)), lens_type)
        focus_dec = self._decode_lens_for_type(int(raw.get("Focus",0)), lens_type)
        zoom = int(zoom_dec) * self._input_sign("Zoom", in_inverts)
        focus = int(focus_dec) * self._input_sign("Focus", in_inverts)
        ox = float(x) * self._output_sign("X", out_inverts)
        oy = float(y) * self._output_sign("Y", out_inverts)
        oz = float(z) * self._output_sign("Z", out_inverts)
        pos_scale = max(1.0, float(applied.get("pos_scale", self.freed_pos_scale)))
        payload = bytearray((0xD1, max(0,min(255,int(raw.get("Cam ID",1))))))
        for v in (pan,tilt,roll): payload.extend(_s24be(round(float(v)*32768)))
        for v in (ox,oy,oz): payload.extend(_s24be(round(float(v)*pos_scale)))
        payload.extend(_s24be(int(zoom))); payload.extend(_s24be(int(focus))); payload.extend(b"\x00\x00")
        payload.append((0x40-sum(payload[:28]))&0xff)
        try:
            self._freed_sock.sendto(bytes(payload),(str(applied.get("target_ip",self.freed_target_ip)), int(applied.get("target_port",self.freed_target_port))))
        except Exception:
            return
        t=time.perf_counter(); self._freed_out_times.append(t); recent=[q for q in self._freed_out_times if q>=t-1]
        self.freed_out_fps=(len(recent)-1)/(recent[-1]-recent[0]) if len(recent)>1 and recent[-1]>recent[0] else float(len(recent))

    # --- timer/state ---
    def _tick(self):
        try:
            for _ in range(100):
                try: self._parse_w1p(self._w1p_rx.get_nowait())
                except queue.Empty: break
            self._motion_tick(); self._send_freed(); self.stateChanged.emit()
        except Exception as exc: self._log(f"[SRVR] tick: {exc}")

    # --- config ---
    @staticmethod
    def _normalise_list(value, default, length):
        out = list(value) if isinstance(value, list) else list(default)
        if len(out) < length:
            out.extend(list(default)[len(out):length])
        return out[:length]

    def _normalise_drive_modes(self, modes):
        defaults = [
            {"name":"Mode 1", "max_speed_mps":25.0, "goto_speed_mps":7.5, "accel_mps2":5.0, "decel_mps2":5.0, "crossover_mps2":10.0, "stop_decel_mps2":7.5},
            {"name":"Mode 2", "max_speed_mps":25.0, "goto_speed_mps":7.5, "accel_mps2":5.0, "decel_mps2":5.0, "crossover_mps2":10.0, "stop_decel_mps2":7.5},
        ]
        src = modes if isinstance(modes, list) else []
        out = []
        for i in range(2):
            d = defaults[i].copy()
            if i < len(src) and isinstance(src[i], dict):
                d.update(src[i])
                # Migrate the early Qt Quick test key.
                if "max_speed" in src[i] and "max_speed_mps" not in src[i]:
                    d["max_speed_mps"] = src[i]["max_speed"]
            d["name"] = str(d.get("name") or f"Mode {i+1}")
            for key in ("max_speed_mps","goto_speed_mps","accel_mps2","decel_mps2","crossover_mps2","stop_decel_mps2"):
                try: d[key] = max(0.01, float(d[key]))
                except Exception: d[key] = defaults[i][key]
            out.append(d)
        return out

    def _apply_active_drive_profile(self, sync=True):
        self.active_drive_mode = 0 if int(self.active_drive_mode) <= 0 else 1
        m = self.drive_modes[self.active_drive_mode]
        self.max_speed_mps = float(m["max_speed_mps"])
        self.goto_speed_mps = min(float(m["goto_speed_mps"]), self.max_speed_mps)
        self.max_accel_mps2 = float(m["accel_mps2"])
        self.max_decel_mps2 = float(m["decel_mps2"])
        self.max_crossover_mps2 = float(m["crossover_mps2"])
        self.max_stop_decel_mps2 = float(m["stop_decel_mps2"])
        if sync:
            self._sync_w1p_settings()

    @staticmethod
    def _kg_to_lb(value: float) -> float:
        return float(value) * 2.2046226218487757

    @staticmethod
    def _lb_to_kg(value: float) -> float:
        return float(value) / 2.2046226218487757

    def _freed_snapshot(self) -> dict:
        """Return the complete editable Free-D configuration in canonical form."""
        return {
            "input_enabled": bool(self.freed_input_enabled),
            "input_bind_ip": str(self.freed_input_bind_ip),
            "input_port": int(self.freed_input_port),
            "input_offsets": dict(self.freed_input_offsets),
            "input_inverts": dict(self.freed_input_inverts),
            "output_enabled": bool(self.freed_output_enabled),
            "target_ip": str(self.freed_target_ip),
            "target_port": int(self.freed_target_port),
            "rate_hz": float(self.freed_rate_hz),
            "output_offsets": dict(self.freed_output_offsets),
            "output_inverts": dict(self.freed_output_inverts),
            "pos_scale": float(self.freed_pos_scale),
            "lens_type": str(self.freed_lens_type),
            "lens_scale_mode": str(self.freed_lens_scale_mode),
            "lens_cal": dict(self.freed_lens_cal),
            "lens_auto_seen": dict(self._freed_lens_auto_seen),
            "geometry": [dict(p) for p in self.geometry],
            "skate_weight_kg": float(self.skate_weight_kg),
            "static_weight_kg": float(self.skate_weight_kg),  # legacy config compatibility
            "cable_weight_kg100m": float(self.cable_weight_kg100m),
            "cable_tension_kg": float(self.cable_tension_kg),
            "skate_weight_unit": str(self.skate_weight_unit),
            "static_weight_unit": str(self.skate_weight_unit),  # legacy config compatibility
            "cable_weight_unit": str(self.cable_weight_unit),
            "cable_tension_unit": str(self.cable_tension_unit),
            "highline_mode": str(self.highline_mode),
        }

    def _restore_freed_snapshot(self, snap: dict) -> None:
        if not isinstance(snap, dict):
            return
        self.freed_input_enabled = bool(snap.get("input_enabled", self.freed_input_enabled))
        self.freed_input_bind_ip = str(snap.get("input_bind_ip", self.freed_input_bind_ip))
        self.freed_input_port = max(1, min(65535, int(snap.get("input_port", self.freed_input_port))))
        self.freed_input_offsets = {k: float(v) for k, v in dict(snap.get("input_offsets", self.freed_input_offsets)).items() if k in ("Pan","Tilt","Roll")}
        for k in ("Pan","Tilt","Roll"):
            self.freed_input_offsets.setdefault(k, 0.0)
        self.freed_input_inverts = {k: bool(v) for k, v in dict(snap.get("input_inverts", self.freed_input_inverts)).items() if k in ("Pan","Tilt","Roll","Zoom","Focus")}
        for k in ("Pan","Tilt","Roll","Zoom","Focus"):
            self.freed_input_inverts.setdefault(k, False)
        self.freed_output_enabled = bool(snap.get("output_enabled", self.freed_output_enabled))
        self.freed_target_ip = str(snap.get("target_ip", self.freed_target_ip))
        self.freed_target_port = max(1, min(65535, int(snap.get("target_port", self.freed_target_port))))
        self.freed_rate_hz = max(1.0, min(100.0, float(snap.get("rate_hz", self.freed_rate_hz))))
        self.freed_output_offsets = {k: float(v) for k, v in dict(snap.get("output_offsets", self.freed_output_offsets)).items() if k in ("X","Y","Z")}
        for k in ("X","Y","Z"):
            self.freed_output_offsets.setdefault(k, 0.0)
        self.freed_output_inverts = {k: bool(v) for k, v in dict(snap.get("output_inverts", self.freed_output_inverts)).items() if k in ("X","Y","Z")}
        for k in ("X","Y","Z"):
            self.freed_output_inverts.setdefault(k, False)
        self.freed_pos_scale = max(1.0, float(snap.get("pos_scale", self.freed_pos_scale)))
        self.freed_lens_type = str(snap.get("lens_type", self.freed_lens_type)) if str(snap.get("lens_type", self.freed_lens_type)) in ("i16","u16","i24","u24") else "u16"
        self.freed_lens_scale_mode = self._normalise_lens_scale(snap.get("lens_scale_mode", self.freed_lens_scale_mode))
        cal = dict(snap.get("lens_cal", self.freed_lens_cal))
        for key in ("zoom_wide","zoom_tele","focus_near","focus_far"):
            try: self.freed_lens_cal[key] = float(cal.get(key, self.freed_lens_cal[key]))
            except Exception: pass
        seen = dict(snap.get("lens_auto_seen", self._freed_lens_auto_seen))
        self._freed_lens_auto_seen = {k: seen.get(k) for k in ("zoom_min","zoom_max","focus_min","focus_max")}
        geom = snap.get("geometry")
        if isinstance(geom, list) and len(geom) >= 5:
            self.geometry = [dict(geom[i]) for i in range(5)]
            for i, g in enumerate(self.geometry):
                g["name"] = str(g.get("name") or ("P1 (Near)" if i == 0 else "P5 (Far)" if i == 4 else f"P{i+1}"))
                g["x"] = float(g.get("x", i*25.0))
                g["y"] = float(g.get("y", 0.0))
                g["z"] = float(g.get("z", 0.0) or 0.0) if i in (0,4) else None
        self.skate_weight_kg = max(0.0, float(snap.get("skate_weight_kg", snap.get("static_weight_kg", self.skate_weight_kg))))
        self.cable_weight_kg100m = max(0.0, float(snap.get("cable_weight_kg100m", self.cable_weight_kg100m)))
        self.cable_tension_kg = max(0.01, float(snap.get("cable_tension_kg", self.cable_tension_kg)))
        self.skate_weight_unit = "lbs" if str(snap.get("skate_weight_unit", snap.get("static_weight_unit", self.skate_weight_unit))).lower().startswith("lb") else "kg"
        self.cable_weight_unit = "lbs/100m" if str(snap.get("cable_weight_unit", self.cable_weight_unit)).lower().startswith("lb") else "kg/100m"
        self.cable_tension_unit = "lbs" if str(snap.get("cable_tension_unit", self.cable_tension_unit)).lower().startswith("lb") else "kg"
        self.highline_mode = "Dual Highline" if str(snap.get("highline_mode", self.highline_mode)).lower().startswith("dual") else "Single Highline"

    @staticmethod
    def _normalise_lens_scale(value) -> str:
        text = str(value or "Auto").strip().lower()
        if text.startswith("full"):
            return "Full Scale"
        if text.startswith("manual"):
            return "Manual"
        return "Auto"

    def _lens_limits(self):
        t = str(self.freed_lens_type).lower()
        if t == "u16": return 0.0, 65535.0
        if t == "i16": return -32768.0, 32767.0
        if t == "u24": return 0.0, 16777215.0
        return -8388608.0, 8388607.0

    def _lens_percent(self, field: str, value: float) -> float:
        field = "zoom" if str(field).lower().startswith("zoom") else "focus"
        mode = str(self.freed_lens_scale_mode)
        if mode == "Full Scale":
            lo, hi = self._lens_limits()
        elif mode == "Auto":
            lo = self._freed_lens_auto_seen.get(field+"_min")
            hi = self._freed_lens_auto_seen.get(field+"_max")
            if lo is None or hi is None or abs(float(hi)-float(lo)) < 1e-9:
                lo = float(self.freed_lens_cal["zoom_wide" if field == "zoom" else "focus_near"])
                hi = float(self.freed_lens_cal["zoom_tele" if field == "zoom" else "focus_far"])
        else:
            lo = float(self.freed_lens_cal["zoom_wide" if field == "zoom" else "focus_near"])
            hi = float(self.freed_lens_cal["zoom_tele" if field == "zoom" else "focus_far"])
        if abs(float(hi)-float(lo)) < 1e-9:
            return 0.0
        return max(0.0, min(100.0, (float(value)-float(lo)) * 100.0 / (float(hi)-float(lo))))

    def _remember_lens_auto(self, field: str, value: float) -> None:
        field = "zoom" if str(field).lower().startswith("zoom") else "focus"
        v = float(value)
        mn, mx = field+"_min", field+"_max"
        old_min, old_max = self._freed_lens_auto_seen.get(mn), self._freed_lens_auto_seen.get(mx)
        self._freed_lens_auto_seen[mn] = v if old_min is None else min(float(old_min), v)
        self._freed_lens_auto_seen[mx] = v if old_max is None else max(float(old_max), v)

    def _setup_snapshot(self) -> dict:
        return {
            "ctrl_ip": str(self.ctrl_ip),
            "w1p_ip": str(self.w1p_ip),
            "reverse_joystick": bool(self.reverse_joystick),
            "reverse_motor": bool(self.reverse_motor),
            "joystick_deadband_pct": float(self.joystick_deadband_pct),
            "joystick_calibration": {
                "left": float(self.joystick_cal_left),
                "centre": float(self.joystick_cal_centre),
                "right": float(self.joystick_cal_right),
            },
            "position_source": str(self.position_source),
            "units_per_m": float(self.winch_units_per_m),
            "drive_modes": [dict(x) for x in self.drive_modes],
            "active_drive_mode": int(self.active_drive_mode),
            "acceleration_mode": str(self.acceleration_mode),
            "battery_change_mode": bool(self.battery_change_mode),
            "ctrl_aux_assignments": list(self.ctrl_aux_assignments),
            "w1p_aux_assignments": list(self.w1p_aux_assignments),
        }

    def _restore_setup_snapshot(self, snap: dict) -> None:
        self.ctrl_ip = str(snap.get("ctrl_ip", self.ctrl_ip))
        self.w1p_ip = str(snap.get("w1p_ip", self.w1p_ip))
        self.reverse_joystick = bool(snap.get("reverse_joystick", self.reverse_joystick))
        self.reverse_motor = bool(snap.get("reverse_motor", self.reverse_motor))
        self.joystick_deadband_pct = max(0.0, min(25.0, float(snap.get("joystick_deadband_pct", self.joystick_deadband_pct))))
        joy_cal = snap.get("joystick_calibration", {}) if isinstance(snap.get("joystick_calibration", {}), dict) else {}
        try:
            left = float(joy_cal.get("left", self.joystick_cal_left))
            centre = float(joy_cal.get("centre", self.joystick_cal_centre))
            right = float(joy_cal.get("right", self.joystick_cal_right))
            if abs(left-centre) >= 0.05 and abs(right-centre) >= 0.05 and (left-centre)*(right-centre) < 0.0:
                self.joystick_cal_left, self.joystick_cal_centre, self.joystick_cal_right = left, centre, right
        except Exception:
            pass
        self.position_source = "Encoder"
        self.winch_units_per_m = max(1.0, float(snap.get("units_per_m", self.winch_units_per_m)))
        self.drive_modes = self._normalise_drive_modes(snap.get("drive_modes", self.drive_modes))
        self.active_drive_mode = 0 if int(snap.get("active_drive_mode", self.active_drive_mode)) <= 0 else 1
        self.acceleration_mode = "Power" if str(snap.get("acceleration_mode", self.acceleration_mode)).lower().startswith("power") else "Speed"
        self.battery_change_mode = bool(snap.get("battery_change_mode", self.battery_change_mode))
        self.ctrl_aux_assignments = [str(x) for x in self._normalise_list(snap.get("ctrl_aux_assignments"), self.ctrl_aux_assignments, 5)]
        self.w1p_aux_assignments = [str(x) for x in self._normalise_list(snap.get("w1p_aux_assignments"), self.w1p_aux_assignments, 5)]
        self._apply_active_drive_profile(sync=False)
        self._ctrl_rx_times.clear()
        self.w1p.reconfigure(self.w1p_ip, self.w1p_port)
        if not self.smoke_test:
            self._sync_w1p_settings()
            self._sync_service_mode_to_winch(force=True)

    def _setup_snapshot_from_config(self, c: dict) -> dict:
        """Normalise a transferable config into a Setup draft without applying it."""
        snap = self._setup_snapshot()
        if not isinstance(c, dict):
            return snap
        snap["ctrl_ip"] = str(c.get("ctrl_ip", snap["ctrl_ip"]) or snap["ctrl_ip"])
        snap["w1p_ip"] = str(c.get("w1p_ip", snap["w1p_ip"]) or snap["w1p_ip"])
        snap["reverse_joystick"] = bool(c.get("reverse_joystick", snap["reverse_joystick"]))
        snap["reverse_motor"] = bool(c.get("reverse_motor", snap["reverse_motor"]))
        try: snap["joystick_deadband_pct"] = max(0.0, min(25.0, float(c.get("joystick_deadband_pct", snap["joystick_deadband_pct"]))))
        except Exception: pass
        joy = c.get("joystick_calibration") if isinstance(c.get("joystick_calibration"), dict) else {}
        if joy:
            try:
                left = float(joy.get("left", snap["joystick_calibration"]["left"]))
                centre = float(joy.get("centre", snap["joystick_calibration"]["centre"]))
                right = float(joy.get("right", snap["joystick_calibration"]["right"]))
                if abs(left-centre) >= 0.05 and abs(right-centre) >= 0.05 and (left-centre)*(right-centre) < 0.0:
                    snap["joystick_calibration"] = {"left":left, "centre":centre, "right":right}
            except Exception:
                pass
        snap["position_source"] = "Encoder"
        try: snap["units_per_m"] = max(1.0, float(c.get("units_per_m", snap["units_per_m"])))
        except Exception: pass
        snap["drive_modes"] = self._normalise_drive_modes(c.get("drive_modes", snap["drive_modes"]))
        try: snap["active_drive_mode"] = 0 if int(c.get("active_drive_mode", snap["active_drive_mode"])) <= 0 else 1
        except Exception: snap["active_drive_mode"] = 0
        snap["acceleration_mode"] = "Power" if str(c.get("acceleration_mode", snap["acceleration_mode"])).lower().startswith("power") else "Speed"
        snap["battery_change_mode"] = bool(c.get("battery_change_mode", snap["battery_change_mode"]))
        snap["ctrl_aux_assignments"] = [str(x) for x in self._normalise_list(c.get("ctrl_aux_assignments"), snap["ctrl_aux_assignments"], 5)]
        snap["w1p_aux_assignments"] = [str(x) for x in self._normalise_list(c.get("w1p_aux_assignments"), snap["w1p_aux_assignments"], 5)]
        return snap

    def _freed_snapshot_from_config(self, c: dict) -> dict:
        """Normalise a transferable config into a Free-D draft without applying it."""
        snap = self._freed_snapshot()
        if not isinstance(c, dict):
            return snap
        fd = c.get("free_d") if isinstance(c.get("free_d"), dict) else {}
        snap["input_enabled"] = bool(fd.get("input_enabled", snap["input_enabled"]))
        snap["input_bind_ip"] = str(fd.get("input_bind_ip", snap["input_bind_ip"]))
        try: snap["input_port"] = max(1, min(65535, int(fd.get("input_port", snap["input_port"]))))
        except Exception: pass
        snap["output_enabled"] = bool(fd.get("output_enabled", snap["output_enabled"]))
        snap["target_ip"] = str(fd.get("target_ip", snap["target_ip"]))
        try: snap["target_port"] = max(1, min(65535, int(fd.get("target_port", snap["target_port"]))))
        except Exception: pass
        try: snap["rate_hz"] = max(1.0, min(100.0, float(fd.get("rate_hz", snap["rate_hz"]))))
        except Exception: pass
        try: snap["pos_scale"] = max(1.0, float(fd.get("pos_scale", snap["pos_scale"])))
        except Exception: pass
        for src_key, axes in (("input_offsets", ("Pan","Tilt","Roll")), ("output_offsets", ("X","Y","Z"))):
            vals = fd.get(src_key) if isinstance(fd.get(src_key), dict) else {}
            for key in axes:
                try: snap[src_key][key] = float(vals.get(key, snap[src_key][key]))
                except Exception: pass
        for src_key, axes in (("input_inverts", ("Pan","Tilt","Roll","Zoom","Focus")), ("output_inverts", ("X","Y","Z"))):
            vals = fd.get(src_key) if isinstance(fd.get(src_key), dict) else {}
            for key in axes:
                snap[src_key][key] = bool(vals.get(key, snap[src_key][key]))
        lt = str(fd.get("lens_type", snap["lens_type"]))
        snap["lens_type"] = lt if lt in ("i16","u16","i24","u24") else "u16"
        snap["lens_scale_mode"] = self._normalise_lens_scale(fd.get("lens_scale_mode", snap["lens_scale_mode"]))
        cal = fd.get("lens_cal") if isinstance(fd.get("lens_cal"), dict) else {}
        for key in ("zoom_wide","zoom_tele","focus_near","focus_far"):
            try: snap["lens_cal"][key] = float(cal.get(key, snap["lens_cal"][key]))
            except Exception: pass
        seen = fd.get("lens_auto_seen") if isinstance(fd.get("lens_auto_seen"), dict) else {}
        for key in ("zoom_min","zoom_max","focus_min","focus_max"):
            if key in seen: snap["lens_auto_seen"][key] = seen.get(key)
        geom = c.get("geometry") if isinstance(c.get("geometry"), list) else snap["geometry"]
        if len(geom) >= 5:
            out = []
            for i in range(5):
                src = geom[i] if isinstance(geom[i], dict) else snap["geometry"][i]
                d = dict(snap["geometry"][i]); d.update(src)
                d["name"] = str(d.get("name") or ("P1 (Near)" if i == 0 else "P5 (Far)" if i == 4 else f"P{i+1}"))
                try: d["x"] = float(d.get("x", i*25.0))
                except Exception: d["x"] = float(i*25.0)
                try: d["y"] = float(d.get("y", 0.0))
                except Exception: d["y"] = 0.0
                if i in (0,4):
                    try: d["z"] = float(d.get("z", 0.0) or 0.0)
                    except Exception: d["z"] = 0.0
                else: d["z"] = None
                out.append(d)
            snap["geometry"] = out
        try: snap["skate_weight_kg"] = max(0.0, float(fd.get("skate_weight_kg", fd.get("static_weight_kg", snap["skate_weight_kg"]))))
        except Exception: pass
        try: snap["cable_weight_kg100m"] = max(0.0, float(fd.get("cable_weight_kg100m", snap["cable_weight_kg100m"])))
        except Exception: pass
        try: snap["cable_tension_kg"] = max(0.01, float(fd.get("cable_tension_kg", snap["cable_tension_kg"])))
        except Exception: pass
        snap["skate_weight_unit"] = "lbs" if str(fd.get("skate_weight_unit", fd.get("static_weight_unit", snap["skate_weight_unit"]))).lower().startswith("lb") else "kg"
        snap["cable_weight_unit"] = "lbs/100m" if str(fd.get("cable_weight_unit", snap["cable_weight_unit"])).lower().startswith("lb") else "kg/100m"
        snap["cable_tension_unit"] = "lbs" if str(fd.get("cable_tension_unit", snap["cable_tension_unit"])).lower().startswith("lb") else "kg"
        snap["highline_mode"] = "Dual Highline" if str(fd.get("highline_mode", snap["highline_mode"])).lower().startswith("dual") else "Single Highline"
        return snap

    @staticmethod
    def _dialog_path(value) -> Path:
        text = str(value or "").strip()
        if text.startswith("file:"):
            parsed = urlparse(text)
            text = unquote(parsed.path)
        return Path(text).expanduser()

    def _apply_imported_run_config(self, c: dict) -> None:
        """Apply transferable Run-only values when Setup Apply is pressed."""
        if not isinstance(c, dict):
            return
        default_names = [f"P{i}" for i in range(1,11)]
        if "preset_names" in c:
            self.preset_names = [str(x or default_names[i]) for i,x in enumerate(self._normalise_list(c.get("preset_names"), default_names, 10))]
        if "preset_positions" in c:
            raw_pos = self._normalise_list(c.get("preset_positions"), [None]*10, 10)
            vals = []
            for v in raw_pos:
                try: vals.append(None if v is None else float(v))
                except Exception: vals.append(None)
            self.preset_positions = vals
        if "preset_visible" in c:
            self.preset_visible = [bool(x) for x in self._normalise_list(c.get("preset_visible"), [True]*10, 10)]
        lim = c.get("limits") if isinstance(c.get("limits"), dict) else None
        if lim is not None:
            try: self.state.near_limit.position_m = float(lim.get("near", self.state.near_limit.position_m or 0.0))
            except Exception: pass
            try: self.state.far_limit.position_m = float(lim.get("far", self.state.far_limit.position_m or 100.0))
            except Exception: pass
            try: self.state.ref_point.position_m = float(lim.get("ref", self.state.ref_point.position_m or 50.0))
            except Exception: pass
            raw = lim.get("raw") if isinstance(lim.get("raw"), dict) else {}
            for key in ("near","ref","far"):
                if key in raw:
                    try: self._limit_raw[key] = None if raw.get(key) is None else int(raw.get(key))
                    except Exception: self._limit_raw[key] = None
            for lp,key in ((self.state.near_limit,"nearRamp"),(self.state.far_limit,"farRamp")):
                r = lim.get(key) if isinstance(lim.get(key), dict) else None
                if r is None: continue
                lp.ramp_mode = "Percentage" if str(r.get("mode", lp.ramp_mode)).lower().startswith("percent") else "Distance"
                try: lp.ramp_distance_m = max(0.0, float(r.get("distance", lp.ramp_distance_m)))
                except Exception: pass
                try: lp.ramp_percentage = max(0.0, min(100.0, float(r.get("percentage", lp.ramp_percentage))))
                except Exception: pass

    def _finish_pending_import_if_handled(self) -> None:
        if self._pending_import_setup_handled and self._pending_import_freed_handled:
            self._pending_import_config = None

    def _load_config(self):
        try:
            if not self._config_path.exists():
                self._apply_active_drive_profile(sync=False)
                return
            c = json.loads(self._config_path.read_text())
            if not isinstance(c, dict):
                raise ValueError("config root must be an object")

            self.ctrl_ip = str(c.get("ctrl_ip", self.ctrl_ip) or self.ctrl_ip)
            self.w1p_ip = str(c.get("w1p_ip", self.w1p_ip) or self.w1p_ip)
            self.reverse_joystick = bool(c.get("reverse_joystick", self.reverse_joystick))
            self.reverse_motor = bool(c.get("reverse_motor", self.reverse_motor))
            self.joystick_deadband_pct = max(0.0, min(25.0, float(c.get("joystick_deadband_pct", self.joystick_deadband_pct))))
            joy_cal = c.get("joystick_calibration", {}) if isinstance(c.get("joystick_calibration", {}), dict) else {}
            try:
                left = float(joy_cal.get("left", self.joystick_cal_left))
                centre = float(joy_cal.get("centre", self.joystick_cal_centre))
                right = float(joy_cal.get("right", self.joystick_cal_right))
                if abs(left-centre) >= 0.05 and abs(right-centre) >= 0.05 and (left-centre)*(right-centre) < 0.0:
                    self.joystick_cal_left, self.joystick_cal_centre, self.joystick_cal_right = left, centre, right
            except Exception:
                pass
            # Encoder is the currently proven position source. Persist the field
            # for the locked Setup control without inventing an unverified source.
            self.position_source = "Encoder"
            self.ctrl_aux_assignments = [str(x) for x in self._normalise_list(c.get("ctrl_aux_assignments"), self.ctrl_aux_assignments, 5)]
            self.w1p_aux_assignments = [str(x) for x in self._normalise_list(c.get("w1p_aux_assignments"), self.w1p_aux_assignments, 5)]
            self.winch_units_per_m = max(1.0, float(c.get("units_per_m", self.winch_units_per_m)))

            self.drive_modes = self._normalise_drive_modes(c.get("drive_modes"))
            try: self.active_drive_mode = 0 if int(c.get("active_drive_mode", 0)) <= 0 else 1
            except Exception: self.active_drive_mode = 0
            self.acceleration_mode = "Power" if str(c.get("acceleration_mode", "Speed")).lower().startswith("power") else "Speed"
            self.battery_change_mode = bool(c.get("battery_change_mode", False))
            self._apply_active_drive_profile(sync=False)

            default_names = [f"P{i}" for i in range(1,11)]
            self.preset_names = [str(x or default_names[i]) for i,x in enumerate(self._normalise_list(c.get("preset_names"), default_names, 10))]
            raw_pos = self._normalise_list(c.get("preset_positions"), [None]*10, 10)
            self.preset_positions = []
            for v in raw_pos:
                try: self.preset_positions.append(None if v is None else float(v))
                except Exception: self.preset_positions.append(None)
            self.preset_visible = [bool(x) for x in self._normalise_list(c.get("preset_visible"), [True]*10, 10)]

            lim = c.get("limits", {}) if isinstance(c.get("limits", {}), dict) else {}
            self.state.near_limit.position_m = float(lim.get("near", 0.0))
            self.state.far_limit.position_m = float(lim.get("far", 100.0))
            self.state.ref_point.position_m = float(lim.get("ref", 50.0))
            raw = lim.get("raw", {}) if isinstance(lim.get("raw", {}), dict) else {}
            for key in ("near", "ref", "far"):
                try:
                    self._limit_raw[key] = None if raw.get(key) is None else int(raw.get(key))
                except Exception:
                    self._limit_raw[key] = None
            for lp,key in ((self.state.near_limit,"nearRamp"),(self.state.far_limit,"farRamp")):
                r = lim.get(key, {}) if isinstance(lim.get(key, {}), dict) else {}
                lp.ramp_mode = "Percentage" if str(r.get("mode", "Distance")).lower().startswith("percent") else "Distance"
                lp.ramp_distance_m = max(0.0, float(r.get("distance", 2.0)))
                lp.ramp_percentage = max(0.0, min(100.0, float(r.get("percentage", 10.0))))

            default_geometry = [
                {"name":"P1 (Near)","x":0.0,"y":0.0,"z":0.0},
                {"name":"P2","x":25.0,"y":5.0,"z":None},
                {"name":"P3","x":50.0,"y":8.0,"z":None},
                {"name":"P4","x":75.0,"y":5.0,"z":None},
                {"name":"P5 (Far)","x":100.0,"y":0.0,"z":0.0},
            ]
            g = c.get("geometry") if isinstance(c.get("geometry"), list) else default_geometry
            self.geometry = []
            for i in range(5):
                src = g[i] if i < len(g) and isinstance(g[i], dict) else default_geometry[i]
                d = default_geometry[i].copy(); d.update(src)
                d["name"] = str(d.get("name") or default_geometry[i]["name"])
                d["x"] = float(d.get("x", default_geometry[i]["x"]))
                d["y"] = float(d.get("y", default_geometry[i]["y"]))
                if i in (0,4): d["z"] = float(d.get("z", 0.0) or 0.0)
                else: d["z"] = None
                self.geometry.append(d)

            fd = c.get("free_d", {}) if isinstance(c.get("free_d", {}), dict) else {}
            self.freed_input_enabled = bool(fd.get("input_enabled", self.freed_input_enabled))
            self.freed_input_bind_ip = str(fd.get("input_bind_ip", self.freed_input_bind_ip))
            self.freed_input_port = max(1, min(65535, int(fd.get("input_port", self.freed_input_port))))
            self.freed_output_enabled = bool(fd.get("output_enabled", self.freed_output_enabled))
            self.freed_target_ip = str(fd.get("target_ip", self.freed_target_ip))
            self.freed_target_port = max(1, min(65535, int(fd.get("target_port", self.freed_target_port))))
            self.freed_rate_hz = max(1.0, min(100.0, float(fd.get("rate_hz", self.freed_rate_hz))))
            self.freed_pos_scale = max(1.0, float(fd.get("pos_scale", self.freed_pos_scale)))
            self.freed_input_offsets = {k: float(v) for k,v in dict(fd.get("input_offsets", self.freed_input_offsets)).items() if k in ("Pan","Tilt","Roll")}
            for k in ("Pan","Tilt","Roll"): self.freed_input_offsets.setdefault(k, 0.0)
            self.freed_input_inverts = {k: bool(v) for k,v in dict(fd.get("input_inverts", self.freed_input_inverts)).items() if k in ("Pan","Tilt","Roll","Zoom","Focus")}
            for k in ("Pan","Tilt","Roll","Zoom","Focus"): self.freed_input_inverts.setdefault(k, False)
            self.freed_output_offsets = {k: float(v) for k,v in dict(fd.get("output_offsets", self.freed_output_offsets)).items() if k in ("X","Y","Z")}
            for k in ("X","Y","Z"): self.freed_output_offsets.setdefault(k, 0.0)
            self.freed_output_inverts = {k: bool(v) for k,v in dict(fd.get("output_inverts", self.freed_output_inverts)).items() if k in ("X","Y","Z")}
            for k in ("X","Y","Z"): self.freed_output_inverts.setdefault(k, False)
            self.freed_lens_type = str(fd.get("lens_type", self.freed_lens_type)) if str(fd.get("lens_type", self.freed_lens_type)) in ("i16","u16","i24","u24") else "u16"
            self.freed_lens_scale_mode = self._normalise_lens_scale(fd.get("lens_scale_mode", self.freed_lens_scale_mode))
            lens_cal = dict(fd.get("lens_cal", self.freed_lens_cal))
            for key in ("zoom_wide","zoom_tele","focus_near","focus_far"):
                try: self.freed_lens_cal[key] = float(lens_cal.get(key, self.freed_lens_cal[key]))
                except Exception: pass
            seen = dict(fd.get("lens_auto_seen", self._freed_lens_auto_seen))
            self._freed_lens_auto_seen = {k: seen.get(k) for k in ("zoom_min","zoom_max","focus_min","focus_max")}
            self.skate_weight_kg = max(0.0, float(fd.get("skate_weight_kg", fd.get("static_weight_kg", self.skate_weight_kg))))
            self.cable_weight_kg100m = max(0.0, float(fd.get("cable_weight_kg100m", self.cable_weight_kg100m)))
            self.cable_tension_kg = max(0.01, float(fd.get("cable_tension_kg", self.cable_tension_kg)))
            self.skate_weight_unit = "lbs" if str(fd.get("skate_weight_unit", fd.get("static_weight_unit", self.skate_weight_unit))).lower().startswith("lb") else "kg"
            self.cable_weight_unit = "lbs/100m" if str(fd.get("cable_weight_unit", self.cable_weight_unit)).lower().startswith("lb") else "kg/100m"
            self.cable_tension_unit = "lbs" if str(fd.get("cable_tension_unit", self.cable_tension_unit)).lower().startswith("lb") else "kg"
            self.highline_mode = "Dual Highline" if str(fd.get("highline_mode", self.highline_mode)).lower().startswith("dual") else "Single Highline"
        except Exception as exc:
            self._log(f"[Config] load failed: {exc}")
            self.drive_modes = self._normalise_drive_modes(self.drive_modes)
            self._apply_active_drive_profile(sync=False)

    def _save_config(self, include_staged_freed: bool = False):
        try:
            # Free-D has explicit Apply/Reset semantics. Unrelated saves (preset,
            # drive mode, etc.) must not accidentally commit staged Free-D edits.
            if include_staged_freed or not hasattr(self, "_saved_freed_snapshot"):
                freed_snap = self._freed_snapshot()
            else:
                freed_snap = dict(self._saved_freed_snapshot)
            c = {
                "ctrl_ip": self.ctrl_ip,
                "w1p_ip": self.w1p_ip,
                "reverse_joystick": self.reverse_joystick,
                "reverse_motor": self.reverse_motor,
                "joystick_deadband_pct": self.joystick_deadband_pct,
                "joystick_calibration": {
                    "left": self.joystick_cal_left,
                    "centre": self.joystick_cal_centre,
                    "right": self.joystick_cal_right,
                },
                "position_source": self.position_source,
                "ctrl_aux_assignments": self.ctrl_aux_assignments,
                "w1p_aux_assignments": self.w1p_aux_assignments,
                "units_per_m": self.winch_units_per_m,
                "drive_modes": self.drive_modes,
                "active_drive_mode": self.active_drive_mode,
                "acceleration_mode": self.acceleration_mode,
                "battery_change_mode": self.battery_change_mode,
                "preset_names": self.preset_names,
                "preset_positions": self.preset_positions,
                "preset_visible": self.preset_visible,
                "limits": {
                    "near": self.state.near_limit.position_m,
                    "far": self.state.far_limit.position_m,
                    "ref": self.state.ref_point.position_m,
                    "raw": dict(self._limit_raw),
                    "nearRamp": {"mode":self.state.near_limit.ramp_mode,"distance":self.state.near_limit.ramp_distance_m,"percentage":self.state.near_limit.ramp_percentage},
                    "farRamp": {"mode":self.state.far_limit.ramp_mode,"distance":self.state.far_limit.ramp_distance_m,"percentage":self.state.far_limit.ramp_percentage},
                },
                "geometry": [dict(p) for p in freed_snap.get("geometry", self.geometry)],
                "free_d": {
                    "input_enabled": bool(freed_snap.get("input_enabled", self.freed_input_enabled)),
                    "input_bind_ip": str(freed_snap.get("input_bind_ip", self.freed_input_bind_ip)),
                    "input_port": int(freed_snap.get("input_port", self.freed_input_port)),
                    "output_enabled": bool(freed_snap.get("output_enabled", self.freed_output_enabled)),
                    "target_ip": str(freed_snap.get("target_ip", self.freed_target_ip)),
                    "target_port": int(freed_snap.get("target_port", self.freed_target_port)),
                    "rate_hz": float(freed_snap.get("rate_hz", self.freed_rate_hz)),
                    "pos_scale": float(freed_snap.get("pos_scale", self.freed_pos_scale)),
                    "input_offsets": dict(freed_snap.get("input_offsets", self.freed_input_offsets)),
                    "input_inverts": dict(freed_snap.get("input_inverts", self.freed_input_inverts)),
                    "output_offsets": dict(freed_snap.get("output_offsets", self.freed_output_offsets)),
                    "output_inverts": dict(freed_snap.get("output_inverts", self.freed_output_inverts)),
                    "lens_type": str(freed_snap.get("lens_type", self.freed_lens_type)),
                    "lens_scale_mode": str(freed_snap.get("lens_scale_mode", self.freed_lens_scale_mode)),
                    "lens_cal": dict(freed_snap.get("lens_cal", self.freed_lens_cal)),
                    "lens_auto_seen": dict(freed_snap.get("lens_auto_seen", self._freed_lens_auto_seen)),
                    "skate_weight_kg": float(freed_snap.get("skate_weight_kg", freed_snap.get("static_weight_kg", self.skate_weight_kg))),
                    "static_weight_kg": float(freed_snap.get("skate_weight_kg", freed_snap.get("static_weight_kg", self.skate_weight_kg))),  # legacy
                    "cable_weight_kg100m": float(freed_snap.get("cable_weight_kg100m", self.cable_weight_kg100m)),
                    "cable_tension_kg": float(freed_snap.get("cable_tension_kg", self.cable_tension_kg)),
                    "skate_weight_unit": str(freed_snap.get("skate_weight_unit", freed_snap.get("static_weight_unit", self.skate_weight_unit))),
                    "static_weight_unit": str(freed_snap.get("skate_weight_unit", freed_snap.get("static_weight_unit", self.skate_weight_unit))),  # legacy
                    "cable_weight_unit": str(freed_snap.get("cable_weight_unit", self.cable_weight_unit)),
                    "cable_tension_unit": str(freed_snap.get("cable_tension_unit", self.cable_tension_unit)),
                    "highline_mode": str(freed_snap.get("highline_mode", self.highline_mode)),
                },
            }
            self._config_path.write_text(json.dumps(c, indent=2))
        except Exception as exc:
            self._log(f"[Config] save failed: {exc}")

    # --- QML properties ---
    @Property(bool, notify=stateChanged)
    def ctrlConnected(self): return self._ctrl_connected()
    @Property(bool, notify=stateChanged)
    def w1pConnected(self): return self.w1p.connected
    @Property(bool, notify=stateChanged)
    def freeDActive(self): return bool(self.freed_input_last_rx and time.time()-self.freed_input_last_rx<2.0)
    @Property(float, notify=stateChanged)
    def freeDFps(self): return float(self.freed_in_fps)
    @Property(bool, notify=stateChanged)
    def ctrlTsConnected(self): return self._ctrl_connected()
    @Property(bool, notify=stateChanged)
    def ads1115Connected(self): return bool(self._ctrl_connected() and not (self._ctrl_flags & FLAG_ADS1115_FAULT))
    @Property(bool, notify=stateChanged)
    def w1pTsConnected(self): return bool(self.w1p.connected)
    @Property(bool, notify=stateChanged)
    def rs485Connected(self): return bool(self.w1p.connected and self.winch_rs_status == "Connected")
    @Property(float, notify=stateChanged)
    def joystickValue(self): return float(self._calibrated_joystick(self._ctrl_axis))
    @Property(float, notify=stateChanged)
    def joystickRawValue(self): return float(self._ctrl_axis)
    @Property(bool, notify=stateChanged)
    def systemReady(self): return not self.state.estop_active
    @Property(str, notify=stateChanged)
    def bannerText(self):
        if not self.state.estop_active:
            return "SYSTEM READY"

        # Operator-facing source names are intentionally limited to the three
        # system nodes used everywhere else in the SRVR UI.  A CTRL hardware
        # fault (including ADS1115) is reported as CTRL; a W1P/RS485 fault is
        # reported as W1P.  Do not expose lower-level RS485/ADS implementation
        # names in the top safety banner.
        ctrl_fault = bool(
            self._ctrl_estop
            or (self._ctrl_flags & FLAG_ADS1115_FAULT)
            or (not self._ctrl_connected())
        )
        w1p_fault = bool(
            self._w1p_estop
            or (not self.w1p.connected)
            or (self.winch_rs_status != "Connected")
        )

        parts = []
        if self._srvr_estop:
            parts.append("SRVR")
        if ctrl_fault:
            parts.append("CTRL")
        if w1p_fault:
            parts.append("W1P")
        return "E-Stop | " + (" & ".join(parts) if parts else "SRVR")
    @Property(float, notify=stateChanged)
    def position(self): return float(self.state.pos_m or 0.0)
    @Property(float, notify=stateChanged)
    def currentSpeed(self): return float(self.current_speed_mps)
    @Property(float, notify=stateChanged)
    def maxSpeed(self): return float(self.max_speed_mps)
    @Property(float, notify=stateChanged)
    def toNear(self): return max(0.0,self.position-float(self.state.near_limit.position_m or 0.0))
    @Property(float, notify=stateChanged)
    def toFar(self): return max(0.0,float(self.state.far_limit.position_m or 100.0)-self.position)
    @Property(float, notify=stateChanged)
    def nearLimit(self): return float(self.state.near_limit.position_m or 0.0)
    @Property(float, notify=stateChanged)
    def farLimit(self): return float(self.state.far_limit.position_m or 100.0)
    @Property(float, notify=stateChanged)
    def refPoint(self): return float(self.state.ref_point.position_m or 0.0)
    @Property(float, notify=stateChanged)
    def nearRampDistance(self):
        span = abs(float(self.farLimit) - float(self.nearLimit))
        return float(self._ramp_distance(self.state.near_limit, span))
    @Property(float, notify=stateChanged)
    def farRampDistance(self):
        span = abs(float(self.farLimit) - float(self.nearLimit))
        return float(self._ramp_distance(self.state.far_limit, span))
    @Property(str, notify=configChanged)
    def nearRampMode(self): return str(self.state.near_limit.ramp_mode)
    @Property(str, notify=configChanged)
    def farRampMode(self): return str(self.state.far_limit.ramp_mode)
    @Property(float, notify=configChanged)
    def nearRampValue(self):
        return float(self.state.near_limit.ramp_percentage if self.state.near_limit.ramp_mode == "Percentage" else self.state.near_limit.ramp_distance_m)
    @Property(float, notify=configChanged)
    def farRampValue(self):
        return float(self.state.far_limit.ramp_percentage if self.state.far_limit.ramp_mode == "Percentage" else self.state.far_limit.ramp_distance_m)
    @Property(str, notify=configChanged)
    def driveModeName(self): return str(self.drive_modes[self.active_drive_mode].get("name",f"Mode {self.active_drive_mode+1}"))
    @Property(int, notify=configChanged)
    def activeDriveMode(self): return int(self.active_drive_mode)
    @Property(str, notify=configChanged)
    def driveMode1Name(self): return str(self.drive_modes[0].get("name", "Mode 1"))
    @Property(str, notify=configChanged)
    def driveMode2Name(self): return str(self.drive_modes[1].get("name", "Mode 2"))
    @Property(str, notify=configChanged)
    def accelerationMode(self): return self.acceleration_mode
    @Property(bool, notify=configChanged)
    def batteryChange(self): return self.battery_change_mode
    @Property('QVariantList', notify=configChanged)
    def presets(self):
        return [{"index":i,"label":f"P{i+1}","name":self.preset_names[i],"position":self.preset_positions[i] if self.preset_positions[i] is not None else 0.0,"set":self.preset_positions[i] is not None,"visible":self.preset_visible[i]} for i in range(10)]
    @Property('QVariantList', notify=configChanged)
    def geometryPoints(self): return self.geometry
    @Property('QVariantList', notify=stateChanged)
    def cableProfile(self):
        # Staged Free-D edits are previewed immediately in BOTH diagrams.  Apply
        # still controls what is transmitted on the live Free-D output.
        return self._cable_profile()
    @Property('QVariantMap', notify=stateChanged)
    def freeDInput(self):
        r=self.freed_in_raw; d=self.freed_in
        pan = float(d["Pan"]) * self._input_sign("Pan") + float(self.freed_input_offsets.get("Pan", 0.0))
        tilt = float(d["Tilt"]) * self._input_sign("Tilt") + float(self.freed_input_offsets.get("Tilt", 0.0))
        roll = float(d["Roll"]) * self._input_sign("Roll") + float(self.freed_input_offsets.get("Roll", 0.0))
        zoom = float(d["Zoom"]) * self._input_sign("Zoom")
        focus = float(d["Focus"]) * self._input_sign("Focus")
        return {
            "cam":int(r["Cam ID"]),"panRaw":int(r["Pan"]),"pan":pan,
            "tiltRaw":int(r["Tilt"]),"tilt":tilt,"rollRaw":int(r["Roll"]),"roll":roll,
            "zoomRaw":int(r["Zoom"]),"zoom":zoom,"focusRaw":int(r["Focus"]),"focus":focus,
            "zoomPct":self._lens_percent("zoom", zoom),"focusPct":self._lens_percent("focus", focus),
            "fps":float(self.freed_in_fps)
        }
    @Property('QVariantMap', notify=stateChanged)
    def freeDOutput(self):
        x,y,z=self._xyz()
        return {
            "x":float(x)*self._output_sign("X"),
            "y":float(y)*self._output_sign("Y"),
            "z":float(z)*self._output_sign("Z"),
            "fps":float(self.freed_out_fps),
            "targetFps":float(self.freed_rate_hz),
        }

    # Editable Setup / Free-D configuration uses a slower configChanged signal so
    # live 20 Hz telemetry updates cannot steal focus or reset text while typing.
    @Property(str, notify=configChanged)
    def ctrlIp(self): return str(self.ctrl_ip)
    @Property(str, notify=configChanged)
    def w1pIp(self): return str(self.w1p_ip)
    @Property(bool, notify=configChanged)
    def ctrlInverted(self): return bool(self.reverse_joystick)
    @Property(bool, notify=configChanged)
    def w1pInverted(self): return bool(self.reverse_motor)
    @Property(float, notify=configChanged)
    def unitsPerM(self): return float(self.winch_units_per_m)
    @Property(float, notify=configChanged)
    def joystickDeadband(self): return float(self.joystick_deadband_pct)
    @Property(str, notify=configChanged)
    def positionSource(self): return str(self.position_source)
    @Property('QVariantList', notify=configChanged)
    def driveModes(self): return [dict(x) for x in self.drive_modes]
    @Property('QVariantList', notify=configChanged)
    def ctrlAuxAssignments(self): return list(self.ctrl_aux_assignments)
    @Property('QVariantList', notify=configChanged)
    def w1pAuxAssignments(self): return list(self.w1p_aux_assignments)
    @Property('QVariantMap', notify=configChanged)
    def setupDraft(self):
        snap = copy.deepcopy(getattr(self, "_setup_draft", self._setup_snapshot()))
        return snap

    @Property('QVariantMap', notify=configChanged)
    def freeDDraft(self):
        snap = copy.deepcopy(getattr(self, "_freed_draft", self._freed_snapshot()))
        snap["skate_weight_value"] = self._kg_to_lb(snap["skate_weight_kg"]) if snap.get("skate_weight_unit") == "lbs" else float(snap["skate_weight_kg"])
        snap["cable_weight_value"] = self._kg_to_lb(snap["cable_weight_kg100m"]) if snap.get("cable_weight_unit") == "lbs/100m" else float(snap["cable_weight_kg100m"])
        snap["cable_tension_value"] = self._kg_to_lb(snap["cable_tension_kg"]) if snap.get("cable_tension_unit") == "lbs" else float(snap["cable_tension_kg"])
        return snap

    def _lens_percent_snapshot(self, field: str, value: float, snap: dict) -> float:
        field = "zoom" if str(field).lower().startswith("zoom") else "focus"
        mode = str(snap.get("lens_scale_mode", "Auto"))
        lens_type = str(snap.get("lens_type", "u16"))
        if lens_type == "u16": limits = (0.0, 65535.0)
        elif lens_type == "i16": limits = (-32768.0, 32767.0)
        elif lens_type == "u24": limits = (0.0, 16777215.0)
        else: limits = (-8388608.0, 8388607.0)
        cal = dict(snap.get("lens_cal", {}))
        seen = dict(snap.get("lens_auto_seen", {}))
        if mode == "Full Scale":
            lo, hi = limits
        elif mode == "Auto":
            lo, hi = seen.get(field+"_min"), seen.get(field+"_max")
            if lo is None or hi is None or abs(float(hi)-float(lo)) < 1e-9:
                lo = float(cal.get("zoom_wide" if field == "zoom" else "focus_near", 0.0))
                hi = float(cal.get("zoom_tele" if field == "zoom" else "focus_far", 32767.0))
        else:
            lo = float(cal.get("zoom_wide" if field == "zoom" else "focus_near", 0.0))
            hi = float(cal.get("zoom_tele" if field == "zoom" else "focus_far", 32767.0))
        if abs(float(hi)-float(lo)) < 1e-9: return 0.0
        return max(0.0, min(100.0, (float(value)-float(lo))*100.0/(float(hi)-float(lo))))

    @Property('QVariantMap', notify=stateChanged)
    def freeDInputPreview(self):
        snap = getattr(self, "_freed_draft", self._freed_snapshot())
        r = self.freed_in_raw
        pan = float(self.freed_in.get("Pan",0.0))*self._input_sign("Pan", snap.get("input_inverts",{})) + float(snap.get("input_offsets",{}).get("Pan",0.0))
        tilt = float(self.freed_in.get("Tilt",0.0))*self._input_sign("Tilt", snap.get("input_inverts",{})) + float(snap.get("input_offsets",{}).get("Tilt",0.0))
        roll = float(self.freed_in.get("Roll",0.0))*self._input_sign("Roll", snap.get("input_inverts",{})) + float(snap.get("input_offsets",{}).get("Roll",0.0))
        zoom = float(self._decode_lens_for_type(int(r.get("Zoom",0)), snap.get("lens_type","u16")))*self._input_sign("Zoom", snap.get("input_inverts",{}))
        focus = float(self._decode_lens_for_type(int(r.get("Focus",0)), snap.get("lens_type","u16")))*self._input_sign("Focus", snap.get("input_inverts",{}))
        return {"cam":int(r.get("Cam ID",1)),"panRaw":int(r.get("Pan",0)),"pan":pan,
                "tiltRaw":int(r.get("Tilt",0)),"tilt":tilt,"rollRaw":int(r.get("Roll",0)),"roll":roll,
                "zoomRaw":int(r.get("Zoom",0)),"zoom":zoom,"focusRaw":int(r.get("Focus",0)),"focus":focus,
                "zoomPct":self._lens_percent_snapshot("zoom",zoom,snap),"focusPct":self._lens_percent_snapshot("focus",focus,snap),
                "fps":float(self.freed_in_fps)}

    @Property('QVariantMap', notify=stateChanged)
    def freeDOutputPreview(self):
        snap = getattr(self, "_freed_draft", self._freed_snapshot())
        x,y,z = self._xyz(snap)
        inv = snap.get("output_inverts",{})
        return {"x":float(x)*self._output_sign("X",inv), "y":float(y)*self._output_sign("Y",inv),
                "z":float(z)*self._output_sign("Z",inv), "fps":float(self.freed_out_fps),
                "targetFps":float(snap.get("rate_hz",self.freed_rate_hz))}

    @Property('QVariantList', notify=stateChanged)
    def freeDPreviewCableProfile(self):
        return self._cable_profile(getattr(self, "_freed_draft", self._freed_snapshot()))

    @Property('QVariantMap', notify=configChanged)
    def calibrationSummary(self):
        def item(lp, raw_key):
            is_set = lp.position_m is not None
            return {
                "set": bool(is_set),
                "position": float(lp.position_m or 0.0),
                "raw": "—" if self._limit_raw.get(raw_key) is None else str(self._limit_raw.get(raw_key)),
            }
        return {
            "near": item(self.state.near_limit, "near"),
            "ref": item(self.state.ref_point, "ref"),
            "far": item(self.state.far_limit, "far"),
        }
    @Property(bool, notify=configChanged)
    def freeDInputEnabled(self): return bool(self.freed_input_enabled)
    @Property(str, notify=configChanged)
    def freeDInputIp(self): return str(self.freed_input_bind_ip)
    @Property(int, notify=configChanged)
    def freeDInputPort(self): return int(self.freed_input_port)
    @Property(bool, notify=configChanged)
    def freeDOutputEnabled(self): return bool(self.freed_output_enabled)
    @Property(str, notify=configChanged)
    def freeDOutputIp(self): return str(self.freed_target_ip)
    @Property(int, notify=configChanged)
    def freeDOutputPort(self): return int(self.freed_target_port)
    @Property(float, notify=configChanged)
    def freeDOutputRate(self): return float(self.freed_rate_hz)
    @Property('QVariantMap', notify=configChanged)
    def freeDInputOffsets(self): return dict(self.freed_input_offsets)
    @Property('QVariantMap', notify=configChanged)
    def freeDInputInverts(self): return dict(self.freed_input_inverts)
    @Property('QVariantMap', notify=configChanged)
    def freeDOutputOffsets(self): return dict(self.freed_output_offsets)
    @Property('QVariantMap', notify=configChanged)
    def freeDOutputInverts(self): return dict(self.freed_output_inverts)
    @Property(str, notify=configChanged)
    def lensType(self): return str(self.freed_lens_type)
    @Property(str, notify=configChanged)
    def lensScale(self): return str(self.freed_lens_scale_mode)
    @Property('QVariantMap', notify=configChanged)
    def lensCalibration(self): return dict(self.freed_lens_cal)
    @Property(float, notify=configChanged)
    def skateWeightValue(self): return self._kg_to_lb(self.skate_weight_kg) if self.skate_weight_unit == "lbs" else float(self.skate_weight_kg)
    @Property(str, notify=configChanged)
    def skateWeightUnit(self): return str(self.skate_weight_unit)
    # Legacy aliases retained so an older QML/config package can still bind safely.
    @Property(float, notify=configChanged)
    def staticWeightValue(self): return self.skateWeightValue
    @Property(str, notify=configChanged)
    def staticWeightUnit(self): return self.skateWeightUnit
    @Property(float, notify=configChanged)
    def cableWeightValue(self): return self._kg_to_lb(self.cable_weight_kg100m) if self.cable_weight_unit == "lbs/100m" else float(self.cable_weight_kg100m)
    @Property(str, notify=configChanged)
    def cableWeightUnit(self): return str(self.cable_weight_unit)
    @Property(float, notify=configChanged)
    def cableTensionValue(self): return self._kg_to_lb(self.cable_tension_kg) if self.cable_tension_unit == "lbs" else float(self.cable_tension_kg)
    @Property(str, notify=configChanged)
    def cableTensionUnit(self): return str(self.cable_tension_unit)
    @Property(str, notify=configChanged)
    def highlineMode(self): return str(self.highline_mode)
    @Property(str, notify=logChanged)
    def logText(self):
        with self._lock: return "\n".join(self._logs)
    @Property(int, notify=logChanged)
    def logRevision(self): return int(self._log_revision)
    @Property(int, notify=logChanged)
    def logCount(self):
        with self._lock: return len(self._log_entries)
    @Slot(str, str, str, result='QVariantList')
    def filteredLogEntries(self, view, severity, search):
        view = str(view or "Live")
        severity = str(severity or "All")
        needle = str(search or "").strip().casefold()
        sev_map = {"Info":"INFO", "Warning":"WARN", "Fault":"FAULT"}
        wanted_level = sev_map.get(severity)
        with self._lock:
            entries = [dict(x) for x in self._log_entries]
        out = []
        for entry in entries:
            if view != "Live" and entry.get("view") != view:
                continue
            if wanted_level and entry.get("level") != wanted_level:
                continue
            if needle:
                hay = " ".join(str(entry.get(k, "")) for k in ("time", "level", "source", "message")).casefold()
                if needle not in hay:
                    continue
            out.append(entry)
        return out
    @Property(str, notify=calibrationChanged)
    def calibrationType(self): return self.calibration_type
    @Property(int, notify=calibrationChanged)
    def calibrationStep(self): return self.calibration_step
    @Property(bool, notify=calibrationChanged)
    def calibrationOpen(self): return self.calibration_open
    @Property(str, notify=calibrationChanged)
    def calibrationTitle(self): return self.calibration_title
    @Property(bool, notify=joystickCalibrationChanged)
    def joystickCalibrationOpen(self): return bool(self.joystick_calibration_open)
    @Property(int, notify=joystickCalibrationChanged)
    def joystickCalibrationStep(self): return int(self.joystick_calibration_step)
    @Property(str, notify=joystickCalibrationChanged)
    def joystickCalibrationTitle(self): return str(self.joystick_calibration_title)
    @Property(str, notify=joystickCalibrationChanged)
    def joystickCalibrationError(self): return str(self.joystick_calibration_error)
    @Property('QVariantMap', notify=joystickCalibrationChanged)
    def joystickCalibrationCaptures(self):
        return {
            "left": "—" if self._joystick_cal_pending.get("left") is None else f"{float(self._joystick_cal_pending['left']):.4f}",
            "centre": "—" if self._joystick_cal_pending.get("centre") is None else f"{float(self._joystick_cal_pending['centre']):.4f}",
            "right": "—" if self._joystick_cal_pending.get("right") is None else f"{float(self._joystick_cal_pending['right']):.4f}",
        }
    @Property(str, notify=stateChanged)
    def srvrTime(self): return time.strftime("%Y-%m-%d  %H:%M:%S")
    @Property(str, notify=stateChanged)
    def uptime(self):
        s=int(time.time()-self.started); return f"{s//3600:02d}:{(s%3600)//60:02d}:{s%60:02d}"

    def _notify_config(self):
        self.configChanged.emit()
        self.stateChanged.emit()

    # --- QML actions ---
    def _position_relative_to_near(self, pos=None) -> float:
        if pos is None:
            pos = self.state.pos_m
        nl = float(self.state.near_limit.position_m or 0.0)
        return float(pos or 0.0) - nl

    def _preset_absolute_position(self, i: int):
        if not (0 <= i < 10) or self.preset_positions[i] is None:
            return None
        return float(self.state.near_limit.position_m or 0.0) + float(self.preset_positions[i])

    @Slot(int,str)
    def setPresetName(self,i,name):
        if 0 <= i < 10:
            self.preset_names[i] = str(name).strip() or f"P{i+1}"
            self._save_config(); self._notify_config()

    @Slot(int,float)
    def setPresetPosition(self,i,value):
        # User-facing preset distances are relative to the Near end of the span.
        # Keep manually entered presets inside the current saved cable span.
        if 0 <= i < 10:
            span = max(0.0, abs(float(self.farLimit) - float(self.nearLimit)))
            self.preset_positions[i] = max(0.0, min(span, float(value))) if span > 0 else 0.0
            self._save_config(); self._notify_config()

    @Slot(int)
    def savePreset(self,i):
        if 0 <= i < 10 and self.state.pos_m is not None:
            self.preset_positions[i] = self._position_relative_to_near(self.state.pos_m)
            self._save_config(); self._notify_config()

    @Slot(int)
    def recallPreset(self,i):
        target = self._preset_absolute_position(i)
        if target is not None:
            self.goto_target_m = self._clamp_goto_target_inside_limits(target)

    @Slot(int)
    def togglePresetVisible(self,i):
        if 0 <= i < 10:
            self.preset_visible[i] = not self.preset_visible[i]
            self._save_config(); self._notify_config()

    @Slot(str)
    def saveLimit(self,which):
        """Save current feedback position as Near/Far/Reference.

        A simple Save does not clear Not-Calibrated: only a Slip (known physical
        point) or completion of the Limit Calibration wizard establishes the
        position reference safely.
        """
        if self.state.pos_m is None:
            return
        lp = self._limit(which)
        lp.position_m = float(self.state.pos_m)
        key = "near" if lp is self.state.near_limit else "far" if lp is self.state.far_limit else "ref"
        raw = getattr(self, "_last_raw_pos", None)
        self._limit_raw[key] = None if raw is None else int(raw)
        self._save_config(); self._sync_w1p_settings(); self._notify_config()

    @Slot(str)
    def recallLimit(self,which):
        lp = self._limit(which)
        if lp.position_m is not None:
            self.goto_target_m = self._clamp_goto_target_inside_limits(float(lp.position_m))

    @Slot(str)
    def slipLimit(self,which):
        """Re-reference W1P position at a known point after cable/pulley slip."""
        lp = self._limit(which)
        if lp.position_m is None:
            return
        target = float(lp.position_m)
        self.goto_target_m = None
        self._sync_position(target)
        self._not_calibrated = False
        self._sync_service_mode_to_winch(force=True)
        self._save_config(); self._notify_config()

    def _limit(self,which):
        w = str(which).lower()
        return self.state.near_limit if w.startswith("near") else self.state.far_limit if w.startswith("far") else self.state.ref_point

    @Slot(str,str,float)
    def setRamping(self,which,mode,value):
        """Set a ramp value while keeping Distance and Percentage equivalent.

        The physical ramp point never jumps merely because the operator changes
        units. Both representations are maintained from the same cable span.
        """
        lp = self._limit(which)
        if lp is self.state.ref_point:
            return
        span = max(0.001, abs(float(self.farLimit) - float(self.nearLimit)))
        new_mode = "Percentage" if str(mode).lower().startswith("percent") else "Distance"
        v = max(0.0, float(value))
        if new_mode == "Percentage":
            pct = max(0.0, min(100.0, v))
            lp.ramp_percentage = pct
            lp.ramp_distance_m = span * pct / 100.0
        else:
            dist = min(span, v)
            lp.ramp_distance_m = dist
            lp.ramp_percentage = max(0.0, min(100.0, dist * 100.0 / span))
        lp.ramp_mode = new_mode
        self._save_config(); self._notify_config()

    @Slot(str,str)
    def changeRampingMode(self, which, mode):
        """Convert the existing ramp to the newly selected representation."""
        lp = self._limit(which)
        if lp is self.state.ref_point:
            return
        span = max(0.001, abs(float(self.farLimit) - float(self.nearLimit)))
        physical_distance = self._ramp_distance(lp, span)
        new_mode = "Percentage" if str(mode).lower().startswith("percent") else "Distance"
        lp.ramp_distance_m = max(0.0, min(span, physical_distance))
        lp.ramp_percentage = max(0.0, min(100.0, lp.ramp_distance_m * 100.0 / span))
        lp.ramp_mode = new_mode
        self._save_config(); self._notify_config()

    @Slot(int)
    def setDriveMode(self,i):
        self.active_drive_mode = 0 if int(i) <= 0 else 1
        self._apply_active_drive_profile(sync=True)
        self._save_config(); self._notify_config()

    @Slot(int,str)
    def renameDriveMode(self,i,name):
        if i in (0,1):
            self.drive_modes[i]["name"] = str(name).strip() or f"Mode {i+1}"
            self._save_config(); self._notify_config()

    @Slot(str)
    def setAccelerationMode(self,mode):
        self.acceleration_mode = "Power" if str(mode).lower().startswith("power") else "Speed"
        self._sync_w1p_settings(); self._save_config(); self._notify_config()

    @Slot(bool)
    def setBatteryChange(self,on):
        self.battery_change_mode = bool(on)
        self._battery_change_went_outside_limits = False
        self._sync_service_mode_to_winch(force=True)
        self._save_config(); self._notify_config()

    @Slot()
    def toggleSrvrEStop(self):
        """Toggle only the SRVR software E-stop latch from the status banner.

        Other E-stop / connection / RS485 safety sources remain authoritative.
        Engaging the SRVR latch immediately sends STOP + software Servo Enable
        OFF. Clearing the SRVR latch restores software Servo Enable, matching
        the proven legacy SRVR behaviour; W1P's own safety gate still prevents
        motion until all real safety sources are healthy.
        """
        self._srvr_estop = not bool(self._srvr_estop)
        self.goto_target_m = None
        self._send_velocity(0.0, force=True)
        if not self.smoke_test:
            try:
                self.w1p.send("STOP")
                self.w1p.send("SW_SRVON 0" if self._srvr_estop else "SW_SRVON 1")
            except Exception:
                pass
        self._log("[SRVR E-Stop] " + ("ACTIVE" if self._srvr_estop else "CLEAR"))
        self.stateChanged.emit()

    @Slot()
    def openLimitCalibration(self):
        self.calibration_type = "Limit"
        self.calibration_open = True
        self.calibration_step = 0
        self.calibration_title = "Set Near Limit"
        self.goto_target_m = None
        self._sync_service_mode_to_winch(force=True)
        self.calibrationChanged.emit(); self.stateChanged.emit()

    @Slot()
    def openWinchCalibration(self):
        self.calibration_type = "Winch"
        self.calibration_open = True
        self.calibration_step = 0
        self.calibration_title = "Set Zero"
        self.goto_target_m = None
        self._winch_cal_zero_raw = None
        self._sync_service_mode_to_winch(force=True)
        self.calibrationChanged.emit(); self.stateChanged.emit()

    @Slot()
    def cancelCalibration(self):
        self.calibration_open = False
        self.goto_target_m = None
        self._sync_service_mode_to_winch(force=True)
        self.calibrationChanged.emit(); self.stateChanged.emit()

    def _sync_position(self, pos_m: float):
        self.state.pos_m = float(pos_m)
        self._winch_position_accept_jump_until = time.time() + 2.0
        self._winch_last_pos_accept_t = 0.0
        self._send_velocity(0.0, force=True)
        if not self.smoke_test:
            self.w1p.send(f"SYNC_POS {float(pos_m):.3f}")

    @Slot()
    def calibrationNext(self):
        if self.calibration_type == "Limit":
            if self.calibration_step == 0:
                # Near establishes the operator coordinate system: Near = 0.00 m.
                self.state.near_limit.position_m = 0.0
                raw = getattr(self, "_last_raw_pos", None)
                self._limit_raw["near"] = None if raw is None else int(raw)
                self._sync_position(0.0)
                self.calibration_step = 1
                self.calibration_title = "Set Far Limit"
            elif self.calibration_step == 1:
                # After Near was synchronised to zero, Far is a positive span distance.
                far = abs(float(self.state.pos_m or 0.0))
                self.state.far_limit.position_m = max(0.01, far)
                raw = getattr(self, "_last_raw_pos", None)
                self._limit_raw["far"] = None if raw is None else int(raw)
                self.state.total_length_m = self.state.far_limit.position_m
                self._sync_position(self.state.far_limit.position_m)
                self.calibration_step = 2
                self.calibration_title = "Set Reference Point"
            elif self.calibration_step == 2:
                ref = abs(float(self.state.pos_m or 0.0))
                self.state.ref_point.position_m = min(max(0.0, ref), float(self.state.far_limit.position_m or ref))
                raw = getattr(self, "_last_raw_pos", None)
                self._limit_raw["ref"] = None if raw is None else int(raw)
                self._sync_position(self.state.ref_point.position_m)
                self._not_calibrated = False
                self._sync_w1p_settings()
                self._save_config()
                self.calibration_step = 3
                self.calibration_title = "Done"
            else:
                self.calibration_open = False
                self._sync_service_mode_to_winch(force=True)
        else:
            raw = int(getattr(self, "_last_raw_pos", 0) or 0)
            if self.calibration_step == 0:
                self._winch_cal_zero_raw = raw
                self.calibration_step = 1
                self.calibration_title = "Set 20 m"
            elif self.calibration_step == 1:
                zero = int(self._winch_cal_zero_raw or 0)
                delta = abs(raw-zero)
                if delta <= 0:
                    self._log("[Calibration] Winch calibration failed: raw position did not change")
                else:
                    self.winch_units_per_m = max(1.0, delta/20.0)
                    self._sync_w1p_settings()
                    self._save_config()
                self.calibration_step = 2
                self.calibration_title = "Done"
            else:
                self.calibration_open = False
                self._sync_service_mode_to_winch(force=True)
        self.calibrationChanged.emit(); self.configChanged.emit(); self.stateChanged.emit()

    @Slot()
    def calibrationBack(self):
        if self.calibration_step > 0:
            self.calibration_step -= 1
        if self.calibration_type == "Limit":
            self.calibration_title = ("Set Near Limit","Set Far Limit","Set Reference Point","Done")[self.calibration_step]
        else:
            self.calibration_title = ("Set Zero","Set 20 m","Done")[min(self.calibration_step,2)]
        self.calibrationChanged.emit()

    @Slot(str,str)
    def setNetwork(self,which,value):
        if which == "CTRL":
            self.ctrl_ip = str(value).strip()
            self._ctrl_rx_times.clear()
        elif which == "W1P":
            self.w1p_ip = str(value).strip()
            self.w1p.reconfigure(self.w1p_ip,self.w1p_port)
        self._save_config(); self._notify_config()

    @Slot(str,bool)
    def setDirection(self,which,inverted):
        if which == "CTRL":
            self.reverse_joystick = bool(inverted)
        elif which == "W1P":
            self.reverse_motor = bool(inverted)
            self._sync_w1p_settings()
        self._save_config(); self._notify_config()

    @Slot(float)
    def setUnitsPerM(self,v):
        self.winch_units_per_m = max(1.0,float(v))
        self._sync_w1p_settings(); self._save_config(); self._notify_config()

    @Slot()
    def beginSetupEdit(self):
        """Refresh Setup from live values only when there are no unapplied edits."""
        if self._pending_import_config is not None and not self._pending_import_setup_handled:
            return
        if not getattr(self, "_setup_draft_dirty", False):
            self._saved_setup_snapshot = self._setup_snapshot()
            self._setup_draft = copy.deepcopy(self._saved_setup_snapshot)
            self._notify_config()

    @Slot()
    def beginFreeDEdit(self):
        """Refresh Free-D from live values only when there are no unapplied edits."""
        if self._pending_import_config is not None and not self._pending_import_freed_handled:
            return
        if not getattr(self, "_freed_draft_dirty", False):
            self._saved_freed_snapshot = self._freed_snapshot()
            self._freed_draft = copy.deepcopy(self._saved_freed_snapshot)
            self._notify_config()

    @Slot()
    def applySetupSettings(self):
        """Atomically commit the Setup draft; no Setup editor writes are live before this."""
        self._restore_setup_snapshot(copy.deepcopy(self._setup_draft))
        if self._pending_import_config is not None and not self._pending_import_setup_handled:
            self._apply_imported_run_config(self._pending_import_config)
            self._pending_import_setup_handled = True
        self._save_config(include_staged_freed=False)
        self._saved_setup_snapshot = self._setup_snapshot()
        self._setup_draft = copy.deepcopy(self._saved_setup_snapshot)
        self._setup_draft_dirty = False
        self._finish_pending_import_if_handled()
        self._log("[Config] Setup settings applied")
        self._notify_config()

    @Slot()
    def resetSetupSettings(self):
        """Discard Setup draft edits and show the last applied/saved values."""
        # Live Setup state is always the last applied/saved state because staged
        # Setup editors never write to it. This also picks up legitimate Run-page
        # changes (for example a Mode name) made since Setup was first opened.
        self._saved_setup_snapshot = self._setup_snapshot()
        self._setup_draft = copy.deepcopy(self._saved_setup_snapshot)
        self._setup_draft_dirty = False
        if self._pending_import_config is not None and not self._pending_import_setup_handled:
            self._pending_import_setup_handled = True
            self._finish_pending_import_if_handled()
        self._log("[Config] Setup staged edits reset")
        self._notify_config()

    @Slot(str, result=str)
    def exportConfigFile(self, value):
        """Export the currently APPLIED full configuration to a transferable JSON file."""
        try:
            path = self._dialog_path(value)
            if not str(path): return ""
            if path.suffix.lower() != ".json":
                path = Path(str(path) + ".hvp2p.json")
            path.parent.mkdir(parents=True, exist_ok=True)
            self._save_config(include_staged_freed=False)
            payload = json.loads(self._config_path.read_text(encoding="utf-8"))
            payload["_meta"] = {"format":"HV P2P SRVR Config", "version":self.version}
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            self._log(f"[Config] exported: {path}")
            return str(path)
        except Exception as exc:
            self._log(f"[Config] export failed: {exc}")
            return ""

    @Slot(str, result=bool)
    def stageConfigFile(self, value):
        """Load a transfer file into Setup/Free-D drafts; Apply buttons remain authoritative."""
        try:
            path = self._dialog_path(value)
            c = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(c, dict):
                raise ValueError("config root must be an object")
            self._setup_draft = self._setup_snapshot_from_config(c)
            self._freed_draft = self._freed_snapshot_from_config(c)
            self._pending_import_config = copy.deepcopy(c)
            self._pending_import_setup_handled = False
            self._pending_import_freed_handled = False
            self._setup_draft_dirty = True
            self._freed_draft_dirty = True
            self._log(f"[Config] loaded into pending Setup/Free-D drafts: {path}")
            self._notify_config()
            return True
        except Exception as exc:
            self._log(f"[Config] transfer load failed: {exc}")
            return False

    # Legacy internal save/load slots retained for compatibility. They operate on
    # the app's private config.json, not the transferable file-picker actions.
    @Slot()
    def saveConfig(self):
        self._save_config(include_staged_freed=False)
        self._saved_setup_snapshot = self._setup_snapshot()
        self._saved_freed_snapshot = self._freed_snapshot()
        self._setup_draft = copy.deepcopy(self._saved_setup_snapshot)
        self._freed_draft = copy.deepcopy(self._saved_freed_snapshot)
        self._setup_draft_dirty = False
        self._freed_draft_dirty = False
        self._log("[Config] configuration saved")
        self._notify_config()

    @Slot()
    def loadConfig(self):
        self._load_config()
        self._saved_setup_snapshot = self._setup_snapshot()
        self._saved_freed_snapshot = self._freed_snapshot()
        self._setup_draft = copy.deepcopy(self._saved_setup_snapshot)
        self._freed_draft = copy.deepcopy(self._saved_freed_snapshot)
        self._pending_import_config = None
        self._pending_import_setup_handled = True
        self._pending_import_freed_handled = True
        self._setup_draft_dirty = False
        self._freed_draft_dirty = False
        self.w1p.reconfigure(self.w1p_ip, self.w1p_port)
        if not self.smoke_test:
            self._sync_w1p_settings(); self._sync_service_mode_to_winch(force=True); self._start_freed_input()
        self._log("[Config] configuration loaded")
        self._notify_config()

    # Legacy live-edit slots retained for compatibility with older internal
    # callers/tests and external integrations. The locked Setup QML never calls
    # these: Setup uses the setSetup* draft API so its values remain unapplied
    # until the operator presses Apply.
    @Slot(float)
    def setJoystickDeadband(self, value):
        self.joystick_deadband_pct = max(0.0, min(25.0, float(value)))
        self._save_config(); self._notify_config()

    @Slot(str)
    def setPositionSource(self, value):
        self.position_source = "Encoder"
        self._save_config(); self._notify_config()

    @Slot(int, str, float)
    def setDriveModeValue(self, index, key, value):
        i, key = int(index), str(key)
        allowed = {"max_speed_mps", "goto_speed_mps", "accel_mps2", "decel_mps2", "crossover_mps2", "stop_decel_mps2"}
        if i not in (0, 1) or key not in allowed:
            return
        v = max(0.01, float(value))
        self.drive_modes[i][key] = v
        if key == "max_speed_mps":
            self.drive_modes[i]["goto_speed_mps"] = min(float(self.drive_modes[i]["goto_speed_mps"]), v)
        elif key == "goto_speed_mps":
            self.drive_modes[i][key] = min(v, float(self.drive_modes[i]["max_speed_mps"]))
        if i == self.active_drive_mode:
            self._apply_active_drive_profile(sync=True)
        self._save_config(); self._notify_config()

    @Slot(str, int, str)
    def setAuxAssignment(self, which, index, value):
        i = int(index)
        if not 0 <= i < 5:
            return
        target = self.ctrl_aux_assignments if str(which).upper().startswith("CTRL") else self.w1p_aux_assignments
        target[i] = str(value)
        self._save_config(); self._notify_config()

    @Slot(str,str)
    def setSetupNetwork(self, which, value):
        key = "ctrl_ip" if str(which).upper().startswith("CTRL") else "w1p_ip"
        self._setup_draft[key] = str(value).strip()
        self._setup_draft_dirty = True
        self._notify_config()

    @Slot(str,bool)
    def setSetupDirection(self, which, inverted):
        key = "reverse_joystick" if str(which).upper().startswith("CTRL") else "reverse_motor"
        self._setup_draft[key] = bool(inverted)
        self._setup_draft_dirty = True
        self._notify_config()

    @Slot(float)
    def setSetupUnitsPerM(self, value):
        self._setup_draft["units_per_m"] = max(1.0, float(value))
        self._setup_draft_dirty = True
        self._notify_config()

    @Slot(float)
    def setSetupJoystickDeadband(self, value):
        self._setup_draft["joystick_deadband_pct"] = max(0.0, min(25.0, float(value)))
        self._setup_draft_dirty = True
        self._notify_config()

    @Slot(str)
    def setSetupPositionSource(self, value):
        self._setup_draft["position_source"] = "Encoder"
        self._setup_draft_dirty = True
        self._notify_config()

    @Slot(int,str)
    def renameSetupDriveMode(self, index, name):
        i = int(index)
        if i in (0,1):
            self._setup_draft["drive_modes"][i]["name"] = str(name).strip() or f"Mode {i+1}"
            self._setup_draft_dirty = True
            self._notify_config()

    @Slot(int,str,float)
    def setSetupDriveModeValue(self, index, key, value):
        i, key = int(index), str(key)
        allowed = {"max_speed_mps", "goto_speed_mps", "accel_mps2", "decel_mps2", "crossover_mps2", "stop_decel_mps2"}
        if i not in (0,1) or key not in allowed: return
        dm = self._setup_draft["drive_modes"][i]
        v = max(0.01, float(value))
        dm[key] = v
        if key == "max_speed_mps": dm["goto_speed_mps"] = min(float(dm["goto_speed_mps"]), v)
        elif key == "goto_speed_mps": dm[key] = min(v, float(dm["max_speed_mps"]))
        self._setup_draft_dirty = True
        self._notify_config()

    @Slot(str)
    def setSetupAccelerationMode(self, mode):
        self._setup_draft["acceleration_mode"] = "Power" if str(mode).lower().startswith("power") else "Speed"
        self._setup_draft_dirty = True
        self._notify_config()

    @Slot(bool)
    def setSetupBatteryChange(self, on):
        self._setup_draft["battery_change_mode"] = bool(on)
        self._setup_draft_dirty = True
        self._notify_config()

    @Slot(str,int,str)
    def setSetupAuxAssignment(self, which, index, value):
        i = int(index)
        if not 0 <= i < 5: return
        key = "ctrl_aux_assignments" if str(which).upper().startswith("CTRL") else "w1p_aux_assignments"
        self._setup_draft[key][i] = str(value)
        self._setup_draft_dirty = True
        self._notify_config()

    @Slot()
    def openJoystickCalibration(self):
        # The joystick must be moved to both endpoints, so hold winch output at
        # zero for the complete wizard and capture raw CTRL values only.
        self.calibration_open = False
        # If another service calibration was open programmatically, immediately
        # restore the W1P service-mode state before starting joystick capture.
        # Joystick calibration itself never enables service movement.
        self._sync_service_mode_to_winch(force=True)
        self.joystick_calibration_open = True
        self._joystick_neutral_required = True
        self.joystick_calibration_step = 0
        self.joystick_calibration_title = "Set Joystick Left"
        self.joystick_calibration_error = ""
        self._joystick_cal_pending = {"left": None, "centre": None, "right": None}
        self.goto_target_m = None
        self._send_velocity(0.0, force=True)
        self._log("[Calibration] Joystick calibration started")
        self.joystickCalibrationChanged.emit(); self.calibrationChanged.emit(); self.stateChanged.emit()

    @Slot()
    def cancelJoystickCalibration(self):
        self.joystick_calibration_open = False
        self.joystick_calibration_error = ""
        self.goto_target_m = None
        self._send_velocity(0.0, force=True)
        self._log("[Calibration] Joystick calibration cancelled")
        self.joystickCalibrationChanged.emit(); self.stateChanged.emit()

    @Slot()
    def joystickCalibrationBack(self):
        if self.joystick_calibration_step > 0:
            self.joystick_calibration_step -= 1
        self.joystick_calibration_title = (
            "Set Joystick Left", "Set Joystick Centre", "Set Joystick Right"
        )[self.joystick_calibration_step]
        self.joystick_calibration_error = ""
        self.joystickCalibrationChanged.emit()

    @Slot()
    def joystickCalibrationNext(self):
        raw = max(-1.0, min(1.0, float(self._ctrl_axis)))
        if self.joystick_calibration_step == 0:
            self._joystick_cal_pending["left"] = raw
            self.joystick_calibration_step = 1
            self.joystick_calibration_title = "Set Joystick Centre"
        elif self.joystick_calibration_step == 1:
            self._joystick_cal_pending["centre"] = raw
            self.joystick_calibration_step = 2
            self.joystick_calibration_title = "Set Joystick Right"
        else:
            self._joystick_cal_pending["right"] = raw
            left = float(self._joystick_cal_pending["left"])
            centre = float(self._joystick_cal_pending["centre"])
            right = float(self._joystick_cal_pending["right"])
            lspan, rspan = left-centre, right-centre
            if abs(lspan) < 0.05 or abs(rspan) < 0.05 or lspan*rspan >= 0.0:
                self.joystick_calibration_error = "Invalid calibration range. Left and Right must be on opposite sides of Centre."
                self._log("[Calibration] Joystick calibration rejected: invalid Left/Centre/Right range")
                self.joystickCalibrationChanged.emit(); self.stateChanged.emit()
                return
            self.joystick_calibration_error = ""
            self.joystick_calibration_open = False
            # Setup uses explicit Apply/Reset semantics. Completing the wizard
            # stages the new raw calibration only; the live joystick mapping and
            # persistent config are unchanged until Setup Apply is pressed.
            self._setup_draft["joystick_calibration"] = {"left":left, "centre":centre, "right":right}
            self._setup_draft_dirty = True
            self._log(f"[Calibration] Joystick calibration staged L={left:.4f} C={centre:.4f} R={right:.4f}; press Apply to commit")
        self.goto_target_m = None
        self._send_velocity(0.0, force=True)
        self.joystickCalibrationChanged.emit(); self.configChanged.emit(); self.stateChanged.emit()

    @Slot(str,bool)
    def setFreeDEnabled(self, which, enabled):
        key = "input_enabled" if str(which).lower().startswith("in") else "output_enabled"
        self._freed_draft[key] = bool(enabled)
        self._freed_draft_dirty = True
        self._notify_config()

    @Slot(str,str,str)
    def setFreeDNetwork(self, which, field, value):
        which, field = str(which).lower(), str(field).lower()
        try:
            if which.startswith("in"):
                if field == "ip": self._freed_draft["input_bind_ip"] = str(value).strip() or "0.0.0.0"
                elif field == "port": self._freed_draft["input_port"] = max(1, min(65535, int(float(value))))
            else:
                if field == "ip": self._freed_draft["target_ip"] = str(value).strip()
                elif field == "port": self._freed_draft["target_port"] = max(1, min(65535, int(float(value))))
                elif field in ("fps","rate"): self._freed_draft["rate_hz"] = max(1.0, min(100.0, float(value)))
        except Exception as exc:
            self._log(f"[Free-D] invalid staged {which} {field}: {value} ({exc})")
        self._freed_draft_dirty = True
        self._notify_config()

    @Slot(str,str,float)
    def setFreeDOffset(self, side, axis, value):
        if str(side).lower().startswith("in"):
            axis = str(axis).title()
            if axis in ("Pan","Tilt","Roll"): self._freed_draft["input_offsets"][axis] = float(value)
        else:
            axis = str(axis).upper()
            if axis in ("X","Y","Z"): self._freed_draft["output_offsets"][axis] = float(value)
        self._freed_draft_dirty = True
        self._notify_config()

    @Slot(str,str,bool)
    def setFreeDInvert(self, side, axis, enabled):
        if str(side).lower().startswith("in"):
            axis = str(axis).title()
            if axis in ("Pan","Tilt","Roll","Zoom","Focus"): self._freed_draft["input_inverts"][axis] = bool(enabled)
        else:
            axis = str(axis).upper()
            if axis in ("X","Y","Z"): self._freed_draft["output_inverts"][axis] = bool(enabled)
        self._freed_draft_dirty = True
        self._notify_config()

    @Slot(int,str,float)
    def setGeometryPoint(self, index, axis, value):
        i, axis = int(index), str(axis).lower()
        if not 0 <= i < 5 or axis not in ("x","y","z"): return
        if axis == "z" and i not in (0,4): return
        self._freed_draft["geometry"][i][axis] = float(value)
        self._freed_draft_dirty = True
        self._notify_config()

    @Slot(str,float)
    def setWeightValue(self, which, value):
        which, v = str(which).lower(), max(0.0, float(value))
        if which.startswith("skate") or which.startswith("static"):
            self._freed_draft["skate_weight_kg"] = self._lb_to_kg(v) if self._freed_draft.get("skate_weight_unit") == "lbs" else v
        elif which.startswith("cable"):
            self._freed_draft["cable_weight_kg100m"] = self._lb_to_kg(v) if self._freed_draft.get("cable_weight_unit") == "lbs/100m" else v
        elif which.startswith("tension"):
            kg = self._lb_to_kg(v) if self._freed_draft.get("cable_tension_unit") == "lbs" else v
            self._freed_draft["cable_tension_kg"] = max(0.01, kg)
        self._freed_draft_dirty = True
        self._notify_config()

    @Slot(str,str)
    def setWeightUnit(self, which, unit):
        which, unit = str(which).lower(), str(unit)
        if which.startswith("skate") or which.startswith("static"):
            self._freed_draft["skate_weight_unit"] = "lbs" if unit.lower().startswith("lb") else "kg"
        elif which.startswith("cable"):
            self._freed_draft["cable_weight_unit"] = "lbs/100m" if unit.lower().startswith("lb") else "kg/100m"
        elif which.startswith("tension"):
            self._freed_draft["cable_tension_unit"] = "lbs" if unit.lower().startswith("lb") else "kg"
        self._freed_draft_dirty = True
        self._notify_config()

    @Slot(str)
    def setHighlineMode(self, mode):
        self._freed_draft["highline_mode"] = "Dual Highline" if str(mode).lower().startswith("dual") else "Single Highline"
        self._freed_draft_dirty = True
        self._notify_config()

    @Slot(str,float)
    def setLensCalibration(self, which, value):
        key = str(which)
        if key in self._freed_draft["lens_cal"]:
            self._freed_draft["lens_cal"][key] = float(value)
            self._freed_draft_dirty = True
            self._notify_config()

    @Slot()
    def applyFreeDSettings(self):
        """Atomically commit the Free-D draft and restart the input listener."""
        self._restore_freed_snapshot(copy.deepcopy(self._freed_draft))
        self._save_config(include_staged_freed=True)
        self._saved_freed_snapshot = self._freed_snapshot()
        self._freed_draft = copy.deepcopy(self._saved_freed_snapshot)
        self._freed_draft_dirty = False
        if self._pending_import_config is not None and not self._pending_import_freed_handled:
            self._pending_import_freed_handled = True
            self._finish_pending_import_if_handled()
        if not self.smoke_test: self._start_freed_input()
        self._log("[Free-D] settings applied")
        self._notify_config()

    @Slot()
    def resetFreeDSettings(self):
        """Discard Free-D draft edits and show the last applied/saved values."""
        self._saved_freed_snapshot = self._freed_snapshot()
        self._freed_draft = copy.deepcopy(self._saved_freed_snapshot)
        self._freed_draft_dirty = False
        if self._pending_import_config is not None and not self._pending_import_freed_handled:
            self._pending_import_freed_handled = True
            self._finish_pending_import_if_handled()
        self._log("[Free-D] staged edits reset")
        self._notify_config()

    @Slot(result=str)
    def saveLog(self):
        try:
            log_dir = self._config_path.parent / "Logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            path = log_dir / ("HV_P2P_SRVR_Log_" + time.strftime("%Y%m%d_%H%M%S") + ".txt")
            with self._lock:
                path.write_text("\n".join(self._logs) + "\n", encoding="utf-8")
            self._log(f"[SRVR] Log saved: {path}")
            return str(path)
        except Exception as exc:
            self._log(f"[SRVR] Log save failed: {exc}")
            return ""

    @Slot()
    def clearLog(self):
        with self._lock:
            self._logs.clear()
            self._log_entries.clear()
            self._log_revision += 1
        self.logChanged.emit()

    @Slot(str)
    def setLensType(self,t):
        t = str(t)
        if t in ("i16","u16","i24","u24"):
            self._freed_draft["lens_type"] = t
            self._freed_draft_dirty = True
            self._notify_config()

    @Slot(str)
    def setLensScale(self,s):
        self._freed_draft["lens_scale_mode"] = self._normalise_lens_scale(s)
        self._freed_draft_dirty = True
        self._notify_config()

    @Slot(str,float)
    def captureLens(self,which,value):
        key = str(which)
        if key in self._freed_draft["lens_cal"]:
            self._freed_draft["lens_cal"][key] = float(value)
            self._freed_draft_dirty = True
            self._notify_config()

    @Slot()
    def shutdown(self):
        try:
            if hasattr(self, "timer"):
                self.timer.stop()
        except Exception:
            pass
        if self._stop_evt.is_set(): return
        self._stop_evt.set(); self._freed_in_stop.set()
        try: self.w1p.send("STOP"); self.w1p.send("SW_SRVON 0"); time.sleep(.05)
        except Exception: pass
        self.w1p.close()
        try:
            if self._freed_in_sock: self._freed_in_sock.close()
            self._freed_sock.close()
        except Exception: pass
