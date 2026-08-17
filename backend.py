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
import json, math, os, queue, socket, struct, threading, time

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
    stateChanged = Signal()
    logChanged = Signal()
    calibrationChanged = Signal()

    def __init__(self, version="26.08.17.06", smoke_test: bool = False):
        super().__init__()
        self.version = version
        self.smoke_test = bool(smoke_test)
        self.started = time.time()
        self._lock = threading.RLock()
        self._logs = deque(maxlen=1200)
        self.state = WinchState()
        self.ctrl_ip = "172.20.1.101"
        self.w1p_ip = "172.20.1.102"
        self.w1p_port = 5000
        self.reverse_joystick = False
        self.reverse_motor = False
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
        self.geometry = [
            {"name":"P1 (Near)","x":0.0,"y":0.0,"z":0.0},
            {"name":"P2","x":25.0,"y":5.0,"z":None},
            {"name":"P3","x":50.0,"y":8.0,"z":None},
            {"name":"P4","x":75.0,"y":5.0,"z":None},
            {"name":"P5 (Far)","x":100.0,"y":0.0,"z":0.0},
        ]
        self.static_weight_kg = 25.0
        self.cable_weight_kg100m = 4.5
        self.cable_tension_kg = 100.0
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

        self._config_path = self._config_file_path()
        self._load_config()
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

    def _log(self, msg):
        line = f"{time.strftime('%H:%M:%S')}  {str(msg).strip()}"
        with self._lock: self._logs.append(line)
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

        axis = self._ctrl_axis * (-1 if self.reverse_joystick else 1)
        if abs(axis*100) < JOY_DEADBAND_PCT:
            axis = 0.0
        if self.goto_target_m is not None and abs(axis*100) >= JOY_DEADBAND_PCT:
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
            with self._lock:
                self.freed_in_raw={"Cam ID":int(data[1]),"Pan":raw_pan,"Tilt":raw_tilt,"Roll":raw_roll,"Zoom":rz,"Focus":rf}
                self.freed_in={"Cam ID":int(data[1]),"Pan":raw_pan/32768.0,"Tilt":raw_tilt/32768.0,"Roll":raw_roll/32768.0,"Zoom":self._decode_lens(rz),"Focus":self._decode_lens(rf)}
                self.freed_input_last_rx=now; self._freed_in_times.append(now)
                recent=[t for t in self._freed_in_times if t>=now-1]
                self.freed_in_fps=(len(recent)-1)/(recent[-1]-recent[0]) if len(recent)>1 and recent[-1]>recent[0] else float(len(recent))

    def _decode_lens(self,u24):
        t=self.freed_lens_type.lower()
        if t=="u24": return u24
        if t=="u16": return u24 & 0xffff
        if t=="i16":
            v=u24 & 0xffff; return v-0x10000 if v&0x8000 else v
        return u24-0x1000000 if u24&0x800000 else u24

    def _xyz(self):
        x=float(self.state.pos_m or 0.0)-float(self.state.near_limit.position_m or 0.0)
        # Interpolate Y through P1..P5 then apply a smooth cable-sag estimate.
        pts=[(float(p["x"]),float(p["y"])) for p in self.geometry]
        pts.sort()
        y=pts[0][1]
        for (x0,y0),(x1,y1) in zip(pts[:-1],pts[1:]):
            if x0<=x<=x1:
                t=(x-x0)/max(1e-9,x1-x0); y=y0+(y1-y0)*t; break
        span=max(.1,pts[-1][0]-pts[0][0]); rel=max(0,min(span,x-pts[0][0]))
        rope=max(0,self.cable_weight_kg100m)/100.0; tension=max(1,self.cable_tension_kg)
        sag=(rope*rel*(span-rel))/(2*tension)
        y-=sag
        z0=float(self.geometry[0].get("z") or 0); z1=float(self.geometry[-1].get("z") or 0); z=z0+(z1-z0)*(rel/span)
        return x+self.freed_output_offsets["X"], y+self.freed_output_offsets["Y"], z+self.freed_output_offsets["Z"]

    def _send_freed(self):
        if not self.freed_output_enabled: return
        now=time.perf_counter(); hz=max(1,min(100,self.freed_rate_hz))
        if now-self._last_freed_tx<1/hz: return
        self._last_freed_tx=now; x,y,z=self._xyz(); m=self.freed_in
        payload=bytearray((0xD1,max(0,min(255,int(m["Cam ID"])))))
        for v in (m["Pan"],m["Tilt"],m["Roll"]): payload.extend(_s24be(round(float(v)*32768)))
        for v in (x,y,z): payload.extend(_s24be(round(float(v)*self.freed_pos_scale)))
        payload.extend(_s24be(int(m["Zoom"]))); payload.extend(_s24be(-int(m["Focus"]))); payload.extend(b"\x00\x00")
        payload.append((0x40-sum(payload[:28]))&0xff)
        try: self._freed_sock.sendto(bytes(payload),(self.freed_target_ip,self.freed_target_port))
        except Exception: return
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
            self.freed_lens_type = str(fd.get("lens_type", self.freed_lens_type)) if str(fd.get("lens_type", self.freed_lens_type)) in ("i16","u16","i24","u24") else "u16"
            scale = str(fd.get("lens_scale_mode", self.freed_lens_scale_mode))
            self.freed_lens_scale_mode = scale if scale in ("Auto","Manual","Full Scale") else "Auto"
            self.static_weight_kg = max(0.0, float(fd.get("static_weight_kg", self.static_weight_kg)))
            self.cable_weight_kg100m = max(0.0, float(fd.get("cable_weight_kg100m", self.cable_weight_kg100m)))
            self.cable_tension_kg = max(1.0, float(fd.get("cable_tension_kg", self.cable_tension_kg)))
            self.highline_mode = "Dual Highline" if str(fd.get("highline_mode", self.highline_mode)).lower().startswith("dual") else "Single Highline"
        except Exception as exc:
            self._log(f"[Config] load failed: {exc}")
            self.drive_modes = self._normalise_drive_modes(self.drive_modes)
            self._apply_active_drive_profile(sync=False)

    def _save_config(self):
        try:
            c = {
                "ctrl_ip": self.ctrl_ip,
                "w1p_ip": self.w1p_ip,
                "reverse_joystick": self.reverse_joystick,
                "reverse_motor": self.reverse_motor,
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
                    "nearRamp": {"mode":self.state.near_limit.ramp_mode,"distance":self.state.near_limit.ramp_distance_m,"percentage":self.state.near_limit.ramp_percentage},
                    "farRamp": {"mode":self.state.far_limit.ramp_mode,"distance":self.state.far_limit.ramp_distance_m,"percentage":self.state.far_limit.ramp_percentage},
                },
                "geometry": self.geometry,
                "free_d": {
                    "input_enabled": self.freed_input_enabled,
                    "input_bind_ip": self.freed_input_bind_ip,
                    "input_port": self.freed_input_port,
                    "output_enabled": self.freed_output_enabled,
                    "target_ip": self.freed_target_ip,
                    "target_port": self.freed_target_port,
                    "rate_hz": self.freed_rate_hz,
                    "pos_scale": self.freed_pos_scale,
                    "lens_type": self.freed_lens_type,
                    "lens_scale_mode": self.freed_lens_scale_mode,
                    "static_weight_kg": self.static_weight_kg,
                    "cable_weight_kg100m": self.cable_weight_kg100m,
                    "cable_tension_kg": self.cable_tension_kg,
                    "highline_mode": self.highline_mode,
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
    def systemReady(self): return not self.state.estop_active
    @Property(str, notify=stateChanged)
    def bannerText(self):
        if not self.state.estop_active: return "SYSTEM READY"
        parts=[]
        if self._ctrl_estop: parts.append("CTRL")
        if self._w1p_estop: parts.append("W1P")
        if self._ctrl_flags & FLAG_ADS1115_FAULT: parts.append("ADS1115")
        if not self._ctrl_connected(): parts.append("CTRL")
        if not self.w1p.connected: parts.append("W1P")
        if self.winch_rs_status!="Connected": parts.append("RS485")
        uniq=[]
        for p in parts:
            if p not in uniq: uniq.append(p)
        return "E-STOP | " + (" & ".join(uniq) if uniq else "SRVR")
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
    @Property(str, notify=stateChanged)
    def nearRampMode(self): return str(self.state.near_limit.ramp_mode)
    @Property(str, notify=stateChanged)
    def farRampMode(self): return str(self.state.far_limit.ramp_mode)
    @Property(float, notify=stateChanged)
    def nearRampValue(self):
        return float(self.state.near_limit.ramp_percentage if self.state.near_limit.ramp_mode == "Percentage" else self.state.near_limit.ramp_distance_m)
    @Property(float, notify=stateChanged)
    def farRampValue(self):
        return float(self.state.far_limit.ramp_percentage if self.state.far_limit.ramp_mode == "Percentage" else self.state.far_limit.ramp_distance_m)
    @Property(str, notify=stateChanged)
    def driveModeName(self): return str(self.drive_modes[self.active_drive_mode].get("name",f"Mode {self.active_drive_mode+1}"))
    @Property(int, notify=stateChanged)
    def activeDriveMode(self): return int(self.active_drive_mode)
    @Property(str, notify=stateChanged)
    def driveMode1Name(self): return str(self.drive_modes[0].get("name", "Mode 1"))
    @Property(str, notify=stateChanged)
    def driveMode2Name(self): return str(self.drive_modes[1].get("name", "Mode 2"))
    @Property(str, notify=stateChanged)
    def accelerationMode(self): return self.acceleration_mode
    @Property(bool, notify=stateChanged)
    def batteryChange(self): return self.battery_change_mode
    @Property('QVariantList', notify=stateChanged)
    def presets(self):
        return [{"index":i,"label":f"P{i+1}","name":self.preset_names[i],"position":self.preset_positions[i] if self.preset_positions[i] is not None else 0.0,"set":self.preset_positions[i] is not None,"visible":self.preset_visible[i]} for i in range(10)]
    @Property('QVariantList', notify=stateChanged)
    def geometryPoints(self): return self.geometry
    @Property('QVariantMap', notify=stateChanged)
    def freeDInput(self):
        r=self.freed_in_raw; d=self.freed_in
        return {"cam":int(r["Cam ID"]),"panRaw":int(r["Pan"]),"pan":float(d["Pan"]),"tiltRaw":int(r["Tilt"]),"tilt":float(d["Tilt"]),"rollRaw":int(r["Roll"]),"roll":float(d["Roll"]),"zoomRaw":int(r["Zoom"]),"zoom":float(d["Zoom"]),"focusRaw":int(r["Focus"]),"focus":float(d["Focus"]),"fps":float(self.freed_in_fps)}
    @Property('QVariantMap', notify=stateChanged)
    def freeDOutput(self):
        x,y,z=self._xyz(); return {"x":x,"y":y,"z":z,"fps":self.freed_out_fps}
    @Property(str, notify=logChanged)
    def logText(self):
        with self._lock: return "\n".join(self._logs)
    @Property(str, notify=calibrationChanged)
    def calibrationType(self): return self.calibration_type
    @Property(int, notify=calibrationChanged)
    def calibrationStep(self): return self.calibration_step
    @Property(bool, notify=calibrationChanged)
    def calibrationOpen(self): return self.calibration_open
    @Property(str, notify=calibrationChanged)
    def calibrationTitle(self): return self.calibration_title
    @Property(str, notify=stateChanged)
    def srvrTime(self): return time.strftime("%Y-%m-%d  %H:%M:%S")
    @Property(str, notify=stateChanged)
    def uptime(self):
        s=int(time.time()-self.started); return f"{s//3600:02d}:{(s%3600)//60:02d}:{s%60:02d}"

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
            self._save_config(); self.stateChanged.emit()

    @Slot(int,float)
    def setPresetPosition(self,i,value):
        # User-facing preset distances are relative to the Near end of the span.
        if 0 <= i < 10:
            self.preset_positions[i] = float(value)
            self._save_config(); self.stateChanged.emit()

    @Slot(int)
    def savePreset(self,i):
        if 0 <= i < 10 and self.state.pos_m is not None:
            self.preset_positions[i] = self._position_relative_to_near(self.state.pos_m)
            self._save_config(); self.stateChanged.emit()

    @Slot(int)
    def recallPreset(self,i):
        target = self._preset_absolute_position(i)
        if target is not None:
            self.goto_target_m = self._clamp_goto_target_inside_limits(target)

    @Slot(int)
    def togglePresetVisible(self,i):
        if 0 <= i < 10:
            self.preset_visible[i] = not self.preset_visible[i]
            self._save_config(); self.stateChanged.emit()

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
        self._save_config(); self._sync_w1p_settings(); self.stateChanged.emit()

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
        self._save_config(); self.stateChanged.emit()

    def _limit(self,which):
        w = str(which).lower()
        return self.state.near_limit if w.startswith("near") else self.state.far_limit if w.startswith("far") else self.state.ref_point

    @Slot(str,str,float)
    def setRamping(self,which,mode,value):
        lp = self._limit(which)
        if lp is self.state.ref_point:
            return
        lp.ramp_mode = "Percentage" if str(mode).lower().startswith("percent") else "Distance"
        if lp.ramp_mode == "Percentage":
            lp.ramp_percentage = max(0.0, min(100.0, float(value)))
        else:
            lp.ramp_distance_m = max(0.0, float(value))
        self._save_config(); self.stateChanged.emit()

    @Slot(int)
    def setDriveMode(self,i):
        self.active_drive_mode = 0 if int(i) <= 0 else 1
        self._apply_active_drive_profile(sync=True)
        self._save_config(); self.stateChanged.emit()

    @Slot(int,str)
    def renameDriveMode(self,i,name):
        if i in (0,1):
            self.drive_modes[i]["name"] = str(name).strip() or f"Mode {i+1}"
            self._save_config(); self.stateChanged.emit()

    @Slot(str)
    def setAccelerationMode(self,mode):
        self.acceleration_mode = "Power" if str(mode).lower().startswith("power") else "Speed"
        self._sync_w1p_settings(); self._save_config(); self.stateChanged.emit()

    @Slot(bool)
    def setBatteryChange(self,on):
        self.battery_change_mode = bool(on)
        self._battery_change_went_outside_limits = False
        self._sync_service_mode_to_winch(force=True)
        self._save_config(); self.stateChanged.emit()

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
                self._sync_position(0.0)
                self.calibration_step = 1
                self.calibration_title = "Set Far Limit"
            elif self.calibration_step == 1:
                # After Near was synchronised to zero, Far is a positive span distance.
                far = abs(float(self.state.pos_m or 0.0))
                self.state.far_limit.position_m = max(0.01, far)
                self.state.total_length_m = self.state.far_limit.position_m
                self._sync_position(self.state.far_limit.position_m)
                self.calibration_step = 2
                self.calibration_title = "Set Reference Point"
            elif self.calibration_step == 2:
                ref = abs(float(self.state.pos_m or 0.0))
                self.state.ref_point.position_m = min(max(0.0, ref), float(self.state.far_limit.position_m or ref))
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
        self.calibrationChanged.emit(); self.stateChanged.emit()

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
        self._save_config(); self.stateChanged.emit()

    @Slot(str,bool)
    def setDirection(self,which,inverted):
        if which == "CTRL":
            self.reverse_joystick = bool(inverted)
        elif which == "W1P":
            self.reverse_motor = bool(inverted)
            self._sync_w1p_settings()
        self._save_config(); self.stateChanged.emit()

    @Slot(float)
    def setUnitsPerM(self,v):
        self.winch_units_per_m = max(1.0,float(v))
        self._sync_w1p_settings(); self._save_config(); self.stateChanged.emit()

    @Slot()
    def clearLog(self):
        with self._lock:
            self._logs.clear()
        self.logChanged.emit()

    @Slot(str)
    def setLensType(self,t):
        t = str(t)
        if t in ("i16","u16","i24","u24"):
            self.freed_lens_type = t
            self._save_config(); self.stateChanged.emit()

    @Slot(str)
    def setLensScale(self,s):
        s = str(s)
        if s in ("Auto","Manual","Full Scale"):
            self.freed_lens_scale_mode = s
            self._save_config(); self.stateChanged.emit()

    @Slot(str,float)
    def captureLens(self,which,value):
        key = str(which)
        if key in self.freed_lens_cal:
            self.freed_lens_cal[key] = float(value)
            self._save_config(); self.stateChanged.emit()

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
