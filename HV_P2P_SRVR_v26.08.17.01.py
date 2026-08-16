# ==============================================================
# HV P2P SRVR v26.08.17.01
#
# Server-side control application for HV P2P systems. Original dark colour scheme with Free-D top/side views with Free-D top/side views, ShotOver input table, camera cone overlays, and high-rate threaded Free-D output.
#
# CTRL compatibility:
#   - HV P2P CTRL (ESP32-POE-ISO)
#   - UDP control packets on port 5000
#   - Supports controller flags:
#       bit0 = E-Stop (controller drives GUI E-Stop)
#       bit1 = Cancel (soft stop / cancel current move)
#
# This revision updates naming to date-based convention and
# formalises ESP32-POE-ISO controller compatibility.
# ==============================================================
#
#!/usr/bin/env python3
"""
HV P2P SRVR v26.08.17.01 (Tkinter)

- RS485 must be explicitly Connected before Active is permitted.
- RS485 and ADS1115 interface losses create named red safety states.

- Stabilises the SRVR top E-Stop/status banner so it is a single non-flashing line and cannot create yellow half-height bands above/below the text.
- Bottom row shows Winch Connection and Controller Connection.
- Centre area adds Free-D Top View and Side View displays, Free-D input, and Free-D UDP output settings.
- Speed box shows:
    * Current Speed
    * Maximum Speed button (above Battery Change Mode)
    * Battery Change Mode (ON/OFF)
- Maximum Speed popup:
    * Slider in m/s (1.0–40.0)
    * Manual Entry: [value] [m/s | km/h]
    * Internally everything in m/s
"""

from __future__ import annotations
from collections import deque

# Controller acceptance + stability tuning
controller_expected_ip = None   # Only accept controller packets from this IP (set from GUI Controller IP field)
CTRL_CONNECT_ON_S = 2.0         # Must see a packet within this age to consider connected
CTRL_DISCONNECT_OFF_S = 6.0     # Must miss packets longer than this to consider disconnected (hysteresis)
CTRL_JOYSTICK_HOLD_S = 0.0      # Hold last joystick value briefly after last packet (prevents flicker)
CTRL_JOYSTICK_DECAY_S = 0.0     # Then decay towards 0 for safety if packets stop
CTRL_RX_WINDOW_S = 0.75     # stable fast loss window; CONTROL packets arrive every 50 ms
CTRL_RX_MIN_PKTS = 2          # require two recent packets to prevent one-packet flicker
JOY_DEADBAND_PCT = 5.0      # +/- percent around zero treated as 0
JOY_FILTER_ALPHA = 0.65     # lower = smoother

CTRL_DEBUG_RX = False  # CMD-window debug print replaced by SRVR Log tab
CTRL_DEBUG_RX_PERIOD_S = 0.25
WINCH_STATUS_TIMEOUT_S = 0.75  # match CTRL stable-fast loss detection without false flicker
W1P_RS485_STALE_CLASSIFY_GRACE_S = 1.50  # keep a known RS485 fault classified as W1P Fault during brief Modbus timeout stalls
WINCH_CONNECT_TIMEOUT_S = 0.75
WINCH_RECV_TIMEOUT_S = 0.075
WINCH_RECONNECT_RETRY_S = 0.1
WINCH_PROBE_INTERVAL_S = 0.05  # poll W1P at CTRL-style control cadence
CONTROL_LOOP_DT_S = 0.05

# CTRL-TS display transport is event-driven: safety timers remain fast,
# but the touchscreen receives updates only when the display payload changes
# meaningfully, plus a slow recovery heartbeat for boot-order/reconnect cases.
HMI_DISPLAY_MIN_CHANGE_INTERVAL_S = 0.04  # v13: 25 Hz display path for smoother CTRL-TS progress without full-screen redraw
HMI_DISPLAY_KEEPALIVE_S = 3.0
HMI_DISPLAY_POS_QUANTUM_M = 0.001
HMI_DISPLAY_SPEED_QUANTUM_MPS = 0.01
WINCH_POS_JUMP_GRACE_S = 2.0
WINCH_POS_REJECT_LOG_S = 2.0


import queue
import socket
import struct
import threading
import time
import os
import sys
import json
import math
from dataclasses import dataclass, field
from typing import Optional

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
import tkinter.font as tkfont

# ------------------------------------------------------------
# Live SRVR log support
# ------------------------------------------------------------
APP_LOG_QUEUE = queue.Queue(maxsize=2000)


def _queue_put_drop_oldest(q: queue.Queue, item) -> None:
    """Bound long-running producer queues without blocking safety/network threads."""
    try:
        q.put_nowait(item)
        return
    except queue.Full:
        pass
    try:
        q.get_nowait()
    except queue.Empty:
        pass
    try:
        q.put_nowait(item)
    except queue.Full:
        pass


def _app_log(message: str):
    """Thread-safe application log sink used by UDP threads and GUI code."""
    try:
        ts = time.strftime("%H:%M:%S")
        line = f"{ts}  {str(message).strip()}"
        try:
            APP_LOG_QUEUE.put_nowait(line)
        except queue.Full:
            try:
                APP_LOG_QUEUE.get_nowait()
            except Exception:
                pass
            try:
                APP_LOG_QUEUE.put_nowait(line)
            except Exception:
                pass
    except Exception:
        pass


def _hide_windows_console():
    """Hide the Windows console window when launched as a .py app.

    The live data that used to be printed to the CMD window is now shown in
    the SRVR Log tab. Set HV_P2P_KEEP_CONSOLE=1 to keep the console visible
    during development/debugging.
    """
    try:
        if os.name != "nt" or os.environ.get("HV_P2P_KEEP_CONSOLE") == "1":
            return
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
    except Exception:
        pass

# Standard UI fonts (tabs + headings)
FONT_SMALL = ("Segoe UI", 9)
FONT_SMALL_BOLD = ("Segoe UI", 9, "bold")
GRAPH_FONT = ("Segoe UI", 10)
GRAPH_FONT_BOLD = ("Segoe UI", 10, "bold")

# Standard tab layout constants - keep all Actions cards identical across tabs.
TAB_ACTIONS_W = 180
TAB_ACTIONS_H = 108
TAB_ACTIONS_COL_W = TAB_ACTIONS_W + 12
TAB_CARD_PADY = (3, 3)
TAB_HEADING_PADY = (4, 1)
TAB_ROW_PADY = (0, 1)
TAB_LABEL_PADX = (12, 6)
TAB_VALUE_PADX = (6, 12)
TAB_ACTION_BUTTON_PADY = (0, 2)
TAB_ACTION_STATUS_PADY = (1, 2)
PRESET_COUNT = 10

AUX_ACTION_OPTIONS = [
    "Accel Mode",
    "Battery Change",
    "Drive Mode",
    "Goto Far",
    "Goto Near",
    "Goto P1",
    "Goto P2",
    "Goto P3",
    "Goto P4",
    "Goto P5",
    "Goto P6",
    "Goto P7",
    "Goto P8",
    "Goto P9",
    "Goto P10",
    "Goto Ref",
    "Slip Far",
    "Slip Near",
    "Slip P1",
    "Slip P2",
    "Slip P3",
    "Slip P4",
    "Slip P5",
    "Slip P6",
    "Slip P7",
    "Slip P8",
    "Slip P9",
    "Slip P10",
    "Slip Ref",
    "Limit Calibration",
    "Winch Calibration",
]

# ------------------------------------------------------------
# Data classes / state
# ------------------------------------------------------------

@dataclass
class LimitPoint:
    name: str
    position_m: Optional[float] = None
    slip_offset_m: float = 0.0
    ramp_distance_m: Optional[float] = None  # metres
    ramp_mode: str = "Distance"              # "Distance" or "Percentage"
    ramp_percentage: Optional[float] = None  # if mode == "Percentage"

    def has_position(self) -> bool:
        return self.position_m is not None


@dataclass
class WinchState:
    pos_m: Optional[float] = None
    total_length_m: float = 100.0

    near_limit: LimitPoint = field(
        default_factory=lambda: LimitPoint("Near Limit", position_m=0.0)
    )
    ref_point: LimitPoint = field(
        default_factory=lambda: LimitPoint("Reference Point", position_m=50.0)
    )
    far_limit: LimitPoint = field(
        default_factory=lambda: LimitPoint("Far Limit", position_m=100.0)
    )

    ramp_zone_near: float = 5.0
    ramp_zone_far: float = 5.0

    estop_active: bool = False
    demo_mode: bool = False

    limit_reason: Optional[str] = None


@dataclass
class ConnectionStatus:
    connected: bool = False
    last_seen: float = 0.0
    last_error: Optional[str] = None


# ------------------------------------------------------------
# W1P UDP client/shared state
# ------------------------------------------------------------

W1P_PACKET_PREFIXES = ("STATUS", "HELLO", "PONG", "OK", "ERR", "W1PTS_AUX", "W1P_HMI_STATUS")

class ArduinoClient(threading.Thread):
    """UDP-based W1P client wrapper preserving the existing SRVR interface."""

    def __init__(
        self,
        host: str = "172.20.1.102",
        port: int = 5000,
        rx_queue: Optional[queue.Queue] = None,
        status_obj: Optional[ConnectionStatus] = None,
    ):
        super().__init__(daemon=True)
        self.host = host
        self.port = port
        self.rx_queue = rx_queue or queue.Queue(maxsize=500)
        self.status = status_obj or ConnectionStatus()
        self._stop_event = threading.Event()
        self._tx_queue: queue.Queue[str] = queue.Queue(maxsize=200)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setblocking(False)
        self._last_probe = 0.0

    def run(self):
        self.status.last_error = None
        while not self._stop_event.is_set():
            try:
                while True:
                    cmd = self._tx_queue.get_nowait()
                    payload = cmd if cmd.endswith("\n") else (cmd + "\n")
                    self._sock.sendto(payload.encode("ascii", errors="ignore"), (self.host, self.port))
            except queue.Empty:
                pass
            except Exception as e:
                self.status.last_error = str(e)

            # Periodic UDP probe so W1P learns the SRVR peer and returns STATUS.
            try:
                now = time.time()
                if (now - self._last_probe) >= WINCH_PROBE_INTERVAL_S:
                    self._last_probe = now
                    self._sock.sendto(b"STATUS\n", (self.host, self.port))
            except Exception as e:
                self.status.last_error = str(e)

            # Receive replies on the same UDP socket the W1P is replying to.
            try:
                while True:
                    data, addr = self._sock.recvfrom(4096)
                    if not data:
                        break
                    if addr[0] != self.host:
                        continue
                    line_text = data.decode("ascii", errors="ignore")
                    accepted = False
                    for raw_line in line_text.splitlines():
                        line = raw_line.strip()
                        if not line or not line.startswith(W1P_PACKET_PREFIXES):
                            continue
                        accepted = True
                        _queue_put_drop_oldest(self.rx_queue, line)
                    if accepted:
                        self.status.last_seen = time.time()
                        self.status.connected = True
                        self.status.last_error = None
            except BlockingIOError:
                pass
            except Exception as e:
                self.status.last_error = str(e)

            last_seen = float(self.status.last_seen or 0.0)
            self.status.connected = last_seen > 0 and ((time.time() - last_seen) <= WINCH_STATUS_TIMEOUT_S)
            time.sleep(0.02)

    def force_reconnect(self):
        self.status.connected = False
        self.status.last_seen = 0.0

    def stop(self):
        self._stop_event.set()
        try:
            self._sock.close()
        except Exception:
            pass

    def send(self, cmd: str):
        _queue_put_drop_oldest(self._tx_queue, cmd)

    def reconfigure(self, host: str, port: int):
        self.host = host
        self.port = port
        self.force_reconnect()


# ------------------------------------------------------------
# Controller Arduino UDP (heartbeat + joystick)
# ------------------------------------------------------------

SERVER_BIND_IP = "0.0.0.0"
SERVER_BIND_PORT = 5000
HEARTBEAT_CODE = 0xA5
HEARTBEAT_ACK = 0x5A
CONTROL_PACKET_CODE = 0xA6

# Controller flags bit definitions (from HV P2P CTRL Mk1)
# Bit 0: E-Stop pressed (1 = E-Stop engaged at controller)
# Bit 1: Cancel pressed (1 = request to cancel current motion / goto)
FLAG_ESTOP_PRESSED = 0x10
FLAG_CANCEL_PRESSED = 0x01
FLAG_MODE_TOGGLE = 0x02  # momentary button for drive mode toggle
FLAG_BATT_CHANGE_TOGGLE = 0x04  # momentary button to toggle Battery Change mode
FLAG_AUX1 = 0x20
FLAG_AUX2 = 0x40
FLAG_AUX3 = 0x80
FLAG_AUX4 = 0x0100
FLAG_ADS1115_FAULT = 0x0200  # CTRL reports ADS1115 interface missing/unhealthy


def _decode_controller_flags(flags: int) -> str:
    try:
        names = []
        if flags & FLAG_ESTOP_PRESSED:
            names.append("ESTOP")
        if flags & FLAG_CANCEL_PRESSED:
            names.append("CANCEL")
        if flags & FLAG_MODE_TOGGLE:
            names.append("MODE")
        if flags & FLAG_BATT_CHANGE_TOGGLE:
            names.append("BATT")
        if flags & FLAG_AUX1:
            names.append("AUX1")
        if flags & FLAG_AUX2:
            names.append("AUX2")
        if flags & FLAG_AUX3:
            names.append("AUX3")
        if flags & FLAG_AUX4:
            names.append("AUX4")
        if flags & FLAG_ADS1115_FAULT:
            names.append("ADS1115_FAULT")
        return ",".join(names) if names else "none"
    except Exception:
        return "?"


controller_events: queue.Queue = queue.Queue(maxsize=500)
controller_listener_stop = threading.Event()

controller_state = {
    "_rx_times": deque(maxlen=200),  # timestamps of recent CTRL packets
    "_connected": False,

    # Joystick calibration (raw -> percent)
    "joy_center": 0.0,
    "joy_min": -1.0,
    "joy_max": 1.0,
    "joystick_raw": 0.0,
    "connected": False,
    "last_seen": 0.0,
    "last_ip": None,
    "last_port": None,
    "flags": 0,
    "joystick": 0.0,
    "hmi_last_seen": 0.0,
    "hmi_connected_reported": False,
    "hmi_version": "",
    "hmi_age_ms": 999999,
    "ads1115_connected_reported": False,
    "ads1115_last_seen": 0.0,
}


def _parse_control_packet(packet: bytes):
    """
    Packet formats:
        Legacy A6:
            Byte 0: 0xA6
            Byte 1: flags (8-bit bitfield)
            Bytes 2-5: float32 joystick axis (-1.0 .. +1.0, big-endian)
            Bytes 6-7: reserved
        Extended A7:
            Byte 0: 0xA7
            Bytes 1-2: flags (16-bit big-endian bitfield)
            Bytes 3-6: float32 joystick axis (-1.0 .. +1.0, big-endian)
            Bytes 7-9: reserved
    """
    if not packet:
        return None

    code = packet[0]
    if code == CONTROL_PACKET_CODE:
        if len(packet) < 8:
            return None
        flags = int(packet[1])
        joystick = struct.unpack("!f", packet[2:6])[0]
    elif code == 0xA7:
        if len(packet) < 10:
            return None
        flags = (int(packet[1]) << 8) | int(packet[2])
        joystick = struct.unpack("!f", packet[3:7])[0]
    else:
        return None

    joystick = max(-1.0, min(1.0, joystick))

    return {
        "type": "controller_data",
        "flags": flags,
        "joystick": joystick,
    }



def _parse_kv_line(line: str) -> dict:
    out = {}
    try:
        parts = str(line or "").strip().split("|")
        for item in parts[1:]:
            if "=" in item:
                k, v = item.split("=", 1)
                out[k.strip()] = v.strip()
    except Exception:
        pass
    return out

def _controller_udp_listener():
    """Receive CTRL heartbeat/control/HMI packets on UDP 5000.

    A packet is counted exactly once. Earlier builds appended each CTRL packet
    twice and enqueued it twice, which defeated the two-packet stability test.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((SERVER_BIND_IP, SERVER_BIND_PORT))
        sock.settimeout(0.4)
    except OSError as exc:
        _app_log(f"[SRVR] Controller UDP bind failed {SERVER_BIND_IP}:{SERVER_BIND_PORT} -> {exc}")
        try:
            sock.close()
        except Exception:
            pass
        return

    while not controller_listener_stop.is_set():
        try:
            data, addr = sock.recvfrom(2048)
        except socket.timeout:
            continue
        except OSError:
            break
        if not data:
            continue
        ip, _port = addr
        try:
            if controller_expected_ip and ip != controller_expected_ip:
                continue
        except Exception:
            continue

        # Heartbeat ACK must use this bound listener socket.
        if data[0] == HEARTBEAT_CODE:
            try:
                sock.sendto(bytes([HEARTBEAT_ACK]), addr)
            except OSError:
                pass
            continue

        try:
            line_text = data.decode("ascii", errors="ignore").strip()
        except Exception:
            line_text = ""
        if line_text.startswith("HMI_STATUS|"):
            fields = _parse_kv_line(line_text)
            now_hmi = time.time()
            controller_state["hmi_last_seen"] = now_hmi
            controller_state["hmi_connected_reported"] = str(fields.get("ctrl_ts", "0")).strip() == "1"
            controller_state["hmi_version"] = fields.get("version", "")
            try:
                controller_state["hmi_age_ms"] = int(float(fields.get("age_ms", 999999)))
            except Exception:
                controller_state["hmi_age_ms"] = 999999
            controller_state["ads1115_connected_reported"] = str(fields.get("ads", fields.get("ads1115", "0"))).strip() == "1"
            controller_state["ads1115_last_seen"] = now_hmi
            continue

        msg = _parse_control_packet(data)
        if not msg:
            continue
        now_rx = time.time()
        try:
            controller_state["last_seen"] = now_rx
            controller_state["_rx_times"].append(now_rx)
            controller_state["last_ip"] = addr[0]
            controller_state["last_port"] = addr[1]
            controller_state["joystick_raw"] = float(msg.get("joystick_raw", msg.get("joystick", msg.get("axis", 0.0))) or 0.0)
            controller_state["joystick"] = float(_calibrate_joystick(controller_state["joystick_raw"]))
            controller_state["flags"] = int(msg.get("flags", 0))
            _queue_put_drop_oldest(controller_events, (now_rx, addr, msg))
            if CTRL_DEBUG_RX:
                t_last = float(controller_state.get("_dbg_last", 0.0) or 0.0)
                if (now_rx - t_last) >= CTRL_DEBUG_RX_PERIOD_S:
                    controller_state["_dbg_last"] = now_rx
                    _app_log(
                        f"[CTRL RX] ip={addr[0]} joystick_raw={controller_state['joystick_raw']:+.3f} "
                        f"flags=0x{controller_state['flags']:04X} ({_decode_controller_flags(controller_state['flags'])})"
                    )
        except Exception as exc:
            _app_log(f"[SRVR] CTRL packet handling error: {exc}")

    try:
        sock.close()
    except Exception:
        pass

def start_controller_udp_listener():
    controller_listener_stop.clear()
    t = threading.Thread(target=_controller_udp_listener, daemon=True)
    t.start()


def _calibrate_joystick(raw_value: float) -> float:
    """Map controller joystick value to -100..+100.

    CTRL sends an already-normalised -1.000..+1.000
    joystick axis.  Treat that directly as the source of truth so stale SRVR
    joystick calibration values cannot turn centre into +100%.  Older/raw
    controller values outside that range still use the saved min/centre/max
    calibration path.
    """
    try:
        v = float(raw_value)

        # New CTRL normalised protocol path. Apply the SRVR deadband here as
        # well as in the motion path so a small start-up centre offset never
        # appears as live joystick movement in the GUI or logs.
        if -1.05 <= v <= 1.05:
            pct = max(-100.0, min(100.0, v * 100.0))
            return 0.0 if abs(pct) < JOY_DEADBAND_PCT else pct

        # Legacy/raw calibration path.
        c = float(controller_state.get("joy_center", 0.0) or 0.0)
        mn = float(controller_state.get("joy_min", -1.0) or -1.0)
        mx = float(controller_state.get("joy_max", 1.0) or 1.0)

        if not (mn < c < mx):
            return max(-100.0, min(100.0, v))

        if v >= c:
            span = max(1e-6, (mx - c))
            pct = (v - c) * 100.0 / span
            return max(0.0, min(100.0, pct))
        else:
            span = max(1e-6, (c - mn))
            pct = (c - v) * 100.0 / span
            return -max(0.0, min(100.0, pct))
    except Exception:
        return 0.0


def _normalize_joy_cal(cal: dict | None) -> dict:
    default = {"min": -1.0, "center": 0.0, "max": 1.0}
    if not isinstance(cal, dict):
        return default
    try:
        mn = float(cal.get("min", -1.0))
        c = float(cal.get("center", 0.0))
        mx = float(cal.get("max", 1.0))
    except Exception:
        return default

    # Migrate older placeholder defaults that used +/-100 while the controller sends -1..+1.
    if abs(mn + 100.0) < 1e-6 and abs(c) < 1e-6 and abs(mx - 100.0) < 1e-6:
        return default

    if not (mn < c < mx):
        return default
    return {"min": mn, "center": c, "max": mx}


def get_controller_status():
    now = time.time()
    rx = controller_state.get("_rx_times")
    if rx is None:
        rx = deque(maxlen=200)
        controller_state["_rx_times"] = rx

    try:
        while rx and (now - rx[0]) > CTRL_RX_WINDOW_S:
            rx.popleft()
    except Exception:
        pass

    pkt_count = len(rx) if rx else 0
    connected = pkt_count >= CTRL_RX_MIN_PKTS
    controller_state["_connected"] = connected

    last_seen = float(controller_state.get("last_seen", 0.0) or 0.0)
    age_s = (now - last_seen) if last_seen > 0 else 9999.0

    joystick = float(controller_state.get("joystick", 0.0) or 0.0)
    joystick_raw = float(controller_state.get("joystick_raw", joystick) or 0.0)
    flags = int(controller_state.get("flags", 0) or 0)
    hmi_last_seen = float(controller_state.get("hmi_last_seen", 0.0) or 0.0)
    hmi_status_age_s = (now - hmi_last_seen) if hmi_last_seen > 0 else 9999.0
    hmi_connected = bool(controller_state.get("hmi_connected_reported", False)) and hmi_status_age_s <= 3.5
    ads_last_seen = float(controller_state.get("ads1115_last_seen", 0.0) or 0.0)
    ads_status_age_s = (now - ads_last_seen) if ads_last_seen > 0 else 9999.0
    # v26.06.26.25: ADS1115 health must be explicit. A live CTRL packet stream
    # no longer implies that the external ADS1115 interface is healthy.
    ads1115_status_known = ads_last_seen > 0 and ads_status_age_s <= 2.0
    ads1115_connected = bool(controller_state.get("ads1115_connected_reported", False)) and ads1115_status_known

    return {
        "connected": connected,
        "age_s": age_s,
        "pkt_count": pkt_count,
        "last_ip": controller_state.get("last_ip"),
        "last_port": controller_state.get("last_port"),
        "expected_ip": controller_expected_ip,
        "joystick": joystick,
        "joystick_raw": joystick_raw,
        "flags": flags,
        "hmi_connected": hmi_connected,
        "hmi_status_age_s": hmi_status_age_s,
        "hmi_version": controller_state.get("hmi_version", ""),
        "hmi_age_ms": controller_state.get("hmi_age_ms", 999999),
        "ads1115_connected": ads1115_connected,
        "ads1115_status_known": ads1115_status_known,
        "ads1115_status_age_s": ads_status_age_s,
    }


def _controller_axis_normalized(status: dict | None = None) -> tuple[float, float]:
    """Return joystick as (normalized -1..+1, percent -100..+100)."""
    try:
        cs = status if isinstance(status, dict) else get_controller_status()
        axis_pct = float(cs.get("joystick", 0.0) or 0.0)
    except Exception:
        axis_pct = 0.0
    axis_pct = max(-100.0, min(100.0, axis_pct))
    axis = max(-1.0, min(1.0, axis_pct / 100.0))
    return axis, axis_pct

# ------------------------------------------------------------
# Main Tkinter App
# ------------------------------------------------------------

class HVP2PServerApp:

    def _on_any_button_release(self, event=None):
        """Auto-save configuration whenever an Apply button is clicked."""
        try:
            w = event.widget
            try:
                txt = str(w.cget("text"))
            except Exception:
                return
            if txt != "Apply":
                return
            try:
                self.root.after(80, self.on_save_config)
            except Exception:
                self.on_save_config()
        except Exception:
            pass

    def __init__(self, root: tk.Tk):
        self.root = root

        try:
            self.root.bind_all("<ButtonRelease-1>", self._on_any_button_release, add="+")
        except Exception:
            pass
        # Standardise button font sizing
        style = ttk.Style()
        # Standard small font across tabs (and most UI)
        try:
            for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkCaptionFont", "TkSmallCaptionFont", "TkIconFont", "TkTooltipFont"):
                f = tkfont.nametofont(name)
                f.configure(family="Segoe UI", size=9)
        except Exception:
            pass

        style.configure("TButton", font=FONT_SMALL)
        style.configure("TLabel", font=FONT_SMALL)
        style.configure("TCheckbutton", font=FONT_SMALL)
        style.configure("TRadiobutton", font=FONT_SMALL)
        style.configure("TEntry", font=FONT_SMALL)
        style.configure("TCombobox", font=FONT_SMALL)
        style.configure("Heading.TLabel", font=FONT_SMALL_BOLD)

        try:
            _prog_name = os.path.splitext(os.path.basename(__file__))[0].replace("_", " ")
        except Exception:
            _prog_name = "HV P2P SRVR"
        root.title(_prog_name)
        root.configure(bg="#000000")

        # Keep the native ttk tab/button styling.
        # Do not force the ttk clam theme here; it changes the Run / Setup / Free-D tab appearance.
        style = ttk.Style(root)
        style.configure("TButton", font=FONT_SMALL)
        style.configure("RunAux.TButton", font=FONT_SMALL, padding=(4, 1))

        # File menu for configuration management
        menubar = tk.Menu(root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Save Config", command=self.on_save_as_config)
        file_menu.add_command(label="Load Config", command=self.on_load_config_dialog)
        menubar.add_cascade(label="File", menu=file_menu)
        root.config(menu=menubar)
        try:
            root.protocol("WM_DELETE_WINDOW", self._on_close)
        except Exception:
            pass

        # Try to go fullscreen / maximised
        try:
            root.state("zoomed")
        except Exception:
            try:
                root.attributes("-zoomed", True)
            except Exception:
                root.attributes("-fullscreen", True)

        # Main content frame
        self.main_frame = tk.Frame(root, bg="#111111")
        self.main_frame.pack(side="top", fill="both", expand=True)

        # Configure rows: 0=E-stop,1=Free-D Top View,2=Free-D Side View,3=Tabs,4=Connections,5=Status
        for r, weight in enumerate([0, 1, 1, 0, 0, 0]):
            self.main_frame.rowconfigure(r, weight=weight)
        self.main_frame.columnconfigure(0, weight=1)

        # Core state
        self.state = WinchState()
        self.arduino_status = ConnectionStatus()
        self.arduino_rx = queue.Queue(maxsize=500)

        self.current_speed_mps = 0.0       # actual W1P/drive feedback speed
        self.requested_speed_mps = 0.0       # raw SRVR target sent to W1P
        self.profile_speed_mps = 0.0         # W1P profiled target
        self.drive_command_speed_mps = 0.0   # final W1P command sent to EL7
        self.display_speed_mps = 0.0
        self._last_display_pos_m = None
        self._last_display_pos_t = time.time()
        self._last_display_abs_pos_m = None
        self._last_display_abs_pos_t = time.time()
        self.max_speed_mps = 20.0
        self.max_accel_mps2 = 2.0
        self.max_decel_mps2 = 2.0
        self.max_crossover_mps2 = 4.0
        self.max_stop_decel_mps2 = 4.0
        self.goto_speed_mps = 1.0

        # Drive modes (2 profiles for speed/accel/decel/crossover)
        self.drive_modes = [
            {
                "name": "Mode 1",
                "max_speed_mps": float(self.max_speed_mps),
                "max_goto_speed_mps": float(getattr(self, "goto_speed_mps", min(self.max_speed_mps, 1.0))),
                "max_accel_mps2": float(getattr(self, "max_accel_mps2", 2.0)),
                "max_decel_mps2": float(getattr(self, "max_decel_mps2", 2.0)),
                "max_crossover_mps2": float(getattr(self, "max_crossover_mps2", 4.0)),
                "max_stop_decel_mps2": float(getattr(self, "max_stop_decel_mps2", getattr(self, "max_decel_mps2", 2.0))),
            },
            {
                "name": "Mode 2",
                "max_speed_mps": float(self.max_speed_mps),
                "max_goto_speed_mps": float(getattr(self, "goto_speed_mps", min(self.max_speed_mps, 1.0))),
                "max_accel_mps2": float(getattr(self, "max_accel_mps2", 2.0)),
                "max_decel_mps2": float(getattr(self, "max_decel_mps2", 2.0)),
                "max_crossover_mps2": float(getattr(self, "max_crossover_mps2", 4.0)),
                "max_stop_decel_mps2": float(getattr(self, "max_stop_decel_mps2", getattr(self, "max_decel_mps2", 2.0))),
            },
        ]
        self.active_drive_mode = 0
        self.battery_change_mode = False
        self.system_calibration_mode = False
        self._system_calibration_aux_step = 0
        self.winch_calibration_mode = False
        self._winch_calibration_aux_step = 0
        self._winch_calibration_zero_raw = None
        self._winch_calibration_zero_pos_m = None
        self.winch_raw_pos_units = 0
        self.not_calibrated_mode = True
        self._system_calibration_popup = None
        self._system_calibration_step = 0
        self._system_calibration_aux_step = 0
        self.accel_type = getattr(self, 'accel_type', 'Dynamic')
        self.goto_target_m = None
        self.goto_speed_fraction = 0.5

        # Default connection parameters
        self.winch_host = "172.20.1.102"
        self.winch_port = 5000
        self.controller_ip_ref = "172.20.1.101"
        self.ctrl_ts_ip_ref = ""  # Waveshare HMI is UART via CTRL in WS-HMI architecture
        self.w1pts_last_seen = 0.0
        self.w1pts_connected_reported = False
        self.w1pts_version = ""
        self.w1pts_age_ms = 999999
        self._ctrl_estop_active = False
        self._w1p_estop_active = False
        self._srvr_estop_latched = False
        self._last_estop_source = "SRVR"

        # Direction inversion flags
        self.reverse_joystick = False
        self.reverse_motor = False
        self.last_controller_value = 0.0
        self.last_winch_output = 0.0
        self.controller_type = "HV P2P CTRL Mk1"
        self.winch_type = "HV P2P W1P"
        self.winch_units_per_m = 21220.7
        self.winch_pos_source = "--"
        self.winch_rs_status = "Disconnected"
        self.winch_leadshine_config = "--"
        self.winch_drive_writes_enabled = False
        self.ctrl_display_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._last_ctrl_display_tx = 0.0
        self._last_ctrl_display_repeat_tx = 0.0
        self._last_ctrl_display_pkt = b""
        self._last_ctrl_display_change_tx = 0.0
        self._winch_position_accept_jump_until = 0.0
        self._winch_last_pos_accept_t = 0.0
        self._winch_last_pos_reject_log_t = 0.0

        # Free-D defaults.  Leadshine encoder position is mapped to X tracking.
        # Y is calculated height above ground from up to 5 user-entered points and
        # the Skate/Cable/Tension sag model.  Z is the top-view / camera offset axis.  ShotOver Free-D input can
        # supply Camera ID, Pan, Tilt, Roll, Zoom, Focus, and measured FPS.
        self.freed_output_enabled = False
        self.freed_target_ip = "172.20.1.120"
        self.freed_target_port = 40000
        self.freed_camera_id = 1
        self.freed_rate_hz = 25.0
        self.freed_z_offset_m = float(getattr(self, "freed_x_m", 0.0) or 0.0)  # migrated from earlier X Offset field
        self.freed_pan = 0.0
        self.freed_tilt = 0.0
        self.freed_roll = 0.0
        self.freed_zoom = 0
        self.freed_focus = 0
        self.freed_pos_scale = 640.0  # Free-D position counts per metre
        # Active sag estimate inputs. Skate weight is the total suspended camera
        # package. Cable weight and tension are entered per individual highline.
        # Dual Highline mode shares the package load equally between two lines.
        self.freed_skate_weight_kg = 35.0
        self.freed_weight_per_100m_kg = 4.8
        self.freed_sag_tension_kgf = 1200.0
        self.freed_highline_mode = "Single Highline"
        self.freed_input_enabled = True
        self.freed_input_bind_ip = "0.0.0.0"
        self.freed_input_port = 40001
        # User-facing Invert checkboxes default OFF.  Native Free-D Pan and Focus
        # directions are corrected in code so the UI checkboxes stay consistent across channels.
        self.freed_input_inverts = {"Pan": False, "Tilt": False, "Roll": False, "Zoom": False, "Focus": False}
        # Per-axis offsets are applied after input invert / before display and packet output, to set the camera/skate home.
        self.freed_input_offsets = {"Pan": 0.0, "Tilt": 0.0, "Roll": 0.0}
        # Output axis inversion only affects the generated Free-D X/Y/Z tracking packet.
        self.freed_output_inverts = {"X": False, "Y": False, "Z": False}
        self.freed_output_offsets = {"X": 0.0, "Y": 0.0, "Z": 0.0}
        self.freed_input_timeout_s = 2.0
        self.freed_in_camera_id = 1
        self.freed_in_pan = 0.0
        self.freed_in_tilt = 0.0
        self.freed_in_roll = 0.0
        self.freed_in_zoom = 0
        self.freed_in_focus = 0
        self.freed_in_fps = 0.0
        self.freed_input_last_rx = 0.0
        self.freed_input_last_addr = "--"
        self._freed_input_lock = threading.Lock()
        self._freed_input_sock = None
        self._freed_input_thread = None
        self._freed_input_stop = threading.Event()
        self._freed_input_fps_times = deque(maxlen=120)
        self.freed_in_raw_camera_id = 0
        self.freed_in_raw_pan = 0
        self.freed_in_raw_tilt = 0
        self.freed_in_raw_roll = 0
        self.freed_in_raw_zoom = 0
        self.freed_in_raw_focus = 0
        self.freed_in_raw_fps = 0.0

        # Free-D lens calibration for Run-tab lens bars.
        self.freed_lens_type = "i24"
        self.freed_lens_scale_mode = "Auto"
        self.freed_lens_cal = {
            "zoom_wide": -8388608.0,
            "zoom_tele": 8388607.0,
            "focus_near": -8388608.0,
            "focus_far": 8388607.0,
        }
        self._freed_lens_auto_seen = {
            "zoom_min": None,
            "zoom_max": None,
            "focus_min": None,
            "focus_max": None,
        }
        # Persist Auto lens scaling.  Earlier builds learned the Auto Zoom/Focus
        # min/max range only in RAM, so closing and reopening SRVR could make the
        # Run-tab lens bars revert until the lens had been swept again.
        self._freed_lens_auto_last_save_s = 0.0
        self.freed_out_fps = 0.0
        self._freed_output_fps_times = deque(maxlen=240)
        self._freed_output_thread = None
        self._freed_output_stop = threading.Event()
        self.freed_height_points = [
            {"enabled": True, "y_m": 0.0, "z_m": 0.0},
            {"enabled": False, "y_m": 25.0, "z_m": 0.0},
            {"enabled": True, "y_m": 50.0, "z_m": 0.0},
            {"enabled": False, "y_m": 75.0, "z_m": 0.0},
            {"enabled": True, "y_m": 100.0, "z_m": 0.0},
        ]
        self.freed_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._last_freed_tx = 0.0


        # Preset positions (6 slots, None = not set)
        self.preset_positions: list[float | None] = [None] * PRESET_COUNT
        self.preset_labels: list[tk.Label] = []
        self.preset_show_buttons: list[ttk.Button] = []
        self.preset_visible: list[bool] = [False] * PRESET_COUNT
        # Preset names (editable), default P1..P6
        self.preset_names: list[str] = [f"P{i+1}" for i in range(PRESET_COUNT)]
        self.preset_name_vars: list[tk.StringVar] = []

        # Config file path (auto-save & auto-load)
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        except NameError:
            base_dir = os.getcwd()
        self.config_path = os.path.join(base_dir, "config.json")
        self.default_config_path = self.config_path

        # Attempt to load last configuration
        self._load_config()
        # Free-D Input On/Off is controlled by the Free-D tab and saved in config.

        # Always start in a safe startup state until the operator re-establishes
        # where the system is physically located on the cable span.
        self.not_calibrated_mode = True

        # Winch Arduino client (TCP) uses possibly updated host/port
        self.arduino_client = ArduinoClient(
            host=self.winch_host,
            port=self.winch_port,
            rx_queue=self.arduino_rx,
            status_obj=self.arduino_status,
        )
        self.arduino_client.start()

        # Controller Arduino (UDP)
        start_controller_udp_listener()

        self.last_sent_vel = 0.0

        # Build UI
        self._build_layout()

        self._sync_limits_to_winch()
        # W1P now auto-enables drive command writes when SRVR, RS485, config, feedback and SRDY are healthy.
        self._enter_not_calibrated_mode()

        # Start timers
        self._start_timers()

        # Ensure a config file exists with current settings
        self._save_config()

    def _on_close(self):
        """Stop background UDP threads and close the SRVR window cleanly.

        Closing SRVR is treated as an SRVR E-stop source.  Send a best-effort
        STOP and software Servo Enable OFF before shutting the UDP client down.
        W1P also has its own peer-timeout fail-safe, so Servo Enable will still
        drop even if this final packet is missed.
        """
        try:
            client = getattr(self, "arduino_client", None)
            if client is not None:
                try:
                    client.send("STOP")
                except Exception:
                    pass
                try:
                    client.send("SW_SRVON 0")
                except Exception:
                    pass
                try:
                    time.sleep(0.08)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            self._save_config()
        except Exception:
            pass
        try:
            controller_listener_stop.set()
        except Exception:
            pass
        try:
            client = getattr(self, "arduino_client", None)
            if client is not None:
                client.stop()
                client.join(timeout=0.5)
        except Exception:
            pass
        try:
            self._freed_output_stop.set()
        except Exception:
            pass
        try:
            self._freed_input_stop.set()
        except Exception:
            pass
        for sock_name in ("_freed_input_sock", "freed_sock", "ctrl_display_sock"):
            try:
                sock = getattr(self, sock_name, None)
                if sock is not None:
                    sock.close()
            except Exception:
                pass
        try:
            self.root.destroy()
        except Exception:
            pass

    # ---------------- Layout ----------------

    def _build_layout(self):
        self.main_frame.configure(bg="#111111")
        # Layout rows already configured in __init__
        self._build_estop_bar()          # row 0
        self._build_freed_top_view()     # row 1 - replaces original progress bar
        self._build_freed_side_view()    # row 2 - Free-D side view
        self._build_tabs_section()       # row 3
        self._build_connections_row()    # row 4
        self._build_status_bar()         # row 5

    def _build_estop_bar(self):
        # Fixed-height, one-line safety banner. Use an explicit placed label
        # and cached updates so the 50 ms SRVR refresh loop cannot redraw a
        # flashing yellow/red three-band bar above the Top View graph.
        bar_h = 34
        bar = tk.Frame(self.main_frame, bg="#802020", height=bar_h)
        bar.grid(row=0, column=0, sticky="ew")
        bar.grid_propagate(False)
        bar.bind("<Button-1>", self.on_estop_clicked)
        try:
            self.main_frame.rowconfigure(0, minsize=bar_h, weight=0)
        except Exception:
            pass

        self.estop_label = tk.Label(
            bar,
            text="Status | E-Stop",
            fg="white",
            bg="#802020",
            font=("Segoe UI", 15, "bold"),
            anchor="center",
            justify="center",
            wraplength=0,
            bd=0,
            padx=0,
            pady=0,
        )
        self.estop_label.place(x=0, y=0, relwidth=1.0, relheight=1.0)
        self.estop_label.bind("<Button-1>", self.on_estop_clicked)
        self.estop_frame = bar
        self._estop_bar_cached = ("Status | E-Stop", "#802020")


    def _build_freed_top_view(self):
        """Free-D top view replacing the original progress bar section."""
        frame = tk.Frame(self.main_frame, bg="#111111", height=260)
        frame.grid(row=1, column=0, sticky="nsew", padx=12, pady=(4, 4))
        frame.grid_propagate(False)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        header = tk.Frame(frame, bg="#1a1a1a", highlightbackground="#2f2f2f", highlightthickness=1)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        header.columnconfigure(1, weight=0)

        tk.Label(
            header,
            text="Top View: X (Tracking) / Z (Offset)",
            fg="#eeeeee",
            bg="#1a1a1a",
            font=("Segoe UI", 12, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(6, 2))

        self.freed_top_live_var = tk.StringVar(value="")
        # Header live values are hidden to keep the tracking view clean.

        self.freed_top_canvas = tk.Canvas(frame, bg="#202020", highlightthickness=0)
        self.freed_top_canvas.grid(row=1, column=0, sticky="nsew")
        self.freed_top_canvas.bind("<Configure>", lambda e: self._redraw_freed_top_view())


    def _build_freed_side_view(self):
        """Centre Free-D side-view display."""
        frame = tk.Frame(self.main_frame, bg="#111111", height=260)
        frame.grid(row=2, column=0, sticky="nsew", padx=12, pady=(4, 4))
        frame.grid_propagate(False)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        header = tk.Frame(frame, bg="#1a1a1a", highlightbackground="#2f2f2f", highlightthickness=1)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        header.columnconfigure(1, weight=0)

        tk.Label(
            header,
            text="Side View: X (Tracking) / Y (Sag)",
            fg="#eeeeee",
            bg="#1a1a1a",
            font=("Segoe UI", 12, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(6, 2))

        self.freed_live_var = tk.StringVar(value="")
        # Header live values are hidden to keep the tracking view clean.

        self.freed_canvas = tk.Canvas(frame, bg="#202020", highlightthickness=0)
        self.freed_canvas.grid(row=1, column=0, sticky="nsew")
        self.freed_canvas.bind("<Configure>", lambda e: self._redraw_freed_side_view())

    def _freed_valid_height_points(self):
        pts = []
        try:
            for p in getattr(self, "freed_height_points", []) or []:
                if not isinstance(p, dict):
                    continue
                if not bool(p.get("enabled", True)):
                    continue
                y = float(p.get("y_m", 0.0))
                z = float(p.get("z_m", 0.0))
                pts.append((y, z))
        except Exception:
            pts = []
        pts.sort(key=lambda v: v[0])
        return pts

    def _freed_base_height_for_x(self, x_m: float) -> float:
        """Piecewise-linear height reference from the enabled X/Y points."""
        pts = self._freed_valid_height_points()
        if not pts:
            return 0.0
        if len(pts) == 1:
            return float(pts[0][1])
        x = float(x_m)
        if x <= pts[0][0]:
            return float(pts[0][1])
        if x >= pts[-1][0]:
            return float(pts[-1][1])
        for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
            if x0 <= x <= x1:
                span = max(1e-9, float(x1) - float(x0))
                t = (x - float(x0)) / span
                return float(y0) + (float(y1) - float(y0)) * t
        return float(pts[-1][1])

    def _freed_estimated_sag_drop(self, x_m: float) -> float:
        """Return whole-span cable sag at *x_m* in metres.

        The configured Y points define the unsagged/reference height profile.
        Sag is then applied once across the complete highline span rather than
        being restarted between each enabled point. Cable self-weight produces
        one continuous parabolic component. The camera package is treated as a
        point load at the live skate position, producing two continuous straight
        load-deflection segments that meet at the skate. This prevents an
        enabled mid-span height point from creating a false W-shaped cable.
        """
        try:
            pts = self._freed_valid_height_points()
            if len(pts) >= 2:
                support_x0 = float(pts[0][0])
                support_x1 = float(pts[-1][0])
            else:
                support_x0 = 0.0
                try:
                    support_x1 = max(1.0, float(self._limit_display_position_m(self.state.far_limit)))
                except Exception:
                    support_x1 = max(1.0, float(getattr(self.state, "total_length_m", 100.0) or 100.0))

            if support_x1 < support_x0:
                support_x0, support_x1 = support_x1, support_x0
            span_m = max(1e-6, support_x1 - support_x0)
            x = float(x_m)
            if x <= support_x0 or x >= support_x1:
                return 0.0
            x = max(support_x0, min(support_x1, x))

            rope_kg_m = max(0.0, float(getattr(self, "freed_weight_per_100m_kg", 4.8) or 0.0)) / 100.0
            skate_total_kg = max(0.0, float(getattr(self, "freed_skate_weight_kg", 35.0) or 0.0))
            tension_per_line = max(1.0, float(getattr(self, "freed_sag_tension_kgf", 1200.0) or 1200.0))
            highline_mode = str(getattr(self, "freed_highline_mode", "Single Highline") or "Single Highline").strip().lower()
            line_count = 2.0 if highline_mode.startswith("dual") else 1.0
            skate_per_line_kg = skate_total_kg / line_count

            # Uniform cable self-weight over the full support-to-support span.
            left_m = x - support_x0
            right_m = support_x1 - x
            cable_drop = (rope_kg_m * left_m * right_m) / (2.0 * tension_per_line)

            # Point-load deflection caused by the camera package at its live X.
            # Use the tracking position directly to avoid recursively asking for
            # the already sag-adjusted Free-D XYZ value.
            try:
                skate_x = float(self._display_position_relative_m()) + self._freed_output_offset_value("X")
            except Exception:
                skate_x = float(getattr(self.state, "pos_m", support_x0) or support_x0)
            skate_x = max(support_x0, min(support_x1, skate_x))

            if x <= skate_x:
                skate_drop = (skate_per_line_kg * (x - support_x0) * (support_x1 - skate_x)) / (tension_per_line * span_m)
            else:
                skate_drop = (skate_per_line_kg * (skate_x - support_x0) * (support_x1 - x)) / (tension_per_line * span_m)

            return max(0.0, cable_drop + skate_drop)
        except Exception:
            return 0.0

    def _freed_z_for_y(self, y_m: float) -> float:
        # Historical method name retained for compatibility. It now returns the
        # sag-adjusted Side View Y value for tracking position X.
        return self._freed_base_height_for_x(y_m) - self._freed_estimated_sag_drop(y_m)

    def _freed_z_offset_for_x(self, x_m: float) -> float:
        """Interpolate the top-view Z offset between Point 1 and Point 5."""
        try:
            pts = list(getattr(self, "freed_height_points", []) or [])
            if len(pts) >= 5:
                p0 = pts[0] if isinstance(pts[0], dict) else {}
                p5 = pts[4] if isinstance(pts[4], dict) else {}
                x0 = float(p0.get("y_m", 0.0))
                x1 = float(p5.get("y_m", max(1.0, float(getattr(self.state, "total_length_m", 100.0) or 100.0))))
                z0 = float(p0.get("z_offset_m", getattr(self, "freed_z_offset_m", 0.0)))
                z1 = float(p5.get("z_offset_m", getattr(self, "freed_z_offset_m", z0)))
                if abs(x1 - x0) < 1e-9:
                    return z0
                t = max(0.0, min(1.0, (float(x_m) - x0) / (x1 - x0)))
                return z0 + (z1 - z0) * t
        except Exception:
            pass
        try:
            return float(getattr(self, "freed_z_offset_m", getattr(self, "freed_x_m", 0.0)) or 0.0)
        except Exception:
            return 0.0

    def _freed_output_offset_value(self, name: str) -> float:
        try:
            return float(dict(getattr(self, "freed_output_offsets", {}) or {}).get(str(name), 0.0) or 0.0)
        except Exception:
            return 0.0

    def _freed_input_offset_value(self, name: str) -> float:
        try:
            return float(dict(getattr(self, "freed_input_offsets", {}) or {}).get(str(name), 0.0) or 0.0)
        except Exception:
            return 0.0

    def _current_freed_xyz(self):
        # Free-D coordinate mapping for HV P2P SYS:
        # X = tracking position along cable span from Near=0m to Far=positive.
        #     The X offset moves the skate/camera home position on both graphs.
        # Y = calculated height above ground from configured cable height points
        #     plus one continuous whole-span Skate/Cable/Tension sag model,
        #     with a final Y offset for height/home trimming.
        # Z = interpolated camera offset for the top-view offset axis, with final Z offset.
        try:
            base_x = float(self._display_position_relative_m())
        except Exception:
            try:
                base_x = float(getattr(self.state, "pos_m", 0.0) or 0.0)
            except Exception:
                base_x = 0.0
        x = base_x + self._freed_output_offset_value("X")
        y = self._freed_z_for_y(x) + self._freed_output_offset_value("Y")
        try:
            z = self._freed_z_offset_for_x(x) + self._freed_output_offset_value("Z")
        except Exception:
            z = self._freed_output_offset_value("Z")
        return x, y, z


    def _freed_motion_for_display(self):
        """Return current Free-D motion values for display overlays."""
        try:
            cam_id, pan, tilt, roll, zoom, focus = self._current_freed_input_motion()
            return int(cam_id), float(pan), float(tilt), float(roll), int(zoom), int(focus)
        except Exception:
            return 0, 0.0, 0.0, 0.0, 0, 0

    @staticmethod
    def _freed_u24_to_int(b: bytes) -> int:
        if len(b) < 3:
            return 0
        return (int(b[0]) << 16) | (int(b[1]) << 8) | int(b[2])

    def _lens_type_limits(self, lens_type: str | None = None) -> tuple[float, float]:
        t = str(lens_type or getattr(self, "freed_lens_type", "i24")).strip().lower()
        if t == "u16":
            return 0.0, 65535.0
        if t == "i16":
            return -32768.0, 32767.0
        if t == "u24":
            return 0.0, 16777215.0
        return -8388608.0, 8388607.0

    def _decode_lens_raw_value(self, signed24: int, unsigned24: int) -> int:
        """Decode Free-D zoom/focus according to the selected lens calibration data type."""
        t = str(getattr(self, "freed_lens_type", "i24")).strip().lower()
        try:
            u24 = int(unsigned24) & 0xFFFFFF
            s24 = int(signed24)
            if t == "u24":
                return u24
            if t == "u16":
                return u24 & 0xFFFF
            if t == "i16":
                v = u24 & 0xFFFF
                if v & 0x8000:
                    v -= 0x10000
                return v
            return s24
        except Exception:
            return int(signed24 or 0)

    def _lens_full_limits_for_current_type(self) -> tuple[float, float]:
        return self._lens_type_limits(getattr(self, "freed_lens_type", "i24"))

    def _lens_get_endpoint_pair(self, field: str) -> tuple[float, float]:
        cal = dict(getattr(self, "freed_lens_cal", {}) or {})
        lo_default, hi_default = self._lens_full_limits_for_current_type()
        if field == "zoom":
            return float(cal.get("zoom_wide", lo_default)), float(cal.get("zoom_tele", hi_default))
        return float(cal.get("focus_near", lo_default)), float(cal.get("focus_far", hi_default))

    def _lens_norm(self, field: str, value: float) -> float:
        """Return 0..1 lens position for Zoom/Focus bars using Full scale, Manual, or Auto."""
        try:
            field = "zoom" if str(field).lower().startswith("zoom") else "focus"
            value = float(value or 0.0)
            mode = str(getattr(self, "freed_lens_scale_mode", "Auto") or "Auto").strip().lower()
            if mode.startswith("full"):
                lo, hi = self._lens_full_limits_for_current_type()
            elif mode.startswith("auto"):
                seen = getattr(self, "_freed_lens_auto_seen", {}) or {}
                lo = seen.get(f"{field}_min")
                hi = seen.get(f"{field}_max")
                if lo is None or hi is None or abs(float(hi) - float(lo)) < 1e-9:
                    lo, hi = self._lens_get_endpoint_pair(field)
            else:
                lo, hi = self._lens_get_endpoint_pair(field)
            lo, hi = float(lo), float(hi)
            if abs(hi - lo) < 1e-9:
                return 0.0
            return max(0.0, min(1.0, (value - lo) / (hi - lo)))
        except Exception:
            return 0.0

    def _lens_norm_for_display(self, field: str, value: float) -> float:
        """Return 0..1 lens position for Run-tab percentage bars, with endpoint snap.

        The live lens values can jitter by a few counts at the physical Wide/Tele or
        Near/Far limits, which previously showed values like 0.018% or 99.983%
        even when the lens was sitting on its calibrated end stop. Keep the normal
        calibrated scaling through the travel, but snap tiny endpoint errors so the
        display reaches true 0.000% and 100.000%.
        """
        try:
            n = float(self._lens_norm(field, value))
            # 0.05% deadband at each end: enough to clean endpoint jitter without
            # hiding meaningful movement through the active lens range.
            if n <= 0.0005:
                return 0.0
            if n >= 0.9995:
                return 1.0
            return max(0.0, min(1.0, n))
        except Exception:
            return 0.0

    def _remember_lens_auto_value(self, field: str, value: float):
        try:
            mode = str(getattr(self, "freed_lens_scale_mode", "Auto") or "Auto").strip().lower()
            if not mode.startswith("auto"):
                return
            field = "zoom" if str(field).lower().startswith("zoom") else "focus"
            seen = getattr(self, "_freed_lens_auto_seen", None)
            if not isinstance(seen, dict):
                seen = {}
                self._freed_lens_auto_seen = seen
            mn_key, mx_key = f"{field}_min", f"{field}_max"
            v = float(value or 0.0)
            old_min = seen.get(mn_key)
            old_max = seen.get(mx_key)
            new_min = v if old_min is None else min(float(old_min), v)
            new_max = v if old_max is None else max(float(old_max), v)
            changed = (old_min is None or abs(float(new_min) - float(old_min)) > 1e-9 or
                       old_max is None or abs(float(new_max) - float(old_max)) > 1e-9)
            seen[mn_key] = new_min
            seen[mx_key] = new_max
            # Save the learned Auto scale periodically so the same Zoom/Focus
            # scaling is restored after SRVR is closed and reopened.
            if changed:
                now = time.time()
                if (now - float(getattr(self, "_freed_lens_auto_last_save_s", 0.0) or 0.0)) >= 2.0:
                    self._freed_lens_auto_last_save_s = now
                    try:
                        self.root.after(0, self._save_config)
                    except Exception:
                        self._save_config()
        except Exception:
            pass

    def _current_lens_value(self, field: str) -> float:
        """Return the current lens value used by the Lens Calibration capture buttons.

        This reads the live Free-D lens fields directly when input is fresh, so the
        Zoom Wide/Tele and Focus Near/Far buttons capture the values that are visibly
        changing in the Run tab.  Focus still uses the native code inversion, while
        the visible Invert checkbox can remain OFF.
        """
        try:
            is_zoom = str(field).lower().startswith("zoom")
            if bool(getattr(self, "freed_input_enabled", False)) and self._freed_input_recent():
                with self._freed_input_lock:
                    if is_zoom:
                        return float(int(getattr(self, "freed_in_zoom", 0) or 0) * self._freed_input_sign("Zoom"))
                    return float(int(getattr(self, "freed_in_focus", 0) or 0) * self._freed_input_sign("Focus"))
            if is_zoom:
                return float(int(getattr(self, "freed_zoom", 0) or 0) * self._freed_input_sign("Zoom"))
            return float(int(getattr(self, "freed_focus", 0) or 0) * self._freed_input_sign("Focus"))
        except Exception:
            return 0.0

    def _update_lens_settings_from_ui(self, save: bool = False):
        try:
            if hasattr(self, "_freed_lens_type_var"):
                t = str(self._freed_lens_type_var.get()).strip() or "i24"
                if t in ("i16", "u16", "i24", "u24"):
                    self.freed_lens_type = t
            if hasattr(self, "_freed_lens_scale_var"):
                m = str(self._freed_lens_scale_var.get()).strip() or "Auto"
                if m in ("Auto", "Manual", "Full scale"):
                    self.freed_lens_scale_mode = m
            self._update_lens_live_vars()
            self._redraw_run_live_section()
            if save:
                try:
                    self._save_config()
                except Exception:
                    pass
        except Exception:
            pass

    def _capture_lens_endpoint(self, endpoint: str):
        try:
            self._update_lens_settings_from_ui()
            cal = dict(getattr(self, "freed_lens_cal", {}) or {})
            captured = self._current_lens_value("zoom" if endpoint.startswith("zoom") else "focus")
            cal[endpoint] = captured
            self.freed_lens_cal = cal
            try:
                seen = getattr(self, "_freed_lens_auto_seen", None)
                if not isinstance(seen, dict):
                    seen = {"zoom_min": None, "zoom_max": None, "focus_min": None, "focus_max": None}
                if endpoint.startswith("zoom"):
                    vals = [float(cal.get("zoom_wide", captured)), float(cal.get("zoom_tele", captured))]
                    seen["zoom_min"], seen["zoom_max"] = min(vals), max(vals)
                else:
                    vals = [float(cal.get("focus_near", captured)), float(cal.get("focus_far", captured))]
                    seen["focus_min"], seen["focus_max"] = min(vals), max(vals)
                self._freed_lens_auto_seen = seen
            except Exception:
                pass
            self._sync_lens_cal_vars()
            # Also write the target StringVar directly so the Free-D tab label updates
            # immediately even if the normal sync path is delayed by live input refresh.
            var_name = {
                "zoom_wide": "_freed_zoom_wide_var",
                "zoom_tele": "_freed_zoom_tele_var",
                "focus_near": "_freed_focus_near_var",
                "focus_far": "_freed_focus_far_var",
            }.get(str(endpoint))
            if var_name and hasattr(self, var_name):
                try:
                    getattr(self, var_name).set(f"{float(captured):0.0f}")
                except Exception:
                    pass
            self._redraw_run_live_section()
            try:
                self._save_config()
            except Exception:
                pass
            self._set_status(f"Lens calibration captured: {endpoint.replace('_', ' ')} = {float(captured):0.0f}")
        except Exception:
            pass

    def _reset_lens_calibration(self):
        try:
            self._update_lens_settings_from_ui()
            lo, hi = self._lens_full_limits_for_current_type()
            self.freed_lens_cal = {
                "zoom_wide": lo,
                "zoom_tele": hi,
                "focus_near": lo,
                "focus_far": hi,
            }
            self._freed_lens_auto_seen = {"zoom_min": None, "zoom_max": None, "focus_min": None, "focus_max": None}
            self._sync_lens_cal_vars()
            self._redraw_run_live_section()
            try:
                self._save_config()
            except Exception:
                pass
            self._set_status("Lens calibration reset")
        except Exception:
            pass

    def _sync_lens_cal_vars(self):
        try:
            if hasattr(self, "_freed_lens_type_var"):
                self._freed_lens_type_var.set(str(getattr(self, "freed_lens_type", "i24")))
            if hasattr(self, "_freed_lens_scale_var"):
                self._freed_lens_scale_var.set(str(getattr(self, "freed_lens_scale_mode", "Auto")))
            cal = dict(getattr(self, "freed_lens_cal", {}) or {})
            for key, var_name in (
                ("zoom_wide", "_freed_zoom_wide_var"),
                ("zoom_tele", "_freed_zoom_tele_var"),
                ("focus_near", "_freed_focus_near_var"),
                ("focus_far", "_freed_focus_far_var"),
            ):
                if hasattr(self, var_name):
                    getattr(self, var_name).set(f"{float(cal.get(key, 0.0)):0.0f}")
            self._update_lens_live_vars()
        except Exception:
            pass

    def _update_lens_live_vars(self):
        """Keep the Free-D tab live Zoom/Focus lens readouts matched to the Run tab."""
        try:
            zoom = self._current_lens_value("zoom")
            focus = self._current_lens_value("focus")
            if hasattr(self, "_freed_zoom_live_var"):
                self._freed_zoom_live_var.set(f"{float(zoom):0.0f}")
            if hasattr(self, "_freed_focus_live_var"):
                self._freed_focus_live_var.set(f"{float(focus):0.0f}")
        except Exception:
            pass

    def _draw_run_bar(self, canvas, value: float, norm: float, label: str, unit: str = ""):
        try:
            canvas.delete("all")
            w = max(20, int(canvas.winfo_width()))
            h = max(14, int(canvas.winfo_height()))
            norm = max(0.0, min(1.0, float(norm)))
            canvas.create_rectangle(1, 1, w-2, h-2, outline="#4a4a4a", fill="#101010")
            canvas.create_rectangle(2, 2, 2 + max(0, int((w-4) * norm)), h-3, outline="", fill="#5f7f9f")
            if unit == "%":
                txt = f"{label}: {float(value):0.3f}%"
            elif unit:
                txt = f"{label}: {float(value):0.2f}{unit}"
            else:
                txt = f"{label}: {float(value):0.0f}"
            canvas.create_text(8, h/2, text=txt, anchor="w", fill="#eeeeee", font=("Segoe UI", 9, "bold"))
        except Exception:
            pass

    def _draw_attitude_canvas(self, canvas, label: str, angle_deg: float, mode: str = "heading"):
        try:
            canvas.delete("all")
            w = max(44, int(canvas.winfo_width()))
            h = max(44, int(canvas.winfo_height()))
            # Keep the text and direction display fully inside the compact card.
            title_h = 17.0
            cx = w / 2.0
            graph_top = title_h + 2.0
            graph_bottom = max(graph_top + 22.0, h - 7.0)
            cy = graph_top + (graph_bottom - graph_top) / 2.0
            r = max(10.0, min((w - 12.0) / 2.0, (graph_bottom - graph_top) / 2.0) * 0.72)
            canvas.create_text(cx, 10, text=f"{label}: {float(angle_deg):0.3f}°", fill="#eeeeee", font=("Segoe UI", 9, "bold"))
            canvas.create_oval(cx-r, cy-r, cx+r, cy+r, outline="#555555", fill="#151515")
            if mode == "roll":
                a = math.radians(float(angle_deg))
                dx, dy = math.cos(a) * r, math.sin(a) * r
                canvas.create_line(cx-dx, cy-dy, cx+dx, cy+dy, fill="#d0d0d0", width=2)
                tri = max(5.0, r * 0.22)
                canvas.create_polygon(cx-tri, cy+tri*0.7, cx+tri, cy+tri*0.7, cx, cy-tri, fill="#9f9f9f", outline="#ffffff")
            elif mode == "tilt":
                a = math.radians(max(-90.0, min(90.0, float(angle_deg))))
                x2 = cx + math.cos(a) * r
                y2 = cy - math.sin(a) * r
                canvas.create_line(cx-r, cy, cx+r, cy, fill="#555555")
                canvas.create_line(cx, cy, x2, y2, fill="#d0d0d0", width=2, arrow="last")
            else:
                a = math.radians(float(angle_deg) - 90.0)
                x2 = cx + math.cos(a) * r
                y2 = cy + math.sin(a) * r
                n_y = max(graph_top + 5.0, cy - r + 7.0)
                canvas.create_text(cx, n_y, text="N", fill="#888888", font=("Segoe UI", 8, "bold"))
                canvas.create_line(cx, cy, x2, y2, fill="#d0d0d0", width=2, arrow="last")
        except Exception:
            pass

    def _redraw_run_live_section(self):
        if not hasattr(self, "run_bar_canvases") and not hasattr(self, "run_attitude_canvases"):
            return
        try:
            self._sync_freed_offsets_from_ui()
            x_m, y_m, z_m = self._current_freed_xyz()
            _cam_id, pan, tilt, roll, zoom, focus = self._freed_motion_for_display()
            try:
                span = max(0.1, float(self._limit_display_position_m(self.state.far_limit)))
            except Exception:
                span = max(0.1, float(getattr(self.state, "total_length_m", 100.0) or 100.0))
            pts = self._freed_valid_height_points()
            y_vals = [p[1] for p in pts] + [float(y_m), 0.0]
            y_min, y_max = min(y_vals), max(y_vals)
            if abs(y_max - y_min) < 0.25:
                y_min -= 0.5
                y_max += 0.5
            z_abs = max(1.0, abs(float(z_m)) * 1.4, 2.0)
            bars = getattr(self, "run_bar_canvases", {}) or {}
            if "X" in bars:
                self._draw_run_bar(bars["X"], x_m, float(x_m) / span, "X", " m")
            if "Y" in bars:
                self._draw_run_bar(bars["Y"], y_m, (float(y_m) - y_min) / max(1e-9, y_max - y_min), "Y", " m")
            if "Z" in bars:
                self._draw_run_bar(bars["Z"], z_m, (float(z_m) + z_abs) / max(1e-9, z_abs * 2.0), "Z", " m")
            if "Zoom" in bars:
                zoom_norm = self._lens_norm_for_display("zoom", zoom)
                self._draw_run_bar(bars["Zoom"], zoom_norm * 100.0, zoom_norm, "Zoom", "%")
            if "Focus" in bars:
                focus_norm = self._lens_norm_for_display("focus", focus)
                self._draw_run_bar(bars["Focus"], focus_norm * 100.0, focus_norm, "Focus", "%")
            attitudes = getattr(self, "run_attitude_canvases", {}) or {}
            if "Pan" in attitudes:
                self._draw_attitude_canvas(attitudes["Pan"], "Pan", pan, "heading")
            if "Tilt" in attitudes:
                self._draw_attitude_canvas(attitudes["Tilt"], "Tilt", tilt, "tilt")
            if "Roll" in attitudes:
                self._draw_attitude_canvas(attitudes["Roll"], "Roll", roll, "roll")
            if hasattr(self, "run_current_speed_var"):
                v = float(getattr(self, "display_speed_mps", getattr(self, "current_speed_mps", 0.0)) or 0.0)
                self.run_current_speed_var.set(f"{v:0.2f} m/s  |  {v*3.6:0.2f} km/h")
            if hasattr(self, "run_max_speed_var"):
                mx, mode_name = self._current_max_speed_info()
                display_mode = "Uncalibrated" if str(mode_name).lower().startswith("not calibrated") else str(mode_name)
                self.run_max_speed_var.set(f"{mx:0.2f} m/s  |  {mx*3.6:0.2f} km/h")
                if hasattr(self, "run_accel_mode_var"):
                    self.run_accel_mode_var.set(self._display_accel_type())
                if hasattr(self, "run_drive_mode_var"):
                    self.run_drive_mode_var.set(display_mode)
                elif hasattr(self, "run_speed_mode_var"):
                    self.run_speed_mode_var.set(display_mode)
            if hasattr(self, "run_lens_scale_var"):
                self.run_lens_scale_var.set(f"Scale: {getattr(self, 'freed_lens_scale_mode', 'Auto')} / {getattr(self, 'freed_lens_type', 'i24')}")
            self._refresh_run_aux_buttons()
            self._refresh_preset_confirm_buttons()
            self._refresh_limit_confirm_buttons()
        except Exception:
            pass

    def _freed_zoom_cone_deg(self, zoom: int) -> float:
        """Map calibrated Free-D zoom to a visual cone angle. Wide = wider cone, Tele = narrower cone."""
        try:
            # Use the same lens normalisation as the Zoom bar so i16/u16/i24/u24 and Auto/Manual/Full all work.
            zn = max(0.0, min(1.0, float(self._lens_norm("zoom", zoom))))
            return max(5.0, min(42.0, 42.0 - 35.0 * zn))
        except Exception:
            try:
                z = abs(int(zoom or 0))
                zn = max(0.0, min(1.0, z / 8388607.0))
                return max(5.0, min(42.0, 42.0 - 35.0 * zn))
            except Exception:
                return 28.0


    def _freed_camera_view_projections(self, pan_deg, tilt_deg):
        """Return projected camera headings for the Top (X/Z) and Side (X/Y) views."""
        try:
            p = math.radians(float(pan_deg))
            t = math.radians(float(tilt_deg))
            ct = math.cos(t)
            # Project compass Pan and Tilt into the project axes:
            # X = tracking direction, Y = vertical, Z = lateral offset.
            dx = ct * math.sin(p)
            dy = math.sin(t)
            dz = ct * math.cos(p)
            top_scale = max(0.0, min(1.0, math.hypot(dx, dz)))
            side_scale = max(0.0, min(1.0, math.hypot(dx, dy)))
            top_angle = math.degrees(math.atan2(dz, dx)) if top_scale > 1e-6 else 0.0
            side_angle = math.degrees(math.atan2(dy, dx)) if side_scale > 1e-6 else 0.0
            return top_angle, top_scale, side_angle, side_scale
        except Exception:
            return 90.0 - float(pan_deg or 0.0), 1.0, float(tilt_deg or 0.0), 1.0

    def _draw_freed_camera_overlay(self, c, sx, sy, px_per_m, angle_deg, roll_deg, zoom, focus, span, label_prefix="", max_cone_px=None, projection_scale=1.0):
        """Draw a camera icon, zoom cone and focus line projected into one graph plane."""
        try:
            cone_deg = self._freed_zoom_cone_deg(zoom)
            # Cone length stays within the graph; focus draws as a cross-line inside that cone.
            if max_cone_px is not None:
                base_length_px = max(28.0, float(max_cone_px))
            else:
                base_length_px = max(28.0, min(260.0, max(1.0, float(span)) * 0.35 * max(1.0, px_per_m)))
            base_length_px = min(260.0, base_length_px)
            projection_scale = max(0.0, min(1.0, float(projection_scale)))
            length_px = base_length_px * projection_scale
            end_on = length_px < 14.0
            focus_norm = max(0.0, min(1.0, self._lens_norm("focus", focus)))
            focus_px = max(8.0, min(length_px, length_px * (0.12 + 0.88 * focus_norm))) if not end_on else 0.0
            a = math.radians(float(angle_deg))
            half = math.radians(cone_deg / 2.0)
            # Screen coordinates: +X right, +Y down. Use -sin for upward positive view angle.
            cx = math.cos(a)
            cy = -math.sin(a)
            lx = math.cos(a - half)
            ly = -math.sin(a - half)
            rx = math.cos(a + half)
            ry = -math.sin(a + half)
            p1 = (sx + lx * length_px, sy + ly * length_px)
            p2 = (sx + rx * length_px, sy + ry * length_px)
            pc = (sx + cx * length_px, sy + cy * length_px)
            pf = (sx + cx * focus_px, sy + cy * focus_px)
            if end_on:
                # The camera is pointing almost perpendicular to this graph plane.
                # Draw an end-on target rather than a misleading full-length cone.
                c.create_oval(sx - 9, sy - 9, sx + 9, sy + 9, outline="#ffffff", width=1)
                c.create_line(sx - 6, sy, sx + 6, sy, fill="#c8c8c8", dash=(3, 2))
                c.create_line(sx, sy - 6, sx, sy + 6, fill="#c8c8c8", dash=(3, 2))
                return
            c.create_polygon(sx, sy, p1[0], p1[1], p2[0], p2[1], outline="#888888", fill="")
            # Draw a light center/rim only so labels, cable and ramp zones remain visible through the cone.
            c.create_line(sx, sy, p1[0], p1[1], fill="#8a8a8a", dash=(3, 3))
            c.create_line(sx, sy, p2[0], p2[1], fill="#8a8a8a", dash=(3, 3))
            c.create_line(sx, sy, pc[0], pc[1], fill="#c8c8c8", width=1, dash=(5, 4))
            c.create_line(pf[0] - 9*cy, pf[1] + 9*cx, pf[0] + 9*cy, pf[1] - 9*cx, fill="#ffffff", width=1, dash=(4, 3))
            # Focus line is drawn without text to keep the graph clean.

            # Camera body icon: diamond/arrow aligned with the active view axis.
            # The cone/focus line follows Pan on the Top View.
            # and Tilt on the Side View.  Rotate the body icon on the same axis so
            # the whole camera graphic turns together instead of the body staying
            # fixed horizontally while only the cone moves.
            r = math.radians(float(roll_deg))
            cos_r = math.cos(r)
            sin_r = math.sin(r)
            # Forward basis follows the same screen-space angle used by the cone.
            # Local +Y points to the camera body's right-hand side on screen.
            nx = -cy
            ny = cx
            body = [(-10, -6), (8, -6), (14, 0), (8, 6), (-10, 6)]
            pts = []
            for bx, by in body:
                # Apply roll in local camera space first, then align the resulting
                # body to the Pan/Tilt axis used by the overlay cone.
                lx_body = bx * cos_r - by * sin_r
                ly_body = bx * sin_r + by * cos_r
                x = sx + (lx_body * cx) + (ly_body * nx)
                y = sy + (lx_body * cy) + (ly_body * ny)
                pts.extend([x, y])
            c.create_polygon(*pts, fill="", outline="#ffffff", width=1)
            c.create_line(sx, sy, sx + cx * 18, sy + cy * 18, fill="#ffffff", width=1, dash=(4, 3))
            # Camera text labels are intentionally omitted; values remain in the Free-D Input table.
        except Exception:
            pass

    def _draw_freed_span_markers(self, c, map_x, x0, y0, x1, y1, span, line_y=None, skate_x_m=None, path_y_for_x=None, dynamic_preset_labels=False):
        """Draw ramp zones plus solid Ref/Skate/Preset markers on the Free-D views."""
        try:
            span = max(0.1, float(span))
            if line_y is None:
                line_y = y0 + (y1 - y0) * 0.5
            try:
                line_y = float(line_y)
            except Exception:
                line_y = y0 + (y1 - y0) * 0.5

            def _label_positions_for_line(local_line_y):
                try:
                    ly = float(local_line_y)
                except Exception:
                    ly = y0 + (y1 - y0) * 0.5
                name_y = max(y0 + 12, min(ly - 16, y1 - 32))
                value_y = min(y1 - 12, max(ly + 16, y0 + 30))
                return name_y, value_y

            label_y, dist_y = _label_positions_for_line(line_y)

            def _path_line_y(x_m):
                try:
                    if callable(path_y_for_x):
                        return max(y0 + 10, min(y1 - 10, float(path_y_for_x(float(x_m)))))
                except Exception:
                    pass
                return line_y

            # Ramping zones - dark amber shaded areas at Near and Far.
            try:
                near_ramp = float(getattr(self.state, "ramp_zone_near", 0.0) or 0.0)
            except Exception:
                near_ramp = 0.0
            try:
                far_ramp = float(getattr(self.state, "ramp_zone_far", 0.0) or 0.0)
            except Exception:
                far_ramp = 0.0
            near_ramp = max(0.0, min(span, near_ramp))
            far_ramp = max(0.0, min(span, far_ramp))
            if near_ramp > 0.001:
                nx = map_x(near_ramp)
                c.create_rectangle(x0, y0, nx, y1, outline="#7c5c1e", fill="#33260e", tags=("freed_ramp_zone",))
                c.create_line(nx, y0, nx, y1, fill="#b48a2c", dash=(5, 4), tags=("freed_ramp_zone",))
            if far_ramp > 0.001:
                fx = map_x(max(0.0, span - far_ramp))
                c.create_rectangle(fx, y0, x1, y1, outline="#7c5c1e", fill="#33260e", tags=("freed_ramp_zone",))
                c.create_line(fx, y0, fx, y1, fill="#b48a2c", dash=(5, 4), tags=("freed_ramp_zone",))

            def _fmt_m(v):
                try:
                    return f"{float(v):0.2f} m"
                except Exception:
                    return "--.-- m"

            def _draw_label_with_pad(tx, ty, text, fill, anchor, font):
                """Draw readable graph label text with a small solid dark pad behind it."""
                try:
                    item = c.create_text(
                        tx, ty,
                        text=str(text),
                        fill=fill,
                        anchor=anchor,
                        font=font,
                        tags=("freed_marker_label",),
                    )
                    bbox = c.bbox(item)
                    if bbox:
                        pad_x, pad_y = 4, 2
                        bg = c.create_rectangle(
                            bbox[0] - pad_x, bbox[1] - pad_y,
                            bbox[2] + pad_x, bbox[3] + pad_y,
                            outline="",
                            fill="#181818",
                            tags=("freed_marker_label",),
                        )
                        c.tag_lower(bg, item)
                    return item
                except Exception:
                    return None

            def _marker_text(px, name, distance, color="#ffffff", anchor="center", xoffset=0, distance_text=None, local_line_y=None, value_color=None):
                try:
                    name_y, value_y = _label_positions_for_line(local_line_y if local_line_y is not None else line_y)
                    txt2 = str(distance_text) if distance_text is not None else _fmt_m(distance)
                    solid_value_color = value_color if value_color is not None else color
                    _draw_label_with_pad(px + xoffset, name_y, str(name), color, anchor, GRAPH_FONT_BOLD)
                    _draw_label_with_pad(px + xoffset, value_y, txt2, solid_value_color, anchor, GRAPH_FONT)
                except Exception:
                    pass

            def _side_label_anchor(px, prefer_right=True):
                """Place preset text beside the marker line rather than centred over it."""
                try:
                    margin = 118
                    if prefer_right and px <= (x1 - margin):
                        return "w", 8
                    if px >= (x0 + margin):
                        return "e", -8
                    return "w", 8
                except Exception:
                    return "w", 8

            # End labels: name above the line and distance from the current skate below it.
            try:
                skate = max(0.0, min(span, float(skate_x_m if skate_x_m is not None else 0.0)))
            except Exception:
                skate = 0.0
            # Near/Ref/Far labels are drawn above the graph by _draw_freed_endpoint_header().

            # Reference point marker - solid blue.
            try:
                ref_pos = float(self._limit_display_position_m(self.state.ref_point))
                if 0.0 <= ref_pos <= span:
                    rx = map_x(ref_pos)
                    c.create_line(rx, y0, rx, y1, fill="#62b4ff", width=2)
            except Exception:
                pass

            # Current skate marker remains grey/dashed to separate the live position
            # from saved Ref/Preset positions. Do not draw a Skate name/distance label
            # here - the To Near / To Far readouts already show the live position.
            try:
                if 0.0 <= skate <= span:
                    sx = map_x(skate)
                    c.create_line(sx, y0, sx, y1, fill="#707070", dash=(3, 3))
            except Exception:
                pass

            # Enabled preset markers - solid green.  On the Side View, optional
            # path_y_for_x makes each preset label follow the local sag/cable path.
            presets = list(getattr(self, "preset_positions", []) or [])
            visible = list(getattr(self, "preset_visible", []) or [])
            names = list(getattr(self, "preset_names", []) or [])
            for idx, pos in enumerate(presets[:PRESET_COUNT]):
                if pos is None:
                    continue
                if idx >= len(visible) or not bool(visible[idx]):
                    continue
                try:
                    px_m = float(pos)
                except Exception:
                    continue
                if not (0.0 <= px_m <= span):
                    continue
                px = map_x(px_m)
                name = names[idx] if idx < len(names) and str(names[idx]).strip() else f"P{idx + 1}"
                preset_color = "#8fd18f"
                c.create_line(px, y0, px, y1, fill=preset_color, width=2)

                # Put the label beside the preset line, not centred on the line.
                # On the Side View, keep the label vertically locked to the local cable path;
                # on the Top View, keep the same side-offset treatment for readability.
                if dynamic_preset_labels:
                    local_line_y = _path_line_y(px_m)
                else:
                    local_line_y = line_y
                anchor, xoff = _side_label_anchor(px, prefer_right=True)
                _marker_text(
                    px,
                    str(name),
                    px_m,
                    "#dfffdc",
                    anchor=anchor,
                    xoffset=xoff,
                    local_line_y=local_line_y,
                    value_color="#dfffdc",
                )
        except Exception:
            pass

    def _draw_freed_endpoint_header(self, c, map_x, x0, y0, x1, span, skate_x_m=None):
        """Draw Near/Ref/Far labels and distance readouts above the graph area."""
        try:
            span = max(0.1, float(span))
            try:
                skate = max(0.0, min(span, float(skate_x_m if skate_x_m is not None else 0.0)))
            except Exception:
                skate = 0.0
            def _fmt_m(v):
                try:
                    return f"{float(v):0.2f} m"
                except Exception:
                    return "--.-- m"
            y_name = max(8, y0 - 20)
            y_dist = max(18, y0 - 8)
            # Near/Far show distance from current skate to each end.
            c.create_text(x0 + 2, y_name, text="Near End", fill="#cfcfcf", anchor="w", font=GRAPH_FONT_BOLD)
            c.create_text(x0 + 2, y_dist, text=f"To Near: {_fmt_m(abs(skate))}", fill="#cfcfcf", anchor="w", font=GRAPH_FONT)
            c.create_text(x1 - 2, y_name, text="Far End", fill="#cfcfcf", anchor="e", font=GRAPH_FONT_BOLD)
            c.create_text(x1 - 2, y_dist, text=f"To Far: {_fmt_m(abs(span - skate))}", fill="#cfcfcf", anchor="e", font=GRAPH_FONT)
            try:
                ref_pos = float(self._limit_display_position_m(self.state.ref_point))
                if 0.0 <= ref_pos <= span:
                    rx = map_x(ref_pos)
                    # Keep the ref header clear of the graph edges.
                    anchor = "center"
                    xoff = 0
                    if rx < x0 + 120:
                        anchor = "w"; xoff = 72
                    elif rx > x1 - 120:
                        anchor = "e"; xoff = -72
                    c.create_text(rx + xoff, y_name, text="Ref", fill="#62b4ff", anchor=anchor, font=GRAPH_FONT_BOLD)
                    c.create_text(rx + xoff, y_dist, text=_fmt_m(ref_pos), fill="#62b4ff", anchor=anchor, font=GRAPH_FONT)
            except Exception:
                pass
        except Exception:
            pass

    def _redraw_freed_top_view(self):
        c = getattr(self, "freed_top_canvas", None)
        if c is None:
            return
        try:
            c.delete("all")
            w = max(100, int(c.winfo_width()))
            h = max(100, int(c.winfo_height()))
            pad_l, pad_r, pad_t, pad_b = 55, 25, 28, 42
            x0, y0 = pad_l, pad_t
            x1, y1 = w - pad_r, h - pad_b
            c.create_rectangle(x0, y0, x1, y1, outline="#404040", fill="#181818")

            try:
                span = max(0.1, float(self._limit_display_position_m(self.state.far_limit)))
            except Exception:
                span = max(0.1, float(getattr(self.state, "total_length_m", 100.0) or 100.0))
            if span <= 0:
                span = 100.0

            x_m, y_sag_m, z_off_m = self._current_freed_xyz()
            cam_id, pan, tilt, roll, zoom, focus = self._freed_motion_for_display()
            top_samples = []
            sample_count = 90
            for i in range(sample_count + 1):
                xv = span * i / sample_count
                top_samples.append((xv, self._freed_z_offset_for_x(xv)))
            z_vals = [z for _xv, z in top_samples] + [z_off_m, 0.0]
            # Top View uses a fixed, symmetric metres scale instead of auto-scaling
            # tightly to the current offset. This keeps 1 m small and 20 m visibly
            # much larger, so the displayed cable angle reflects the actual Z offset.
            try:
                max_abs_z = max(abs(float(z)) for z in z_vals)
            except Exception:
                max_abs_z = 0.0
            z_half_range = max(20.0, max_abs_z * 1.15)
            z_min = -z_half_range
            z_max = z_half_range

            def map_x(xv):
                return x0 + max(0.0, min(1.0, float(xv) / span)) * (x1 - x0)
            def map_y(zv):
                return y1 - ((float(zv) - z_min) / max(1e-9, z_max - z_min)) * (y1 - y0)

            for i in range(6):
                yy = y0 + (y1 - y0) * i / 5.0
                c.create_line(x0, yy, x1, yy, fill="#242424")
            for i in range(6):
                xx = x0 + (x1 - x0) * i / 5.0
                c.create_line(xx, y0, xx, y1, fill="#242424")
                c.create_text(xx, y1 + 18, text=f"{span*i/5.0:0.0f}m", fill="#9a9a9a", font=GRAPH_FONT)

            sx = map_x(x_m)
            sy = map_y(z_off_m)
            def top_path_y_for_x(xv):
                return map_y(self._freed_z_offset_for_x(xv))
            self._draw_freed_span_markers(
                c, map_x, x0, y0, x1, y1, span,
                line_y=sy,
                skate_x_m=x_m,
                path_y_for_x=top_path_y_for_x,
                dynamic_preset_labels=True,
            )
            coords = []
            for xv, zv in top_samples:
                coords.extend([map_x(xv), map_y(zv)])
            if len(coords) >= 4:
                # Draw the actual offset cable run rather than a second duplicate cable line.
                c.create_line(*coords, fill="#d0d0d0", width=3, smooth=True)

            px_per_m = (x1 - x0) / max(1e-9, span)
            # Top View is the X/Z projection of the shared 3D Pan/Tilt direction.
            top_angle, top_scale, _side_angle, _side_scale = self._freed_camera_view_projections(pan, tilt)
            self._draw_freed_camera_overlay(
                c, sx, sy, px_per_m, top_angle, roll, zoom, focus, span,
                label_prefix="", max_cone_px=(y1 - y0) * 0.75,
                projection_scale=top_scale,
            )
            try:
                c.tag_raise("freed_marker_label")
            except Exception:
                pass
            self._draw_freed_endpoint_header(c, map_x, x0, y0, x1, span, skate_x_m=x_m)

            if hasattr(self, "freed_top_live_var"):
                status = "ON" if bool(getattr(self, "freed_output_enabled", False)) else "OFF"
                target = f"{getattr(self, 'freed_target_ip', '')}:{getattr(self, 'freed_target_port', '')}"
                out_fps = float(getattr(self, "freed_out_fps", 0.0) or 0.0)
                self.freed_top_live_var.set(f"X={x_m:0.2f} m   Z Offset={z_off_m:0.2f} m   Free-D: {status} {out_fps:0.1f} fps -> {target}")
        except Exception:
            pass

    def _redraw_freed_side_view(self):
        c = getattr(self, "freed_canvas", None)
        if c is None:
            return
        try:
            c.delete("all")
            w = max(100, int(c.winfo_width()))
            h = max(100, int(c.winfo_height()))
            pad_l, pad_r, pad_t, pad_b = 55, 25, 28, 42
            x0, y0 = pad_l, pad_t
            x1, y1 = w - pad_r, h - pad_b
            c.create_rectangle(x0, y0, x1, y1, outline="#404040", fill="#181818")

            pts = self._freed_valid_height_points()
            try:
                span = max(0.1, float(self._limit_display_position_m(self.state.far_limit)))
            except Exception:
                span = max(0.1, float(getattr(self.state, "total_length_m", 100.0) or 100.0))
            if span <= 0:
                span = 100.0
            if not pts:
                pts = [(0.0, 0.0), (span, 0.0)]

            x_m, y_sag_m, z_off_m = self._current_freed_xyz()
            cam_id, pan, tilt, roll, zoom, focus = self._freed_motion_for_display()
            sample_count = 180
            sample_xs = [span * i / sample_count for i in range(sample_count + 1)]
            sample_xs.extend(float(p[0]) for p in pts)
            sample_xs.append(float(x_m))
            sample_xs = sorted(set(max(0.0, min(span, round(float(xv), 6))) for xv in sample_xs))
            samples = [(xv, self._freed_z_for_y(xv)) for xv in sample_xs]
            sag_vals = [p[1] for p in pts] + [yv for _xv, yv in samples] + [y_sag_m, 0.0]
            sag_min = min(sag_vals)
            sag_max = max(sag_vals)
            if abs(sag_max - sag_min) < 0.25:
                sag_min -= 0.5
                sag_max += 0.5
            sag_pad = max(0.25, (sag_max - sag_min) * 0.15)
            sag_min -= sag_pad
            sag_max += sag_pad

            def map_x(xv):
                return x0 + max(0.0, min(1.0, float(xv) / span)) * (x1 - x0)
            def map_y(yv):
                return y1 - ((float(yv) - sag_min) / max(1e-9, sag_max - sag_min)) * (y1 - y0)

            for i in range(6):
                yy = y0 + (y1 - y0) * i / 5.0
                c.create_line(x0, yy, x1, yy, fill="#242424")
            for i in range(6):
                xx = x0 + (x1 - x0) * i / 5.0
                c.create_line(xx, y0, xx, y1, fill="#242424")
                c.create_text(xx, y1 + 18, text=f"{span*i/5.0:0.0f}m", fill="#9a9a9a", font=GRAPH_FONT)
            # Removed the old dashed zero-height reference line; the calculated cable path is the side-view reference.

            sx = map_x(x_m)
            sy = map_y(y_sag_m)
            def path_y_for_x(xv):
                return map_y(self._freed_z_for_y(xv))
            self._draw_freed_span_markers(
                c, map_x, x0, y0, x1, y1, span,
                line_y=sy,
                skate_x_m=x_m,
                path_y_for_x=path_y_for_x,
                dynamic_preset_labels=True,
            )

            coords = []
            for xv, yv in samples:
                coords.extend([map_x(xv), map_y(yv)])
            if len(coords) >= 4:
                # Do not spline-smooth the cable: a point load creates a real
                # slope change at the skate, and Tk splines can overshoot into a W.
                c.create_line(*coords, fill="#d0d0d0", width=3, smooth=False)
            # Manual Y height points are used as known AGL control points for the sag curve.
            # Do not draw the old unsagged/reference dots; the displayed line is the calculated cable path.

            px_per_m = (x1 - x0) / max(1e-9, span)
            # Side View is the X/Y projection of the same 3D direction. Pan changes
            # the along-cable component and projected length; Tilt changes elevation.
            _top_angle, _top_scale, side_angle, side_scale = self._freed_camera_view_projections(pan, tilt)
            self._draw_freed_camera_overlay(
                c, sx, sy, px_per_m, side_angle, roll, zoom, focus, span,
                label_prefix="", max_cone_px=(y1 - y0) * 0.75,
                projection_scale=side_scale,
            )
            try:
                c.tag_raise("freed_marker_label")
            except Exception:
                pass
            self._draw_freed_endpoint_header(c, map_x, x0, y0, x1, span, skate_x_m=x_m)

            if hasattr(self, "freed_live_var"):
                in_fps = float(getattr(self, "freed_in_fps", 0.0) or 0.0)
                self.freed_live_var.set(f"X={x_m:0.2f} m   Y Height={y_sag_m:0.2f} m   Input FPS={in_fps:0.1f}")
        except Exception:
            pass

    # ---------------- Tabs UI ----------------

    def _build_tabs_section(self):
        """
        Tabs area (tight layout).
        """
        tabs_outer = tk.Frame(self.main_frame, bg="#111111")
        tabs_outer.grid(row=3, column=0, sticky="nsew", pady=TAB_CARD_PADY)
        tabs_outer.columnconfigure(0, weight=1)
        tabs_outer.rowconfigure(0, weight=1)
        tabs_outer.grid_propagate(True)

        notebook = ttk.Notebook(tabs_outer)
        notebook.grid(row=0, column=0, sticky="nsew", padx=12, pady=0)
        self.notebook = notebook

        tab_setup = tk.Frame(notebook, bg="#111111")
        tab_cable = tk.Frame(notebook, bg="#111111")
        tab_presets = tk.Frame(notebook, bg="#111111")
        tab_freed = tk.Frame(notebook, bg="#111111")
        tab_log = tk.Frame(notebook, bg="#111111")
        self.tab_setup = tab_setup
        self.tab_cable = tab_cable
        self.tab_presets = tab_presets
        self.tab_freed = tab_freed
        self.tab_log = tab_log

        notebook.add(tab_presets, text="Run")
        notebook.add(tab_setup, text="Setup")
        notebook.add(tab_freed, text="Free-D")
        notebook.add(tab_log, text="Log")
        self._build_presets_tab(tab_presets)
        self._build_drive_limits_tab(tab_setup)
        # Near/Ref/Far calibration controls live on the Run tab.
        self._build_freed_tab(tab_freed)
        self._build_log_tab(tab_log)


    def _build_log_tab(self, parent):
        """Live Log tab replacing the old CMD-window debug stream."""
        parent.configure(bg="#111111")
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        header = tk.Frame(parent, bg="#111111")
        header.grid(row=0, column=0, sticky="ew", padx=8, pady=(4, 2))
        header.columnconfigure(0, weight=1)
        tk.Label(
            header,
            text="Live Log Display",
            fg="#dddddd",
            bg="#111111",
            font=FONT_SMALL_BOLD,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(header, text="Save Log", command=self._save_log_tab).grid(row=0, column=1, sticky="e", padx=(8, 0))
        ttk.Button(header, text="Clear Log", command=self._clear_log_tab).grid(row=0, column=2, sticky="e", padx=(6, 0))

        body = tk.Frame(parent, bg="#111111")
        body.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        self.log_text = tk.Text(
            body,
            bg="#050505",
            fg="#d8d8d8",
            insertbackground="#d8d8d8",
            selectbackground="#2f4f6f",
            font=("Consolas", 9),
            wrap="none",
            height=10,
            bd=1,
            relief="solid",
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        yscroll = ttk.Scrollbar(body, orient="vertical", command=self.log_text.yview)
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll = ttk.Scrollbar(body, orient="horizontal", command=self.log_text.xview)
        xscroll.grid(row=1, column=0, sticky="ew")
        self.log_text.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.log_text.configure(state="disabled")
        self._log_line_count = 0
        self._log_auto_follow = True
        _app_log("[SRVR] Log tab ready")

    def _save_log_tab(self):
        """Save the currently displayed SRVR live log beside the running .py file."""
        try:
            if not hasattr(self, "log_text"):
                return
            try:
                self.log_text.configure(state="normal")
                contents = self.log_text.get("1.0", "end-1c")
            finally:
                try:
                    self.log_text.configure(state="disabled")
                except Exception:
                    pass

            base_dir = os.getcwd()
            try:
                script_path = os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0] else ""
                if script_path and os.path.isdir(os.path.dirname(script_path)):
                    base_dir = os.path.dirname(script_path)
            except Exception:
                base_dir = os.getcwd()

            filename = "HV_P2P_SRVR_Log_" + time.strftime("%Y%m%d_%H%M%S") + ".txt"
            out_path = os.path.join(base_dir, filename)
            with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(contents.rstrip() + "\n")
            _app_log(f"[SRVR] Log saved: {out_path}")
            try:
                self._set_status(f"Log saved: {filename}")
            except Exception:
                pass
        except Exception as exc:
            _app_log(f"[SRVR] Log save failed: {exc}")
            try:
                messagebox.showerror("Save Log", f"Could not save log:\n{exc}")
            except Exception:
                pass

    def _clear_log_tab(self):
        try:
            self.log_text.configure(state="normal")
            self.log_text.delete("1.0", "end")
            self.log_text.configure(state="disabled")
            self._log_line_count = 0
            self._log_auto_follow = True
            _app_log("[SRVR] Log cleared")
        except Exception:
            pass

    def _append_log_line(self, line: str):
        try:
            if not hasattr(self, "log_text"):
                return
            # Follow new entries only when the user was already at the bottom.
            # Scrolling upward therefore freezes the current view. Returning the
            # scrollbar to the bottom automatically resumes live following.
            try:
                at_bottom = float(self.log_text.yview()[1]) >= 0.999999
            except Exception:
                at_bottom = True
            self._log_auto_follow = bool(at_bottom)

            self.log_text.configure(state="normal")
            self.log_text.insert("end", str(line).rstrip() + "\n")
            self._log_line_count = int(getattr(self, "_log_line_count", 0) or 0) + 1
            while self._log_line_count > 1000:
                self.log_text.delete("1.0", "2.0")
                self._log_line_count -= 1
            if self._log_auto_follow:
                self.log_text.see("end")
            self.log_text.configure(state="disabled")
        except Exception:
            try:
                self.log_text.configure(state="disabled")
            except Exception:
                pass

    def _drain_log_queue(self):
        try:
            drained = 0
            while drained < 100:
                try:
                    line = APP_LOG_QUEUE.get_nowait()
                except queue.Empty:
                    break
                self._append_log_line(line)
                drained += 1
        except Exception:
            pass
        try:
            self.root.after(100, self._drain_log_queue)
        except Exception:
            pass


    def _build_freed_tab(self, parent):
        """Free-D input/output settings and 5-point cable sag table."""
        parent.configure(bg="#111111")
        # Four Free-D setting cards share the available width evenly;
        # the standard Actions card stays fixed on the far right, matching Setup.
        for col in range(4):
            parent.columnconfigure(col, weight=1, uniform="freed_cards")
        parent.columnconfigure(4, weight=0, minsize=TAB_ACTIONS_COL_W)
        parent.rowconfigure(0, weight=0)
        parent.rowconfigure(1, weight=0)

        label_font = ("Segoe UI", 9)

        def _normalise_three_decimal_var(var):
            try:
                text = str(var.get()).strip()
                if text not in ("", "-", ".", "-."):
                    var.set(f"{float(text):0.3f}")
            except Exception:
                pass

        # Left: Free-D Input
        in_card = tk.Frame(parent, bg="#1a1a1a", highlightbackground="#2a2f3a", highlightthickness=1, width=340, height=236)
        in_card.grid(row=0, column=0, sticky="nsew", padx=(8, 4), pady=TAB_CARD_PADY)
        in_card.grid_propagate(False)
        for col in range(6):
            in_card.columnconfigure(col, weight=1 if col in (1, 3, 5) else 0)

        # Middle: Free-D Output
        out_card = tk.Frame(parent, bg="#1a1a1a", highlightbackground="#2a2f3a", highlightthickness=1, width=340, height=236)
        out_card.grid(row=0, column=1, sticky="nsew", padx=(4, 4), pady=TAB_CARD_PADY)
        out_card.grid_propagate(False)
        for col in range(4):
            out_card.columnconfigure(col, weight=0)
        out_card.columnconfigure(1, weight=1, uniform="freed_output_value_cols")
        out_card.columnconfigure(2, weight=1, uniform="freed_output_value_cols")
        out_card.columnconfigure(3, weight=0)

        points_card = tk.Frame(parent, bg="#1a1a1a", highlightbackground="#2a2f3a", highlightthickness=1, width=360, height=236)
        points_card.grid(row=0, column=2, sticky="nsew", padx=(4, 4), pady=TAB_CARD_PADY)
        points_card.grid_propagate(False)
        for col in range(5):
            points_card.columnconfigure(col, weight=1 if col > 0 else 0)

        lens_card = tk.Frame(parent, bg="#1a1a1a", highlightbackground="#2a2f3a", highlightthickness=1, width=230, height=236)
        lens_card.grid(row=0, column=3, sticky="nsew", padx=(4, 4), pady=TAB_CARD_PADY)
        lens_card.grid_propagate(False)
        lens_card.columnconfigure(0, weight=0)
        lens_card.columnconfigure(1, weight=1)
        lens_card.columnconfigure(2, weight=1)


        tk.Label(in_card, text="Free-D Input", fg="#dddddd", bg="#1a1a1a", font=FONT_SMALL_BOLD).grid(
            row=0, column=0, columnspan=5, sticky="w", padx=12, pady=TAB_HEADING_PADY
        )
        self._freed_input_enabled_var = tk.StringVar(value="ON" if bool(getattr(self, "freed_input_enabled", True)) else "OFF")
        self._freed_input_bind_var = tk.StringVar(value=str(getattr(self, "freed_input_bind_ip", "0.0.0.0")))
        self._freed_input_port_var = tk.StringVar(value=str(getattr(self, "freed_input_port", 40001)))

        # Equal-width Free-D Input value columns: Raw / Decoded / Offset span the card width.
        for col in range(5):
            in_card.columnconfigure(col, weight=0)
        in_card.columnconfigure(1, weight=1, uniform="freed_input_value_cols")
        in_card.columnconfigure(2, weight=1, uniform="freed_input_value_cols")
        in_card.columnconfigure(3, weight=1, uniform="freed_input_value_cols")
        in_card.columnconfigure(4, weight=0)

        # Input state, IP Address and Port are staged together on one row and
        # only become active when the Free-D Apply button is pressed.
        input_row = tk.Frame(in_card, bg="#1a1a1a")
        input_row.grid(row=1, column=0, columnspan=5, sticky="ew", padx=8, pady=TAB_ROW_PADY)
        network_font = ("Segoe UI", 8)
        input_row.columnconfigure(1, weight=0)
        input_row.columnconfigure(3, weight=1, minsize=108)
        input_row.columnconfigure(5, weight=0)
        tk.Label(input_row, text="Input:", fg="#dddddd", bg="#1a1a1a", font=network_font).grid(row=0, column=0, sticky="e", padx=(0, 2))
        ttk.Combobox(input_row, textvariable=self._freed_input_enabled_var, values=["OFF", "ON"], state="readonly", width=3, font=network_font).grid(row=0, column=1, sticky="w", padx=(0, 5))
        tk.Label(input_row, text="IP Address:", fg="#dddddd", bg="#1a1a1a", font=network_font).grid(row=0, column=2, sticky="e", padx=(0, 2))
        tk.Entry(input_row, textvariable=self._freed_input_bind_var, width=15, font=network_font, bg="#111111", fg="#dddddd", insertbackground="#dddddd", bd=1, relief="solid").grid(row=0, column=3, sticky="ew", padx=(0, 5))
        tk.Label(input_row, text="Port:", fg="#dddddd", bg="#1a1a1a", font=network_font).grid(row=0, column=4, sticky="e", padx=(0, 2))
        tk.Entry(input_row, textvariable=self._freed_input_port_var, width=5, font=network_font, bg="#111111", fg="#dddddd", insertbackground="#dddddd", bd=1, relief="solid").grid(row=0, column=5, sticky="w", padx=(0, 0))

        tk.Label(in_card, text="Value", fg="#bbbbbb", bg="#1a1a1a", font=label_font).grid(row=2, column=0, sticky="w", padx=(12, 4), pady=(6, 2))
        tk.Label(in_card, text="Raw Data", fg="#bbbbbb", bg="#1a1a1a", font=label_font).grid(row=2, column=1, sticky="ew", padx=4, pady=(6, 2))
        tk.Label(in_card, text="Decoded Data", fg="#bbbbbb", bg="#1a1a1a", font=label_font).grid(row=2, column=2, sticky="ew", padx=4, pady=(6, 2))
        tk.Label(in_card, text="Offset", fg="#bbbbbb", bg="#1a1a1a", font=label_font).grid(row=2, column=3, sticky="ew", padx=4, pady=(6, 2))
        tk.Label(in_card, text="Invert", fg="#bbbbbb", bg="#1a1a1a", font=label_font).grid(row=2, column=4, sticky="w", padx=(4, 12), pady=(6, 2))
        self._freed_input_field_vars = {}
        self._freed_input_offset_vars = {}
        self._freed_input_invert_vars = {}
        invert_fields = {"Pan", "Tilt", "Roll", "Zoom", "Focus"}
        offset_fields = {"Pan", "Tilt", "Roll"}
        saved_inverts = dict(getattr(self, "freed_input_inverts", {}) or {})
        saved_in_offsets = dict(getattr(self, "freed_input_offsets", {}) or {})

        def _sync_freed_input_inverts(*_args):
            try:
                self.freed_input_inverts = {
                    key: bool(var.get())
                    for key, var in getattr(self, "_freed_input_invert_vars", {}).items()
                }
                self._redraw_freed_top_view()
                self._redraw_freed_side_view()
                self._redraw_run_live_section()
            except Exception:
                pass

        def _sync_freed_input_offsets_live(*_args):
            try:
                self._sync_freed_offsets_from_ui()
                self._redraw_freed_top_view()
                self._redraw_freed_side_view()
                self._redraw_run_live_section()
            except Exception:
                pass

        for idx, name in enumerate(["Cam ID", "Pan", "Tilt", "Roll", "Zoom", "Focus", "FPS"], start=3):
            raw_var = tk.StringVar(value="--")
            dec_var = tk.StringVar(value="--")
            self._freed_input_field_vars[name] = (raw_var, dec_var)
            tk.Label(in_card, text=f"{name}:", fg="#dddddd", bg="#1a1a1a", font=label_font).grid(row=idx, column=0, sticky="e", padx=(12, 4), pady=TAB_ROW_PADY)
            tk.Label(in_card, textvariable=raw_var, fg="#cfcfcf", bg="#111111", font=("Segoe UI", 9), anchor="w", width=10, bd=1, relief="solid").grid(row=idx, column=1, sticky="ew", padx=4, pady=TAB_ROW_PADY)
            tk.Label(in_card, textvariable=dec_var, fg="#cfcfcf", bg="#111111", font=("Segoe UI", 9), anchor="w", width=10, bd=1, relief="solid").grid(row=idx, column=2, sticky="ew", padx=4, pady=TAB_ROW_PADY)
            if name in offset_fields:
                off = tk.StringVar(value=f"{float(saved_in_offsets.get(name, 0.0) or 0.0):0.3f}")
                self._freed_input_offset_vars[name] = off
                try:
                    off.trace_add("write", _sync_freed_input_offsets_live)
                except Exception:
                    pass
                off_entry = tk.Entry(in_card, textvariable=off, width=8, bg="#111111", fg="#dddddd", insertbackground="#dddddd", bd=1, relief="solid")
                off_entry.grid(row=idx, column=3, sticky="ew", padx=4, pady=TAB_ROW_PADY)
                off_entry.bind("<FocusOut>", lambda _e, v=off: _normalise_three_decimal_var(v))
                off_entry.bind("<Return>", lambda _e, v=off: _normalise_three_decimal_var(v))
            else:
                tk.Label(in_card, text="", fg="#dddddd", bg="#1a1a1a", font=label_font).grid(row=idx, column=3, sticky="ew", padx=4, pady=TAB_ROW_PADY)
            if name in invert_fields:
                inv = tk.BooleanVar(value=bool(saved_inverts.get(name, False)))
                self._freed_input_invert_vars[name] = inv
                try:
                    inv.trace_add("write", _sync_freed_input_inverts)
                except Exception:
                    pass
                ttk.Checkbutton(in_card, variable=inv).grid(row=idx, column=4, sticky="w", padx=(4, 12), pady=TAB_ROW_PADY)
            else:
                tk.Label(in_card, text="", fg="#dddddd", bg="#1a1a1a", font=label_font).grid(row=idx, column=4, sticky="w", padx=(4, 12), pady=TAB_ROW_PADY)
        # No separate status row: live state is shown through FPS and decoded/raw fields.

        self._freed_enabled_var = tk.StringVar(value="ON" if getattr(self, "freed_output_enabled", False) else "OFF")
        self._freed_ip_var = tk.StringVar(value=str(getattr(self, "freed_target_ip", "172.20.1.120")))
        self._freed_port_var = tk.StringVar(value=str(getattr(self, "freed_target_port", 40000)))
        self._freed_cam_var = tk.StringVar(value=str(getattr(self, "freed_camera_id", 1)))
        self._freed_rate_var = tk.StringVar(value=f"{float(getattr(self, 'freed_rate_hz', 25.0)):0.3f}")
        self._freed_zoffset_var = tk.StringVar(value=f"{float(getattr(self, 'freed_z_offset_m', getattr(self, 'freed_z_offset_m', 0.0))):0.3f}")
        self._freed_scale_var = tk.StringVar(value=f"{float(getattr(self, 'freed_pos_scale', 640.0)):0.1f}")
        self._freed_skate_weight_var = tk.StringVar(value=f"{float(getattr(self, 'freed_skate_weight_kg', 35.0)):0.1f}")
        self._freed_weight_per_100m_var = tk.StringVar(value=f"{float(getattr(self, 'freed_weight_per_100m_kg', 4.8)):0.2f}")
        self._freed_tension_var = tk.StringVar(value=f"{float(getattr(self, 'freed_sag_tension_kgf', 1200.0)):0.1f}")
        _saved_highline_mode = str(getattr(self, "freed_highline_mode", "Single Highline") or "Single Highline")
        _saved_highline_mode = "Dual Highline" if _saved_highline_mode.strip().lower().startswith("dual") else "Single Highline"
        self._freed_highline_mode_var = tk.StringVar(value=_saved_highline_mode)

        tk.Label(out_card, text="Free-D Output", fg="#dddddd", bg="#1a1a1a", font=FONT_SMALL_BOLD).grid(
            row=0, column=0, columnspan=5, sticky="w", padx=12, pady=TAB_HEADING_PADY
        )

        # Output state, IP Address and Port are staged together on one row and
        # only become active when the Free-D Apply button is pressed.
        output_row = tk.Frame(out_card, bg="#1a1a1a")
        output_row.grid(row=1, column=0, columnspan=5, sticky="ew", padx=8, pady=TAB_ROW_PADY)
        output_row.columnconfigure(1, weight=0)
        output_row.columnconfigure(3, weight=1, minsize=108)
        output_row.columnconfigure(5, weight=0)
        tk.Label(output_row, text="Output:", fg="#dddddd", bg="#1a1a1a", font=network_font).grid(row=0, column=0, sticky="e", padx=(0, 2))
        ttk.Combobox(output_row, textvariable=self._freed_enabled_var, values=["OFF", "ON"], state="readonly", width=3, font=network_font).grid(row=0, column=1, sticky="w", padx=(0, 5))
        tk.Label(output_row, text="IP Address:", fg="#dddddd", bg="#1a1a1a", font=network_font).grid(row=0, column=2, sticky="e", padx=(0, 2))
        tk.Entry(output_row, textvariable=self._freed_ip_var, width=15, font=network_font, bg="#111111", fg="#dddddd", insertbackground="#dddddd", bd=1, relief="solid").grid(row=0, column=3, sticky="ew", padx=(0, 5))
        tk.Label(output_row, text="Port:", fg="#dddddd", bg="#1a1a1a", font=network_font).grid(row=0, column=4, sticky="e", padx=(0, 2))
        tk.Entry(output_row, textvariable=self._freed_port_var, width=5, font=network_font, bg="#111111", fg="#dddddd", insertbackground="#dddddd", bd=1, relief="solid").grid(row=0, column=5, sticky="w", padx=(0, 0))

        for col in range(5):
            out_card.columnconfigure(col, weight=0)
        out_card.columnconfigure(1, weight=1, uniform="freed_output_value_cols")
        out_card.columnconfigure(2, weight=1, uniform="freed_output_value_cols")
        out_card.columnconfigure(3, weight=1, uniform="freed_output_value_cols")
        out_card.columnconfigure(4, weight=0)

        tk.Label(out_card, text="Value", fg="#bbbbbb", bg="#1a1a1a", font=label_font).grid(row=2, column=0, sticky="w", padx=(12, 4), pady=(6, 2))
        tk.Label(out_card, text="Raw Data", fg="#bbbbbb", bg="#1a1a1a", font=label_font).grid(row=2, column=1, sticky="ew", padx=4, pady=(6, 2))
        tk.Label(out_card, text="Decoded Data", fg="#bbbbbb", bg="#1a1a1a", font=label_font).grid(row=2, column=2, sticky="ew", padx=4, pady=(6, 2))
        tk.Label(out_card, text="Offset", fg="#bbbbbb", bg="#1a1a1a", font=label_font).grid(row=2, column=3, sticky="ew", padx=4, pady=(6, 2))
        tk.Label(out_card, text="Invert", fg="#bbbbbb", bg="#1a1a1a", font=label_font).grid(row=2, column=4, sticky="w", padx=(4, 12), pady=(6, 2))
        self._freed_output_field_vars = {}
        self._freed_output_offset_vars = {}
        self._freed_output_invert_vars = {}
        saved_out_inverts = dict(getattr(self, "freed_output_inverts", {}) or {})
        saved_out_offsets = dict(getattr(self, "freed_output_offsets", {}) or {})

        def _sync_freed_output_inverts(*_args):
            try:
                self.freed_output_inverts = {
                    key: bool(var.get())
                    for key, var in getattr(self, "_freed_output_invert_vars", {}).items()
                }
                self._update_freed_output_ui()
            except Exception:
                pass

        def _sync_freed_output_offsets_live(*_args):
            try:
                self._sync_freed_offsets_from_ui()
                self._update_freed_output_ui()
                self._redraw_freed_top_view()
                self._redraw_freed_side_view()
                self._redraw_run_live_section()
            except Exception:
                pass

        for idx, name in enumerate(["X", "Y", "Z", "FPS"], start=3):
            raw_var = tk.StringVar(value="--")
            dec_var = tk.StringVar(value="--")
            self._freed_output_field_vars[name] = (raw_var, dec_var)
            tk.Label(out_card, text=f"{name}:", fg="#dddddd", bg="#1a1a1a", font=label_font).grid(row=idx, column=0, sticky="e", padx=(12, 4), pady=TAB_ROW_PADY)
            if name == "FPS":
                tk.Entry(out_card, textvariable=self._freed_rate_var, width=10, bg="#111111", fg="#dddddd", insertbackground="#dddddd", bd=1, relief="solid").grid(row=idx, column=1, sticky="ew", padx=4, pady=TAB_ROW_PADY)
                tk.Label(out_card, textvariable=dec_var, fg="#cfcfcf", bg="#111111", font=("Segoe UI", 9), anchor="w", width=10, bd=1, relief="solid").grid(row=idx, column=2, sticky="ew", padx=4, pady=TAB_ROW_PADY)
                tk.Label(out_card, text="", fg="#dddddd", bg="#1a1a1a", font=label_font).grid(row=idx, column=3, sticky="ew", padx=4, pady=TAB_ROW_PADY)
                tk.Label(out_card, text="", fg="#dddddd", bg="#1a1a1a", font=label_font).grid(row=idx, column=4, sticky="w", padx=(4, 12), pady=TAB_ROW_PADY)
            else:
                tk.Label(out_card, textvariable=raw_var, fg="#cfcfcf", bg="#111111", font=("Segoe UI", 9), anchor="w", width=10, bd=1, relief="solid").grid(row=idx, column=1, sticky="ew", padx=4, pady=TAB_ROW_PADY)
                tk.Label(out_card, textvariable=dec_var, fg="#cfcfcf", bg="#111111", font=("Segoe UI", 9), anchor="w", width=10, bd=1, relief="solid").grid(row=idx, column=2, sticky="ew", padx=4, pady=TAB_ROW_PADY)
                off = tk.StringVar(value=f"{float(saved_out_offsets.get(name, 0.0) or 0.0):0.3f}")
                self._freed_output_offset_vars[name] = off
                try:
                    off.trace_add("write", _sync_freed_output_offsets_live)
                except Exception:
                    pass
                off_entry = tk.Entry(out_card, textvariable=off, width=8, bg="#111111", fg="#dddddd", insertbackground="#dddddd", bd=1, relief="solid")
                off_entry.grid(row=idx, column=3, sticky="ew", padx=4, pady=TAB_ROW_PADY)
                off_entry.bind("<FocusOut>", lambda _e, v=off: _normalise_three_decimal_var(v))
                off_entry.bind("<Return>", lambda _e, v=off: _normalise_three_decimal_var(v))
                inv = tk.BooleanVar(value=bool(saved_out_inverts.get(name, False)))
                self._freed_output_invert_vars[name] = inv
                try:
                    inv.trace_add("write", _sync_freed_output_inverts)
                except Exception:
                    pass
                ttk.Checkbutton(out_card, variable=inv).grid(row=idx, column=4, sticky="w", padx=(4, 12), pady=TAB_ROW_PADY)

        self._freed_output_scale_note = tk.StringVar(value=f"Free-D scale: {float(getattr(self, 'freed_pos_scale', 640.0)):0.1f} counts/m")
        tk.Label(out_card, textvariable=self._freed_output_scale_note, fg="#aaaaaa", bg="#1a1a1a", font=("Segoe UI", 8), anchor="w").grid(row=7, column=0, columnspan=5, sticky="ew", padx=12, pady=(3, 6))

        tk.Label(points_card, text="X (Tracking) / Y (Sag) / Z (Offset)", fg="#dddddd", bg="#1a1a1a", font=FONT_SMALL_BOLD).grid(row=0, column=0, columnspan=5, sticky="w", padx=12, pady=TAB_HEADING_PADY)
        tk.Label(points_card, text="Use", fg="#bbbbbb", bg="#1a1a1a", font=label_font).grid(row=1, column=0, sticky="w", padx=(12, 4), pady=(2, 2))
        tk.Label(points_card, text="Point", fg="#bbbbbb", bg="#1a1a1a", font=label_font).grid(row=1, column=1, sticky="w", padx=4, pady=(2, 2))
        tk.Label(points_card, text="X", fg="#bbbbbb", bg="#1a1a1a", font=label_font).grid(row=1, column=2, sticky="w", padx=4, pady=(2, 2))
        tk.Label(points_card, text="Y", fg="#bbbbbb", bg="#1a1a1a", font=label_font).grid(row=1, column=3, sticky="w", padx=4, pady=(2, 2))
        tk.Label(points_card, text="Z", fg="#bbbbbb", bg="#1a1a1a", font=label_font).grid(row=1, column=4, sticky="w", padx=(4, 12), pady=(2, 2))

        self._freed_point_vars = []
        pts = list(getattr(self, "freed_height_points", []) or [])
        while len(pts) < 5:
            idx = len(pts)
            pts.append({"enabled": False, "y_m": float(idx * 25.0), "z_m": 0.0, "z_offset_m": float(getattr(self, "freed_z_offset_m", 0.0)) if idx in (0, 4) else 0.0})
        for i in range(5):
            p = pts[i] if isinstance(pts[i], dict) else {}
            en = tk.BooleanVar(value=bool(p.get("enabled", True)))
            xv = tk.StringVar(value=f"{float(p.get('y_m', 0.0)):0.3f}")
            yv = tk.StringVar(value=f"{float(p.get('z_m', 0.0)):0.3f}")
            if i in (0, 4):
                zv = tk.StringVar(value=f"{float(p.get('z_offset_m', getattr(self, 'freed_z_offset_m', 0.0))):0.3f}")
            else:
                zv = tk.StringVar(value="")
            self._freed_point_vars.append({"enabled": en, "x": xv, "y": yv, "z": zv})
            ttk.Checkbutton(points_card, variable=en).grid(row=i+2, column=0, sticky="w", padx=(12, 4), pady=TAB_ROW_PADY)
            tk.Label(points_card, text=f"P{i+1}", fg="#dddddd", bg="#1a1a1a", font=label_font).grid(row=i+2, column=1, sticky="w", padx=4, pady=TAB_ROW_PADY)
            tk.Entry(points_card, textvariable=xv, width=9, bg="#111111", fg="#dddddd", insertbackground="#dddddd", bd=1, relief="solid").grid(row=i+2, column=2, sticky="w", padx=4, pady=TAB_ROW_PADY)
            tk.Entry(points_card, textvariable=yv, width=9, bg="#111111", fg="#dddddd", insertbackground="#dddddd", bd=1, relief="solid").grid(row=i+2, column=3, sticky="w", padx=4, pady=TAB_ROW_PADY)
            z_state = "normal" if i in (0, 4) else "disabled"
            tk.Entry(points_card, textvariable=zv, width=9, bg="#111111", fg="#dddddd", disabledbackground="#151515", disabledforeground="#666666", insertbackground="#dddddd", bd=1, relief="solid", state=z_state).grid(row=i+2, column=4, sticky="w", padx=(4, 12), pady=TAB_ROW_PADY)

        sag_row = tk.Frame(points_card, bg="#1a1a1a")
        sag_row.grid(row=7, column=0, columnspan=5, sticky="ew", padx=12, pady=(4, 1))
        for sc in (1, 3, 5):
            sag_row.columnconfigure(sc, weight=1)
        sag_font = ("Segoe UI", 7)
        tk.Label(sag_row, text="Skate (kg):", fg="#dddddd", bg="#1a1a1a", font=sag_font).grid(row=0, column=0, sticky="e", padx=(0, 2))
        tk.Entry(sag_row, textvariable=self._freed_skate_weight_var, width=5, bg="#111111", fg="#dddddd", insertbackground="#dddddd", bd=1, relief="solid").grid(row=0, column=1, sticky="w", padx=(0, 4))
        tk.Label(sag_row, text="Cable (kg/100m):", fg="#dddddd", bg="#1a1a1a", font=sag_font).grid(row=0, column=2, sticky="e", padx=(0, 2))
        tk.Entry(sag_row, textvariable=self._freed_weight_per_100m_var, width=5, bg="#111111", fg="#dddddd", insertbackground="#dddddd", bd=1, relief="solid").grid(row=0, column=3, sticky="w", padx=(0, 4))
        tk.Label(sag_row, text="Tension (kg):", fg="#dddddd", bg="#1a1a1a", font=sag_font).grid(row=0, column=4, sticky="e", padx=(0, 2))
        tk.Entry(sag_row, textvariable=self._freed_tension_var, width=6, bg="#111111", fg="#dddddd", insertbackground="#dddddd", bd=1, relief="solid").grid(row=0, column=5, sticky="w")

        # Highline mode is a staged Free-D setting. Changing the drop-down does
        # not alter the active graph/calculation until Apply is pressed; Reset
        # restores the last saved mode.
        tk.Label(sag_row, text="Highline:", fg="#dddddd", bg="#1a1a1a", font=sag_font).grid(row=1, column=0, sticky="e", padx=(0, 2), pady=(3, 0))
        highline_combo = ttk.Combobox(
            sag_row,
            textvariable=self._freed_highline_mode_var,
            values=["Single Highline", "Dual Highline"],
            state="readonly",
            width=14,
        )
        highline_combo.grid(row=1, column=1, columnspan=2, sticky="w", padx=(0, 4), pady=(3, 0))


        tk.Label(lens_card, text="Lens Calibration", fg="#dddddd", bg="#1a1a1a", font=FONT_SMALL_BOLD).grid(row=0, column=0, columnspan=3, sticky="w", padx=12, pady=TAB_HEADING_PADY)
        self._freed_lens_type_var = tk.StringVar(value=str(getattr(self, "freed_lens_type", "i24")))
        self._freed_lens_scale_var = tk.StringVar(value=str(getattr(self, "freed_lens_scale_mode", "Auto")))
        self._freed_zoom_wide_var = tk.StringVar(value="")
        self._freed_zoom_tele_var = tk.StringVar(value="")
        self._freed_focus_near_var = tk.StringVar(value="")
        self._freed_focus_far_var = tk.StringVar(value="")
        self._freed_zoom_live_var = tk.StringVar(value="--")
        self._freed_focus_live_var = tk.StringVar(value="--")
        self._sync_lens_cal_vars()
        self._update_lens_live_vars()

        # v26.06.26.25: keep the four-column Lens Calibration
        # layout, but restore standard SRVR body/value font size for readability.
        for _lc in range(4):
            lens_card.columnconfigure(_lc, weight=1 if _lc in (1, 3) else 0)

        compact_label_font = FONT_SMALL
        compact_value_font = FONT_SMALL
        compact_px = 2
        compact_py = 1

        def _lens_value_label(var):
            return tk.Label(
                lens_card,
                textvariable=var,
                fg="#cfcfcf",
                bg="#111111",
                font=compact_value_font,
                anchor="w",
                width=10,
                bd=1,
                relief="solid",
            )

        tk.Label(lens_card, text="Data:", fg="#dddddd", bg="#1a1a1a", font=compact_label_font).grid(row=1, column=0, sticky="e", padx=(7, compact_px), pady=compact_py)
        lens_type_combo = ttk.Combobox(lens_card, textvariable=self._freed_lens_type_var, values=["i16", "u16", "i24", "u24"], state="readonly", width=5)
        lens_type_combo.grid(row=1, column=1, sticky="ew", padx=(0, 5), pady=compact_py)
        lens_type_combo.bind("<<ComboboxSelected>>", lambda _e: self._update_lens_settings_from_ui(save=True))
        tk.Label(lens_card, text="Scale:", fg="#dddddd", bg="#1a1a1a", font=compact_label_font).grid(row=1, column=2, sticky="e", padx=(0, compact_px), pady=compact_py)
        lens_scale_combo = ttk.Combobox(lens_card, textvariable=self._freed_lens_scale_var, values=["Auto", "Manual", "Full scale"], state="readonly", width=8)
        lens_scale_combo.grid(row=1, column=3, sticky="ew", padx=(0, 7), pady=compact_py)
        lens_scale_combo.bind("<<ComboboxSelected>>", lambda _e: self._update_lens_settings_from_ui(save=True))

        tk.Label(lens_card, text="Zoom Live:", fg="#dddddd", bg="#1a1a1a", font=compact_label_font).grid(row=2, column=0, sticky="e", padx=(7, compact_px), pady=compact_py)
        _lens_value_label(self._freed_zoom_live_var).grid(row=2, column=1, columnspan=3, sticky="ew", padx=(0, 7), pady=compact_py)
        ttk.Button(lens_card, text="Wide", command=lambda: self._capture_lens_endpoint("zoom_wide")).grid(row=3, column=0, sticky="ew", padx=(7, 3), pady=compact_py)
        _lens_value_label(self._freed_zoom_wide_var).grid(row=3, column=1, sticky="ew", padx=(0, 5), pady=compact_py)
        ttk.Button(lens_card, text="Tele", command=lambda: self._capture_lens_endpoint("zoom_tele")).grid(row=3, column=2, sticky="ew", padx=(0, 3), pady=compact_py)
        _lens_value_label(self._freed_zoom_tele_var).grid(row=3, column=3, sticky="ew", padx=(0, 7), pady=compact_py)

        tk.Label(lens_card, text="Focus Live:", fg="#dddddd", bg="#1a1a1a", font=compact_label_font).grid(row=4, column=0, sticky="e", padx=(7, compact_px), pady=compact_py)
        _lens_value_label(self._freed_focus_live_var).grid(row=4, column=1, columnspan=3, sticky="ew", padx=(0, 7), pady=compact_py)
        ttk.Button(lens_card, text="Near", command=lambda: self._capture_lens_endpoint("focus_near")).grid(row=5, column=0, sticky="ew", padx=(7, 3), pady=compact_py)
        _lens_value_label(self._freed_focus_near_var).grid(row=5, column=1, sticky="ew", padx=(0, 5), pady=compact_py)
        ttk.Button(lens_card, text="Far", command=lambda: self._capture_lens_endpoint("focus_far")).grid(row=5, column=2, sticky="ew", padx=(0, 3), pady=compact_py)
        _lens_value_label(self._freed_focus_far_var).grid(row=5, column=3, sticky="ew", padx=(0, 7), pady=compact_py)

        ttk.Button(lens_card, text="Reset Lens Calibration", command=self._reset_lens_calibration).grid(row=6, column=0, columnspan=4, sticky="ew", padx=7, pady=(4, 3))

        # Standard Free-D Actions card on the far right, matching the Setup tab.
        act_card = tk.Frame(parent, bg="#1a1a1a", width=TAB_ACTIONS_W, height=TAB_ACTIONS_H, highlightbackground="#2a2f3a", highlightthickness=1)
        act_card.grid(row=0, column=4, sticky="nw", padx=(4, 8), pady=TAB_CARD_PADY)
        act_card.grid_propagate(False)
        act_card.columnconfigure(0, weight=1)

        tk.Label(act_card, text="Actions", fg="#dddddd", bg="#1a1a1a", font=FONT_SMALL_BOLD).grid(
            row=0, column=0, sticky="w", padx=12, pady=TAB_HEADING_PADY
        )
        ttk.Button(act_card, text="Apply", command=self._save_freed_tab_settings).grid(row=1, column=0, sticky="ew", padx=10, pady=TAB_ACTION_BUTTON_PADY)
        ttk.Button(act_card, text="Reset", command=self._revert_freed_tab_settings).grid(row=2, column=0, sticky="ew", padx=10, pady=TAB_ACTION_BUTTON_PADY)
        self._freed_actions_status = tk.StringVar(value="")
        tk.Label(act_card, textvariable=self._freed_actions_status, fg="#dddddd", bg="#1a1a1a", font=label_font, anchor="w", justify="left").grid(
            row=3, column=0, sticky="w", padx=10, pady=TAB_ACTION_STATUS_PADY
        )

        self._freed_io_confirm_target = None
        self._freed_io_confirm_until = 0.0
        self._freed_io_confirmed_target = None
        self._freed_io_confirmed_until = 0.0
        self._normalise_freed_offset_fields()
        # Input/Output state drop-downs are staged until Apply.

    def _normalise_freed_offset_fields(self):
        """Keep all editable Free-D angle/position offsets at three decimals."""
        for mapping_name in ("_freed_input_offset_vars", "_freed_output_offset_vars"):
            try:
                for var in (getattr(self, mapping_name, {}) or {}).values():
                    text = str(var.get()).strip()
                    if text not in ("", "-", ".", "-."):
                        var.set(f"{float(text):0.3f}")
            except Exception:
                pass

    def _refresh_freed_io_toggle_buttons(self):
        """Refresh the Free-D Input/Output confirmation toggle labels."""
        try:
            now = time.time()
            if self._freed_io_confirm_until and now > float(self._freed_io_confirm_until):
                self._freed_io_confirm_target = None
                self._freed_io_confirm_until = 0.0
            if self._freed_io_confirmed_until and now > float(self._freed_io_confirmed_until):
                self._freed_io_confirmed_target = None
                self._freed_io_confirmed_until = 0.0

            states = {
                "input": bool(getattr(self, "freed_input_enabled", False)),
                "output": bool(getattr(self, "freed_output_enabled", False)),
            }
            labels = {
                "input": getattr(self, "_freed_input_toggle_text_var", None),
                "output": getattr(self, "_freed_output_toggle_text_var", None),
            }
            for target, var in labels.items():
                if var is None:
                    continue
                if self._freed_io_confirmed_target == target:
                    text = "Confirmed"
                elif self._freed_io_confirm_target == target:
                    text = "Confirm?"
                else:
                    text = f"{target.title()} {'On' if states[target] else 'Off'}"
                var.set(text)
        except Exception:
            pass

    def _on_freed_io_toggle(self, target: str):
        """Toggle Free-D Input or Output using the same 10 s / 2 s Aux confirmation timing."""
        try:
            target = str(target or "").strip().lower()
            if target not in ("input", "output"):
                return
            now = time.time()
            if self._freed_io_confirm_target == target and now <= float(self._freed_io_confirm_until or 0.0):
                self._freed_io_confirm_target = None
                self._freed_io_confirm_until = 0.0
                self._freed_io_confirmed_target = target
                self._freed_io_confirmed_until = now + 2.0

                if target == "input":
                    new_state = not bool(getattr(self, "freed_input_enabled", False))
                    self.freed_input_enabled = new_state
                    self._freed_input_enabled_var.set("ON" if new_state else "OFF")
                    self._ensure_freed_input_listener()
                else:
                    new_state = not bool(getattr(self, "freed_output_enabled", False))
                    self.freed_output_enabled = new_state
                    self._freed_enabled_var.set("ON" if new_state else "OFF")
                    self._ensure_freed_output_thread()

                # Persist only the confirmed live On/Off state. Other fields still use Apply.
                self._save_config()
                self._set_status(f"Free-D {target} {'enabled' if new_state else 'disabled'}")
            else:
                self._freed_io_confirm_target = target
                self._freed_io_confirm_until = now + 10.0
                self._freed_io_confirmed_target = None
                self._freed_io_confirmed_until = 0.0

            self._refresh_freed_io_toggle_buttons()
            try:
                self.root.after(2100, self._refresh_freed_io_toggle_buttons)
                self.root.after(10100, self._refresh_freed_io_toggle_buttons)
            except Exception:
                pass
        except Exception:
            pass

    def _save_freed_tab_settings(self):
        try:
            self._normalise_freed_offset_fields()
            self.freed_output_enabled = (str(self._freed_enabled_var.get()).upper() == "ON")
            self.freed_target_ip = str(self._freed_ip_var.get()).strip()
            self.freed_target_port = max(1, min(65535, int(float(self._freed_port_var.get()))))
            self.freed_camera_id = max(0, min(255, int(float(self._freed_cam_var.get()))))
            self.freed_rate_hz = max(1.0, min(100.0, float(self._freed_rate_var.get())))
            self.freed_z_offset_m = float(self._freed_zoffset_var.get())
            self.freed_x_m = self.freed_z_offset_m  # legacy config compatibility
            # Free-D position scale is retained as a config value, but not mixed with W1P CMD Units Per M in the UI.
            self.freed_pos_scale = max(1.0, float(getattr(self, "freed_pos_scale", 640.0) or 640.0))
            self.freed_skate_weight_kg = max(0.0, float(getattr(self, "_freed_skate_weight_var", tk.StringVar(value="35.0")).get()))
            self.freed_weight_per_100m_kg = max(0.0, float(getattr(self, "_freed_weight_per_100m_var", tk.StringVar(value="4.8")).get()))
            self.freed_sag_tension_kgf = max(1.0, float(getattr(self, "_freed_tension_var", tk.StringVar(value="1200.0")).get()))
            selected_highline_mode = str(getattr(self, "_freed_highline_mode_var", tk.StringVar(value="Single Highline")).get() or "Single Highline")
            self.freed_highline_mode = "Dual Highline" if selected_highline_mode.strip().lower().startswith("dual") else "Single Highline"
            self.freed_output_inverts = {
                name: bool(var.get())
                for name, var in getattr(self, "_freed_output_invert_vars", {}).items()
            }
            self.freed_output_offsets = {
                name: float(var.get() or 0.0)
                for name, var in getattr(self, "_freed_output_offset_vars", {}).items()
            }
            self.freed_input_enabled = (str(self._freed_input_enabled_var.get()).upper() == "ON")
            self.freed_input_bind_ip = str(self._freed_input_bind_var.get()).strip() or "0.0.0.0"
            self.freed_input_port = max(1, min(65535, int(float(self._freed_input_port_var.get()))))
            self.freed_input_inverts = {
                name: bool(var.get())
                for name, var in getattr(self, "_freed_input_invert_vars", {}).items()
            }
            self.freed_input_offsets = {
                name: float(var.get() or 0.0)
                for name, var in getattr(self, "_freed_input_offset_vars", {}).items()
            }
            if hasattr(self, "_freed_lens_type_var"):
                self.freed_lens_type = str(self._freed_lens_type_var.get()).strip() or "i24"
            if hasattr(self, "_freed_lens_scale_var"):
                self.freed_lens_scale_mode = str(self._freed_lens_scale_var.get()).strip() or "Auto"
            try:
                self.freed_lens_cal = {
                    "zoom_wide": float(self._freed_zoom_wide_var.get()),
                    "zoom_tele": float(self._freed_zoom_tele_var.get()),
                    "focus_near": float(self._freed_focus_near_var.get()),
                    "focus_far": float(self._freed_focus_far_var.get()),
                }
            except Exception:
                self._reset_lens_calibration()
            pts = []
            for row in getattr(self, "_freed_point_vars", []):
                z_text = str(row.get("z").get()).strip() if row.get("z") is not None else ""
                pts.append({
                    "enabled": bool(row["enabled"].get()),
                    "y_m": float(row["x"].get()),  # legacy key: X tracking position along span
                    "z_m": float(row["y"].get()),  # legacy key: Y sag/height
                    "z_offset_m": float(z_text) if z_text else 0.0,
                })
            self.freed_height_points = pts[:5]
            self._save_config()
            self._ensure_freed_input_listener()
            self._ensure_freed_output_thread()
            self._redraw_freed_top_view()
            self._redraw_freed_side_view()
            self._redraw_run_live_section()
            if hasattr(self, "_freed_actions_status"):
                self._freed_actions_status.set("Saved")
            self._set_status(f"Free-D output {'enabled' if self.freed_output_enabled else 'disabled'} -> {self.freed_target_ip}:{self.freed_target_port}")
        except Exception as e:
            if hasattr(self, "_freed_actions_status"):
                self._freed_actions_status.set("Save failed")
            try:
                messagebox.showerror("Free-D", f"Failed to save Free-D settings:\n{e}")
            except Exception:
                pass

    def _revert_freed_tab_settings(self):
        try:
            cfg = self._load_saved_config_dict()
            self._apply_freed_config(cfg.get("free_d", {}))
            if hasattr(self, "_freed_enabled_var"):
                self._freed_enabled_var.set("ON" if getattr(self, "freed_output_enabled", False) else "OFF")
                self._freed_ip_var.set(str(getattr(self, "freed_target_ip", "172.20.1.120")))
                self._freed_port_var.set(str(getattr(self, "freed_target_port", 40000)))
                self._freed_cam_var.set(str(getattr(self, "freed_camera_id", 1)))
                self._freed_rate_var.set(f"{float(getattr(self, 'freed_rate_hz', 25.0)):0.3f}")
                self._freed_zoffset_var.set(f"{float(getattr(self, 'freed_z_offset_m', getattr(self, 'freed_z_offset_m', 0.0))):0.3f}")
                self._freed_scale_var.set(f"{float(getattr(self, 'freed_pos_scale', 640.0)):0.1f}")
                self._freed_input_enabled_var.set("ON" if bool(getattr(self, "freed_input_enabled", False)) else "OFF")
                self._freed_input_bind_var.set(str(getattr(self, "freed_input_bind_ip", "0.0.0.0")))
                self._freed_input_port_var.set(str(getattr(self, "freed_input_port", 40001)))
                if hasattr(self, "_freed_skate_weight_var"):
                    self._freed_skate_weight_var.set(f"{float(getattr(self, 'freed_skate_weight_kg', 35.0)):0.1f}")
                if hasattr(self, "_freed_weight_per_100m_var"):
                    self._freed_weight_per_100m_var.set(f"{float(getattr(self, 'freed_weight_per_100m_kg', 4.8)):0.2f}")
                if hasattr(self, "_freed_tension_var"):
                    self._freed_tension_var.set(f"{float(getattr(self, 'freed_sag_tension_kgf', 1200.0)):0.1f}")
                if hasattr(self, "_freed_highline_mode_var"):
                    restored_mode = str(getattr(self, "freed_highline_mode", "Single Highline") or "Single Highline")
                    self._freed_highline_mode_var.set("Dual Highline" if restored_mode.strip().lower().startswith("dual") else "Single Highline")
                saved_inverts = dict(getattr(self, "freed_input_inverts", {}) or {})
                for name, var in getattr(self, "_freed_input_invert_vars", {}).items():
                    var.set(bool(saved_inverts.get(name, False)))
                saved_in_offsets = dict(getattr(self, "freed_input_offsets", {}) or {})
                for name, var in getattr(self, "_freed_input_offset_vars", {}).items():
                    var.set(f"{float(saved_in_offsets.get(name, 0.0) or 0.0):0.3f}")
                saved_out_inverts = dict(getattr(self, "freed_output_inverts", {}) or {})
                for name, var in getattr(self, "_freed_output_invert_vars", {}).items():
                    var.set(bool(saved_out_inverts.get(name, False)))
                saved_out_offsets = dict(getattr(self, "freed_output_offsets", {}) or {})
                for name, var in getattr(self, "_freed_output_offset_vars", {}).items():
                    var.set(f"{float(saved_out_offsets.get(name, 0.0) or 0.0):0.3f}")
                self._sync_lens_cal_vars()
                pts = list(getattr(self, "freed_height_points", []) or [])
                while len(pts) < 5:
                    pts.append({"enabled": False, "y_m": 0.0, "z_m": 0.0})
                for i, row in enumerate(getattr(self, "_freed_point_vars", [])):
                    p = pts[i] if i < len(pts) and isinstance(pts[i], dict) else {}
                    row["enabled"].set(bool(p.get("enabled", True)))
                    row["x"].set(f"{float(p.get('y_m', 0.0)):0.3f}")
                    row["y"].set(f"{float(p.get('z_m', 0.0)):0.3f}")
                    if "z" in row:
                        row["z"].set(f"{float(p.get('z_offset_m', getattr(self, 'freed_z_offset_m', 0.0))):0.3f}" if i in (0, 4) else "")
            self._ensure_freed_input_listener()
            self._ensure_freed_output_thread()
            self._normalise_freed_offset_fields()
            self._redraw_freed_top_view()
            self._redraw_freed_side_view()
            self._redraw_run_live_section()
            if hasattr(self, "_freed_actions_status"):
                self._freed_actions_status.set("Recalled")
        except Exception:
            if hasattr(self, "_freed_actions_status"):
                self._freed_actions_status.set("Recall failed")




    def _build_controller_settings_tab(self, parent):
        """Setup tab lower section: CTRL settings, AUX, joystick calibration, W1P settings, W1P-TS AUX assignments, and W1P RS485 calibration."""
        parent.configure(bg="#111111")
        for c in range(3):
            parent.columnconfigure(c, weight=1, uniform="ctrl_content_cols")
        parent.rowconfigure(0, weight=0, minsize=82)
        parent.rowconfigure(1, weight=0, minsize=82)

        label_font = ("Segoe UI", 9)
        entry_w = 18
        options = ["None"] + [x for x in AUX_ACTION_OPTIONS if x != "None"]
        setup_card_h = 82

        def make_card(row, col, title, padx):
            card = tk.Frame(parent, bg="#1a1a1a", highlightbackground="#2a2f3a", highlightthickness=1, height=setup_card_h)
            card.grid(row=row, column=col, sticky="nsew", padx=padx, pady=TAB_CARD_PADY)
            card.grid_propagate(False)
            tk.Label(card, text=title, fg="#dddddd", bg="#1a1a1a", font=FONT_SMALL_BOLD).grid(
                row=0, column=0, columnspan=6, sticky="w", padx=12, pady=(3, 1)
            )
            return card

        # ---------------- CTRL settings ----------------
        card = make_card(0, 0, "Controller Settings", (8, 4))
        card.columnconfigure(0, weight=0)
        card.columnconfigure(1, weight=1)
        card.columnconfigure(2, weight=0)
        card.columnconfigure(3, weight=1)

        try:
            if not hasattr(self, "_tab_joy_center_var"):
                self._tab_joy_center_var = tk.StringVar(value=str(controller_state.get("joy_center", 0.0)))
            if not hasattr(self, "_tab_joy_min_var"):
                self._tab_joy_min_var = tk.StringVar(value=str(controller_state.get("joy_min", -1.0)))
            if not hasattr(self, "_tab_joy_max_var"):
                self._tab_joy_max_var = tk.StringVar(value=str(controller_state.get("joy_max", 1.0)))
            if not hasattr(self, "_tab_joy_current_var"):
                self._tab_joy_current_var = tk.StringVar(value="--")
        except Exception:
            pass

        tk.Label(card, text="CTRL IP:", fg="#dddddd", bg="#1a1a1a", font=label_font).grid(
            row=1, column=0, sticky="e", padx=(12, 4), pady=TAB_ROW_PADY
        )
        self._tab_ctrl_ip = tk.StringVar(value=getattr(self, "controller_ip_ref", ""))
        tk.Entry(card, textvariable=self._tab_ctrl_ip, width=16, bg="#111111", fg="#dddddd", insertbackground="#dddddd", bd=1, relief="solid", font=label_font).grid(
            row=1, column=1, sticky="w", padx=(2, 10), pady=TAB_ROW_PADY
        )

        tk.Label(card, text="CTRL-TS Link:", fg="#dddddd", bg="#1a1a1a", font=label_font).grid(
            row=1, column=2, sticky="e", padx=(8, 4), pady=TAB_ROW_PADY
        )
        self._tab_ctrl_ts_ip = tk.StringVar(value="Disconnected")
        tk.Entry(card, textvariable=self._tab_ctrl_ts_ip, width=16, state="readonly", readonlybackground="#111111", fg="#dddddd", bd=1, relief="solid", font=label_font).grid(
            row=1, column=3, sticky="w", padx=(2, 12), pady=TAB_ROW_PADY
        )

        tk.Label(card, text="ADS1115 Link:", fg="#dddddd", bg="#1a1a1a", font=label_font).grid(
            row=2, column=2, sticky="e", padx=(8, 4), pady=TAB_ROW_PADY
        )
        self._tab_ads1115_link = tk.StringVar(value="Disconnected")
        tk.Entry(card, textvariable=self._tab_ads1115_link, width=16, state="readonly", readonlybackground="#111111", fg="#dddddd", bd=1, relief="solid", font=label_font).grid(
            row=2, column=3, sticky="w", padx=(2, 12), pady=TAB_ROW_PADY
        )

        tk.Label(card, text="Direction:", fg="#dddddd", bg="#1a1a1a", font=label_font).grid(
            row=2, column=0, sticky="e", padx=TAB_LABEL_PADX, pady=TAB_ROW_PADY
        )
        self._tab_ctrl_dir = tk.StringVar(value="Inverted" if getattr(self, "reverse_joystick", False) else "Normal")
        ttk.Combobox(card, textvariable=self._tab_ctrl_dir, values=["Normal", "Inverted"], state="readonly", width=12).grid(
            row=2, column=1, sticky="w", padx=TAB_VALUE_PADX, pady=TAB_ROW_PADY
        )
        self._tab_ctrl_pos_var = tk.StringVar(value="--")

        # ---------------- CTRL AUX Assign ----------------
        aux_card = make_card(0, 1, "CTRL-TS Aux Assign", (4, 4))
        aux_card.columnconfigure(0, weight=0)
        aux_card.columnconfigure(1, weight=1)
        aux_grid = tk.Frame(aux_card, bg="#1a1a1a")
        aux_grid.grid(row=1, column=0, columnspan=6, sticky="ew", padx=12, pady=(0, 2))
        aux_grid.columnconfigure(0, weight=0, minsize=55)
        aux_grid.columnconfigure(1, weight=1, minsize=132, uniform="ctrlts_setup_aux_combo_cols")
        aux_grid.columnconfigure(2, weight=0, minsize=70)
        aux_grid.columnconfigure(3, weight=1, minsize=132, uniform="ctrlts_setup_aux_combo_cols")
        self._aux1_action = tk.StringVar(value=getattr(self, "aux1_action", "None"))
        self._aux2_action = tk.StringVar(value=getattr(self, "aux2_action", "None"))
        self._aux3_action = tk.StringVar(value=getattr(self, "aux3_action", "None"))
        self._aux4_action = tk.StringVar(value=getattr(self, "aux4_action", "None"))
        for i, (label, var) in enumerate([
            ("Aux 1:", self._aux1_action), ("Aux 2:", self._aux2_action),
            ("Aux 3:", self._aux3_action), ("Aux 4:", self._aux4_action)
        ]):
            r = i // 2
            c = (i % 2) * 2
            tk.Label(aux_grid, text=label, fg="#dddddd", bg="#1a1a1a", font=label_font).grid(row=r, column=c, sticky="e", padx=((0 if c == 0 else 16), 4), pady=2)
            ttk.Combobox(aux_grid, textvariable=var, values=options, state="readonly", width=entry_w - 2).grid(row=r, column=c+1, sticky="ew", padx=(0, 12 if c == 0 else 0), pady=2)

        # ---------------- Controller joystick calibration ----------------
        cal_card = make_card(0, 2, "Controller Calibration", (4, 8))
        cal_card.columnconfigure(0, weight=1)
        cal_card.columnconfigure(1, weight=0)

        def _joy_get_raw():
            try:
                return float(controller_state.get("joystick_raw", controller_state.get("joystick", 0.0)) or 0.0)
            except Exception:
                return 0.0

        def _joy_set(which: str):
            v = _joy_get_raw()
            if which == "center":
                self._tab_joy_center_var.set(f"{v:.3f}")
            elif which == "min":
                self._tab_joy_min_var.set(f"{v:.3f}")
            elif which == "max":
                self._tab_joy_max_var.set(f"{v:.3f}")
            try:
                self._tab_joy_status.set(f"Captured {which}: {v:.3f}")
            except Exception:
                pass

        def _joy_apply_local():
            try:
                c = float(self._tab_joy_center_var.get())
                mn = float(self._tab_joy_min_var.get())
                mx = float(self._tab_joy_max_var.get())
                if not (mn < c < mx):
                    self._tab_joy_status.set("Invalid: require min < center < max")
                    return
                controller_state["joy_center"] = c
                controller_state["joy_min"] = mn
                controller_state["joy_max"] = mx
                self._tab_joy_status.set("Applied calibration")
            except Exception:
                try:
                    self._tab_joy_status.set("Apply failed")
                except Exception:
                    pass

        def _joy_reset_local():
            try:
                controller_state["joy_center"] = 0.0
                controller_state["joy_min"] = -1.0
                controller_state["joy_max"] = 1.0
                self._tab_joy_center_var.set("0.0")
                self._tab_joy_min_var.set("-1.0")
                self._tab_joy_max_var.set("1.0")
                self._tab_joy_status.set("Reset calibration")
            except Exception:
                pass

        grid = tk.Frame(cal_card, bg="#1a1a1a")
        grid.grid(row=1, column=0, columnspan=1, sticky="w", padx=12, pady=(0, 3))
        for c in range(6):
            grid.columnconfigure(c, weight=0)
        tk.Label(grid, text="Current:", fg="#dddddd", bg="#1a1a1a", font=label_font).grid(row=0, column=0, sticky="e", padx=(0,3), pady=2)
        tk.Entry(grid, textvariable=self._tab_joy_current_var, width=7, state="readonly", readonlybackground="#111111", fg="#dddddd", bd=1, relief="solid", font=label_font).grid(row=0, column=1, sticky="w", padx=(0,6), pady=2)
        tk.Label(grid, text="Center:", fg="#dddddd", bg="#1a1a1a", font=label_font).grid(row=0, column=3, sticky="e", padx=(4,3), pady=2)
        tk.Entry(grid, textvariable=self._tab_joy_center_var, width=6, bg="#111111", fg="#dddddd", insertbackground="#dddddd", bd=1, relief="solid", font=label_font).grid(row=0, column=4, sticky="w", padx=(0,4), pady=2)
        ttk.Button(grid, text="Set", width=4, command=lambda: _joy_set("center")).grid(row=0, column=5, sticky="w", padx=(0,0), pady=2)
        tk.Label(grid, text="Min:", fg="#dddddd", bg="#1a1a1a", font=label_font).grid(row=1, column=0, sticky="e", padx=(0,3), pady=2)
        tk.Entry(grid, textvariable=self._tab_joy_min_var, width=7, bg="#111111", fg="#dddddd", insertbackground="#dddddd", bd=1, relief="solid", font=label_font).grid(row=1, column=1, sticky="w", padx=(0,6), pady=2)
        ttk.Button(grid, text="Set", width=4, command=lambda: _joy_set("min")).grid(row=1, column=2, sticky="w", padx=(0,6), pady=2)
        tk.Label(grid, text="Max:", fg="#dddddd", bg="#1a1a1a", font=label_font).grid(row=1, column=3, sticky="e", padx=(4,3), pady=2)
        tk.Entry(grid, textvariable=self._tab_joy_max_var, width=6, bg="#111111", fg="#dddddd", insertbackground="#dddddd", bd=1, relief="solid", font=label_font).grid(row=1, column=4, sticky="w", padx=(0,4), pady=2)
        ttk.Button(grid, text="Set", width=4, command=lambda: _joy_set("max")).grid(row=1, column=5, sticky="w", padx=(0,0), pady=2)
        # Controller Calibration captures are applied/saved through the main Setup Actions box.
        self._tab_joy_status = tk.StringVar(value="")
        self._tab_joy_status_label = tk.Label(cal_card, textvariable=self._tab_joy_status, fg="#dddddd", bg="#1a1a1a", font=label_font, anchor="w", justify="left")
        def _joy_status_trace(*_args):
            try:
                msg = str(self._tab_joy_status.get() or "").strip()
                if msg:
                    self._tab_joy_status_label.grid(row=2, column=0, columnspan=6, sticky="w", padx=TAB_VALUE_PADX, pady=(1, 0))
                else:
                    self._tab_joy_status_label.grid_remove()
            except Exception:
                pass
        try:
            self._tab_joy_status.trace_add("write", _joy_status_trace)
        except Exception:
            pass

        # ---------------- W1P winch settings below Controller Settings ----------------
        settings_card = make_card(1, 0, "Winch Settings", (8, 4))
        settings_card.columnconfigure(0, weight=0)
        settings_card.columnconfigure(1, weight=1)
        settings_card.columnconfigure(2, weight=0)
        settings_card.columnconfigure(3, weight=1)
        self._tab_winch_type = tk.StringVar(value=getattr(self, "winch_type", "HV P2P W1P"))
        self._tab_winch_ip = tk.StringVar(value=getattr(self, "winch_host", ""))
        self._tab_winch_dir = tk.StringVar(value="Inverted" if getattr(self, "reverse_motor", False) else "Normal")
        self._tab_w1pts_link_var = tk.StringVar(value="N/A")
        self._tab_winch_rs_var = tk.StringVar(value=getattr(self, 'winch_rs_status', '--'))
        tk.Label(settings_card, text="W1P IP:", fg="#dddddd", bg="#1a1a1a", font=label_font).grid(row=1, column=0, sticky="e", padx=(12, 4), pady=TAB_ROW_PADY)
        tk.Entry(settings_card, textvariable=self._tab_winch_ip, width=16, bg="#111111", fg="#dddddd", insertbackground="#dddddd", bd=1, relief="solid", font=label_font).grid(row=1, column=1, sticky="w", padx=(2, 10), pady=TAB_ROW_PADY)
        tk.Label(settings_card, text="W1P-TS Link:", fg="#dddddd", bg="#1a1a1a", font=label_font).grid(row=1, column=2, sticky="e", padx=(8, 4), pady=TAB_ROW_PADY)
        tk.Entry(settings_card, textvariable=self._tab_w1pts_link_var, width=16, state="readonly", readonlybackground="#111111", fg="#dddddd", bd=1, relief="solid", font=label_font).grid(row=1, column=3, sticky="w", padx=(2, 12), pady=TAB_ROW_PADY)
        tk.Label(settings_card, text="Direction:", fg="#dddddd", bg="#1a1a1a", font=label_font).grid(row=2, column=0, sticky="e", padx=(12, 4), pady=TAB_ROW_PADY)
        ttk.Combobox(settings_card, textvariable=self._tab_winch_dir, values=["Normal", "Inverted"], state="readonly", width=12).grid(row=2, column=1, sticky="w", padx=(2, 10), pady=TAB_ROW_PADY)
        tk.Label(settings_card, text="RS485 Link:", fg="#dddddd", bg="#1a1a1a", font=label_font).grid(row=2, column=2, sticky="e", padx=(8, 4), pady=TAB_ROW_PADY)
        tk.Entry(settings_card, textvariable=self._tab_winch_rs_var, width=16, state="readonly", readonlybackground="#111111", fg="#dddddd", bd=1, relief="solid", highlightthickness=1, highlightbackground="#3c4454", font=label_font).grid(row=2, column=3, sticky="w", padx=(2, 12), pady=TAB_ROW_PADY)

        # ---------------- W1P-TS Aux Assign ----------------
        w1pts_aux_card = make_card(1, 1, "W1P-TS Aux Assign", (4, 4))
        w1pts_aux_card.columnconfigure(0, weight=0)
        w1pts_aux_card.columnconfigure(1, weight=1)
        w1pts_aux_grid = tk.Frame(w1pts_aux_card, bg="#1a1a1a")
        w1pts_aux_grid.grid(row=1, column=0, columnspan=6, sticky="ew", padx=12, pady=(0, 2))
        w1pts_aux_grid.columnconfigure(0, weight=0, minsize=55)
        w1pts_aux_grid.columnconfigure(1, weight=1, minsize=132, uniform="ctrlts_setup_aux_combo_cols")
        w1pts_aux_grid.columnconfigure(2, weight=0, minsize=70)
        w1pts_aux_grid.columnconfigure(3, weight=1, minsize=132, uniform="ctrlts_setup_aux_combo_cols")
        self._w1pts_aux1_action = tk.StringVar(value=getattr(self, "w1pts_aux1_action", "None"))
        self._w1pts_aux2_action = tk.StringVar(value=getattr(self, "w1pts_aux2_action", "None"))
        self._w1pts_aux3_action = tk.StringVar(value=getattr(self, "w1pts_aux3_action", "None"))
        self._w1pts_aux4_action = tk.StringVar(value=getattr(self, "w1pts_aux4_action", "None"))
        for i, (label, var) in enumerate([
            ("Aux 1:", self._w1pts_aux1_action), ("Aux 2:", self._w1pts_aux2_action),
            ("Aux 3:", self._w1pts_aux3_action), ("Aux 4:", self._w1pts_aux4_action)
        ]):
            r = i // 2
            c = (i % 2) * 2
            tk.Label(w1pts_aux_grid, text=label, fg="#dddddd", bg="#1a1a1a", font=label_font).grid(row=r, column=c, sticky="e", padx=((0 if c == 0 else 16), 4), pady=2)
            ttk.Combobox(w1pts_aux_grid, textvariable=var, values=options, state="readonly", width=entry_w - 2).grid(row=r, column=c+1, sticky="ew", padx=(0, 12 if c == 0 else 0), pady=2)

        # ---------------- W1P RS485 calibration below Controller Calibration ----------------
        calib_card = make_card(1, 2, "Winch Calibration", (4, 8))
        calib_card.columnconfigure(0, weight=0)
        calib_card.columnconfigure(1, weight=1)
        self._tab_winch_units_var = tk.StringVar(value=f"{getattr(self, 'winch_units_per_m', 21220.7):0.1f}")
        tk.Label(calib_card, text="CMD Units Per M:", fg="#dddddd", bg="#1a1a1a", font=label_font).grid(row=1, column=0, sticky="e", padx=TAB_LABEL_PADX, pady=TAB_ROW_PADY)
        self._tab_winch_units_entry = tk.Entry(calib_card, textvariable=self._tab_winch_units_var, width=entry_w, bg="#111111", fg="#dddddd", insertbackground="#dddddd", bd=1, relief="solid", font=label_font)
        self._tab_winch_units_entry.grid(row=1, column=1, sticky="w", padx=TAB_VALUE_PADX, pady=TAB_ROW_PADY)
        self._tab_winch_units_entry.bind("<KeyRelease>", lambda _e: (setattr(self, "_tab_winch_units_user_editing", True), setattr(self, "_tab_winch_units_dirty", True)))
        self._tab_winch_units_entry.bind("<FocusIn>", lambda _e: setattr(self, "_tab_winch_units_user_editing", True))
        self._tab_winch_units_entry.bind("<FocusOut>", lambda _e: setattr(self, "_tab_winch_units_user_editing", False))
        self._tab_winch_units_entry.bind("<Return>", lambda _e: self._save_winch_tab_settings())
        tk.Label(calib_card, text="Position Source:", fg="#dddddd", bg="#1a1a1a", font=label_font).grid(row=2, column=0, sticky="e", padx=TAB_LABEL_PADX, pady=TAB_ROW_PADY)
        self._tab_winch_possrc_var = tk.StringVar(value=getattr(self, 'winch_pos_source', '--'))
        tk.Entry(calib_card, textvariable=self._tab_winch_possrc_var, state="readonly", readonlybackground="#111111", fg="#dddddd", bd=1, relief="solid", highlightthickness=1, highlightbackground="#3c4454", font=label_font, width=entry_w).grid(row=2, column=1, sticky="w", padx=TAB_VALUE_PADX, pady=TAB_ROW_PADY)
        # RS485 link status now lives in Winch Settings so this calibration card stays compact.


    def _apply_controller_ip_change(self, new_ip: str):
        """Apply a changed CTRL IP immediately to the UDP filter and live link state.

        v12: do not clear live CTRL/CTRL-TS/ADS1115 state when the operator
        presses Apply but the IP did not actually change. Clearing those fields
        caused a visible Disconnected/E-Stop flash even though the live links
        were still healthy.
        """
        try:
            new_ref = (new_ip or "").strip()
        except Exception:
            new_ref = str(new_ip or "").strip()
        old_ref = str(getattr(self, "controller_ip_ref", "") or "").strip()
        changed = (new_ref != old_ref)
        self.controller_ip_ref = new_ref
        try:
            global controller_expected_ip
            controller_expected_ip = self.controller_ip_ref if self.controller_ip_ref else None
        except Exception:
            pass
        if not changed:
            return
        try:
            rx = controller_state.get("_rx_times")
            if rx is not None:
                rx.clear()
            controller_state["last_seen"] = 0.0
            controller_state["last_ip"] = None
            controller_state["last_port"] = None
            controller_state["_connected"] = False
            controller_state["connected"] = False
            controller_state["joystick"] = 0.0
            controller_state["joystick_raw"] = 0.0
            controller_state["flags"] = 0
            controller_state["hmi_last_seen"] = 0.0
            controller_state["hmi_connected_reported"] = False
            controller_state["ads1115_connected_reported"] = False
            controller_state["ads1115_last_seen"] = 0.0
        except Exception:
            pass
        try:
            self._joy_filt = 0.0
            self.last_controller_value = 0.0
        except Exception:
            pass
        try:
            self._log_ctrl_connected = None
        except Exception:
            pass


    def _load_saved_config_dict(self):
        cfg_path = getattr(self, "config_path", None)
        try:
            if cfg_path and os.path.exists(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as exc:
            _app_log(f"[SRVR] Config read failed: {exc}")
        return self._to_config_dict()

    def _save_aux_assignments(self):
        try:
            self.aux1_action = self._aux1_action.get()
            self.aux2_action = self._aux2_action.get()
            self.aux3_action = self._aux3_action.get()
            self.aux4_action = self._aux4_action.get()
            if hasattr(self, "_w1pts_aux1_action"):
                self.w1pts_aux1_action = self._w1pts_aux1_action.get()
                self.w1pts_aux2_action = self._w1pts_aux2_action.get()
                self.w1pts_aux3_action = self._w1pts_aux3_action.get()
                self.w1pts_aux4_action = self._w1pts_aux4_action.get()
            self._save_config()
            self._set_status("Aux assignments saved")
        except Exception:
            pass

    def _revert_aux_assignments(self):
        try:
            cfg = self._load_saved_config_dict()
            self.aux1_action = cfg.get("aux1_action", getattr(self, "aux1_action", "None"))
            self.aux2_action = cfg.get("aux2_action", getattr(self, "aux2_action", "None"))
            self.aux3_action = cfg.get("aux3_action", getattr(self, "aux3_action", "None"))
            self.aux4_action = cfg.get("aux4_action", getattr(self, "aux4_action", "None"))
            self.w1pts_aux1_action = cfg.get("w1pts_aux1_action", getattr(self, "w1pts_aux1_action", "None"))
            self.w1pts_aux2_action = cfg.get("w1pts_aux2_action", getattr(self, "w1pts_aux2_action", "None"))
            self.w1pts_aux3_action = cfg.get("w1pts_aux3_action", getattr(self, "w1pts_aux3_action", "None"))
            self.w1pts_aux4_action = cfg.get("w1pts_aux4_action", getattr(self, "w1pts_aux4_action", "None"))
            self._aux1_action.set(getattr(self, "aux1_action", "None"))
            self._aux2_action.set(getattr(self, "aux2_action", "None"))
            self._aux3_action.set(getattr(self, "aux3_action", "None"))
            self._aux4_action.set(getattr(self, "aux4_action", "None"))
            if hasattr(self, "_w1pts_aux1_action"):
                self._w1pts_aux1_action.set(getattr(self, "w1pts_aux1_action", "None"))
                self._w1pts_aux2_action.set(getattr(self, "w1pts_aux2_action", "None"))
                self._w1pts_aux3_action.set(getattr(self, "w1pts_aux3_action", "None"))
                self._w1pts_aux4_action.set(getattr(self, "w1pts_aux4_action", "None"))
        except Exception:
            pass

    def _save_controller_tab_settings(self):
        try:
            self._apply_controller_ip_change(self._tab_ctrl_ip.get().strip())
            self.ctrl_ts_ip_ref = ""
            self.reverse_joystick = (self._tab_ctrl_dir.get() == "Inverted")
            self._save_config()
            self._set_status(f"Controller settings saved (CTRL {self.controller_ip_ref}, CTRL-TS Link status shown live)")
        except Exception as e:
            try:
                messagebox.showerror("Controller", f"Failed to save settings:\n{e}")
            except Exception:
                pass

    def _revert_controller_tab_settings(self):
        try:
            self._tab_ctrl_ip.set(getattr(self, "controller_ip_ref", ""))
            if hasattr(self, "_tab_ctrl_ts_ip"):
                self._tab_ctrl_ts_ip.set("Disconnected")
            if hasattr(self, "_tab_ads1115_link"):
                self._tab_ads1115_link.set("Disconnected")
            self._tab_ctrl_dir.set("Inverted" if getattr(self, "reverse_joystick", False) else "Normal")
        except Exception:
            pass

    def _revert_joy_calibration(self):
        try:
            cfg = self._load_saved_config_dict()
            joy_cal = _normalize_joy_cal(cfg.get("joy_cal"))
            controller_state["joy_min"] = float(joy_cal["min"])
            controller_state["joy_center"] = float(joy_cal["center"])
            controller_state["joy_max"] = float(joy_cal["max"])
            if hasattr(self, "_tab_joy_min_var"):
                self._tab_joy_min_var.set(f"{controller_state['joy_min']:.3f}")
            if hasattr(self, "_tab_joy_center_var"):
                self._tab_joy_center_var.set(f"{controller_state['joy_center']:.3f}")
            if hasattr(self, "_tab_joy_max_var"):
                self._tab_joy_max_var.set(f"{controller_state['joy_max']:.3f}")
        except Exception:
            pass

    def _set_active_drive_mode(self, idx: int, save_config: bool = True):
        try:
            idx = 0 if int(idx) not in (0, 1) else int(idx)
        except Exception:
            idx = 0
        try:
            self.active_drive_mode = idx
            if hasattr(self, "drive_mode_sel"):
                self.drive_mode_sel.set(idx)
            modes = getattr(self, "drive_modes", None) or []
            if idx < len(modes):
                m = modes[idx]
                self.max_speed_mps = float(m.get("max_speed_mps", getattr(self, "max_speed_mps", 20.0)))
                self.max_accel_mps2 = float(m.get("max_accel_mps2", getattr(self, "max_accel_mps2", 2.0)))
                self.max_decel_mps2 = float(m.get("max_decel_mps2", getattr(self, "max_decel_mps2", 2.0)))
                self.max_crossover_mps2 = float(m.get("max_crossover_mps2", getattr(self, "max_crossover_mps2", 4.0)))
                self.max_stop_decel_mps2 = float(m.get("max_stop_decel_mps2", getattr(self, "max_stop_decel_mps2", self.max_decel_mps2)))
                self.goto_speed_mps = float(m.get("max_goto_speed_mps", getattr(self, "goto_speed_mps", min(self.max_speed_mps, 1.0))))
            try:
                self._sync_motion_profile_to_winch(force=True)
            except Exception:
                pass
            if save_config:
                self._save_config()
        except Exception:
            pass

    def _set_battery_change_mode(self, enabled: bool, save_config: bool = True):
        try:
            self.battery_change_mode = bool(enabled)
            if self.battery_change_mode:
                self._battery_change_went_outside_limits = False
            else:
                self._battery_change_went_outside_limits = False
            if hasattr(self, "_drive_batt_mode") and isinstance(self._drive_batt_mode, tk.StringVar):
                self._drive_batt_mode.set("ON" if self.battery_change_mode else "OFF")
            if hasattr(self, "battery_button"):
                self.battery_button.config(text=f"Battery Change Mode: {'ON' if self.battery_change_mode else 'OFF'}")
            try:
                self._sync_service_mode_to_winch()
                self._send_controller_display_packet(force=True)
            except Exception:
                pass
            if save_config:
                self._save_config()
        except Exception:
            pass

    def _normalise_accel_type(self, value=None) -> str:
        """Return the internal W1P acceleration mode name.

        User-facing names from v23 are:
        - Power: joystick input behaves like applied power/throttle.
        - Speed: joystick input is requested cable speed.

        Keep Dynamic/Traditional/Normal as accepted aliases so existing configs,
        W1P firmware, and older saved packages remain compatible.
        """
        try:
            s = str(getattr(self, "accel_type", "Dynamic") if value is None else value).strip().lower()
        except Exception:
            s = "dynamic"
        if s in ("power", "traditional", "normal", "throttle"):
            return "Traditional"
        return "Dynamic"

    def _display_accel_type(self, value=None) -> str:
        return "Power" if self._normalise_accel_type(value) == "Traditional" else "Speed"

    def _accel_type_command(self, value=None) -> str:
        return "TRADITIONAL" if self._normalise_accel_type(value) == "Traditional" else "DYNAMIC"

    def _toggle_accel_type(self, save_config: bool = True) -> str:
        cur_norm = self._normalise_accel_type()
        new_val = "Traditional" if cur_norm == "Dynamic" else "Dynamic"
        self.accel_type = new_val
        display_val = self._display_accel_type(new_val)
        try:
            if hasattr(self, "_drive_accel_type") and isinstance(self._drive_accel_type, tk.StringVar):
                self._drive_accel_type.set(display_val)
            if hasattr(self, "run_accel_mode_var"):
                self.run_accel_mode_var.set(display_val)
        except Exception:
            pass
        try:
            self._sync_motion_profile_to_winch(force=True)
        except Exception:
            pass
        if save_config:
            try:
                self._save_config()
            except Exception:
                pass
        return display_val

    def _build_winch_settings_tab(self, parent):
        """Winch settings tab (replaces popup Settings in Winch Connection panel)."""
        # Winch tab layout standard:
        # - Actions card remains the same fixed visible size as Controller / Free-D / Drive.
        # - Winch Settings and Calibration expand evenly across all remaining tab width.
        # - The Actions grid column is fixed/minimum-size rather than part of the
        #   weighted content-column group, so it does not reserve excess blank space.
        ACTIONS_W = TAB_ACTIONS_W
        ACTIONS_H = TAB_ACTIONS_H
        ACTIONS_COL_W = TAB_ACTIONS_COL_W
        parent.columnconfigure(0, weight=1, uniform="winch_content_cols")
        parent.columnconfigure(1, weight=1, uniform="winch_content_cols")
        parent.columnconfigure(2, weight=0, minsize=ACTIONS_COL_W)
        parent.rowconfigure(0, weight=0)

        settings_card = tk.Frame(parent, bg="#1a1a1a", highlightbackground="#2a2f3a", highlightthickness=1)
        settings_card.grid(row=0, column=0, sticky="new", padx=(8, 4), pady=TAB_CARD_PADY)
        settings_card.columnconfigure(0, weight=0)
        settings_card.columnconfigure(1, weight=1)

        calib_card = tk.Frame(parent, bg="#1a1a1a", highlightbackground="#2a2f3a", highlightthickness=1)
        calib_card.grid(row=0, column=1, sticky="new", padx=(4, 4), pady=TAB_CARD_PADY)
        calib_card.columnconfigure(0, weight=0)
        calib_card.columnconfigure(1, weight=1)

        act_card = tk.Frame(parent, bg="#1a1a1a", width=ACTIONS_W, height=ACTIONS_H, highlightbackground="#2a2f3a", highlightthickness=1)
        act_card.grid(row=0, column=2, sticky="nw", padx=(4, 8), pady=TAB_CARD_PADY)
        act_card.grid_propagate(False)
        act_card.columnconfigure(0, weight=1)

        label_font = ("Segoe UI", 9)
        entry_w = 20
        tk.Label(settings_card, text="Winch Settings", fg="#dddddd", bg="#1a1a1a", font=FONT_SMALL_BOLD).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=12, pady=TAB_HEADING_PADY
        )

        settings_card.columnconfigure(2, weight=0)
        settings_card.columnconfigure(3, weight=1)
        self._tab_winch_type = tk.StringVar(value=getattr(self, "winch_type", "HV P2P W1P"))
        self._tab_winch_ip = tk.StringVar(value=getattr(self, "winch_host", ""))
        self._tab_winch_dir = tk.StringVar(value="Inverted" if getattr(self, "reverse_motor", False) else "Normal")
        self._tab_w1pts_link_var = tk.StringVar(value="N/A")
        self._tab_winch_rs_var = tk.StringVar(value=getattr(self, 'winch_rs_status', '--'))

        tk.Label(settings_card, text="W1P IP:", fg="#dddddd", bg="#1a1a1a", font=label_font).grid(row=1, column=0, sticky="e", padx=(12, 4), pady=TAB_ROW_PADY)
        tk.Entry(settings_card, textvariable=self._tab_winch_ip, width=16).grid(row=1, column=1, sticky="w", padx=(2, 10), pady=TAB_ROW_PADY)
        tk.Label(settings_card, text="W1P-TS Link:", fg="#dddddd", bg="#1a1a1a", font=label_font).grid(row=1, column=2, sticky="e", padx=(8, 4), pady=TAB_ROW_PADY)
        tk.Entry(settings_card, textvariable=self._tab_w1pts_link_var, width=16, state="readonly", readonlybackground="#111111", fg="#dddddd", bd=1, relief="solid", font=label_font).grid(row=1, column=3, sticky="w", padx=(2, 12), pady=TAB_ROW_PADY)
        tk.Label(settings_card, text="Direction:", fg="#dddddd", bg="#1a1a1a", font=label_font).grid(row=2, column=0, sticky="e", padx=(12, 4), pady=TAB_ROW_PADY)
        ttk.Combobox(settings_card, textvariable=self._tab_winch_dir, values=["Normal", "Inverted"], state="readonly", width=12).grid(row=2, column=1, sticky="w", padx=(2, 10), pady=TAB_ROW_PADY)
        tk.Label(settings_card, text="RS485 Link:", fg="#dddddd", bg="#1a1a1a", font=label_font).grid(row=2, column=2, sticky="e", padx=(8, 4), pady=TAB_ROW_PADY)
        tk.Entry(settings_card, textvariable=self._tab_winch_rs_var, width=16, state="readonly", readonlybackground="#111111", fg="#dddddd", bd=1, relief="solid", highlightthickness=1, highlightbackground="#3c4454", font=label_font).grid(row=2, column=3, sticky="w", padx=(2, 12), pady=TAB_ROW_PADY)

        tk.Label(calib_card, text="Limit Calibration", fg="#dddddd", bg="#1a1a1a", font=FONT_SMALL_BOLD).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=12, pady=TAB_HEADING_PADY
        )

        tk.Label(calib_card, text="CMD Units Per M:", fg="#dddddd", bg="#1a1a1a", font=label_font).grid(
            row=1, column=0, sticky="e", padx=TAB_LABEL_PADX, pady=TAB_ROW_PADY
        )
        self._tab_winch_units_var = tk.StringVar(value=f"{getattr(self, 'winch_units_per_m', 21220.7):0.1f}")
        self._tab_winch_units_entry = tk.Entry(calib_card, textvariable=self._tab_winch_units_var, width=entry_w)
        self._tab_winch_units_entry.grid(
            row=1, column=1, sticky="w", padx=TAB_VALUE_PADX, pady=TAB_ROW_PADY
        )
        self._tab_winch_units_entry.bind("<KeyRelease>", lambda _e: (setattr(self, "_tab_winch_units_user_editing", True), setattr(self, "_tab_winch_units_dirty", True)))
        self._tab_winch_units_entry.bind("<FocusIn>", lambda _e: setattr(self, "_tab_winch_units_user_editing", True))
        self._tab_winch_units_entry.bind("<FocusOut>", lambda _e: setattr(self, "_tab_winch_units_user_editing", False))
        self._tab_winch_units_entry.bind("<Return>", lambda _e: self._save_winch_tab_settings())

        tk.Label(calib_card, text="Position Source:", fg="#dddddd", bg="#1a1a1a", font=label_font).grid(
            row=2, column=0, sticky="e", padx=TAB_LABEL_PADX, pady=TAB_ROW_PADY
        )
        self._tab_winch_possrc_var = tk.StringVar(value=getattr(self, 'winch_pos_source', '--'))
        possrc_entry = tk.Entry(calib_card, textvariable=self._tab_winch_possrc_var, state="readonly", readonlybackground="#111111", fg="#dddddd", bd=1, relief="solid", highlightthickness=1, highlightbackground="#3c4454", font=label_font, width=entry_w)
        possrc_entry.grid(row=2, column=1, sticky="w", padx=TAB_VALUE_PADX, pady=TAB_ROW_PADY)

        tk.Label(act_card, text="Actions", fg="#dddddd", bg="#1a1a1a", font=FONT_SMALL_BOLD).grid(
            row=0, column=0, sticky="w", padx=12, pady=TAB_HEADING_PADY
        )

        def _winch_tab_apply():
            ok = True
            try:
                self._save_winch_tab_settings()
            except Exception:
                ok = False
            try:
                if hasattr(self, "_winch_actions_status"):
                    self._winch_actions_status.set("Saved" if ok else "Save failed")
            except Exception:
                pass

        def _winch_tab_reset():
            ok = True
            try:
                self._revert_winch_tab_settings()
            except Exception:
                ok = False
            try:
                if hasattr(self, "_winch_actions_status"):
                    self._winch_actions_status.set("Recalled" if ok else "Recall failed")
            except Exception:
                pass

        ttk.Button(act_card, text="Apply", command=_winch_tab_apply).grid(row=1, column=0, sticky="ew", padx=10, pady=TAB_ACTION_BUTTON_PADY)
        ttk.Button(act_card, text="Reset", command=_winch_tab_reset).grid(row=2, column=0, sticky="ew", padx=10, pady=TAB_ACTION_BUTTON_PADY)
        self._winch_actions_status = tk.StringVar(value="")
        tk.Label(act_card, textvariable=self._winch_actions_status, fg="#dddddd", bg="#1a1a1a", font=label_font, anchor="w", justify="left").grid(
            row=3, column=0, sticky="w", padx=10, pady=TAB_ACTION_STATUS_PADY
        )

    def _refresh_drive_control_button(self):
        # Legacy manual drive-control UI removed. W1P automatically enables drive command writes
        # only while the SRVR/RS485/config/feedback/SRDY safety gate is healthy.
        return

    def _sync_drive_mode_legacy_name_keys(self):
        """Keep legacy top-level mode name keys aligned with drive_modes.

        v26.06.26.25: Some operator configs were copied between builds using
        mode_a_name/mode_b_name or drive_mode_names, while newer builds store
        names inside drive_modes[].  Keep all forms populated so copied
        config.json files preserve renamed Mode A / Mode B titles.
        """
        try:
            modes = getattr(self, "drive_modes", None) or []
            if len(modes) >= 2:
                self.mode_a_name = str(modes[0].get("name", getattr(self, "mode_a_name", "Mode A")) or "Mode A")
                self.mode_b_name = str(modes[1].get("name", getattr(self, "mode_b_name", "Mode B")) or "Mode B")
        except Exception:
            pass

    def _apply_drive_mode_legacy_name_keys(self, cfg: dict):
        """Apply mode names from any supported config key layout."""
        try:
            if not isinstance(cfg, dict):
                return
            names = None
            if isinstance(cfg.get("drive_mode_names"), list):
                names = cfg.get("drive_mode_names")
            a = cfg.get("mode_a_name", None)
            b = cfg.get("mode_b_name", None)
            if names and len(names) >= 2:
                a = names[0] if a in (None, "") else a
                b = names[1] if b in (None, "") else b
            if getattr(self, "drive_modes", None) and len(self.drive_modes) >= 2:
                if str(a or "").strip():
                    self.drive_modes[0]["name"] = str(a).strip()
                if str(b or "").strip():
                    self.drive_modes[1]["name"] = str(b).strip()
            self._sync_drive_mode_legacy_name_keys()
        except Exception:
            pass

    def _save_winch_tab_settings(self):
        try:
            new_type = self._tab_winch_type.get().strip() or "HV P2P W1P"
            new_host = self._tab_winch_ip.get().strip()
            old_host = str(getattr(self, "winch_host", "") or "").strip()
            self.winch_type = new_type
            self.winch_host = new_host
            self.reverse_motor = (self._tab_winch_dir.get() == "Inverted")
            self.winch_units_per_m = float(str(self._tab_winch_units_var.get()).strip())
            if self.winch_units_per_m < 1.0:
                self.winch_units_per_m = 1.0
            if hasattr(self, "_tab_winch_units_var"):
                self._tab_winch_units_var.set(f"{self.winch_units_per_m:0.1f}")
            self._tab_winch_units_user_editing = False
            self._tab_winch_units_dirty = False
            self._tab_winch_units_hold_until = time.time() + 5.0
            try:
                # v12: only re-open the W1P TCP client if the target IP changed.
                # Reconfiguring on every Apply caused a brief Winch Disconnected flash
                # and could make SRVR/CTRL-TS show a false safety change.
                if new_host != old_host:
                    self.arduino_client.reconfigure(self.winch_host, self.winch_port)
                    self.winch_drive_writes_enabled = False
                self.arduino_client.send(f"SET_UNITS_PER_M {self.winch_units_per_m:.1f}")
                self.arduino_client.send(f"SET_MOTOR_REVERSE {1 if bool(getattr(self, 'reverse_motor', False)) else 0}")
                self._sync_motion_profile_to_winch(force=True)
            except Exception:
                pass
            self._save_config()
            self._set_status(f"Winch settings saved ({self.winch_type} @ {self.winch_host})")
        except Exception as e:
            try:
                messagebox.showerror("Winch", f"Failed to save settings:\n{e}")
            except Exception:
                pass

    def _revert_winch_tab_settings(self):
        try:
            cfg = self._load_saved_config_dict()
            self.winch_type = cfg.get("winch_type", getattr(self, "winch_type", "HV P2P W1P"))
            self.winch_host = cfg.get("winch_host", getattr(self, "winch_host", ""))
            self.reverse_motor = bool(cfg.get("reverse_motor", getattr(self, "reverse_motor", False)))
            try:
                self.winch_units_per_m = float(cfg.get("winch_units_per_m", getattr(self, "winch_units_per_m", 21220.7)))
                if self.winch_units_per_m < 1.0:
                    self.winch_units_per_m = 1.0
            except Exception:
                pass
            if hasattr(self, "_tab_winch_type"):
                self._tab_winch_type.set(getattr(self, "winch_type", "HV P2P W1P"))
            self._tab_winch_ip.set(getattr(self, "winch_host", ""))
            self._tab_winch_dir.set("Inverted" if getattr(self, "reverse_motor", False) else "Normal")
            if hasattr(self, "_tab_winch_units_var"):
                self._tab_winch_units_user_editing = False
                self._tab_winch_units_var.set(f"{getattr(self, 'winch_units_per_m', 21220.7):0.1f}")
            try:
                self.arduino_client.reconfigure(self.winch_host, self.winch_port)
            except Exception:
                pass
        except Exception:
            pass


    def _rename_drive_mode(self, idx: int):
        try:
            current = self.drive_modes[idx].get("name", f"Mode {idx+1}")
        except Exception:
            current = f"Mode {idx+1}"
        new_name = simpledialog.askstring("Drive Mode Name", f"Enter name for Drive Mode {idx+1}:", initialvalue=current)
        if not new_name:
            return
        try:
            self.drive_modes[idx]["name"] = new_name.strip()
            self._sync_drive_mode_legacy_name_keys()
            if hasattr(self, "drive_mode_name_vars"):
                self.drive_mode_name_vars[idx].set(self.drive_modes[idx]["name"])
            try:
                self._refresh_setup_action_buttons()
            except Exception:
                pass
            self._save_config()
        except Exception:
            pass


    def _build_drive_limits_tab(self, tab):
        # tab is a tk.Frame created by the tabs notebook
        tab.configure(bg="#111111")
        # v26.06.26.25: Setup tab now uses a consistent three-column content grid:
        # Setup / Mode A / Mode B on the top row, then Controller / CTRL-TS Aux /
        # Controller Calibration below.  The Actions card remains fixed at right.
        for _c in range(3):
            tab.columnconfigure(_c, weight=1, uniform="setup_content_cols")
        tab.columnconfigure(3, weight=0, minsize=TAB_ACTIONS_COL_W)
        tab.rowconfigure(0, weight=0, minsize=82)
        tab.rowconfigure(1, weight=0, minsize=164)

        label_font = ("Segoe UI", 9)

        # ----------------------------
        # Drive Settings state
        # ----------------------------
        if not hasattr(self, "accel_type"):
            self.accel_type = "Dynamic"
        self._drive_accel_type = tk.StringVar(value=self._display_accel_type())
        self._drive_batt_mode = tk.StringVar(value="ON" if getattr(self, "battery_change_mode", False) else "OFF")

        # ----------------------------
        # Drive Modes
        # ----------------------------
        if not getattr(self, "drive_modes", None) or len(self.drive_modes) < 2:
            self.drive_modes = [
                {"name": "Mode A", "max_speed_mps": 20.0, "max_goto_speed_mps": 1.0, "goto_speed_unit": "m/s", "max_accel_mps2": 2.0, "max_decel_mps2": 2.0, "max_crossover_mps2": 4.0, "max_stop_decel_mps2": 4.0},
                {"name": "Mode B", "max_speed_mps": 20.0, "max_goto_speed_mps": 1.0, "goto_speed_unit": "m/s", "max_accel_mps2": 2.0, "max_decel_mps2": 2.0, "max_crossover_mps2": 4.0, "max_stop_decel_mps2": 4.0},
            ]
        if len(self.drive_modes) >= 2:
            # v26.08.17.01: keep the locked UI defaults Mode 1 / Mode 2.
            # Preserve any operator-renamed custom names from config.
            if not str(self.drive_modes[0].get("name", "")).strip():
                self.drive_modes[0]["name"] = "Mode 1"
            if not str(self.drive_modes[1].get("name", "")).strip():
                self.drive_modes[1]["name"] = "Mode 2"
            self._sync_drive_mode_legacy_name_keys()
        if not hasattr(self, "active_drive_mode"):
            self.active_drive_mode = 0

        self.drive_mode_sel = tk.IntVar(value=int(getattr(self, "active_drive_mode", 0)))
        self.drive_mode_name_vars = [
            tk.StringVar(value=str(self.drive_modes[0].get("name", "Mode A"))),
            tk.StringVar(value=str(self.drive_modes[1].get("name", "Mode B"))),
        ]

        self._mode_vars = []
        for i in range(2):
            m = self.drive_modes[i]
            _speed_unit = str(m.get('speed_unit', 'm/s')) if str(m.get('speed_unit', 'm/s')) in ('m/s', 'km/h') else 'm/s'
            _mps = float(m.get('max_speed_mps', 20.0))
            self._mode_vars.append({
                "speed": tk.StringVar(value=f"{(_mps * 3.6 if _speed_unit == 'km/h' else _mps):.2f}"),
                "speed_unit": tk.StringVar(value=_speed_unit),
                "_speed_unit_last": _speed_unit,
                "goto_speed": tk.StringVar(value=f"{(float(m.get('max_goto_speed_mps', min(_mps, 1.0))) * 3.6 if str(m.get('goto_speed_unit', _speed_unit)) == 'km/h' else float(m.get('max_goto_speed_mps', min(_mps, 1.0)))):.2f}"),
                "goto_speed_unit": tk.StringVar(value=(str(m.get('goto_speed_unit', _speed_unit)) if str(m.get('goto_speed_unit', _speed_unit)) in ('m/s', 'km/h') else 'm/s')),
                "_goto_speed_unit_last": (str(m.get('goto_speed_unit', _speed_unit)) if str(m.get('goto_speed_unit', _speed_unit)) in ('m/s', 'km/h') else 'm/s'),
                "accel": tk.StringVar(value=f"{float(m.get('max_accel_mps2', 2.0)):.2f}"),
                "decel": tk.StringVar(value=f"{float(m.get('max_decel_mps2', 2.0)):.2f}"),
                "crossover": tk.StringVar(value=f"{float(m.get('max_crossover_mps2', 4.0)):.2f}"),
                "stop_decel": tk.StringVar(value=f"{float(m.get('max_stop_decel_mps2', m.get('max_decel_mps2', 2.0))):.2f}"),
            })

        def _active_mode_idx() -> int:
            try:
                idx = int(getattr(self, "active_drive_mode", 0))
            except Exception:
                idx = 0
            return 0 if idx not in (0, 1) else idx

        def apply_runtime_from_mode(idx: int, save_config: bool = True):
            try:
                idx = 0 if idx not in (0, 1) else idx
                self.active_drive_mode = idx
                self.drive_mode_sel.set(idx)
                m2 = self.drive_modes[idx]
                self.max_speed_mps = float(m2.get("max_speed_mps", getattr(self, "max_speed_mps", 20.0)))
                self.goto_speed_mps = float(m2.get("max_goto_speed_mps", min(getattr(self, "max_speed_mps", 20.0), 1.0)))
                self.max_accel_mps2 = float(m2.get("max_accel_mps2", getattr(self, "max_accel_mps2", 2.0)))
                self.max_decel_mps2 = float(m2.get("max_decel_mps2", getattr(self, "max_decel_mps2", 2.0)))
                self.max_crossover_mps2 = float(m2.get("max_crossover_mps2", getattr(self, "max_crossover_mps2", 4.0)))
                self.max_stop_decel_mps2 = float(m2.get("max_stop_decel_mps2", m2.get("max_decel_mps2", getattr(self, "max_stop_decel_mps2", getattr(self, "max_decel_mps2", 2.0)))))
                if save_config:
                    self._save_config()
                    self._set_status(f"{self.drive_mode_name_vars[idx].get()}: active")
            except Exception:
                pass

        def save_drive_settings_only():
            self.battery_change_mode = (self._drive_batt_mode.get() == "ON")
            self.accel_type = self._normalise_accel_type(self._drive_accel_type.get())

        def revert_drive_settings_only(cfg: dict | None = None):
            cfg = cfg if isinstance(cfg, dict) else self._load_saved_config_dict()
            self.accel_type = self._normalise_accel_type(cfg.get("accel_type", getattr(self, "accel_type", "Dynamic")))
            self.battery_change_mode = bool(cfg.get("battery_change_mode", getattr(self, "battery_change_mode", False)))
            if hasattr(self, '_drive_accel_type'):
                self._drive_accel_type.set(self._display_accel_type())
            if hasattr(self, '_drive_batt_mode'):
                self._drive_batt_mode.set("ON" if getattr(self, "battery_change_mode", False) else "OFF")

        def save_mode_only(idx: int):
            idx = 0 if idx not in (0, 1) else idx
            v = self._mode_vars[idx]
            speed_val = float(v["speed"].get())
            if v.get("speed_unit") and v["speed_unit"].get() == "km/h":
                speed_val = speed_val / 3.6
            goto_speed_val = float(v["goto_speed"].get())
            if v.get("goto_speed_unit") and v["goto_speed_unit"].get() == "km/h":
                goto_speed_val = goto_speed_val / 3.6
            self.drive_modes[idx]["name"] = self.drive_mode_name_vars[idx].get().strip() or ("Mode A" if idx == 0 else "Mode B")
            self._sync_drive_mode_legacy_name_keys()
            self.drive_modes[idx]["speed_unit"] = v["speed_unit"].get() if v.get("speed_unit") and v["speed_unit"].get() in ("m/s", "km/h") else "m/s"
            self.drive_modes[idx]["goto_speed_unit"] = v["goto_speed_unit"].get() if v.get("goto_speed_unit") and v["goto_speed_unit"].get() in ("m/s", "km/h") else self.drive_modes[idx]["speed_unit"]
            v["_speed_unit_last"] = self.drive_modes[idx]["speed_unit"]
            v["_goto_speed_unit_last"] = self.drive_modes[idx]["goto_speed_unit"]
            self.drive_modes[idx]["max_speed_mps"] = max(0.1, float(speed_val))
            self.drive_modes[idx]["max_goto_speed_mps"] = min(max(0.02, float(goto_speed_val)), self.drive_modes[idx]["max_speed_mps"])
            self.drive_modes[idx]["max_accel_mps2"] = max(0.1, float(v["accel"].get()))
            self.drive_modes[idx]["max_decel_mps2"] = max(0.1, float(v["decel"].get()))
            self.drive_modes[idx]["max_crossover_mps2"] = max(0.1, float(v["crossover"].get()))
            self.drive_modes[idx]["max_stop_decel_mps2"] = max(0.1, float(v["stop_decel"].get()))
            if _active_mode_idx() == idx:
                apply_runtime_from_mode(idx, save_config=False)

        def revert_mode_only(idx: int, cfg: dict | None = None):
            idx = 0 if idx not in (0, 1) else idx
            cfg = cfg if isinstance(cfg, dict) else self._load_saved_config_dict()
            dm = cfg.get("drive_modes") if isinstance(cfg, dict) else None
            if isinstance(dm, list) and len(dm) >= 2 and isinstance(dm[idx], dict):
                m2 = dm[idx]
            else:
                m2 = self.drive_modes[idx]
            default_name = "Mode A" if idx == 0 else "Mode B"
            self.drive_modes[idx]["name"] = str(m2.get("name", default_name))
            if self.drive_modes[idx]["name"] in ("", f"Mode {idx+1}"):
                self.drive_modes[idx]["name"] = default_name
            self.drive_modes[idx]["speed_unit"] = (str(m2.get("speed_unit", self.drive_modes[idx].get("speed_unit", "m/s"))) if str(m2.get("speed_unit", self.drive_modes[idx].get("speed_unit", "m/s"))) in ("m/s", "km/h") else "m/s")
            self.drive_modes[idx]["max_speed_mps"] = float(m2.get("max_speed_mps", 20.0))
            self.drive_modes[idx]["max_goto_speed_mps"] = float(m2.get("max_goto_speed_mps", min(self.drive_modes[idx].get("max_speed_mps", 20.0), 1.0)))
            self.drive_modes[idx]["goto_speed_unit"] = (str(m2.get("goto_speed_unit", self.drive_modes[idx].get("speed_unit", "m/s"))) if str(m2.get("goto_speed_unit", self.drive_modes[idx].get("speed_unit", "m/s"))) in ("m/s", "km/h") else "m/s")
            self.drive_modes[idx]["max_accel_mps2"] = float(m2.get("max_accel_mps2", 2.0))
            self.drive_modes[idx]["max_decel_mps2"] = float(m2.get("max_decel_mps2", 2.0))
            self.drive_modes[idx]["max_crossover_mps2"] = float(m2.get("max_crossover_mps2", 4.0))
            self.drive_modes[idx]["max_stop_decel_mps2"] = float(m2.get("max_stop_decel_mps2", m2.get("max_decel_mps2", 2.0)))
            self.drive_mode_name_vars[idx].set(self.drive_modes[idx]["name"])
            v2 = self._mode_vars[idx]
            if v2.get("speed_unit"):
                v2["speed_unit"].set(self.drive_modes[idx].get("speed_unit", "m/s"))
                v2["_speed_unit_last"] = v2["speed_unit"].get()
            mps_val = float(self.drive_modes[idx].get("max_speed_mps", 20.0))
            if v2.get("speed_unit") and v2["speed_unit"].get() == "km/h":
                v2["speed"].set(f"{mps_val * 3.6:.2f}")
            else:
                v2["speed"].set(f"{mps_val:.2f}")
            if v2.get("goto_speed_unit"):
                v2["goto_speed_unit"].set(self.drive_modes[idx].get("goto_speed_unit", self.drive_modes[idx].get("speed_unit", "m/s")))
            goto_mps_val = float(self.drive_modes[idx].get("max_goto_speed_mps", min(mps_val, 1.0)))
            if v2.get("goto_speed_unit") and v2["goto_speed_unit"].get() == "km/h":
                v2["goto_speed"].set(f"{goto_mps_val * 3.6:.2f}")
            else:
                v2["goto_speed"].set(f"{goto_mps_val:.2f}")
            v2["accel"].set(f"{float(self.drive_modes[idx].get('max_accel_mps2', 2.0)):.2f}")
            v2["decel"].set(f"{float(self.drive_modes[idx].get('max_decel_mps2', 2.0)):.2f}")
            v2["crossover"].set(f"{float(self.drive_modes[idx].get('max_crossover_mps2', 4.0)):.2f}")
            v2["stop_decel"].set(f"{float(self.drive_modes[idx].get('max_stop_decel_mps2', self.drive_modes[idx].get('max_decel_mps2', 2.0))):.2f}")

        def _drive_tab_apply():
            ok = True
            try:
                # v12: start the apply grace before any config/IP/profile writes so
                # live status widgets do not flash Disconnected while values are saved.
                self._settings_apply_grace_until = time.time() + 1.5
                save_drive_settings_only()
                save_mode_only(0)
                save_mode_only(1)
                if hasattr(self, "_tab_joy_center_var"):
                    controller_state["joy_center"] = float(self._tab_joy_center_var.get())
                    controller_state["joy_min"] = float(self._tab_joy_min_var.get())
                    controller_state["joy_max"] = float(self._tab_joy_max_var.get())
                if hasattr(self, "_tab_ctrl_ip"):
                    self._save_controller_tab_settings()
                if hasattr(self, "_aux1_action"):
                    self._save_aux_assignments()
                if hasattr(self, "_tab_winch_type"):
                    self._save_winch_tab_settings()
                self._save_config()
                # Applying mode/settings can briefly pause status/display packets; keep
                # the safety banner green unless a real E-stop flag is reported.
                self._settings_apply_grace_until = time.time() + 1.5
                self._sync_motion_profile_to_winch(force=True)
                self._set_status("Setup settings saved")
            except Exception:
                ok = False
            try:
                if hasattr(self, "_drive_actions_status"):
                    self._drive_actions_status.set("Saved" if ok else "Save failed")
            except Exception:
                pass

        def _drive_tab_reset():
            ok = True
            try:
                if bool(getattr(self, "system_calibration_mode", False)) or bool(getattr(self, "winch_calibration_mode", False)):
                    self._cancel_active_calibration_restore_config()
                    if hasattr(self, "_drive_actions_status"):
                        self._drive_actions_status.set("Calibration cancelled")
                    return
                # v20: Reset on the Setup tab should recall editable settings only.
                # Do not reload calibration/not-calibrated state here, otherwise a
                # stale config can make the live calibrated/slip position go Un-Calibrated.
                cfg = self._load_saved_config_dict()
                was_not_calibrated = bool(getattr(self, "not_calibrated_mode", False))
                live_pos_before_reset = getattr(self.state, "pos_m", None)
                revert_drive_settings_only(cfg)
                revert_mode_only(0, cfg)
                revert_mode_only(1, cfg)
                if hasattr(self, "_tab_ctrl_ip"):
                    self._revert_controller_tab_settings()
                if hasattr(self, "_aux1_action"):
                    self._revert_aux_assignments()
                if hasattr(self, "_tab_winch_type"):
                    self._revert_winch_tab_settings()
                if hasattr(self, "_tab_joy_min_var"):
                    self._revert_joy_calibration()
                # Restore live calibration state/position after recalling settings.
                self.not_calibrated_mode = was_not_calibrated
                if live_pos_before_reset is not None:
                    try:
                        self.state.pos_m = float(live_pos_before_reset)
                    except Exception:
                        pass
                apply_runtime_from_mode(_active_mode_idx(), save_config=False)
                self._sync_limits_to_winch()
                self._set_status("Setup settings reverted")
            except Exception:
                ok = False
            try:
                if hasattr(self, "_drive_actions_status"):
                    self._drive_actions_status.set("Recalled" if ok else "Recall failed")
            except Exception:
                pass

        def build_setup_panel(col: int, padx_tuple):
            # v21: keep this card the same compact height as the Mode cards so the
            # Battery Change button sits at the bottom without a spare blank row.
            panel = tk.Frame(tab, bg="#1a1a1a", highlightbackground="#2a2f3a", highlightthickness=1, height=106)
            panel.grid(row=0, column=col, sticky="nsew", padx=padx_tuple, pady=TAB_CARD_PADY)
            panel.grid_propagate(False)
            panel.columnconfigure(0, weight=1)
            panel.rowconfigure(1, weight=1)
            tk.Label(panel, text="Setup", fg="#dddddd", bg="#1a1a1a", font=FONT_SMALL_BOLD).grid(
                row=0, column=0, sticky="w", padx=12, pady=(3, 0)
            )
            grid = tk.Frame(panel, bg="#1a1a1a")
            grid.grid(row=1, column=0, sticky="sew", padx=10, pady=(0, 4))
            for _c in range(2):
                grid.columnconfigure(_c, weight=1, uniform="setup_button_cols")
            for _r in range(3):
                grid.rowconfigure(_r, weight=0)
            # v21 requested order and compact spacing:
            # Top: Limit Calibration / Winch Calibration
            # Middle: Accel Mode / Drive Mode
            # Bottom: Battery Change (full width, at the bottom of the card)
            self.setup_action_names = ["Limit Calibration", "Winch Calibration", "Accel Mode", "Drive Mode", "Battery Change"]
            self.setup_action_button_vars = []
            self.setup_action_buttons = []
            self._setup_action_confirm_idx = None
            self._setup_action_confirm_until = 0.0
            self._setup_action_confirmed_idx = None
            self._setup_action_confirmed_until = 0.0
            self._setup_action_confirmed_text = ""
            for i, _name in enumerate(self.setup_action_names):
                var = tk.StringVar(value=_name)
                btn = ttk.Button(
                    grid,
                    textvariable=var,
                    command=lambda idx=i: self._on_setup_action_button(idx),
                    style="RunAux.TButton",
                )
                if _name == "Battery Change":
                    btn.grid(row=2, column=0, columnspan=2, sticky="ew", padx=0, pady=(0, 2))
                else:
                    btn.grid(row=i // 2, column=i % 2, sticky="ew", padx=(0 if i % 2 == 0 else 4, 4 if i % 2 == 0 else 0), pady=(0, 2))
                self.setup_action_button_vars.append(var)
                self.setup_action_buttons.append(btn)
            self._refresh_setup_action_buttons()

        def build_mode_panel(col: int, idx: int, padx_tuple):
            panel = tk.Frame(tab, bg="#1a1a1a", highlightbackground="#2a2f3a", highlightthickness=1, height=106)
            panel.grid(row=0, column=col, sticky="nsew", padx=padx_tuple, pady=TAB_CARD_PADY)
            panel.grid_propagate(False)
            panel.columnconfigure(0, weight=0)
            panel.columnconfigure(1, weight=1, minsize=145)
            panel.columnconfigure(2, weight=0)
            panel.columnconfigure(3, weight=1, minsize=145)

            hdr = tk.Frame(panel, bg="#1a1a1a")
            hdr.grid(row=0, column=0, columnspan=4, sticky="ew", padx=12, pady=(6, 4))
            hdr.columnconfigure(1, weight=1)

            rb = ttk.Radiobutton(hdr, variable=self.drive_mode_sel, value=idx, command=lambda i=idx: apply_runtime_from_mode(i))
            rb.grid(row=0, column=0, sticky="w", padx=(0, 6))

            name_lbl = tk.Label(
                hdr, textvariable=self.drive_mode_name_vars[idx],
                fg="#dddddd", bg="#1a1a1a", font=FONT_SMALL_BOLD, cursor="hand2"
            )
            name_lbl.grid(row=0, column=1, sticky="w")
            name_lbl.bind("<Button-1>", lambda e, i=idx: self._rename_drive_mode(i))

            v = self._mode_vars[idx]

            tk.Label(panel, text="Max Speed:", fg="#dddddd", bg="#1a1a1a", font=label_font).grid(
                row=1, column=0, sticky="e", padx=(12, 6), pady=TAB_ROW_PADY
            )
            speed_holder = tk.Frame(panel, bg="#1a1a1a")
            speed_holder.grid(row=1, column=1, sticky="ew", padx=(4, 6), pady=TAB_ROW_PADY)
            speed_holder.columnconfigure(1, weight=0, minsize=56)
            se = ttk.Entry(speed_holder, textvariable=v["speed"], width=7)
            se.grid(row=0, column=0, sticky="w")
            unit = ttk.Combobox(speed_holder, textvariable=v["speed_unit"], values=["m/s", "km/h"], width=5, state="readonly")
            unit.grid(row=0, column=1, sticky="w", padx=(4, 0))
            se.bind("<Return>", lambda _e: _drive_tab_apply())

            def _unit_changed(_evt=None):
                new_unit = v["speed_unit"].get()
                old_unit = str(v.get("_speed_unit_last", new_unit))
                if new_unit == old_unit:
                    return
                try:
                    raw = float(v["speed"].get())
                except Exception:
                    v["_speed_unit_last"] = new_unit
                    return
                if old_unit == "m/s" and new_unit == "km/h":
                    raw *= 3.6
                elif old_unit == "km/h" and new_unit == "m/s":
                    raw /= 3.6
                v["speed"].set(f"{raw:.2f}")
                v["_speed_unit_last"] = new_unit
            unit.bind("<<ComboboxSelected>>", _unit_changed)

            tk.Label(panel, text="Goto Speed:", fg="#dddddd", bg="#1a1a1a", font=label_font).grid(
                row=1, column=2, sticky="e", padx=(12, 6), pady=TAB_ROW_PADY
            )
            goto_holder = tk.Frame(panel, bg="#1a1a1a")
            goto_holder.grid(row=1, column=3, sticky="ew", padx=(4, 6), pady=TAB_ROW_PADY)
            goto_holder.columnconfigure(1, weight=0, minsize=56)
            e_goto = ttk.Entry(goto_holder, textvariable=v["goto_speed"], width=7)
            e_goto.grid(row=0, column=0, sticky="w")
            goto_unit = ttk.Combobox(goto_holder, textvariable=v["goto_speed_unit"], values=["m/s", "km/h"], width=5, state="readonly")
            goto_unit.grid(row=0, column=1, sticky="w", padx=(4, 0))
            e_goto.bind("<Return>", lambda _e: _drive_tab_apply())

            def _goto_unit_changed(_evt=None):
                new_unit = v["goto_speed_unit"].get()
                old_unit = str(v.get("_goto_speed_unit_last", new_unit))
                if new_unit == old_unit:
                    return
                try:
                    raw = float(v["goto_speed"].get())
                except Exception:
                    v["_goto_speed_unit_last"] = new_unit
                    return
                if old_unit == "m/s" and new_unit == "km/h":
                    raw *= 3.6
                elif old_unit == "km/h" and new_unit == "m/s":
                    raw /= 3.6
                v["goto_speed"].set(f"{raw:.2f}")
                v["_goto_speed_unit_last"] = new_unit
            goto_unit.bind("<<ComboboxSelected>>", _goto_unit_changed)

            tk.Label(panel, text="Max Accel:", fg="#dddddd", bg="#1a1a1a", font=label_font).grid(
                row=2, column=0, sticky="e", padx=(12, 6), pady=TAB_ROW_PADY
            )
            accel_holder = tk.Frame(panel, bg="#1a1a1a")
            accel_holder.grid(row=2, column=1, sticky="w", padx=(6, 12), pady=TAB_ROW_PADY)
            e_acc = ttk.Entry(accel_holder, textvariable=v["accel"], width=7)
            e_acc.grid(row=0, column=0, sticky="w")
            tk.Label(accel_holder, text="m/s²", fg="#dddddd", bg="#1a1a1a", font=label_font).grid(row=0, column=1, sticky="w", padx=(5, 0))
            e_acc.bind("<Return>", lambda _e: _drive_tab_apply())

            tk.Label(panel, text="Max De-Accel:", fg="#dddddd", bg="#1a1a1a", font=label_font).grid(
                row=2, column=2, sticky="e", padx=(12, 6), pady=TAB_ROW_PADY
            )
            decel_holder = tk.Frame(panel, bg="#1a1a1a")
            decel_holder.grid(row=2, column=3, sticky="w", padx=(6, 12), pady=TAB_ROW_PADY)
            e_dec = ttk.Entry(decel_holder, textvariable=v["decel"], width=7)
            e_dec.grid(row=0, column=0, sticky="w")
            tk.Label(decel_holder, text="m/s²", fg="#dddddd", bg="#1a1a1a", font=label_font).grid(row=0, column=1, sticky="w", padx=(5, 0))
            e_dec.bind("<Return>", lambda _e: _drive_tab_apply())

            tk.Label(panel, text="Max Cross-Over:", fg="#dddddd", bg="#1a1a1a", font=label_font).grid(
                row=3, column=0, sticky="e", padx=(12, 6), pady=TAB_ROW_PADY
            )
            cross_holder = tk.Frame(panel, bg="#1a1a1a")
            cross_holder.grid(row=3, column=1, sticky="w", padx=(6, 12), pady=TAB_ROW_PADY)
            e_cross = ttk.Entry(cross_holder, textvariable=v["crossover"], width=7)
            e_cross.grid(row=0, column=0, sticky="w")
            tk.Label(cross_holder, text="m/s²", fg="#dddddd", bg="#1a1a1a", font=label_font).grid(row=0, column=1, sticky="w", padx=(5, 0))
            e_cross.bind("<Return>", lambda _e: _drive_tab_apply())

            tk.Label(panel, text="Stop De-Accel:", fg="#dddddd", bg="#1a1a1a", font=label_font).grid(
                row=3, column=2, sticky="e", padx=(12, 6), pady=TAB_ROW_PADY
            )
            stop_holder = tk.Frame(panel, bg="#1a1a1a")
            stop_holder.grid(row=3, column=3, sticky="w", padx=(6, 12), pady=TAB_ROW_PADY)
            e_stop_dec = ttk.Entry(stop_holder, textvariable=v["stop_decel"], width=7)
            e_stop_dec.grid(row=0, column=0, sticky="w")
            tk.Label(stop_holder, text="m/s²", fg="#dddddd", bg="#1a1a1a", font=label_font).grid(row=0, column=1, sticky="w", padx=(5, 0))
            e_stop_dec.bind("<Return>", lambda _e: _drive_tab_apply())

        build_setup_panel(0, (8, 4))
        build_mode_panel(1, 0, (4, 4))
        build_mode_panel(2, 1, (4, 8))

        act_card = tk.Frame(tab, bg="#1a1a1a", width=TAB_ACTIONS_W, height=TAB_ACTIONS_H, highlightbackground="#2a2f3a", highlightthickness=1)
        act_card.grid(row=0, column=3, rowspan=2, sticky="nw", padx=(4, 8), pady=TAB_CARD_PADY)
        act_card.grid_propagate(False)
        act_card.columnconfigure(0, weight=1)

        tk.Label(act_card, text="Actions", fg="#dddddd", bg="#1a1a1a", font=FONT_SMALL_BOLD).grid(
            row=0, column=0, sticky="w", padx=12, pady=TAB_HEADING_PADY
        )
        ttk.Button(act_card, text="Apply", command=_drive_tab_apply).grid(row=1, column=0, sticky="ew", padx=10, pady=TAB_ACTION_BUTTON_PADY)
        ttk.Button(act_card, text="Reset", command=_drive_tab_reset).grid(row=2, column=0, sticky="ew", padx=10, pady=TAB_ACTION_BUTTON_PADY)
        self._drive_actions_status = tk.StringVar(value="")
        tk.Label(act_card, textvariable=self._drive_actions_status, fg="#dddddd", bg="#1a1a1a", font=label_font, anchor="w", justify="left").grid(
            row=3, column=0, sticky="w", padx=10, pady=TAB_ACTION_STATUS_PADY
        )

        apply_runtime_from_mode(_active_mode_idx(), save_config=False)

        ctrl_setup_wrap = tk.Frame(tab, bg="#111111")
        ctrl_setup_wrap.grid(row=1, column=0, columnspan=3, sticky="new", padx=0, pady=(0, 0))
        self._build_controller_settings_tab(ctrl_setup_wrap)


    def _set_calibration_card_selected(self, frame):
        try:
            current = getattr(self, "_calibration_selected_card", None)
            if current is not None and current != frame:
                current.configure(highlightbackground="#2a2f3a", highlightcolor="#2a2f3a")
        except Exception:
            pass
        try:
            frame.configure(highlightbackground="white", highlightcolor="white")
            self._calibration_selected_card = frame
        except Exception:
            pass

    def _bind_calibration_card_selection(self, frame, widget=None):
        if widget is None:
            widget = frame
        try:
            widget.bind("<Button-1>", lambda _e, f=frame: self._set_calibration_card_selected(f), add="+")
            widget.bind("<FocusIn>", lambda _e, f=frame: self._set_calibration_card_selected(f), add="+")
        except Exception:
            pass
        for child in widget.winfo_children():
            self._bind_calibration_card_selection(frame, child)

    def _build_system_calibration_column(self, parent, col: int):
        frame = tk.Frame(parent, bg="#1a1a1a", highlightbackground="#2a2f3a", highlightcolor="#2a2f3a", highlightthickness=1, bd=0)
        frame.grid(row=0, column=col, sticky="new", padx=6, pady=1)
        frame.columnconfigure(0, weight=1)

        header = tk.Frame(frame, bg="#1a1a1a")
        header.grid(row=0, column=0, sticky="ew", padx=8, pady=(4, 1))
        header.columnconfigure(0, weight=1)

        tk.Label(
            header,
            text="Limit Calibration",
            fg="white",
            bg="#1a1a1a",
            font=FONT_SMALL_BOLD,
            anchor="w",
            justify="left",
        ).grid(row=0, column=0, sticky="w")

        body = tk.Frame(frame, bg="#1a1a1a")
        body.grid(row=1, column=0, padx=8, pady=(0, 2), sticky="nsew")
        body.columnconfigure(0, weight=1)

        ttk.Button(body, text="Limit Calibration", command=self.on_start_limit_calibration).grid(
            row=0, column=0, sticky="ew", pady=(0, 1)
        )
        ttk.Button(body, text="Winch Calibration", command=lambda: self._execute_setup_direct_action("Winch Calibration")).grid(
            row=1, column=0, sticky="ew", pady=(1, 0)
        )

        self.system_cal_frame = frame
        self._bind_calibration_card_selection(frame)

    def _service_auto_cancel_battery_change_if_returned_inside(self):
        """Cancel Battery Change after it has gone outside an end limit and returned inside.

        Battery Change deliberately bypasses Near/Far soft limits for tower access.
        Once the carriage has travelled beyond either calibrated end and then
        returns back inside the normal calibrated range, automatically restore
        the previous Mode A/Mode B operation and re-enable normal end-limit guards.
        """
        try:
            if not bool(getattr(self, "battery_change_mode", False)):
                return
            if bool(getattr(self, "system_calibration_mode", False)) or bool(getattr(self, "not_calibrated_mode", False)):
                return
            pos = getattr(self.state, "pos_m", None)
            nl = getattr(self.state.near_limit, "position_m", None)
            fl = getattr(self.state.far_limit, "position_m", None)
            if pos is None or nl is None or fl is None:
                return
            pos = float(pos); nl = float(nl); fl = float(fl)
            lo, hi = (nl, fl) if nl <= fl else (fl, nl)
            outside_margin = 0.05
            inside_margin = 0.02
            if pos < (lo - outside_margin) or pos > (hi + outside_margin):
                self._battery_change_went_outside_limits = True
                return
            if bool(getattr(self, "_battery_change_went_outside_limits", False)) and (lo + inside_margin) <= pos <= (hi - inside_margin):
                self._set_battery_change_mode(False, save_config=True)
                self._set_status("Battery Change auto-cancelled: back inside end limits")
        except Exception:
            pass

    def _service_override_active(self) -> bool:
        return bool(
            getattr(self, "not_calibrated_mode", False)
            or getattr(self, "battery_change_mode", False)
            or getattr(self, "system_calibration_mode", False)
            or getattr(self, "winch_calibration_mode", False)
        )

    def _service_speed_limit_mps(self) -> float:
        return 5.0 / 3.6

    def _current_position_relative_m(self) -> float:
        pos = getattr(self.state, 'pos_m', None)
        if pos is None:
            pos = 0.0
        nl = getattr(self.state.near_limit, 'position_m', None)
        if nl is None:
            nl = 0.0
        try:
            rel = float(pos) - float(nl)
            # During the calibration wizard, the operator is measuring distance
            # away from Near. Far and Reference must therefore remain positive
            # even if the winch/drive raw position counts in the opposite direction.
            if bool(getattr(self, "system_calibration_mode", False)) and int(getattr(self, "_system_calibration_step", 0) or 0) > 0:
                return abs(rel)
            return rel
        except Exception:
            return 0.0

    def _display_abs_position_m(self) -> float | None:
        """Return the latest verified W1P/Leadshine position for SRVR graphics.

        v13 removes SRVR-side dead-reckoning because it made the Top/Side views,
        speed readout and CTRL-TS progress appear to keep moving after the motor
        had physically stopped.  The touchscreen may animate between received
        verified positions, but SRVR no longer predicts beyond the latest drive
        feedback sample.
        """
        try:
            return getattr(self.state, "pos_m", None)
        except Exception:
            return None

    def _display_position_relative_m(self) -> float:
        pos = self._display_abs_position_m()
        if pos is None:
            pos = getattr(self.state, "pos_m", None)
        return self._position_relative_to_near_m(pos)

    def _position_relative_to_near_m(self, pos_m) -> float:
        nl = getattr(self.state.near_limit, 'position_m', None)
        if nl is None:
            nl = 0.0
        if pos_m is None:
            pos_m = 0.0
        try:
            return float(pos_m) - float(nl)
        except Exception:
            return 0.0

    def _limit_display_position_m(self, lp: LimitPoint) -> float:
        if getattr(lp, 'name', '') == 'Near Limit':
            return 0.0
        val = self._position_relative_to_near_m(getattr(lp, 'position_m', None))
        # Far is always a positive distance away from Near on the operator UI.
        # Negative values are reserved for the current skate position when it is
        # manually/battery-change flown outside the programmed limit zone.
        if getattr(lp, 'name', '') == 'Far Limit' and val < 0:
            return abs(val)
        if bool(getattr(self, "system_calibration_mode", False)) and val < 0:
            return abs(val)
        return val

    def _force_hmi_display_update(self):
        try:
            self._send_controller_display_packet(force=True)
        except Exception:
            pass

    def _sync_winch_position(self, pos_m: float):
        try:
            # After a Slip/Sync command the next W1P STATUS may legitimately jump
            # to the newly referenced position. Accept that jump, then return to
            # normal plausibility filtering so bad feedback cannot make the SRVR
            # and CTRL-TS skate marker wander randomly for hours.
            self._winch_position_accept_jump_until = time.time() + WINCH_POS_JUMP_GRACE_S
            self._winch_last_pos_accept_t = 0.0
            self.arduino_client.send(f"SYNC_POS {float(pos_m):.3f}")
        except Exception:
            pass

    def _sanity_accept_winch_position(self, new_pos_m: float, fields: dict) -> bool:
        try:
            new_pos = float(new_pos_m)
            if not math.isfinite(new_pos):
                return False
            old_pos = getattr(self.state, "pos_m", None)
            now = time.time()
            if old_pos is None:
                self._winch_last_pos_accept_t = now
                return True
            if now <= float(getattr(self, "_winch_position_accept_jump_until", 0.0) or 0.0):
                self._winch_last_pos_accept_t = now
                return True
            old_pos = float(old_pos)
            dt = now - float(getattr(self, "_winch_last_pos_accept_t", 0.0) or now)
            if dt <= 0.0 or dt > 1.0:
                dt = WINCH_RECV_TIMEOUT_S if WINCH_RECV_TIMEOUT_S > 0 else 0.075
            jump = abs(new_pos - old_pos)
            try:
                commanded = abs(float(getattr(self, "last_winch_output", 0.0) or 0.0))
            except Exception:
                commanded = 0.0
            try:
                max_speed = abs(float(getattr(self, "max_speed_mps", 20.0) or 20.0))
            except Exception:
                max_speed = 20.0
            # If the system is not commanding movement, be much stricter.
            if commanded < 0.05 and getattr(self, "goto_target_m", None) is None:
                allowed_jump = 0.35
            else:
                allowed_jump = max(0.35, (max_speed + 2.0) * max(dt, 0.05) * 2.5)
            # In active mode, reject values well outside the programmed span.
            if not self._service_override_active():
                nl = float(getattr(self.state.near_limit, "position_m", 0.0) or 0.0)
                fl = float(getattr(self.state.far_limit, "position_m", nl + getattr(self.state, "total_length_m", 100.0)) or (nl + getattr(self.state, "total_length_m", 100.0)))
                lo, hi = (nl, fl) if nl <= fl else (fl, nl)
                if new_pos < (lo - 0.5) or new_pos > (hi + 0.5):
                    jump = max(jump, allowed_jump + 1.0)
            if jump <= allowed_jump:
                self._winch_last_pos_accept_t = now
                return True
            last_log = float(getattr(self, "_winch_last_pos_reject_log_t", 0.0) or 0.0)
            if (now - last_log) >= WINCH_POS_REJECT_LOG_S:
                self._winch_last_pos_reject_log_t = now
                src = str(fields.get("POS_SRC", "?")).strip()
                rs = str(fields.get("RS_STAT", fields.get("MODBUS", "?"))).strip()
                _app_log(f"[W1P-POS] Rejected implausible {src} position jump {old_pos:0.3f} -> {new_pos:0.3f} m (RS={rs})")
            return False
        except Exception as exc:
            _app_log(f"[W1P-POS] Position validation failed closed: {exc}")
            return False

    @staticmethod
    def _quantize_display_value(value: float, quantum: float) -> float:
        try:
            q = max(1e-9, float(quantum))
            return round(float(value) / q) * q
        except Exception:
            return 0.0

    def _set_system_calibration_point(self, lp: LimitPoint, step_idx: int, raw_pos) -> None:
        """Set calibration points in operator coordinates: Near=0, Far positive."""
        try:
            pos = float(raw_pos if raw_pos is not None else 0.0)
        except Exception:
            pos = 0.0
        if step_idx == 0 or getattr(lp, 'name', '') == 'Near Limit':
            self.state.near_limit.position_m = 0.0
            self.state.pos_m = 0.0
            self._sync_winch_position(0.0)
            return
        near = float(getattr(self.state.near_limit, 'position_m', 0.0) or 0.0)
        rel = abs(pos - near)
        calibrated_pos = near + rel
        lp.position_m = float(calibrated_pos)
        self.state.pos_m = float(calibrated_pos)
        self._sync_winch_position(float(calibrated_pos))

    def _preset_absolute_position_m(self, idx: int) -> float | None:
        if not (0 <= idx < len(self.preset_positions)):
            return None
        rel = self.preset_positions[idx]
        if rel is None:
            return None
        nl = getattr(self.state.near_limit, 'position_m', None)
        if nl is None:
            nl = 0.0
        try:
            return float(nl) + float(rel)
        except Exception:
            return None

    def _enter_system_calibration_mode(self):
        self.system_calibration_mode = True
        self._system_calibration_aux_step = 0
        self.goto_target_m = None
        self.current_speed_mps = 0.0
        try:
            self._sync_limits_to_winch()
        except Exception:
            pass
        try:
            self._send_velocity_command(0.0, force=True)
        except Exception:
            pass
        self._set_status("Limit Calibration active.")

    def _exit_system_calibration_mode(self):
        self.system_calibration_mode = False
        try:
            self._sync_limits_to_winch()
        except Exception:
            pass
        try:
            self._send_velocity_command(0.0, force=True)
        except Exception:
            pass
        self._set_status("Limit Calibration finished.")

    def _enter_not_calibrated_mode(self):
        self.not_calibrated_mode = True
        self.goto_target_m = None
        self.current_speed_mps = 0.0
        try:
            self._sync_limits_to_winch()
        except Exception:
            pass
        try:
            self._send_velocity_command(0.0, force=True)
        except Exception:
            pass
        self._set_status("Not Calibrated: establish position with Limit Calibration or Slip.")

    def _exit_not_calibrated_mode(self):
        self.not_calibrated_mode = False
        try:
            self._sync_limits_to_winch()
        except Exception:
            pass
        try:
            self._send_velocity_command(0.0, force=True)
        except Exception:
            pass
        self._set_status("Calibration established. Normal limit operation restored.")

    def on_start_limit_calibration(self):
        if getattr(self, "_system_calibration_popup", None) is not None:
            try:
                self._system_calibration_popup.lift()
                self._system_calibration_popup.focus_force()
                return
            except Exception:
                self._system_calibration_popup = None

        self._enter_system_calibration_mode()

        popup = tk.Toplevel(self.root)
        popup.title("Limit Calibration Wizard")
        popup.transient(self.root)
        popup.grab_set()
        popup.configure(bg="#202020")
        popup.resizable(False, False)
        self._system_calibration_popup = popup
        self._system_calibration_step = 0
        self._system_calibration_aux_step = 0

        page_title = tk.StringVar(value="")
        page_desc = tk.StringVar(value="")
        step_var = tk.StringVar(value="")
        current_pos_var = tk.StringVar(value="")

        container = tk.Frame(popup, bg="#202020")
        container.grid(row=0, column=0, padx=14, pady=14, sticky="nsew")
        container.columnconfigure(0, weight=1)

        tk.Label(container, textvariable=step_var, fg="#8fb7ff", bg="#202020", font=FONT_SMALL_BOLD).grid(
            row=0, column=0, sticky="w", pady=(0, 6)
        )
        tk.Label(container, textvariable=page_title, fg="white", bg="#202020", font=FONT_SMALL_BOLD).grid(
            row=1, column=0, sticky="w", pady=(0, 6)
        )
        tk.Label(container, textvariable=page_desc, fg="#dddddd", bg="#202020", font=FONT_SMALL, justify="left", anchor="w", wraplength=420).grid(
            row=2, column=0, sticky="w", pady=(0, 8)
        )
        tk.Label(container, textvariable=current_pos_var, fg="#8fb7ff", bg="#202020", font=FONT_SMALL_BOLD, justify="left", anchor="w").grid(
            row=3, column=0, sticky="w", pady=(0, 8)
        )
        button_row = tk.Frame(container, bg="#202020")
        button_row.grid(row=4, column=0, sticky="ew")
        button_row.columnconfigure(0, weight=1)
        button_row.columnconfigure(1, weight=1)

        steps = [
            ("Near Limit Set", self.state.near_limit, "Drive to Desired Near Limit Position, then click Set Near Limit"),
            ("Far Limit Set", self.state.far_limit, "Drive to Desired Far Limit Position, then click Set Far Limit"),
            ("Reference Point Set", self.state.ref_point, "Drive to Desired Reference Point Position, then click Set Reference Point"),
        ]

        set_btn = ttk.Button(button_row, text="Set")
        cancel_btn = ttk.Button(button_row, text="Cancel")

        set_btn.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        cancel_btn.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        def close_wizard(status_msg: str | None = None):
            try:
                popup.grab_release()
            except Exception:
                pass
            try:
                popup.destroy()
            except Exception:
                pass
            self._system_calibration_popup = None
            self._exit_system_calibration_mode()
            if status_msg:
                self._set_status(status_msg)

        def _wizard_current_position_text() -> str:
            idx = int(self._system_calibration_step)
            if idx == 0:
                return "Current Position: 0.00 m"
            return f"Current Position: {self._current_position_relative_m():0.2f} m"

        def refresh_page():
            idx = int(self._system_calibration_step)
            title, lp, desc = steps[idx]
            step_var.set(f"Step {idx + 1} of {len(steps)}")
            page_title.set(title)
            page_desc.set(desc)
            current_pos_var.set(_wizard_current_position_text())
            set_btn.configure(text=f"Set {lp.name}")

        def refresh_live_position():
            try:
                if self._system_calibration_popup is popup and popup.winfo_exists():
                    current_pos_var.set(_wizard_current_position_text())
                    popup.after(150, refresh_live_position)
            except Exception:
                pass

        def do_set():
            _, lp, _ = steps[int(self._system_calibration_step)]
            pos = self.state.pos_m
            if pos is None:
                pos = (
                    (self.state.near_limit.position_m or 0.0)
                    + self.state.total_length_m / 2.0
                )
            self._set_system_calibration_point(lp, int(self._system_calibration_step), pos)
            self._update_limits_ui()
            self._redraw_progress()
            self._sync_limits_to_winch()
            if self._system_calibration_step >= len(steps) - 1:
                self._save_config()
            self._force_hmi_display_update()
            self._set_status(f"{lp.name} set to {lp.position_m:0.2f} m")
            if self._system_calibration_step >= len(steps) - 1:
                self._exit_not_calibrated_mode()
                close_wizard("Limits Calibrated")
                return
            self._system_calibration_step += 1
            refresh_page()

        def do_cancel():
            if self._confirm_action("Cancel Calibration", "Exit the system calibration wizard?"):
                close_wizard("Limit Calibration cancelled.")

        set_btn.configure(command=do_set)
        cancel_btn.configure(command=do_cancel)
        popup.protocol("WM_DELETE_WINDOW", do_cancel)
        refresh_page()
        refresh_live_position()


    def on_start_system_calibration(self):
        # Legacy callback/name retained for older menu/AUX assignments.
        return self.on_start_limit_calibration()


    def _build_presets_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=0)
        parent.rowconfigure(1, weight=0)

        self._build_run_live_status_section(parent)

        outer = tk.Frame(parent, bg="#111111")
        outer.grid(row=1, column=0, sticky="new")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=0)

        presets_grid = tk.Frame(outer, bg="#111111")
        presets_grid.grid(row=0, column=0, sticky="new", padx=8, pady=(0, 3))
        for c in range(6):
            presets_grid.columnconfigure(c, weight=1)

        self._build_preset_grid(presets_grid)
        self._refresh_preset_show_buttons()
        self._redraw_run_live_section()

    def _build_run_live_status_section(self, parent):
        panel = tk.Frame(parent, bg="#111111")
        panel.grid(row=0, column=0, sticky="ew", padx=8, pady=TAB_CARD_PADY)
        panel.columnconfigure(0, weight=1)
        panel.columnconfigure(1, weight=0)

        cards_panel = tk.Frame(panel, bg="#111111")
        cards_panel.grid(row=0, column=0, sticky="nsew")
        for c in range(4):
            cards_panel.columnconfigure(c, weight=1, uniform="run_live_cards")

        def make_card(col: int, title: str, width: int = 250, fill_width: bool = True):
            grid_parent = panel if col == 4 else cards_panel
            grid_col = 1 if col == 4 else col
            card = tk.Frame(grid_parent, bg="#1a1a1a", highlightbackground="#2a2f3a", highlightthickness=1, width=width, height=126)
            sticky = "nsew" if fill_width else "nw"
            left_pad = 4 if col > 0 else 0
            right_pad = 0 if col == 4 else 4
            card.grid(row=0, column=grid_col, sticky=sticky, padx=(left_pad, right_pad), pady=TAB_CARD_PADY)
            card.grid_propagate(False)
            card.columnconfigure(0, weight=1)
            tk.Label(card, text=title, fg="#dddddd", bg="#1a1a1a", font=FONT_SMALL_BOLD).grid(row=0, column=0, sticky="w", padx=12, pady=(3, 1))
            return card

        self.run_bar_canvases = {}
        self.run_attitude_canvases = {}

        xyz = make_card(0, "X (Tracking) / Y (Sag) / Z (Offset) Position")
        for r, name in enumerate(["X", "Y", "Z"], start=1):
            cv = tk.Canvas(xyz, width=220, height=20, bg="#101010", highlightthickness=0)
            cv.grid(row=r, column=0, sticky="ew", padx=12, pady=(0, 1))
            cv.bind("<Configure>", lambda _e: self._redraw_run_live_section())
            self.run_bar_canvases[name] = cv

        lens = make_card(1, "Zoom / Focus Position")
        for r, name in enumerate(["Zoom", "Focus"], start=1):
            cv = tk.Canvas(lens, width=220, height=20, bg="#101010", highlightthickness=0)
            cv.grid(row=r, column=0, sticky="ew", padx=12, pady=(0, 1))
            cv.bind("<Configure>", lambda _e: self._redraw_run_live_section())
            self.run_bar_canvases[name] = cv
        self.run_lens_scale_var = tk.StringVar(value="")
        tk.Label(lens, textvariable=self.run_lens_scale_var, fg="#aaaaaa", bg="#1a1a1a", font=("Segoe UI", 8), anchor="w").grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 1))

        att = make_card(2, "Pan / Tilt / Roll Position")
        att_grid = tk.Frame(att, bg="#1a1a1a")
        att_grid.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 1))
        for c in range(3):
            att_grid.columnconfigure(c, weight=1, uniform="attitude")
        for c, name in enumerate(["Pan", "Tilt", "Roll"]):
            cv = tk.Canvas(att_grid, width=86, height=92, bg="#101010", highlightthickness=1, highlightbackground="#303030")
            cv.grid(row=0, column=c, sticky="nsew", padx=3, pady=(1, 1))
            cv.bind("<Configure>", lambda _e: self._redraw_run_live_section())
            self.run_attitude_canvases[name] = cv

        speed = make_card(3, "Status", width=230)
        speed.columnconfigure(0, weight=0)
        speed.columnconfigure(1, weight=1)
        self.run_current_speed_var = tk.StringVar(value="0.00 m/s  |  0.00 km/h")
        self.run_max_speed_var = tk.StringVar(value="0.00 m/s  |  0.00 km/h")
        self.run_accel_mode_var = tk.StringVar(value=self._display_accel_type())
        self.run_drive_mode_var = tk.StringVar(value="Mode 1")
        self.run_speed_mode_var = self.run_drive_mode_var  # compatibility for older refresh helpers
        speed_rows = [
            ("Current Speed:", self.run_current_speed_var),
            ("Maximum Speed:", self.run_max_speed_var),
            ("Accel Mode:", self.run_accel_mode_var),
            ("Drive Mode:", self.run_drive_mode_var),
        ]
        for r, (lab, var) in enumerate(speed_rows, start=1):
            tk.Label(speed, text=lab, fg="#dddddd", bg="#1a1a1a", font=FONT_SMALL).grid(row=r, column=0, sticky="e", padx=(10, 5), pady=(1, 1))
            tk.Label(speed, textvariable=var, fg="#eeeeee", bg="#111111", font=("Segoe UI", 8, "bold"), anchor="w", bd=1, relief="solid").grid(row=r, column=1, sticky="ew", padx=(0, 10), pady=(1, 1))

        aux = make_card(4, "CTRL-TS Aux Assign", width=160, fill_width=False)
        aux_grid = tk.Frame(aux, bg="#1a1a1a")
        aux_grid.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 7))
        aux_grid.columnconfigure(0, weight=1)
        self.run_aux_button_vars = []
        self.run_aux_buttons = []
        self._run_aux_confirm_idx = None
        self._run_aux_confirm_until = 0.0
        self._run_aux_confirmed_idx = None
        self._run_aux_confirmed_until = 0.0
        for i in range(4):
            var = tk.StringVar(value=f"Aux {i+1}")
            btn = ttk.Button(
                aux_grid,
                textvariable=var,
                command=lambda idx=i: self._on_run_aux_button(idx),
                width=14,
                style="RunAux.TButton",
            )
            btn.grid(row=i, column=0, sticky="ew", padx=0, pady=(0, 2 if i == 3 else 0))
            self.run_aux_button_vars.append(var)
            self.run_aux_buttons.append(btn)
        self.run_aux_status_var = tk.StringVar(value="")
        # Status text is kept internal to avoid making this compact button column taller.
        self._refresh_run_aux_buttons()

    def _run_aux_action_name(self, idx: int) -> str:
        try:
            var = getattr(self, f"_aux{idx+1}_action", None)
            if var is not None:
                return str(var.get() or "None")
        except Exception:
            pass
        try:
            return str(getattr(self, f"aux{idx+1}_action", "None") or "None")
        except Exception:
            return "None"

    def _sync_run_aux_assignments_from_ui(self):
        try:
            for i in range(4):
                var = getattr(self, f"_aux{i+1}_action", None)
                if var is not None:
                    setattr(self, f"aux{i+1}_action", str(var.get() or "None"))
        except Exception:
            pass

    def _refresh_run_aux_buttons(self):
        try:
            if not hasattr(self, "run_aux_button_vars"):
                return
            now = time.time()
            if getattr(self, "_run_aux_confirm_until", 0.0) and now > float(getattr(self, "_run_aux_confirm_until", 0.0)):
                self._run_aux_confirm_idx = None
                self._run_aux_confirm_until = 0.0
            if getattr(self, "_run_aux_confirmed_until", 0.0) and now > float(getattr(self, "_run_aux_confirmed_until", 0.0)):
                self._run_aux_confirmed_idx = None
                self._run_aux_confirmed_until = 0.0
                if hasattr(self, "run_aux_status_var"):
                    self.run_aux_status_var.set("")
            for i, var in enumerate(self.run_aux_button_vars):
                action = self._run_aux_action_name(i).strip()
                label = self._aux_action_label(i).strip() if action and action != "None" else f"Aux {i+1}"
                if getattr(self, "_run_aux_confirmed_idx", None) == i:
                    txt = "Confirmed"
                elif getattr(self, "_run_aux_confirm_idx", None) == i:
                    txt = "Confirm?"
                else:
                    txt = label if label and label != "AUX" else f"Aux {i+1}"
                var.set(txt)
        except Exception:
            pass

    def _on_run_aux_button(self, idx: int):
        try:
            action = self._run_aux_action_name(idx)
            if not action or action == "None":
                if hasattr(self, "run_aux_status_var"):
                    self.run_aux_status_var.set(f"Aux {idx+1}: no action assigned")
                self._run_aux_confirm_idx = None
                self._refresh_run_aux_buttons()
                return
            now = time.time()
            if getattr(self, "_run_aux_confirm_idx", None) == idx and now <= float(getattr(self, "_run_aux_confirm_until", 0.0) or 0.0):
                self._sync_run_aux_assignments_from_ui()
                self._run_aux_confirm_idx = None
                self._run_aux_confirm_until = 0.0
                self._run_aux_confirmed_idx = idx
                self._run_aux_confirmed_until = now + 2.0
                if hasattr(self, "run_aux_status_var"):
                    self.run_aux_status_var.set(f"Aux {idx+1}: {action} confirmed")
                self._handle_aux_action(idx)
            else:
                self._run_aux_confirm_idx = idx
                self._run_aux_confirm_until = now + 10.0
                self._run_aux_confirmed_idx = None
                self._run_aux_confirmed_until = 0.0
                if hasattr(self, "run_aux_status_var"):
                    self.run_aux_status_var.set(f"Aux {idx+1}: press again to confirm {action}")
            self._refresh_run_aux_buttons()
        except Exception:
            pass

    def _normalise_setup_action(self, action: str) -> str:
        action = str(action or "").strip()
        if action == "Start Calibration":
            return "Limit Calibration"
        if action == "Acceleration Mode":
            return "Accel Mode"
        return action

    def _current_raw_winch_units(self) -> int:
        try:
            return int(float(getattr(self, "winch_raw_pos_units", 0) or 0))
        except Exception:
            return 0

    def _close_calibration_popup_if_any(self):
        try:
            popup = getattr(self, "_system_calibration_popup", None)
            if popup is not None:
                try:
                    popup.grab_release()
                except Exception:
                    pass
                try:
                    popup.destroy()
                except Exception:
                    pass
        except Exception:
            pass
        self._system_calibration_popup = None

    def _cancel_active_calibration_restore_config(self):
        """Cancel Limit/Winch calibration and restore the last saved config.json state."""
        self._close_calibration_popup_if_any()
        self.system_calibration_mode = False
        self._system_calibration_aux_step = 0
        self._system_calibration_step = 0
        self.winch_calibration_mode = False
        self._winch_calibration_aux_step = 0
        self._winch_calibration_zero_raw = None
        self._winch_calibration_zero_pos_m = None
        self.goto_target_m = None
        try:
            self._send_velocity_command(0.0, force=True)
        except Exception:
            pass
        try:
            self._load_config()
        except Exception:
            pass
        # v20: cancelling calibration restores the previous saved limit/unit values,
        # but it must not falsely make an already calibrated system Un-Calibrated.
        try:
            if hasattr(self, "_pre_calibration_not_calibrated"):
                self.not_calibrated_mode = bool(self._pre_calibration_not_calibrated)
            if getattr(self, "_pre_calibration_pos_m", None) is not None:
                self.state.pos_m = float(self._pre_calibration_pos_m)
        except Exception:
            pass
        try:
            self._update_limits_ui()
        except Exception:
            pass
        try:
            self._sync_limits_to_winch()
            self.arduino_client.send(f"SET_UNITS_PER_M {float(self.winch_units_per_m):.1f}")
        except Exception:
            pass
        try:
            self._redraw_progress()
            self._force_hmi_display_update()
            self._refresh_setup_action_buttons()
            self._refresh_run_aux_buttons()
        except Exception:
            pass
        self._set_status("Calibration cancelled; restored previous saved config.")

    def _begin_limit_calibration(self):
        self._close_calibration_popup_if_any()
        try:
            self._pre_calibration_not_calibrated = bool(getattr(self, "not_calibrated_mode", False))
            self._pre_calibration_pos_m = getattr(self.state, "pos_m", None)
        except Exception:
            pass
        self.winch_calibration_mode = False
        self._winch_calibration_aux_step = 0
        self._winch_calibration_zero_raw = None
        self._system_calibration_aux_step = 0
        self._system_calibration_step = 0
        self._enter_system_calibration_mode()
        self._force_hmi_display_update()
        self._refresh_run_aux_buttons()
        self._set_status("Setup: Limit Calibration")

    def _begin_winch_calibration(self):
        self._close_calibration_popup_if_any()
        try:
            self._pre_calibration_not_calibrated = bool(getattr(self, "not_calibrated_mode", False))
            self._pre_calibration_pos_m = getattr(self.state, "pos_m", None)
        except Exception:
            pass
        self.system_calibration_mode = False
        self._system_calibration_aux_step = 0
        self._system_calibration_step = 0
        self.winch_calibration_mode = True
        self._winch_calibration_aux_step = 0
        self._winch_calibration_zero_raw = None
        self._winch_calibration_zero_pos_m = None
        self.goto_target_m = None
        self.current_speed_mps = 0.0
        try:
            self._send_velocity_command(0.0, force=True)
        except Exception:
            pass
        self._force_hmi_display_update()
        self._refresh_run_aux_buttons()
        self._set_status("Setup: Winch Calibration")

    def _finish_winch_calibration(self, raw20: int):
        raw0 = self._winch_calibration_zero_raw
        if raw0 is None:
            self._set_status("Winch Calibration error: zero point not captured")
            return
        delta = abs(int(raw20) - int(raw0))
        if delta < 20:
            self._set_status("Winch Calibration error: move exactly 20.00 m before Set 20m")
            return
        new_upm = float(delta) / 20.0
        self.winch_units_per_m = max(1.0, new_upm)
        try:
            if hasattr(self, "_tab_winch_units_var"):
                self._tab_winch_units_var.set(f"{self.winch_units_per_m:0.1f}")
        except Exception:
            pass
        try:
            self.arduino_client.send(f"SET_UNITS_PER_M {self.winch_units_per_m:.1f}")
        except Exception:
            pass
        self.winch_calibration_mode = False
        self._winch_calibration_aux_step = 0
        self._winch_calibration_zero_raw = None
        self._winch_calibration_zero_pos_m = None
        self._save_config()
        self._force_hmi_display_update()
        self._set_status(f"Winch Calibrated: {self.winch_units_per_m:0.1f} command units/m")
        self._setup_action_confirmed_text = "Winch Calibrated"

    def _setup_direct_action_label(self, action: str) -> str:
        try:
            action = self._normalise_setup_action(action)
            if action == "Limit Calibration":
                step = int(getattr(self, "_system_calibration_aux_step", 0) or 0)
                if not bool(getattr(self, "system_calibration_mode", False)):
                    return "Limit Calibration"
                if step <= 0:
                    return "Set Near Limit"
                if step == 1:
                    return "Set Far Limit"
                return "Set Ref Point"
            if action == "Winch Calibration":
                step = int(getattr(self, "_winch_calibration_aux_step", 0) or 0)
                if not bool(getattr(self, "winch_calibration_mode", False)):
                    return "Winch Calibration"
                if step <= 0:
                    return "Set Zero"
                return "Set 20m"
            if action == "Accel Mode":
                return f"Accel Mode | {self._display_accel_type()}"
            if action == "Drive Mode":
                return f"Drive Mode | {self._active_speed_mode_name()}"
            if action == "Battery Change":
                return f"Battery Change | {'On' if bool(getattr(self, 'battery_change_mode', False)) else 'Off'}"
            return action
        except Exception:
            return str(action or "")

    def _refresh_setup_action_buttons(self):
        try:
            if not hasattr(self, "setup_action_button_vars"):
                return
            now = time.time()
            if getattr(self, "_setup_action_confirm_until", 0.0) and now > float(getattr(self, "_setup_action_confirm_until", 0.0) or 0.0):
                self._setup_action_confirm_idx = None
                self._setup_action_confirm_until = 0.0
            if getattr(self, "_setup_action_confirmed_until", 0.0) and now > float(getattr(self, "_setup_action_confirmed_until", 0.0) or 0.0):
                self._setup_action_confirmed_idx = None
                self._setup_action_confirmed_until = 0.0
                self._setup_action_confirmed_text = ""
            names = list(getattr(self, "setup_action_names", []) or [])
            for i, var in enumerate(self.setup_action_button_vars):
                if getattr(self, "_setup_action_confirmed_idx", None) == i:
                    txt = str(getattr(self, "_setup_action_confirmed_text", "") or self._setup_direct_action_label(names[i] if i < len(names) else ""))
                elif getattr(self, "_setup_action_confirm_idx", None) == i:
                    txt = "Confirm?"
                else:
                    action = names[i] if i < len(names) else ""
                    txt = self._setup_direct_action_label(action)
                var.set(str(txt or "Setup"))
        except Exception:
            pass

    def _execute_setup_direct_action(self, action: str):
        """Run a fixed Setup-tab action without requiring an AUX assignment."""
        try:
            action = self._normalise_setup_action(action)
            self._setup_action_confirmed_text = ""
            if action == "Limit Calibration":
                step = int(getattr(self, "_system_calibration_aux_step", 0) or 0)
                if not bool(getattr(self, "system_calibration_mode", False)):
                    self._begin_limit_calibration()
                elif step <= 0:
                    pos = self.state.pos_m
                    if pos is not None:
                        self._set_system_calibration_point(self.state.near_limit, 0, pos)
                        self._system_calibration_aux_step = 1
                        self._update_limits_ui()
                        self._redraw_progress()
                        self._sync_limits_to_winch()
                        self._force_hmi_display_update()
                        self._set_status("Setup: Set Near Limit")
                        self._refresh_run_aux_buttons()
                elif step == 1:
                    pos = self.state.pos_m
                    if pos is not None:
                        self._set_system_calibration_point(self.state.far_limit, 1, pos)
                        self._system_calibration_aux_step = 2
                        self._update_limits_ui()
                        self._redraw_progress()
                        self._sync_limits_to_winch()
                        self._force_hmi_display_update()
                        self._set_status("Setup: Set Far Limit")
                        self._refresh_run_aux_buttons()
                else:
                    pos = self.state.pos_m
                    if pos is not None:
                        self._set_system_calibration_point(self.state.ref_point, 2, pos)
                        self._system_calibration_aux_step = 0
                        self._update_limits_ui()
                        self._redraw_progress()
                        self._sync_limits_to_winch()
                        self._save_config()
                        self._force_hmi_display_update()
                        self._exit_not_calibrated_mode()
                        self._exit_system_calibration_mode()
                        self._setup_action_confirmed_text = "Limits Calibrated"
                        self._set_status("Limits Calibrated")
                        self._refresh_run_aux_buttons()
            elif action == "Winch Calibration":
                step = int(getattr(self, "_winch_calibration_aux_step", 0) or 0)
                if not bool(getattr(self, "winch_calibration_mode", False)):
                    self._begin_winch_calibration()
                elif step <= 0:
                    self._winch_calibration_zero_raw = self._current_raw_winch_units()
                    self._winch_calibration_zero_pos_m = getattr(self.state, "pos_m", None)
                    self._winch_calibration_aux_step = 1
                    self._force_hmi_display_update()
                    self._set_status(f"Setup: Set Zero raw={self._winch_calibration_zero_raw}")
                    self._refresh_run_aux_buttons()
                else:
                    self._finish_winch_calibration(self._current_raw_winch_units())
            elif action == "Drive Mode":
                new_idx = 1 if int(getattr(self, "active_drive_mode", 0)) == 0 else 0
                if hasattr(self, "_set_active_drive_mode"):
                    self._set_active_drive_mode(new_idx)
                else:
                    self.active_drive_mode = new_idx
                self._set_status(f"Setup: Drive Mode -> {self._active_speed_mode_name()}")
            elif action == "Battery Change":
                new_state = not bool(getattr(self, "battery_change_mode", False))
                self._set_battery_change_mode(new_state, save_config=True)
                self._set_status(f"Setup: Battery Change -> {'ON' if new_state else 'OFF'}")
            elif action == "Accel Mode":
                new_type = self._toggle_accel_type(save_config=True)
                self._set_status(f"Setup: Accel Mode -> {new_type}")
            self._force_hmi_display_update()
            self._refresh_setup_action_buttons()
        except Exception as exc:
            _app_log(f"[SRVR] Setup action failed: {exc}")
    def _on_setup_action_button(self, idx: int):
        try:
            names = list(getattr(self, "setup_action_names", []) or [])
            if idx < 0 or idx >= len(names):
                return
            action = names[idx]
            now = time.time()
            if getattr(self, "_setup_action_confirm_idx", None) == idx and now <= float(getattr(self, "_setup_action_confirm_until", 0.0) or 0.0):
                self._setup_action_confirm_idx = None
                self._setup_action_confirm_until = 0.0
                self._setup_action_confirmed_idx = None
                self._setup_action_confirmed_until = 0.0
                self._setup_action_confirmed_text = ""
                self._execute_setup_direct_action(action)
                # Do not show a generic Confirmed state between calibration steps.
                # Only show the final named completion state briefly.
                final_txt = str(getattr(self, "_setup_action_confirmed_text", "") or "")
                if final_txt in ("Limits Calibrated", "Winch Calibrated"):
                    self._setup_action_confirmed_idx = idx
                    self._setup_action_confirmed_until = now + 2.0
            else:
                self._setup_action_confirm_idx = idx
                self._setup_action_confirm_until = now + 10.0
                self._setup_action_confirmed_idx = None
                self._setup_action_confirmed_until = 0.0
                self._setup_action_confirmed_text = ""
                self._set_status(f"Setup: press again to confirm {self._setup_direct_action_label(action)}")
            self._refresh_setup_action_buttons()
        except Exception:
            pass

    def _set_status(self, msg: str):
        """Write a message to the live log and status bar when available."""
        _app_log(f"[SRVR] {msg}")
        try:
            self.status_var.set(msg)
        except Exception:
            pass







    


    def _build_limit_column(
        self,
        parent,
        col: int,
        lp: LimitPoint,
        allow_ramp: bool,
        is_ref: bool = False,
        is_limit: bool = False,
        row: int = 0,
        columnspan: int = 1,
    ):
        frame = tk.Frame(parent, bg="#1a1a1a", highlightbackground="#2a2f3a", highlightcolor="#2a2f3a", highlightthickness=1, bd=0)
        frame.grid(row=row, column=col, columnspan=columnspan, sticky="new", padx=3, pady=2)
        frame.columnconfigure(0, weight=1)

        # Compact header row: Heading (bold left) + Distance (right) on same row
        header = tk.Frame(frame, bg="#1a1a1a")
        header.grid(row=0, column=0, sticky="ew", padx=8, pady=(4, 1))
        header.columnconfigure(0, weight=1)
        header.columnconfigure(1, weight=0)

        lbl_title = tk.Label(
            header,
            text=lp.name,
            fg="white",
            bg="#1a1a1a",
            font=FONT_SMALL_BOLD,
            anchor="w",
            justify="left",
        )
        lbl_title.grid(row=0, column=0, sticky="w")

        value = self._limit_display_position_m(lp)
        lbl_val = tk.Label(
            header,
            text=f"{value:07.2f} m",
            fg="#dddddd",
            bg="#1a1a1a",
            font=FONT_SMALL,
            anchor="e",
            justify="right",
        )
        lbl_val.grid(row=0, column=1, sticky="e")
        lbl_val.configure(cursor="hand2")
        lbl_val.bind("<Button-1>", lambda _e, p=lp: self.on_limit_distance_edit(p))

        setattr(self, f"{lp.name.replace(' ', '_').lower()}_label", lbl_val)

        # Button layout: all controls on one row.
        # Near/Far: Set | Goto | Slip | Ramping
        # Reference: Set | Goto | Slip
        btn_grid = tk.Frame(frame, bg="#1a1a1a")
        btn_grid.grid(row=1, column=0, padx=8, pady=(4, 7), sticky="ew")
        btn_cols = 3 if is_ref else 4
        for bc in range(btn_cols):
            btn_grid.columnconfigure(bc, weight=1, uniform=f"limit_btn_{self._limit_confirm_key(lp)}")

        key = self._limit_confirm_key(lp)
        if not hasattr(self, "limit_button_vars"):
            self.limit_button_vars = {}
        set_var = tk.StringVar(value="Set")
        goto_var = tk.StringVar(value="Goto")
        slip_var = tk.StringVar(value="Slip")
        self.limit_button_vars[(key, "set")] = set_var
        self.limit_button_vars[(key, "goto")] = goto_var
        self.limit_button_vars[(key, "slip")] = slip_var

        btn_set = ttk.Button(btn_grid, textvariable=set_var, command=lambda p=lp: self.on_limit_set_button(p), width=7)
        btn_set.grid(row=0, column=0, padx=(0, 3), pady=(0, 0), sticky="ew")

        btn_goto = ttk.Button(btn_grid, textvariable=goto_var, command=lambda p=lp: self.on_limit_goto_button(p), width=7)
        btn_goto.grid(row=0, column=1, padx=3, pady=(0, 0), sticky="ew")

        btn_slip = ttk.Button(btn_grid, textvariable=slip_var, command=lambda p=lp: self.on_limit_slip_button(p), width=7)
        btn_slip.grid(row=0, column=2, padx=(3, 0 if is_ref else 3), pady=(0, 0), sticky="ew")

        if not is_ref:
            if allow_ramp and (lp.name.startswith("Near") or lp.name.startswith("Far")):
                btn_ramp = ttk.Button(btn_grid, text="Ramping", command=lambda p=lp: self.on_set_ramping(p), width=7)
            else:
                btn_ramp = ttk.Button(btn_grid, text="Ramping", state="disabled", width=7)
            btn_ramp.grid(row=0, column=3, padx=(3, 0), pady=(0, 0), sticky="ew")


        if lp.name.startswith("Near"):
            self.near_frame = frame
        elif lp.name.startswith("Far"):
            self.far_frame = frame
        else:
            self.ref_frame = frame
        self._bind_calibration_card_selection(frame)


    def _build_preset_grid(self, parent: tk.Frame):
        """Create Run-tab Near/Ref/Far limit cards plus 6 preset position boxes."""
        # Clear any existing labels / vars
        self.preset_labels.clear()
        self.preset_name_vars.clear()
        self.preset_show_buttons.clear()
        self.preset_set_button_vars = []
        self.preset_goto_button_vars = []
        self.limit_button_vars = {}
        self._preset_confirm = getattr(self, "_preset_confirm", None)
        self._limit_confirm = getattr(self, "_limit_confirm", None)

        for c in range(6):
            parent.columnconfigure(c, weight=1, uniform="run_preset_cols")
        parent.rowconfigure(0, weight=0)
        parent.rowconfigure(1, weight=0)

        # Limit controls replace the first six old preset slots: Near spans P1/P2,
        # Ref spans P3/P4, and Far spans P5/P6.
        self._build_limit_column(parent, 0, self.state.near_limit, allow_ramp=True, is_limit=True, row=0, columnspan=2)
        self._build_limit_column(parent, 2, self.state.ref_point, allow_ramp=False, is_ref=True, row=0, columnspan=2)
        self._build_limit_column(parent, 4, self.state.far_limit, allow_ramp=True, is_limit=True, row=0, columnspan=2)

        for idx in range(PRESET_COUNT):
            row = 1
            col = idx

            cell = tk.Frame(parent, bg="#1a1a1a", bd=1, relief="solid")
            cell.grid(row=row, column=col, sticky="nsew", padx=3, pady=(3, 1))
            cell.columnconfigure(0, weight=1)

            # Preset header row: Name (bold left) + Position (right, normal) on same row
            name_default = f"P{idx + 1}"
            if 0 <= idx < len(self.preset_names):
                name_text = self.preset_names[idx]
            else:
                name_text = name_default
            name_var = tk.StringVar(value=name_text)
            self.preset_name_vars.append(name_var)

            header = tk.Frame(cell, bg="#1a1a1a")
            header.grid(row=0, column=0, sticky="ew", padx=6, pady=(2, 0))
            header.columnconfigure(0, weight=1)
            header.columnconfigure(1, weight=0)

            title = tk.Label(
                header,
                textvariable=name_var,
                fg="white",
                bg="#1a1a1a",
                font=FONT_SMALL_BOLD,
                anchor="w",
            )
            title.grid(row=0, column=0, sticky="w")

            lbl_pos = tk.Label(
                header,
                text=self._format_preset_position(idx),
                fg="#dddddd",
                bg="#1a1a1a",
                font=FONT_SMALL,
                anchor="e",
            )
            lbl_pos.grid(row=0, column=1, sticky="e")
            self.preset_labels.append(lbl_pos)

            title.bind("<Button-1>", lambda event, idx=idx: self.on_preset_rename(idx))
            lbl_pos.bind("<Button-1>", lambda event, idx=idx: self.on_preset_distance_edit(idx))

            btn_frame = tk.Frame(cell, bg="#1a1a1a")
            btn_frame.grid(row=1, column=0, sticky="ew", padx=6, pady=(1, 2))
            # Set / Goto / Show use 35 / 35 / 30 to stop Confirmed cropping.
            btn_frame.columnconfigure(0, weight=35)
            btn_frame.columnconfigure(1, weight=35)
            btn_frame.columnconfigure(2, weight=30)

            set_var = tk.StringVar(value="Set")
            goto_var = tk.StringVar(value="Goto")
            self.preset_set_button_vars.append(set_var)
            self.preset_goto_button_vars.append(goto_var)

            btn_set = ttk.Button(btn_frame, textvariable=set_var, command=lambda i=idx: self.on_preset_set(i), width=7)
            btn_set.grid(row=0, column=0, sticky="ew", padx=(0, 2))

            btn_goto = ttk.Button(btn_frame, textvariable=goto_var, command=lambda i=idx: self.on_preset_goto(i), width=7)
            btn_goto.grid(row=0, column=1, sticky="ew", padx=2)

            btn_show = ttk.Button(btn_frame, text=self._preset_visibility_text(idx), command=lambda i=idx: self.on_preset_toggle_visible(i), width=6)
            btn_show.grid(row=0, column=2, sticky="ew", padx=(2, 0))
            self.preset_show_buttons.append(btn_show)

    def _limit_confirm_key(self, lp: LimitPoint) -> str:
        try:
            name = str(getattr(lp, "name", "") or "").lower()
        except Exception:
            name = ""
        if "near" in name:
            return "near"
        if "far" in name:
            return "far"
        return "ref"

    def _limit_confirm_ready(self, kind: str, lp: LimitPoint) -> bool:
        try:
            key = self._limit_confirm_key(lp)
            now = time.time()
            active = getattr(self, "_limit_confirm", None)
            if isinstance(active, dict) and active.get("kind") == kind and active.get("key") == key and str(active.get("label", "")) == "Confirm?" and now <= float(active.get("until", 0.0) or 0.0):
                self._limit_confirm = {"kind": kind, "key": key, "label": "Confirmed", "until": now + 2.0}
                self._refresh_limit_confirm_buttons()
                return True
            self._limit_confirm = {"kind": kind, "key": key, "label": "Confirm?", "until": now + 10.0}
            self._refresh_limit_confirm_buttons()
            return False
        except Exception:
            return False

    def _refresh_limit_confirm_buttons(self):
        try:
            now = time.time()
            active = getattr(self, "_limit_confirm", None)
            if isinstance(active, dict) and now > float(active.get("until", 0.0) or 0.0):
                self._limit_confirm = None
                active = None
            defaults = {"set": "Set", "goto": "Goto", "slip": "Slip"}
            for (key, kind), var in (getattr(self, "limit_button_vars", {}) or {}).items():
                txt = defaults.get(kind, str(kind).title())
                if isinstance(active, dict) and active.get("key") == key and active.get("kind") == kind:
                    txt = str(active.get("label", "Confirm?"))
                try:
                    var.set(txt)
                except Exception:
                    pass
        except Exception:
            pass

    def on_limit_set_button(self, lp: LimitPoint):
        if not self._limit_confirm_ready("set", lp):
            return
        self.on_set_point(lp, require_popup=False)

    def on_limit_goto_button(self, lp: LimitPoint):
        if not self._limit_confirm_ready("goto", lp):
            return
        if self._limit_confirm_key(lp) == "ref":
            self.on_goto_reference(require_popup=False)
        else:
            self.on_goto_limit(lp, require_popup=False)

    def on_limit_slip_button(self, lp: LimitPoint):
        if not self._limit_confirm_ready("slip", lp):
            return
        self.on_set_slip(lp, require_popup=False, show_info=False)

    def on_limit_distance_edit(self, lp: LimitPoint):
        """Manual edit for Near / Ref / Far distance labels from the Run tab."""
        try:
            current = self._limit_display_position_m(lp)
            current_val = f"{float(current):.2f}"
        except Exception:
            current_val = ""
        try:
            new_val = simpledialog.askstring(
                "Edit Position Distance",
                f"Enter distance in metres for {lp.name}:",
                initialvalue=current_val,
                parent=self.root,
            )
        except Exception:
            new_val = None
        if new_val is None:
            return
        new_val = str(new_val).strip()
        if not new_val:
            return
        try:
            distance_m = float(new_val)
        except Exception:
            messagebox.showerror("Position Distance", "Please enter a valid numeric distance in metres.")
            return
        lp.position_m = float(distance_m)
        try:
            nl = self.state.near_limit.position_m
            fl = self.state.far_limit.position_m
            if nl is not None and fl is not None:
                self.state.total_length_m = max(0.1, float(fl) - float(nl))
        except Exception:
            pass
        self._update_limits_ui()
        self._redraw_progress()
        self._redraw_freed_top_view()
        self._redraw_freed_side_view()
        self._sync_limits_to_winch()
        self._save_config()

    def _preset_visibility_text(self, idx: int) -> str:
        if 0 <= idx < len(self.preset_visible) and bool(self.preset_visible[idx]):
            return "Hide"
        return "Show"

    def _refresh_preset_show_buttons(self):
        buttons = getattr(self, "preset_show_buttons", [])
        for idx, btn in enumerate(buttons):
            try:
                btn.config(text=self._preset_visibility_text(idx))
            except Exception:
                pass

    def on_preset_toggle_visible(self, idx: int):
        if not (0 <= idx < PRESET_COUNT):
            return
        if len(self.preset_visible) < PRESET_COUNT:
            self.preset_visible = (list(self.preset_visible) + [False] * PRESET_COUNT)[:PRESET_COUNT]
        self.preset_visible[idx] = not bool(self.preset_visible[idx])
        self._refresh_preset_show_buttons()
        self._redraw_progress()
        self._save_config()

    def _format_preset_position(self, idx: int) -> str:
        rel_pos = None
        if 0 <= idx < len(self.preset_positions):
            rel_pos = self.preset_positions[idx]
        if rel_pos is None:
            return "--.- m"
        try:
            return f"{float(rel_pos):.2f} m"
        except Exception:
            return "--.- m"

    def _update_preset_label(self, idx: int):
        if not (0 <= idx < len(self.preset_labels)):
            return
        self.preset_labels[idx].config(text=self._format_preset_position(idx))


    def on_preset_rename(self, idx: int):
        """Prompt the user to rename a preset slot by clicking its name label."""
        if not (0 <= idx < PRESET_COUNT):
            return

        # Current name or default
        current_name = self.preset_names[idx] if idx < len(self.preset_names) else f"P{idx + 1}"

        new_name = simpledialog.askstring(
            "Rename Preset",
            f"Enter a new name for preset P{idx + 1}:",
            initialvalue=current_name,
            parent=self.root,
        )
        if new_name is None:
            # Cancelled
            return

        new_name = new_name.strip()
        if not new_name:
            new_name = f"P{idx + 1}"

        # Ensure list is correct length
        if len(self.preset_names) < PRESET_COUNT:
            self.preset_names = (self.preset_names + [f"P{i+1}" for i in range(len(self.preset_names), PRESET_COUNT)])[:PRESET_COUNT]

        self.preset_names[idx] = new_name

        # Update label var if present
        if 0 <= idx < len(self.preset_name_vars):
            self.preset_name_vars[idx].set(new_name)

        # Save config so names persist
        self._redraw_progress()
        self._save_config()

    def on_preset_distance_edit(self, idx: int):
        """Prompt user to manually set a preset distance in metres by clicking the distance label."""
        if not (0 <= idx < PRESET_COUNT):
            return

        # Current value as string, if any
        current_val = ""
        if 0 <= idx < len(self.preset_positions) and self.preset_positions[idx] is not None:
            try:
                current_val = f"{float(self.preset_positions[idx]):.2f}"
            except Exception:
                current_val = ""

        # Use preset name if available, else default P#
        if 0 <= idx < len(self.preset_names):
            preset_name = self.preset_names[idx]
        else:
            preset_name = f"P{idx + 1}"

        new_val = simpledialog.askstring(
            "Edit Preset Distance",
            f"Enter distance in metres for preset {preset_name}:",
            initialvalue=current_val,
            parent=self.root,
        )
        if new_val is None:
            # Cancelled
            return

        new_val = new_val.strip()
        if new_val == "":
            # Blank clears the preset distance
            if 0 <= idx < len(self.preset_positions):
                self.preset_positions[idx] = None
                self._update_preset_label(idx)
                self._redraw_progress()
                self._save_config()
            return

        try:
            distance_m = float(new_val)
        except Exception:
            messagebox.showerror(
                "Preset Distance",
                "Please enter a valid numeric distance in metres.",
            )
            return

        if 0 <= idx < len(self.preset_positions):
            self.preset_positions[idx] = distance_m
            self._update_preset_label(idx)
            self._redraw_progress()
            self._save_config()

    def _refresh_preset_confirm_buttons(self):
        try:
            now = time.time()
            active = getattr(self, "_preset_confirm", None)
            if isinstance(active, dict) and now > float(active.get("until", 0.0) or 0.0):
                self._preset_confirm = None
                active = None
            set_vars = getattr(self, "preset_set_button_vars", [])
            goto_vars = getattr(self, "preset_goto_button_vars", [])
            for i, var in enumerate(set_vars):
                txt = "Set"
                if isinstance(active, dict) and active.get("idx") == i and active.get("kind") == "set":
                    txt = str(active.get("label", "Confirm?"))
                var.set(txt)
            for i, var in enumerate(goto_vars):
                txt = "Goto"
                if isinstance(active, dict) and active.get("idx") == i and active.get("kind") == "goto":
                    txt = str(active.get("label", "Confirm?"))
                var.set(txt)
        except Exception:
            pass

    def _preset_button_confirm_ready(self, kind: str, idx: int) -> bool:
        try:
            now = time.time()
            active = getattr(self, "_preset_confirm", None)
            if isinstance(active, dict) and active.get("kind") == kind and active.get("idx") == idx and str(active.get("label", "")) == "Confirm?" and now <= float(active.get("until", 0.0) or 0.0):
                self._preset_confirm = {"kind": kind, "idx": idx, "label": "Confirmed", "until": now + 2.0}
                self._refresh_preset_confirm_buttons()
                return True
            self._preset_confirm = {"kind": kind, "idx": idx, "label": "Confirm?", "until": now + 10.0}
            self._refresh_preset_confirm_buttons()
            return False
        except Exception:
            return False

    def on_preset_set(self, idx: int):
        """Store the current position into the given preset slot."""
        if not self._preset_button_confirm_ready("set", idx):
            return

        rel_pos = self._current_position_relative_m()
        if self.state.pos_m is None:
            # If we don't know current position, default to midpoint of the current span as a relative distance
            nl = self.state.near_limit.position_m or 0.0
            fl = self.state.far_limit.position_m or (nl + self.state.total_length_m)
            rel_pos = max(0.0, float(fl) - float(nl)) / 2.0

        if 0 <= idx < len(self.preset_positions):
            self.preset_positions[idx] = float(rel_pos)
            self._update_preset_label(idx)
            self._redraw_progress()
            self._save_config()

    def on_preset_goto(self, idx: int):
        """Goto the stored preset position, if it exists."""
        if not self._preset_button_confirm_ready("goto", idx):
            return

        if not (0 <= idx < len(self.preset_positions)):
            return
        rel_pos = self.preset_positions[idx]
        if rel_pos is None:
            messagebox.showwarning(
                "Preset Position",
                f"Preset P{idx + 1} is not set yet.",
            )
            return

        abs_pos = self._preset_absolute_position_m(idx)
        if abs_pos is None:
            return

        # If current position is unknown, initialise it to this preset target
        if self.state.pos_m is None:
            self.state.pos_m = float(abs_pos)

        name = self.preset_names[idx] if idx < len(self.preset_names) else f"P{idx+1}"
        self._start_goto_target(float(abs_pos), f"Goto {name} {abs_pos:0.2f} m")
    def _build_status_bar(self):
        frame = tk.Frame(self.main_frame, bg="#111111", height=1)
        frame.grid(row=5, column=0, sticky="ew")
        frame.grid_propagate(False)

        # Bottom motion/demo controls removed (E-Stop at top provides status)
        self.demo_var = tk.BooleanVar(value=False)
        self.motion_status_label = None
        self.demo_button = None


    def _build_connections_row(self):
        frame = tk.Frame(self.main_frame, bg="#181818")
        frame.grid(row=4, column=0, sticky="ew")
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(0, weight=1)

        # Controller Connection (left)
        self.ctrl_frame = tk.Frame(frame, bg="#2f2f2f", bd=1, relief="solid")
        self.ctrl_frame.grid(row=0, column=0, sticky="nsew", padx=8, pady=6)
        self._build_connection_panel(
            self.ctrl_frame,
            title="Controller Connection",
            subtitle="Controller Arduino",
            settings_callback=self.on_controller_settings,
            status_attr="ctrl_status_label",
            ip_attr="ctrl_ip_label",
        )

        # Winch Connection (right)
        self.winch_frame = tk.Frame(frame, bg="#2f2f2f", bd=1, relief="solid")
        self.winch_frame.grid(row=0, column=1, sticky="nsew", padx=8, pady=6)
        self._build_connection_panel(
            self.winch_frame,
            title="Winch Connection",
            subtitle="Winch Arduino",
            settings_callback=self.on_winch_settings,
            status_attr="winch_status_label",
            ip_attr="winch_ip_label",
        )

    def _build_connection_panel(
        self,
        parent,
        title: str,
        subtitle: str,
        settings_callback,
        status_attr: str,
        ip_attr: str,
    ):
        for c in range(3):
            parent.columnconfigure(c, weight=[1, 0, 0][c])
        parent.rowconfigure(0, weight=0)

        title_frame = tk.Frame(parent, bg="#2f2f2f")
        title_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        title_frame.columnconfigure(0, weight=1)
        title_frame.columnconfigure(1, weight=0)

        lbl_title = tk.Label(
            title_frame,
            text=title,
            fg="white",
            bg="#2f2f2f",
            font=FONT_SMALL_BOLD,
            anchor="w",
        )
        lbl_title.grid(row=0, column=0, sticky="w")

        lbl_ip = tk.Label(
            title_frame,
            text="IP: -",
            fg="#bbbbbb",
            bg="#2f2f2f",
            font=FONT_SMALL,
            anchor="e",
        )
        lbl_ip.grid(row=0, column=1, sticky="e", padx=(12, 0))
        # Settings button removed (handled via tabs)

        status_label = tk.Label(
            parent,
            text="Not Connected",
            fg="white",
            bg="#662222",  # red-ish when disconnected
            font=FONT_SMALL_BOLD,
            width=14,
            anchor="center",
        )
        status_label.grid(row=0, column=2, sticky="e", padx=10, pady=10)

        setattr(self, status_attr, status_label)
        setattr(self, ip_attr, lbl_ip)


    # ---------------- Configuration persistence ----------------

    def _to_config_dict(self):
        self._sync_drive_mode_legacy_name_keys()
        return {
            "winch_host": self.winch_host,
            "winch_port": self.winch_port,
            "controller_ip_ref": self.controller_ip_ref,
            "joy_cal": {
                "min": float(controller_state.get("joy_min", -1.0) or -1.0),
                "center": float(controller_state.get("joy_center", 0.0) or 0.0),
                "max": float(controller_state.get("joy_max", 1.0) or 1.0),
            },
            "max_speed_mps": self.max_speed_mps,
            "battery_change_mode": self.battery_change_mode,
            "not_calibrated_mode": getattr(self, "not_calibrated_mode", True),
            "accel_type": self._display_accel_type(),
            "max_accel_mps2": getattr(self, "max_accel_mps2", 2.0),
            "max_decel_mps2": getattr(self, "max_decel_mps2", 2.0),
            "max_crossover_mps2": getattr(self, "max_crossover_mps2", 4.0),
            "max_stop_decel_mps2": getattr(self, "max_stop_decel_mps2", getattr(self, "max_decel_mps2", 2.0)),
            "drive_modes": getattr(self, "drive_modes", []),
            "drive_mode_names": [str(getattr(self, "mode_a_name", "Mode A")), str(getattr(self, "mode_b_name", "Mode B"))],
            "mode_a_name": str(getattr(self, "mode_a_name", "Mode A")),
            "mode_b_name": str(getattr(self, "mode_b_name", "Mode B")),
            "active_drive_mode": int(getattr(self, "active_drive_mode", 0)),
            "near_limit": {
                "position_m": self.state.near_limit.position_m,
                "ramp_mode": self.state.near_limit.ramp_mode,
                "ramp_distance_m": self.state.near_limit.ramp_distance_m,
                "ramp_percentage": self.state.near_limit.ramp_percentage,
            },
            "ref_point": {
                "position_m": self.state.ref_point.position_m,
            },
            "far_limit": {
                "position_m": self.state.far_limit.position_m,
                "ramp_mode": self.state.far_limit.ramp_mode,
                "ramp_distance_m": self.state.far_limit.ramp_distance_m,
                "ramp_percentage": self.state.far_limit.ramp_percentage,
            },
            "reverse_joystick": self.reverse_joystick,
            "reverse_motor": self.reverse_motor,
            "aux1_action": getattr(self, "aux1_action", "None"),
            "aux2_action": getattr(self, "aux2_action", "None"),
            "aux3_action": getattr(self, "aux3_action", "None"),
            "aux4_action": getattr(self, "aux4_action", "None"),
            "w1pts_aux1_action": getattr(self, "w1pts_aux1_action", "None"),
            "w1pts_aux2_action": getattr(self, "w1pts_aux2_action", "None"),
            "w1pts_aux3_action": getattr(self, "w1pts_aux3_action", "None"),
            "w1pts_aux4_action": getattr(self, "w1pts_aux4_action", "None"),
            "controller_type": getattr(self, "controller_type", "HV P2P CTRL Mk1"),
            "ctrl_ts_ip_ref": "",
            "winch_type": getattr(self, "winch_type", "HV P2P W1P"),
            "winch_units_per_m": float(getattr(self, "winch_units_per_m", 21220.7)),
            "presets": self.preset_positions,
            "preset_names": self.preset_names,
            "preset_visible": self.preset_visible,
            "free_d": {
                "enabled": bool(getattr(self, "freed_output_enabled", False)),
                "target_ip": str(getattr(self, "freed_target_ip", "172.20.1.120")),
                "target_port": int(getattr(self, "freed_target_port", 40000)),
                "camera_id": int(getattr(self, "freed_camera_id", 1)),
                "rate_hz": float(getattr(self, "freed_rate_hz", 25.0)),
                "z_offset_m": float(getattr(self, "freed_z_offset_m", getattr(self, "freed_x_m", 0.0))),
                "x_m": float(getattr(self, "freed_z_offset_m", getattr(self, "freed_x_m", 0.0))),  # legacy key
                "pan": float(getattr(self, "freed_pan", 0.0)),
                "tilt": float(getattr(self, "freed_tilt", 0.0)),
                "roll": float(getattr(self, "freed_roll", 0.0)),
                "zoom": int(getattr(self, "freed_zoom", 0)),
                "focus": int(getattr(self, "freed_focus", 0)),
                "pos_scale": float(getattr(self, "freed_pos_scale", 640.0)),
                "skate_weight_kg": float(getattr(self, "freed_skate_weight_kg", 35.0)),
                "weight_per_100m_kg": float(getattr(self, "freed_weight_per_100m_kg", 4.8)),
                "sag_tension_kgf": float(getattr(self, "freed_sag_tension_kgf", 1200.0)),
                "highline_mode": str(getattr(self, "freed_highline_mode", "Single Highline")),
                "input_enabled": bool(getattr(self, "freed_input_enabled", False)),
                "input_bind_ip": str(getattr(self, "freed_input_bind_ip", "0.0.0.0")),
                "input_port": int(getattr(self, "freed_input_port", 40001)),
                "input_inverts": dict(getattr(self, "freed_input_inverts", {}) or {}),
                "input_native_invert_v": 4,
                "input_offsets": dict(getattr(self, "freed_input_offsets", {}) or {}),
                "output_inverts": dict(getattr(self, "freed_output_inverts", {}) or {}),
                "output_offsets": dict(getattr(self, "freed_output_offsets", {}) or {}),
                "lens_type": str(getattr(self, "freed_lens_type", "i24")),
                "lens_scale_mode": str(getattr(self, "freed_lens_scale_mode", "Auto")),
                "lens_cal": dict(getattr(self, "freed_lens_cal", {}) or {}),
                "lens_auto_seen": dict(getattr(self, "_freed_lens_auto_seen", {}) or {}),
                "height_points": getattr(self, "freed_height_points", []),
            },
        }

    def _apply_freed_config(self, cfg: dict):
        """Apply Free-D config block, preserving defaults when keys are missing."""
        if not isinstance(cfg, dict):
            return
        try:
            self.freed_output_enabled = bool(cfg.get("enabled", getattr(self, "freed_output_enabled", False)))
            self.freed_target_ip = str(cfg.get("target_ip", getattr(self, "freed_target_ip", "172.20.1.120"))).strip()
            self.freed_target_port = max(1, min(65535, int(cfg.get("target_port", getattr(self, "freed_target_port", 40000)))))
            self.freed_camera_id = max(0, min(255, int(cfg.get("camera_id", getattr(self, "freed_camera_id", 1)))))
            self.freed_rate_hz = max(1.0, min(100.0, float(cfg.get("rate_hz", getattr(self, "freed_rate_hz", 25.0)))))
            self.freed_z_offset_m = float(cfg.get("z_offset_m", cfg.get("x_m", getattr(self, "freed_z_offset_m", getattr(self, "freed_x_m", 0.0)))))
            self.freed_x_m = self.freed_z_offset_m  # legacy compatibility
            self.freed_pan = float(cfg.get("pan", getattr(self, "freed_pan", 0.0)))
            self.freed_tilt = float(cfg.get("tilt", getattr(self, "freed_tilt", 0.0)))
            self.freed_roll = float(cfg.get("roll", getattr(self, "freed_roll", 0.0)))
            self.freed_zoom = max(0, min(16777215, int(cfg.get("zoom", getattr(self, "freed_zoom", 0)))))
            self.freed_focus = max(0, min(16777215, int(cfg.get("focus", getattr(self, "freed_focus", 0)))))
            self.freed_pos_scale = max(1.0, float(cfg.get("pos_scale", getattr(self, "freed_pos_scale", 640.0))))
            self.freed_skate_weight_kg = max(0.0, float(cfg.get("skate_weight_kg", getattr(self, "freed_skate_weight_kg", 35.0))))
            self.freed_weight_per_100m_kg = max(0.0, float(cfg.get("weight_per_100m_kg", getattr(self, "freed_weight_per_100m_kg", 4.8))))
            self.freed_sag_tension_kgf = max(1.0, float(cfg.get("sag_tension_kgf", getattr(self, "freed_sag_tension_kgf", 1200.0))))
            saved_highline_mode = str(cfg.get("highline_mode", getattr(self, "freed_highline_mode", "Single Highline")) or "Single Highline")
            self.freed_highline_mode = "Dual Highline" if saved_highline_mode.strip().lower().startswith("dual") else "Single Highline"
            self.freed_input_enabled = bool(cfg.get("input_enabled", getattr(self, "freed_input_enabled", False)))
            self.freed_input_bind_ip = str(cfg.get("input_bind_ip", getattr(self, "freed_input_bind_ip", "0.0.0.0"))).strip() or "0.0.0.0"
            self.freed_input_port = max(1, min(65535, int(cfg.get("input_port", getattr(self, "freed_input_port", 40001)))))
            saved_inverts = cfg.get("input_inverts", getattr(self, "freed_input_inverts", {}))
            if not isinstance(saved_inverts, dict):
                saved_inverts = {}
            # Keep the Pan checkbox default OFF during config migration.
            # The previous native Pan sign caused the user-facing checkbox to be needed
            # to restore normal orientation, so older configs must not carry Pan=True forward.
            # Focus remains natively corrected, with the visible checkbox OFF by default.
            try:
                native_invert_v = int(cfg.get("input_native_invert_v", 1) or 1)
            except Exception:
                native_invert_v = 1
            self.freed_input_inverts = {
                "Pan": bool(saved_inverts.get("Pan", False)) if native_invert_v >= 4 else False,
                "Tilt": bool(saved_inverts.get("Tilt", False)),
                "Roll": bool(saved_inverts.get("Roll", False)),
                "Zoom": bool(saved_inverts.get("Zoom", False)),
                "Focus": bool(saved_inverts.get("Focus", False)) if native_invert_v >= 4 else False,
            }
            saved_in_offsets = cfg.get("input_offsets", getattr(self, "freed_input_offsets", {}))
            if not isinstance(saved_in_offsets, dict):
                saved_in_offsets = {}
            self.freed_input_offsets = {
                "Pan": float(saved_in_offsets.get("Pan", 0.0) or 0.0),
                "Tilt": float(saved_in_offsets.get("Tilt", 0.0) or 0.0),
                "Roll": float(saved_in_offsets.get("Roll", 0.0) or 0.0),
            }
            saved_out_inverts = cfg.get("output_inverts", getattr(self, "freed_output_inverts", {}))
            if not isinstance(saved_out_inverts, dict):
                saved_out_inverts = {}
            self.freed_output_inverts = {
                "X": bool(saved_out_inverts.get("X", False)),
                "Y": bool(saved_out_inverts.get("Y", False)),
                "Z": bool(saved_out_inverts.get("Z", False)),
            }
            saved_out_offsets = cfg.get("output_offsets", getattr(self, "freed_output_offsets", {}))
            if not isinstance(saved_out_offsets, dict):
                saved_out_offsets = {}
            self.freed_output_offsets = {
                "X": float(saved_out_offsets.get("X", 0.0) or 0.0),
                "Y": float(saved_out_offsets.get("Y", 0.0) or 0.0),
                "Z": float(saved_out_offsets.get("Z", 0.0) or 0.0),
            }
            self.freed_lens_type = str(cfg.get("lens_type", getattr(self, "freed_lens_type", "i24")) or "i24")
            if self.freed_lens_type not in ("i16", "u16", "i24", "u24"):
                self.freed_lens_type = "i24"
            self.freed_lens_scale_mode = str(cfg.get("lens_scale_mode", getattr(self, "freed_lens_scale_mode", "Auto")) or "Auto")
            if self.freed_lens_scale_mode not in ("Auto", "Manual", "Full scale"):
                self.freed_lens_scale_mode = "Auto"
            lens_cal = cfg.get("lens_cal", getattr(self, "freed_lens_cal", {}))
            lo, hi = self._lens_type_limits(self.freed_lens_type)
            if not isinstance(lens_cal, dict):
                lens_cal = {}
            self.freed_lens_cal = {
                "zoom_wide": float(lens_cal.get("zoom_wide", lo)),
                "zoom_tele": float(lens_cal.get("zoom_tele", hi)),
                "focus_near": float(lens_cal.get("focus_near", lo)),
                "focus_far": float(lens_cal.get("focus_far", hi)),
            }
            auto_seen = cfg.get("lens_auto_seen", None)
            if not isinstance(auto_seen, dict):
                auto_seen = {}
            try:
                z_vals = [float(self.freed_lens_cal.get("zoom_wide", lo)), float(self.freed_lens_cal.get("zoom_tele", hi))]
                f_vals = [float(self.freed_lens_cal.get("focus_near", lo)), float(self.freed_lens_cal.get("focus_far", hi))]
                self._freed_lens_auto_seen = {
                    "zoom_min": float(auto_seen.get("zoom_min", min(z_vals))),
                    "zoom_max": float(auto_seen.get("zoom_max", max(z_vals))),
                    "focus_min": float(auto_seen.get("focus_min", min(f_vals))),
                    "focus_max": float(auto_seen.get("focus_max", max(f_vals))),
                }
            except Exception:
                self._freed_lens_auto_seen = {"zoom_min": None, "zoom_max": None, "focus_min": None, "focus_max": None}
            pts = cfg.get("height_points", getattr(self, "freed_height_points", []))
            fixed = []
            if isinstance(pts, list):
                for p in pts[:5]:
                    if not isinstance(p, dict):
                        continue
                    fixed.append({
                        "enabled": bool(p.get("enabled", True)),
                        "y_m": float(p.get("y_m", 0.0)),
                        "z_m": float(p.get("z_m", 0.0)),
                        "z_offset_m": float(p.get("z_offset_m", getattr(self, "freed_z_offset_m", 0.0))),
                    })
            while len(fixed) < 5:
                idx = len(fixed)
                fixed.append({"enabled": idx in (0, 2, 4), "y_m": float(idx * 25.0), "z_m": 0.0, "z_offset_m": float(getattr(self, "freed_z_offset_m", 0.0)) if idx in (0, 4) else 0.0})
            self.freed_height_points = fixed[:5]
        except Exception:
            pass

    def _apply_config_dict(self, cfg: dict):
        try:
            self.winch_host = cfg.get("winch_host", self.winch_host)
            self.winch_port = int(cfg.get("winch_port", self.winch_port))
        except Exception:
            pass

        self.controller_ip_ref = cfg.get("controller_ip_ref", self.controller_ip_ref)
        self.ctrl_ts_ip_ref = ""

        # Migrate previous WS-HMI packs that used W1P .103.
        # The simplified current IP map uses SRVR .100, CTRL .101, W1P .102; CTRL-TS has no IP.
        if self.winch_host == "172.20.1.103":
            self.winch_host = "172.20.1.102"
        self.ctrl_ts_ip_ref = ""  # Waveshare HMI is UART via CTRL in WS-HMI architecture

        try:
            global controller_expected_ip
            controller_expected_ip = self.controller_ip_ref if self.controller_ip_ref else None
        except Exception:
            pass
        self.max_speed_mps = float(cfg.get("max_speed_mps", self.max_speed_mps))
        self.battery_change_mode = bool(cfg.get("battery_change_mode", False))
        self.not_calibrated_mode = bool(cfg.get("not_calibrated_mode", getattr(self, "not_calibrated_mode", True)))
        self.accel_type = self._normalise_accel_type(cfg.get("accel_type", getattr(self, "accel_type", "Dynamic")))
        try:
            self.max_accel_mps2 = float(cfg.get("max_accel_mps2", getattr(self, "max_accel_mps2", 2.0)))
            self.max_decel_mps2 = float(cfg.get("max_decel_mps2", getattr(self, "max_decel_mps2", 2.0)))
            self.max_crossover_mps2 = float(cfg.get("max_crossover_mps2", getattr(self, "max_crossover_mps2", 4.0)))
            self.max_stop_decel_mps2 = float(cfg.get("max_stop_decel_mps2", getattr(self, "max_stop_decel_mps2", getattr(self, "max_decel_mps2", 2.0))))
        except Exception:
            pass

        # Drive modes (optional)
        try:
            dm = cfg.get("drive_modes")
            if isinstance(dm, list) and len(dm) >= 2:
                fixed = []
                for i in range(2):
                    m = dm[i] if isinstance(dm[i], dict) else {}
                    fixed.append({
                        "name": str(m.get("name", f"Mode {i+1}")),
                        "max_speed_mps": float(m.get("max_speed_mps", self.max_speed_mps)),
                        "speed_unit": (str(m.get("speed_unit", "m/s")) if str(m.get("speed_unit", "m/s")) in ("m/s", "km/h") else "m/s"),
                        "max_goto_speed_mps": float(m.get("max_goto_speed_mps", min(float(m.get("max_speed_mps", self.max_speed_mps)), 1.0))),
                        "goto_speed_unit": (str(m.get("goto_speed_unit", m.get("speed_unit", "m/s"))) if str(m.get("goto_speed_unit", m.get("speed_unit", "m/s"))) in ("m/s", "km/h") else "m/s"),
                        "max_accel_mps2": float(m.get("max_accel_mps2", getattr(self, "max_accel_mps2", 2.0))),
                        "max_decel_mps2": float(m.get("max_decel_mps2", getattr(self, "max_decel_mps2", 2.0))),
                        "max_crossover_mps2": float(m.get("max_crossover_mps2", getattr(self, "max_crossover_mps2", 4.0))),
                        "max_stop_decel_mps2": float(m.get("max_stop_decel_mps2", m.get("max_decel_mps2", getattr(self, "max_decel_mps2", 2.0)))),
                    })
                self.drive_modes = fixed
            self.active_drive_mode = int(cfg.get("active_drive_mode", getattr(self, "active_drive_mode", 0)))
            self.active_drive_mode = 0 if self.active_drive_mode not in (0, 1) else self.active_drive_mode
            if getattr(self, "drive_modes", None):
                am = self.drive_modes[self.active_drive_mode]
                self.max_speed_mps = float(am.get("max_speed_mps", self.max_speed_mps))
                self.goto_speed_mps = float(am.get("max_goto_speed_mps", min(self.max_speed_mps, 1.0)))
                self.max_accel_mps2 = float(am.get("max_accel_mps2", getattr(self, "max_accel_mps2", 2.0)))
                self.max_decel_mps2 = float(am.get("max_decel_mps2", getattr(self, "max_decel_mps2", 2.0)))
                self.max_crossover_mps2 = float(am.get("max_crossover_mps2", getattr(self, "max_crossover_mps2", 4.0)))
                self.max_stop_decel_mps2 = float(am.get("max_stop_decel_mps2", am.get("max_decel_mps2", getattr(self, "max_stop_decel_mps2", getattr(self, "max_decel_mps2", 2.0)))))
        except Exception:
            pass
        self._apply_drive_mode_legacy_name_keys(cfg)
        try:
            if getattr(self, "drive_modes", None) and len(self.drive_modes) >= 2:
                am = self.drive_modes[self.active_drive_mode]
                self.max_speed_mps = float(am.get("max_speed_mps", self.max_speed_mps))
                self.goto_speed_mps = float(am.get("max_goto_speed_mps", min(self.max_speed_mps, 1.0)))
                self.max_accel_mps2 = float(am.get("max_accel_mps2", getattr(self, "max_accel_mps2", 2.0)))
                self.max_decel_mps2 = float(am.get("max_decel_mps2", getattr(self, "max_decel_mps2", 2.0)))
                self.max_crossover_mps2 = float(am.get("max_crossover_mps2", getattr(self, "max_crossover_mps2", 4.0)))
                self.max_stop_decel_mps2 = float(am.get("max_stop_decel_mps2", am.get("max_decel_mps2", getattr(self, "max_stop_decel_mps2", getattr(self, "max_decel_mps2", 2.0)))))
        except Exception:
            pass
        joy_cal = _normalize_joy_cal(cfg.get("joy_cal"))
        controller_state["joy_min"] = float(joy_cal.get("min", -1.0))
        controller_state["joy_center"] = float(joy_cal.get("center", 0.0))
        controller_state["joy_max"] = float(joy_cal.get("max", 1.0))

        self.reverse_joystick = bool(cfg.get("reverse_joystick", False))
        self.reverse_motor = bool(cfg.get("reverse_motor", False))
        self.aux1_action = str(cfg.get("aux1_action", getattr(self, "aux1_action", "")))
        self.aux2_action = str(cfg.get("aux2_action", getattr(self, "aux2_action", "")))
        self.aux3_action = str(cfg.get("aux3_action", getattr(self, "aux3_action", "")))
        self.aux4_action = str(cfg.get("aux4_action", getattr(self, "aux4_action", "")))
        self.w1pts_aux1_action = str(cfg.get("w1pts_aux1_action", getattr(self, "w1pts_aux1_action", "None")))
        self.w1pts_aux2_action = str(cfg.get("w1pts_aux2_action", getattr(self, "w1pts_aux2_action", "None")))
        self.w1pts_aux3_action = str(cfg.get("w1pts_aux3_action", getattr(self, "w1pts_aux3_action", "None")))
        self.w1pts_aux4_action = str(cfg.get("w1pts_aux4_action", getattr(self, "w1pts_aux4_action", "None")))
        aux_map = {
            "Goto Near Limit": "Goto Near",
            "Goto Far Limit": "Goto Far",
            "Reset Ref": "Slip Ref",
            "Start Calibration": "Limit Calibration",
            "Acceleration Mode": "Accel Mode",
            "None": "",
        }
        self.aux1_action = aux_map.get(self.aux1_action, self.aux1_action)
        self.aux2_action = aux_map.get(self.aux2_action, self.aux2_action)
        self.aux3_action = aux_map.get(self.aux3_action, self.aux3_action)
        self.aux4_action = aux_map.get(self.aux4_action, self.aux4_action)
        self.w1pts_aux1_action = aux_map.get(self.w1pts_aux1_action, self.w1pts_aux1_action)
        self.w1pts_aux2_action = aux_map.get(self.w1pts_aux2_action, self.w1pts_aux2_action)
        self.w1pts_aux3_action = aux_map.get(self.w1pts_aux3_action, self.w1pts_aux3_action)
        self.w1pts_aux4_action = aux_map.get(self.w1pts_aux4_action, self.w1pts_aux4_action)
        self.controller_type = cfg.get("controller_type", getattr(self, "controller_type", "HV P2P CTRL Mk1"))
        self.winch_type = cfg.get("winch_type", getattr(self, "winch_type", "HV P2P W1P"))
        try:
            self.winch_units_per_m = float(cfg.get("winch_units_per_m", getattr(self, "winch_units_per_m", 21220.7)))
            # Migrate the old placeholder 1000 units/m value to the EL7-RS2000P + SPA150 starting value.
            if abs(self.winch_units_per_m - 1000.0) < 0.01:
                self.winch_units_per_m = 21220.7
        except Exception:
            self.winch_units_per_m = 21220.7
        self._apply_freed_config(cfg.get("free_d", {}))

        # Load presets if present (support legacy key names too)
        presets = cfg.get("presets")
        if not isinstance(presets, list):
            presets = cfg.get("preset_positions")
        if not isinstance(presets, list):
            presets = cfg.get("preset_positions_m")
        if isinstance(presets, list):
            new_list: list[float | None] = []
            for i in range(PRESET_COUNT):
                if i < len(presets) and presets[i] is not None:
                    try:
                        new_list.append(float(presets[i]))
                    except Exception:
                        new_list.append(None)
                else:
                    new_list.append(None)
            self.preset_positions = new_list


        preset_visible = cfg.get("preset_visible")
        if isinstance(preset_visible, list):
            new_visible: list[bool] = []
            for i in range(PRESET_COUNT):
                new_visible.append(bool(preset_visible[i]) if i < len(preset_visible) else False)
            self.preset_visible = new_visible
        else:
            self.preset_visible = [False] * PRESET_COUNT

        # Load preset names if present
        preset_names = cfg.get("preset_names")
        if isinstance(preset_names, list):
            default_names = [f"P{i+1}" for i in range(PRESET_COUNT)]
            new_names: list[str] = []
            for i in range(PRESET_COUNT):
                if i < len(preset_names) and isinstance(preset_names[i], str) and preset_names[i].strip():
                    new_names.append(preset_names[i].strip())
                else:
                    new_names.append(default_names[i])
            self.preset_names = new_names

        nl = cfg.get("near_limit", {})
        self.state.near_limit.position_m = nl.get("position_m", self.state.near_limit.position_m)
        self.state.near_limit.ramp_mode = nl.get("ramp_mode", self.state.near_limit.ramp_mode)
        self.state.near_limit.ramp_distance_m = nl.get("ramp_distance_m", self.state.near_limit.ramp_distance_m)
        self.state.near_limit.ramp_percentage = nl.get("ramp_percentage", self.state.near_limit.ramp_percentage)

        rp = cfg.get("ref_point", {})
        self.state.ref_point.position_m = rp.get("position_m", self.state.ref_point.position_m)

        fl = cfg.get("far_limit", {})
        self.state.far_limit.position_m = fl.get("position_m", self.state.far_limit.position_m)
        self.state.far_limit.ramp_mode = fl.get("ramp_mode", self.state.far_limit.ramp_mode)
        self.state.far_limit.ramp_distance_m = fl.get("ramp_distance_m", self.state.far_limit.ramp_distance_m)
        self.state.far_limit.ramp_percentage = fl.get("ramp_percentage", self.state.far_limit.ramp_percentage)

        if (
            self.state.near_limit.position_m is not None
            and self.state.far_limit.position_m is not None
        ):
            self.state.total_length_m = max(
                0.1,
                self.state.far_limit.position_m - self.state.near_limit.position_m,
            )

        span = max(0.1, float(getattr(self.state, "total_length_m", 100.0) or 100.0))
        try:
            if self.state.near_limit.ramp_mode == "Percentage" and self.state.near_limit.ramp_percentage is not None:
                self.state.ramp_zone_near = max(0.0, span * (float(self.state.near_limit.ramp_percentage) / 100.0))
            elif self.state.near_limit.ramp_distance_m is not None:
                self.state.ramp_zone_near = max(0.0, float(self.state.near_limit.ramp_distance_m))
        except Exception:
            pass
        try:
            if self.state.far_limit.ramp_mode == "Percentage" and self.state.far_limit.ramp_percentage is not None:
                self.state.ramp_zone_far = max(0.0, span * (float(self.state.far_limit.ramp_percentage) / 100.0))
            elif self.state.far_limit.ramp_distance_m is not None:
                self.state.ramp_zone_far = max(0.0, float(self.state.far_limit.ramp_distance_m))
        except Exception:
            pass

    def _load_config(self):
        cfg_path = getattr(self, "config_path", None)
        if not cfg_path or not os.path.exists(cfg_path):
            return
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                self._apply_config_dict(json.load(f))
        except Exception as exc:
            _app_log(f"[SRVR] Config load failed: {exc}")

    def _save_config(self, path: str | None = None):
        cfg_path = path or getattr(self, "config_path", None)
        if not cfg_path:
            return False
        try:
            cfg = self._to_config_dict()
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
            return True
        except Exception:
            return False

    def on_save_config(self):
        cfg_path = getattr(self, "config_path", None)
        if not cfg_path:
            return False
        return bool(self._save_config(cfg_path))

    def on_save_as_config(self):
        filename = filedialog.asksaveasfilename(
            title="Save Config",
            defaultextension=".json",
            initialfile="config.json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not filename:
            return
        ok = self._save_config(filename)
        if ok:
            messagebox.showinfo("Configuration", f"Configuration backup saved to:\n{filename}")
        else:
            messagebox.showerror("Configuration", f"Failed to save configuration to:\n{filename}")

    def on_load_config_dialog(self):
        filename = filedialog.askopenfilename(
            title="Load Config",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not filename:
            return
        try:
            with open(filename, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            self._apply_config_dict(cfg)
            # Keep the active working config as the local config.json beside the SRVR .py,
            # then overwrite that working config with the imported backup.
            self.config_path = getattr(self, "default_config_path", self.config_path)
            self._save_config(self.config_path)
            try:
                if hasattr(self, "_freed_enabled_var"):
                    self._revert_freed_tab_settings()
            except Exception:
                pass
            self._update_limits_ui()
            self._sync_lens_cal_vars()
            self._update_lens_live_vars()
            self._redraw_progress()
            self._redraw_freed_top_view()
            self._redraw_freed_side_view()
            self._redraw_run_live_section()
            try:
                self.max_speed_button.config(text=self._format_max_speed_text())
                self.battery_button.config(text="Battery Change Mode: ON" if self.battery_change_mode else "Battery Change Mode: OFF")
            except Exception:
                pass
            messagebox.showinfo("Configuration", f"Configuration loaded from:\n{filename}\nand written to:\n{self.config_path}")
        except Exception as e:
            messagebox.showerror("Configuration", f"Failed to load configuration:\n{e}")


    # ---------------- Max speed helpers ----------------

    def _format_max_speed_text(self) -> str:
        kmh = self.max_speed_mps * 3.6
        return f"Maximum Speed: {self.max_speed_mps:0.2f} m/s | {kmh:0.1f} km/h"

    def _active_speed_mode_name(self) -> str:
        if getattr(self, "winch_calibration_mode", False):
            return "Winch Calibration"
        if getattr(self, "system_calibration_mode", False):
            return "Limit Calibration"
        if getattr(self, "not_calibrated_mode", False):
            return "Not Calibrated"
        if getattr(self, "battery_change_mode", False):
            return "Battery Change"
        try:
            modes = getattr(self, "drive_modes", None) or []
            idx = int(getattr(self, "active_drive_mode", 0))
            if 0 <= idx < len(modes):
                name = str(modes[idx].get("name", f"Mode {idx+1}") or "").strip()
                if name:
                    return name
        except Exception:
            pass
        idx = int(getattr(self, "active_drive_mode", 0))
        return f"Mode {idx+1}"

    def _current_max_speed_info(self) -> tuple[float, str]:
        if getattr(self, "winch_calibration_mode", False):
            return self._service_speed_limit_mps(), "Winch Calibration"
        if getattr(self, "system_calibration_mode", False):
            return self._service_speed_limit_mps(), "Limit Calibration"
        if getattr(self, "not_calibrated_mode", False):
            return self._service_speed_limit_mps(), "Not Calibrated"
        if getattr(self, "battery_change_mode", False):
            return self._battery_change_speed_limit_mps(), "Battery Change"
        try:
            return float(getattr(self, "max_speed_mps", 0.0)), self._active_speed_mode_name()
        except Exception:
            return 0.0, self._active_speed_mode_name()


    # ---------------- Callbacks & logic ----------------

    def on_demo_toggled(self):
        self.state.demo_mode = bool(self.demo_var.get())
        if self.state.demo_mode:
            self.demo_button.config(text="Demo Mode: On")
            self._send_velocity_command(0.0, force=True)
        else:
            self.demo_button.config(text="Demo Mode: Off")




    def _rs485_connected(self) -> bool:
        """True only when W1P reports verified Leadshine RS485 feedback/config."""
        try:
            return str(getattr(self, "winch_rs_status", "")).strip().lower() == "connected"
        except Exception:
            return False

    def _w1p_health_state(self, winch_connected_fresh=None) -> str:
        """Return ok/fault/error for the touchscreen W1P node pill.

        error means the W1P Ethernet/status node itself is unavailable. fault
        means the W1P node is alive but its Leadshine RS485/drive interface is
        not healthy. A short stale-packet grace prevents a blocking Modbus
        timeout from making an RS485 fault flash as a W1P node error.
        """
        try:
            now_ts = time.time()
            w_last = float(getattr(self.arduino_status, "last_seen", 0.0) or 0.0)
            age = (now_ts - w_last) if w_last > 0 else 9999.0
            if winch_connected_fresh is None:
                winch_connected_fresh = bool(
                    getattr(self.arduino_status, "connected", False)
                    and w_last > 0
                    and age <= WINCH_STATUS_TIMEOUT_S
                )
            rs_fault = not self._rs485_connected()
            if bool(winch_connected_fresh):
                return "fault" if rs_fault else "ok"
            if rs_fault and w_last > 0 and age <= W1P_RS485_STALE_CLASSIFY_GRACE_S:
                return "fault"
            return "error"
        except Exception:
            return "error"

    def _safety_status_summary(self, cs=None, winch_connected_fresh=None, flags=None):
        """Return (is_red, status_text, sources) for SRVR and both touchscreens.

        v26.06.26.25: every E-stop source combination is shown explicitly.
        Single sources keep the existing wording, e.g. E-Stop SRVR.
        Multiple safety sources show E-Stop | CTRL & SRVR, etc.
        Non-E-stop hardware/interface faults remain explicit faults.
        """
        try:
            sources = list(self._estop_source_list(cs=cs, winch_connected_fresh=winch_connected_fresh, flags=flags))
        except Exception:
            sources = ["SRVR"]

        estop_sources = [x for x in ("CTRL", "SRVR", "W1P") if x in sources]
        fault_sources = [x for x in ("RS485", "ADS1115") if x in sources]

        if estop_sources:
            # Preserve the user's preferred pair orderings where practical.
            pair_names = {
                ("CTRL", "W1P"): "W1P & CTRL",
                ("CTRL", "SRVR"): "CTRL & SRVR",
                ("SRVR", "W1P"): "SRVR & W1P",
                ("CTRL", "SRVR", "W1P"): "CTRL & SRVR & W1P",
            }
            key = tuple(estop_sources)
            if len(estop_sources) == 1:
                return True, f"E-Stop {estop_sources[0]}", sources
            if key in pair_names:
                return True, f"E-Stop | {pair_names[key]}", sources
            return True, "E-Stop | " + " & ".join(estop_sources), sources

        if fault_sources:
            if len(fault_sources) == 2:
                return True, "RS485 & ADS1115 Fault", sources
            if fault_sources[0] == "RS485":
                rs_state = str(getattr(self, "winch_rs_status", "")).strip()
                if rs_state == "Configuration Fault":
                    return True, "RS485 Config Fault", sources
                if rs_state == "Feedback Fault":
                    return True, "RS485 Feedback Fault", sources
            return True, f"{fault_sources[0]} Fault", sources

        if bool(getattr(self.state, "estop_active", False)):
            return True, "E-Stop SRVR", sources
        return False, "", sources

    def _estop_source_list(self, cs=None, winch_connected_fresh=None, flags=None):
        """Return all active safety sources using fail-safe priority."""
        sources = []
        try:
            if cs is None:
                cs = get_controller_status()
            ctrl_connected = bool(cs.get("connected", False))
            if flags is None:
                flags = int(cs.get("flags", 0) or 0)
            if not ctrl_connected:
                sources.append("CTRL")
            else:
                if bool(int(flags) & FLAG_ESTOP_PRESSED) or bool(getattr(self, "_ctrl_estop_active", False)):
                    sources.append("CTRL")
                ads_fault_flag = bool(int(flags) & FLAG_ADS1115_FAULT)
                ads_known_bad = bool(cs.get("ads1115_status_known", False)) and not bool(cs.get("ads1115_connected", False))
                if ads_fault_flag or ads_known_bad:
                    sources.append("ADS1115")
        except Exception:
            sources.append("CTRL")

        try:
            now_ts = time.time()
            w_last = float(getattr(self.arduino_status, "last_seen", 0.0) or 0.0)
            w_age = (now_ts - w_last) if w_last > 0 else 9999.0
            if winch_connected_fresh is None:
                winch_connected_fresh = bool(
                    getattr(self.arduino_status, "connected", False)
                    and w_last > 0
                    and w_age <= WINCH_STATUS_TIMEOUT_S
                )
            # A physical W1P E-stop remains W1P regardless of link freshness.
            if bool(getattr(self, "_w1p_estop_active", False)):
                if "W1P" not in sources:
                    sources.append("W1P")
            elif not bool(winch_connected_fresh):
                # If W1P has just reported an RS485 fault, preserve that source
                # through a short heartbeat stall caused by Modbus timeouts.
                # Only promote it to W1P node loss after the grace expires.
                if (not self._rs485_connected()) and w_last > 0 and w_age <= W1P_RS485_STALE_CLASSIFY_GRACE_S:
                    if "RS485" not in sources:
                        sources.append("RS485")
                elif "W1P" not in sources:
                    sources.append("W1P")
            elif not self._rs485_connected():
                if "RS485" not in sources:
                    sources.append("RS485")
        except Exception:
            if "W1P" not in sources:
                sources.append("W1P")

        if bool(getattr(self, "_srvr_estop_latched", False)):
            sources.append("SRVR")
        try:
            grace_until = float(getattr(self, "_settings_apply_grace_until", 0.0) or 0.0)
            if time.time() < grace_until and not bool(getattr(self, "_ctrl_estop_active", False)) and not bool(getattr(self, "_w1p_estop_active", False)):
                # Suppress link-only/config-apply transients so Apply never flashes
                # Status | E-Stop / E-Stop CTRL while the system remains usable.
                sources = [x for x in sources if x not in ("CTRL", "W1P", "RS485")]
        except Exception:
            pass
        return sources

    def _sync_fail_safe_estop_state(self, cs=None, winch_connected_fresh=None, flags=None):
        """Apply red safety priority with a small clear debounce."""
        try:
            sources = self._estop_source_list(cs=cs, winch_connected_fresh=winch_connected_fresh, flags=flags)
            now_ts = time.time()
            if sources:
                self._ctrl_estop_release_since = 0.0
                if not bool(getattr(self.state, "estop_active", False)):
                    self.state.estop_active = True
                    self._send_stop_command()
                return True, sources
            if bool(getattr(self.state, "estop_active", False)):
                if not hasattr(self, "_ctrl_estop_release_since") or self._ctrl_estop_release_since <= 0.0:
                    self._ctrl_estop_release_since = now_ts
                elif (now_ts - self._ctrl_estop_release_since) >= 0.35:
                    self.state.estop_active = False
            return bool(getattr(self.state, "estop_active", False)), []
        except Exception:
            if not bool(getattr(self.state, "estop_active", False)):
                self.state.estop_active = True
                self._send_stop_command()
            return True, ["SRVR"]

    def _refresh_estop_bar(self):
        """Update the main SRVR status bar with explicit safety-fault names."""
        try:
            is_red, red_text, _sources = self._safety_status_summary()
            if is_red:
                bg = "#802020"
                text = f"Status | {red_text}"
            elif bool(getattr(self, "winch_no_motion_feedback_fault", False)):
                bg = "#802020"
                text = "Status | Drive No Motion"
            elif bool(getattr(self, "battery_change_mode", False)):
                bg = "#8a6500"
                text = "Status | Battery Change"
            elif bool(getattr(self, "system_calibration_mode", False)):
                bg = "#8a6500"
                text = "Status | Calibration"
            elif bool(getattr(self, "not_calibrated_mode", False)):
                bg = "#8a6500"
                text = "Status | Un-Calibrated"
            else:
                bg = "#17632f"
                if bool(getattr(self, "winch_sw_srvon", False)) or bool(getattr(self, "winch_sw_srvon_ready", False)) or bool(getattr(self, "winch_srvon_ready", False)):
                    text = "Status | Active"
                else:
                    text = "Status | Active"

            cached = getattr(self, "_estop_bar_cached", None)
            if cached == (text, bg):
                return
            self._estop_bar_cached = (text, bg)
            if hasattr(self, "estop_frame") and self.estop_frame is not None:
                self.estop_frame.config(bg=bg, height=34)
            if hasattr(self, "estop_label") and self.estop_label is not None:
                self.estop_label.config(bg=bg, text=text, font=("Segoe UI", 15, "bold"), wraplength=0)
        except Exception:
            pass

    def _toggle_estop(self):
        """Internal helper to toggle SRVR E-Stop latch + UI + STOP command."""
        self.state.estop_active = not self.state.estop_active
        self._srvr_estop_latched = bool(self.state.estop_active)
        if self.state.estop_active:
            self._send_stop_command()
            try:
                self.arduino_client.send("SW_SRVON 0")
            except Exception:
                pass
        else:
            # Restore software SRV-ON after the latch is cleared. W1P still remains stopped
            # until a fresh, valid velocity command is issued.
            self._send_stop_command()
            try:
                self.arduino_client.send("SW_SRVON 1")
            except Exception:
                pass
        self._refresh_estop_bar()


    def _start_goto_target(self, target_m: float, label: str | None = None):
        try:
            target = self._clamp_goto_target_inside_limits(float(target_m))
        except Exception:
            return
        self.goto_target_m = target
        try:
            pos = float(getattr(self.state, "pos_m", target) or target)
            self._goto_last_error_m = target - pos
            self._goto_initial_direction = 1.0 if (target - pos) >= 0 else -1.0
            self._goto_approach_dir = self._goto_initial_direction
        except Exception:
            self._goto_last_error_m = 0.0
            self._goto_initial_direction = 0.0
            self._goto_approach_dir = 0.0
        self._goto_settle_since = 0.0
        self._goto_cancelled_by_joystick = False
        self._goto_stop_zone = False
        if label:
            self._set_status(label)

    def _cancel_goto_for_manual(self):
        if getattr(self, "goto_target_m", None) is not None:
            self.goto_target_m = None
            self._goto_settle_since = 0.0
            self._goto_cancelled_by_joystick = True
            self._goto_stop_zone = False
            self._goto_approach_dir = 0.0
            self._send_velocity_command(0.0, force=True)
            self._set_status("Goto cancelled: manual joystick")

    def _cancel_motion(self):
        """Cancel any current motion (e.g. preset Goto) without latching E-Stop.

        This clears goto target, sets commanded speed to zero, and sends a STOP
        to the winch, but leaves estop_active unchanged.
        """
        # Clear any active goto target
        self.goto_target_m = None
        self._goto_stop_zone = False
        self._goto_approach_dir = 0.0
        # Zero current commanded speed
        self.current_speed_mps = 0.0
        self.last_winch_output = 0.0
        # Send a hard STOP to the winch
        self._send_stop_command()

    def _confirm_action(self, title: str, message: str) -> bool:
        """Safety confirmation popup."""
        try:
            return messagebox.askyesno(title, message, parent=self.root)
        except Exception:
            # If parent is not available for any reason, fall back
            return messagebox.askyesno(title, message)

    def on_estop_clicked(self, event=None):
        # Mouse click on the bar/label
        self._toggle_estop()



    def on_goto_reference(self, require_popup: bool = True):
        ref_pos = self.state.ref_point.position_m
        pos = self.state.pos_m
        if ref_pos is None:
            messagebox.showwarning(
                "Goto Reference",
                "Reference Point is not set yet.",
            )
            return

        if pos is None:
            base = self.state.near_limit.position_m
            if base is None:
                base = 0.0
            self.state.pos_m = float(base)

        if require_popup and not self._confirm_action("Goto Reference", "Goto Reference?\n\nThis will move the winch."):
            return

        self._start_goto_target(float(ref_pos), f"Goto Reference {float(ref_pos):0.2f} m")

    def on_goto_limit(self, lp: LimitPoint, require_popup: bool = True):
        if lp.position_m is None:
            messagebox.showwarning(
                "Goto Limit",
                f"{lp.name} does not have a position yet.\\nSet the point first.",
            )
            return

        pos = self.state.pos_m
        if pos is None:
            self.state.pos_m = float(lp.position_m)

        if not self._confirm_action("Goto Limit", f"Goto {lp.name}?\n\nThis will move the winch."):
            return

        self._start_goto_target(float(lp.position_m), f"Goto {lp.name} {float(lp.position_m):0.2f} m")

    def on_set_point(self, lp: LimitPoint, require_popup: bool = True):
        if require_popup and not self._confirm_action("Set Point", f"Set {lp.name} to the current position?"):
            return

        pos = self.state.pos_m
        if pos is None:
            pos = (
                (self.state.near_limit.position_m or 0.0)
                + self.state.total_length_m / 2.0
            )
        lp.position_m = float(pos)
        self._update_limits_ui()
        self._redraw_progress()
        self._sync_limits_to_winch()
        self._save_config()

    def on_set_slip(self, lp: LimitPoint, require_popup: bool = True, show_info: bool = True):
        if require_popup and not self._confirm_action("Set Slip", f"Set Slip for {lp.name} using the current position?"):
            return

        if lp.position_m is None:
            messagebox.showwarning(
                "Set Slip",
                f"{lp.name} does not have a position yet.\\n"
                f"Set the point first, then Set Slip.",
            )
            return

        limit_pos = float(lp.position_m)
        old_pos = self.state.pos_m
        if old_pos is None:
            slip_correction = 0.0
        else:
            slip_correction = limit_pos - old_pos

        self.state.pos_m = limit_pos
        lp.slip_offset_m = slip_correction

        try:
            self._sync_winch_position(limit_pos)
        except Exception:
            pass

        self._update_limits_ui()
        self._redraw_progress()

        nl = self.state.near_limit.position_m
        fl = self.state.far_limit.position_m
        try:
            if nl is not None and fl is not None and float(nl) <= float(self.state.pos_m) <= float(fl):
                if getattr(self, "not_calibrated_mode", False):
                    self._exit_not_calibrated_mode()
        except Exception:
            pass

        if show_info:
            messagebox.showinfo(
                "Set Slip",
                f"""Position re-aligned to {lp.name} at {limit_pos:0.2f} m.
Slip offset by {abs(slip_correction):0.2f} m.""",
            )
        else:
            self._set_status(f"Slip aligned to {lp.name} at {limit_pos:0.2f} m")

    def on_set_ramping(self, lp: LimitPoint):
        if not (lp.name.startswith("Near") or lp.name.startswith("Far")):
            return

        popup = tk.Toplevel(self.root)
        popup.title("Ramping")
        popup.transient(self.root)
        popup.grab_set()
        popup.configure(bg="#202020")

        tk.Label(
            popup,
            text=f"Ramping for {lp.name}",
            fg="white",
            bg="#202020",
            font=FONT_SMALL_BOLD,
        ).grid(row=0, column=0, columnspan=2, padx=10, pady=(10, 4), sticky="w")

        tk.Label(
            popup,
            text="Mode:",
            fg="white",
            bg="#202020",
            font=FONT_SMALL,
        ).grid(row=1, column=0, padx=10, pady=4, sticky="e")

        mode_var = tk.StringVar(value=lp.ramp_mode or "Distance")
        mode_menu = ttk.Combobox(
            popup,
            textvariable=mode_var,
            values=["Distance (m)", "Percentage (%)"],
            state="readonly",
            width=16,
        )
        mode_menu.grid(row=1, column=1, padx=10, pady=4, sticky="w")

        tk.Label(
            popup,
            text="Value:",
            fg="white",
            bg="#202020",
            font=FONT_SMALL,
        ).grid(row=2, column=0, padx=10, pady=4, sticky="e")

        value_entry = tk.Entry(popup, width=7)
        value_entry.grid(row=2, column=1, padx=10, pady=4, sticky="w")

        if lp.ramp_mode == "Percentage" and lp.ramp_percentage is not None:
            value_entry.insert(0, f"{lp.ramp_percentage:.1f}")
        elif lp.ramp_distance_m is not None:
            value_entry.insert(0, f"{lp.ramp_distance_m:.2f}")
        else:
            value_entry.insert(0, "5.0")

        def on_ok():
            try:
                val = float(value_entry.get())
            except ValueError:
                popup.destroy()
                return

            if val <= 0:
                popup.destroy()
                return

            nl_pos = self.state.near_limit.position_m or 0.0
            fl_pos = self.state.far_limit.position_m or self.state.total_length_m
            span = max(0.1, fl_pos - nl_pos)

            selected = mode_var.get()
            ramp_distance = None
            ramp_mode = "Distance"
            ramp_percentage = None

            if selected.startswith("Percentage"):
                ramp_mode = "Percentage"
                ramp_percentage = val
                ramp_distance = span * (val / 100.0)
            else:
                ramp_mode = "Distance"
                ramp_distance = val

            if ramp_distance <= 0:
                popup.destroy()
                return

            lp.ramp_distance_m = ramp_distance
            lp.ramp_mode = ramp_mode
            lp.ramp_percentage = ramp_percentage

            if lp.name.startswith("Near"):
                self.state.ramp_zone_near = ramp_distance
            else:
                self.state.ramp_zone_far = ramp_distance

            self._update_limits_ui()
            self._redraw_progress()
            self._save_config()
            popup.destroy()

        btn_frame = tk.Frame(popup, bg="#202020")
        btn_frame.grid(row=3, column=0, columnspan=2, pady=(6, 10))

        ttk.Button(btn_frame, text="OK", width=8, command=on_ok).pack(
            side="left", padx=4
        )
        ttk.Button(btn_frame, text="Cancel", width=8, command=popup.destroy).pack(
            side="left", padx=4
        )



    def on_winch_settings(self):
        popup = tk.Toplevel(self.root)
        popup.title("Winch Settings")
        popup.grab_set()
        popup.configure(bg="#222222")

        label_font = ("Segoe UI", 9)
        field_width = 20

        tk.Label(
            popup,
            text="Winch Settings",
            fg="white",
            bg="#222222",
            font=FONT_SMALL_BOLD,
        ).grid(row=0, column=0, columnspan=2, pady=(4, 2), padx=10, sticky="w")

        # Row 1: Winch selector
        tk.Label(
            popup,
            text="Winch:",
            fg="white",
            bg="#222222",
            font=label_font,
        ).grid(row=1, column=0, sticky="e", padx=10, pady=4)

        winch_var = tk.StringVar(value=getattr(self, "winch_type", "HV P2P W1P"))
        winch_menu = ttk.Combobox(
            popup,
            textvariable=winch_var,
            values=["HV P2P W1P", "HV P2P W3P"],
            state="readonly",
            width=field_width,
        )
        winch_menu.grid(row=1, column=1, sticky="w", padx=10, pady=4)

        # Row 2: IP Address
        tk.Label(
            popup,
            text="IP Address:",
            fg="white",
            bg="#222222",
            font=label_font,
        ).grid(row=2, column=0, sticky="e", padx=10, pady=4)
        ip_var = tk.StringVar(value=self.winch_host)
        ip_entry = tk.Entry(popup, textvariable=ip_var, width=field_width)
        ip_entry.grid(row=2, column=1, sticky="w", padx=10, pady=4)

        # Row 3: Direction (Normal / Inverted)
        tk.Label(
            popup,
            text="Direction:",
            fg="white",
            bg="#222222",
            font=label_font,
        ).grid(row=3, column=0, sticky="e", padx=10, pady=4)

        direction_var = tk.StringVar(
            value="Inverted" if self.reverse_motor else "Normal"
        )
        dir_menu = ttk.Combobox(
            popup,
            textvariable=direction_var,
            values=["Normal", "Inverted"],
            state="readonly",
            width=field_width,
        )
        dir_menu.grid(row=3, column=1, sticky="w", padx=10, pady=4)

        # Row 4: Output Value (read-only)
        tk.Label(
            popup,
            text="Output Value:",
            fg="white",
            bg="#222222",
            font=label_font,
        ).grid(row=4, column=0, sticky="e", padx=10, pady=4)

        out_var = tk.StringVar(value=f"{self.last_winch_output:.2f}")
        out_entry = tk.Entry(
            popup,
            textvariable=out_var,
            width=field_width,
            state="readonly",
        )
        out_entry.grid(row=4, column=1, sticky="w", padx=10, pady=4)

        def refresh_values():
            # keep output value live while popup is open
            try:
                out_var.set(f"{self.last_winch_output:.2f}")
            except Exception:
                pass
            if popup.winfo_exists():
                popup.after(100, refresh_values)

        def on_ok():
            try:
                self.winch_type = winch_var.get().strip() or "HV P2P W1P"
                self.winch_host = ip_var.get().strip()
                self.reverse_motor = (direction_var.get() == "Inverted")
                # Reconfigure client with same port but new host
                self.arduino_client.reconfigure(self.winch_host, self.winch_port)
                try:
                    self.arduino_client.send(f"SET_MOTOR_REVERSE {1 if bool(getattr(self, 'reverse_motor', False)) else 0}")
                except Exception:
                    pass
                self._save_config()
                popup.destroy()
                messagebox.showinfo(
                    "Winch Connection",
                    f"Winch settings updated.\nWinch: {self.winch_type}\nIP: {self.winch_host}",
                )
            except Exception as e:
                messagebox.showerror("Winch Connection", f"Invalid settings: {e}")

        def on_cancel():
            popup.destroy()

        btn_frame = tk.Frame(popup, bg="#222222")
        btn_frame.grid(row=5, column=0, columnspan=2, pady=(8, 10))
        ttk.Button(btn_frame, text="OK", command=on_ok, width=7).pack(
            side="left", padx=5
        )
        ttk.Button(btn_frame, text="Cancel", command=on_cancel, width=7).pack(
            side="left", padx=5
        )

        # start live refresh loop
        popup.after(100, refresh_values)

    def on_controller_settings(self):
        popup = tk.Toplevel(self.root)
        popup.title("Controller Settings")
        popup.grab_set()
        popup.configure(bg="#222222")

        label_font = ("Segoe UI", 9)
        field_width = 20

        tk.Label(
            popup,
            text="Controller Settings",
            fg="white",
            bg="#222222",
            font=FONT_SMALL_BOLD,
        ).grid(row=0, column=0, columnspan=2, pady=(4, 2), padx=10, sticky="w")

        # Row 1: Controller selector
        tk.Label(
            popup,
            text="Controller:",
            fg="white",
            bg="#222222",
            font=label_font,
        ).grid(row=1, column=0, sticky="e", padx=10, pady=4)

        ctrl_var = tk.StringVar(value=getattr(self, "controller_type", "HV P2P CTRL Mk1"))
        ctrl_menu = ttk.Combobox(
            popup,
            textvariable=ctrl_var,
            values=["HV P2P CTRL Mk1"],
            state="readonly",
            width=field_width,
        )
        ctrl_menu.grid(row=1, column=1, sticky="w", padx=10, pady=4)

        # Row 2: IP Address
        tk.Label(
            popup,
            text="IP Address:",
            fg="white",
            bg="#222222",
            font=label_font,
        ).grid(row=2, column=0, sticky="e", padx=10, pady=4)
        ip_var = tk.StringVar(value=self.controller_ip_ref)
        ip_entry = tk.Entry(popup, textvariable=ip_var, width=field_width)
        ip_entry.grid(row=2, column=1, sticky="w", padx=10, pady=4)

        # Row 3: Direction (Normal / Inverted)
        tk.Label(
            popup,
            text="Direction:",
            fg="white",
            bg="#222222",
            font=label_font,
        ).grid(row=3, column=0, sticky="e", padx=10, pady=4)

        direction_var = tk.StringVar(
            value="Inverted" if self.reverse_joystick else "Normal"
        )
        dir_menu = ttk.Combobox(
            popup,
            textvariable=direction_var,
            values=["Normal", "Inverted"],
            state="readonly",
            width=field_width,
        )
        dir_menu.grid(row=3, column=1, sticky="w", padx=10, pady=4)

        # Row 4: Input Value (read-only)
        tk.Label(
            popup,
            text="Input Value:",
            fg="white",
            bg="#222222",
            font=label_font,
        ).grid(row=4, column=0, sticky="e", padx=10, pady=4)

        in_var = tk.StringVar(value=f"{self.last_controller_value:+.3f}%")
        in_entry = tk.Entry(
            popup,
            textvariable=in_var,
            width=field_width,
            state="readonly",
        )
        in_entry.grid(row=4, column=1, sticky="w", padx=10, pady=4)

        def refresh_values():
            # keep controller value live while popup is open
            try:
                in_var.set(f"{self.last_controller_value:+.3f}%")
            except Exception:
                pass
            if popup.winfo_exists():
                popup.after(100, refresh_values)

        def on_ok():
            try:
                self.controller_type = ctrl_var.get().strip() or "HV P2P CTRL Mk1"
                self._apply_controller_ip_change(ip_var.get().strip())
                self.reverse_joystick = (direction_var.get() == "Inverted")
                self._save_config()
                popup.destroy()
                messagebox.showinfo(
                    "Controller Arduino",
                    f"Controller settings updated.\nController: {self.controller_type}\nIP: {self.controller_ip_ref}",
                )
            except Exception as e:
                messagebox.showerror("Controller Arduino", f"Invalid settings: {e}")

        def on_cancel():
            popup.destroy()

        btn_frame = tk.Frame(popup, bg="#222222")
        btn_frame.grid(row=5, column=0, columnspan=2, pady=(8, 10))
        ttk.Button(btn_frame, text="OK", command=on_ok, width=7).pack(
            side="left", padx=5
        )
        ttk.Button(btn_frame, text="Cancel", command=on_cancel, width=7).pack(
            side="left", padx=5
        )

        # start live refresh loop
        popup.after(100, refresh_values)
    def _update_limits_ui(self):
        for lp in [self.state.near_limit, self.state.ref_point, self.state.far_limit]:
            label_name = f"{lp.name.replace(' ', '_').lower()}_label"
            lbl = getattr(self, label_name, None)
            if lbl is not None:
                val = self._limit_display_position_m(lp)
                lbl.config(text=f"{val:07.2f} m")

    def _update_limit_state(self):
        pos = self.state.pos_m
        nl = self.state.near_limit.position_m
        fl = self.state.far_limit.position_m
        if pos is None or nl is None or fl is None:
            self.state.limit_reason = None
            return

        if pos <= nl:
            self.state.limit_reason = "At Near Limit"
        elif pos >= fl:
            self.state.limit_reason = "At Far Limit"
        else:
            self.state.limit_reason = None

    def _redraw_progress(self):
        c = getattr(self, "progress_canvas", None)
        if c is None:
            return
        c.delete("all")
        w = c.winfo_width()
        h = c.winfo_height()
        if w <= 4 or h <= 4:
            return

        padding = 50
        bar_left = padding
        bar_right = w - padding
        # Keep the progress bar graphic height locked, but move the whole
        # graphic/text block aligned so the first text row keeps about 1.5x top padding
        # inside the 150 px progress section.
        bar_height = h * 0.32
        bar_top = h * 0.28
        bar_bottom = bar_top + bar_height

        c.create_rectangle(
            bar_left, bar_top, bar_right, bar_bottom, fill="#333333", outline="#555555"
        )

        nl_pos = (
            self.state.near_limit.position_m
            if self.state.near_limit.position_m is not None
            else 0.0
        )
        fl_pos = (
            self.state.far_limit.position_m
            if self.state.far_limit.position_m is not None
            else self.state.total_length_m
        )
        span = max(0.1, fl_pos - nl_pos)

        if self.state.near_limit.ramp_mode == "Percentage" and self.state.near_limit.ramp_percentage is not None:
            near_ramp_dist = span * (float(self.state.near_limit.ramp_percentage) / 100.0)
        else:
            near_ramp_dist = self.state.near_limit.ramp_distance_m if self.state.near_limit.ramp_distance_m is not None else self.state.ramp_zone_near

        if self.state.far_limit.ramp_mode == "Percentage" and self.state.far_limit.ramp_percentage is not None:
            far_ramp_dist = span * (float(self.state.far_limit.ramp_percentage) / 100.0)
        else:
            far_ramp_dist = self.state.far_limit.ramp_distance_m if self.state.far_limit.ramp_distance_m is not None else self.state.ramp_zone_far

        ramp_title_y = bar_top - 18
        ramp_value_y = bar_top - 6
        bottom_label_y = bar_bottom + 4
        bottom_value_y = bar_bottom + 20

        font_main = ("Segoe UI", 10)
        font_bold = ("Segoe UI", 10, "bold")

        def x_for_pos(pos_m: float) -> float:
            rel = (pos_m - nl_pos) / span
            rel = max(0.0, min(1.0, rel))
            return bar_left + rel * (bar_right - bar_left)

        # Ramping zones
        # Near
        if near_ramp_dist > 0:
            near_start = nl_pos + near_ramp_dist
            x_nl = x_for_pos(nl_pos)
            x_nr = x_for_pos(near_start)
            x1, x2 = sorted((x_nl, x_nr))
            c.create_rectangle(x1, bar_top, x2, bar_bottom, fill="#cc8a2b", outline="")

            lp = self.state.near_limit
            if lp.ramp_mode == "Percentage" and lp.ramp_percentage is not None:
                label_text = f"{lp.ramp_percentage:.1f} %"
            else:
                label_text = f"{near_ramp_dist:.2f} m"
            cx = (x_nl + x_nr) / 2.0

            c.create_text(
                cx,
                ramp_title_y,
                text="Ramping",
                anchor="s",
                fill="#ffcc80",
                font=font_bold,
            )
            c.create_text(
                cx,
                ramp_value_y,
                text=label_text,
                anchor="s",
                fill="#ffcc80",
                font=font_main,
            )

        # Far
        if far_ramp_dist > 0:
            far_start = fl_pos - far_ramp_dist
            x_fl = x_for_pos(fl_pos)
            x_fr = x_for_pos(far_start)
            x1, x2 = sorted((x_fl, x_fr))
            c.create_rectangle(x1, bar_top, x2, bar_bottom, fill="#cc8a2b", outline="")

            lp = self.state.far_limit
            if lp.ramp_mode == "Percentage" and lp.ramp_percentage is not None:
                label_text = f"{lp.ramp_percentage:.1f} %"
            else:
                label_text = f"{far_ramp_dist:.2f} m"
            cx = (x_fl + x_fr) / 2.0

            c.create_text(
                cx,
                ramp_title_y,
                text="Ramping",
                anchor="s",
                fill="#ffcc80",
                font=font_bold,
            )
            c.create_text(
                cx,
                ramp_value_y,
                text=label_text,
                anchor="s",
                fill="#ffcc80",
                font=font_main,
            )

        # Preset markers
        visible_indices = [i for i in range(min(PRESET_COUNT, len(self.preset_positions), len(self.preset_visible))) if self.preset_positions[i] is not None and bool(self.preset_visible[i])]
        marker_top_y_a = max(16, int(bar_top - 34))
        marker_top_y_b = max(30, int(bar_top - 20))
        marker_triangle_tip = max(20, int(bar_top - 2))
        for vis_order, idx in enumerate(visible_indices):
            preset_pos = self._preset_absolute_position_m(idx)
            if preset_pos is None:
                continue
            x_preset = x_for_pos(float(preset_pos))
            marker_color = "#9ad0ff"
            c.create_line(
                x_preset,
                bar_top,
                x_preset,
                bar_bottom,
                fill=marker_color,
                width=1,
                dash=(3, 3),
            )
            label_y = marker_top_y_a if (vis_order % 2 == 0) else marker_top_y_b
            c.create_polygon(
                x_preset - 5, marker_triangle_tip - 8,
                x_preset + 5, marker_triangle_tip - 8,
                x_preset, marker_triangle_tip,
                fill=marker_color,
                outline="",
            )
            preset_name = self.preset_names[idx] if idx < len(self.preset_names) else f"P{idx+1}"
            c.create_text(
                x_preset,
                label_y,
                text=preset_name,
                anchor="s",
                fill=marker_color,
                font=font_main,
            )

        # Current position
        pos_raw = self._display_abs_position_m()
        if pos_raw is None:
            pos_draw = nl_pos
        else:
            pos_draw = pos_raw

        x_pos = x_for_pos(pos_draw)
        mid_y = (bar_top + bar_bottom) / 2
        color = "#2e8cff"
        if pos_draw <= nl_pos or pos_draw >= fl_pos:
            color = "#d32f2f"
        else:
            in_near_ramp = near_ramp_dist > 0 and pos_draw <= (nl_pos + near_ramp_dist)
            in_far_ramp = far_ramp_dist > 0 and pos_draw >= (fl_pos - far_ramp_dist)
            if in_near_ramp or in_far_ramp:
                color = "#ffa726"
        c.create_rectangle(
            bar_left,
            mid_y - 3,
            x_pos,
            mid_y + 3,
            fill=color,
            outline="",
        )

        c.create_line(
            x_pos, bar_top - 6, x_pos, bar_bottom + 6, fill="white", width=2
        )
        c.create_oval(
            x_pos - 6, mid_y - 6, x_pos + 6, mid_y + 6,
            fill="white", outline=color, width=2
        )
        c.create_text(
            x_pos,
            mid_y - 10,
            text="Skate",
            anchor="s",
            fill="white",
            font=font_main,
        )

        x_nl = x_for_pos(nl_pos)
        x_fl = x_for_pos(fl_pos)
        x_center = (bar_left + bar_right) / 2.0

        c.create_line(x_nl, bar_top, x_nl, bar_bottom, fill="#ffffff", width=2)
        c.create_line(x_fl, bar_top, x_fl, bar_bottom, fill="#ffffff", width=2)

        # Reference marker
        if self.state.ref_point.position_m is not None:
            x_ref = x_for_pos(self.state.ref_point.position_m)
            c.create_line(x_ref, bar_top, x_ref, bar_bottom, fill="#00bfff", width=2)

            ref_pos = self.state.ref_point.position_m or 0.0

            c.create_text(
                x_ref,
                bar_top - 18,
                text="Reference",
                anchor="s",
                fill="#00bfff",
                font=font_bold,
            )
            c.create_text(
                x_ref,
                bar_top - 6,
                text=f"{ref_pos:07.2f} m",
                anchor="s",
                fill="#00bfff",
                font=font_main,
            )

        # Bottom labels and distances

        d_near = max(0.0, pos_draw - nl_pos)
        d_far = max(0.0, fl_pos - pos_draw)

        try:
            max_mps, max_mode_name = self._current_max_speed_info()
        except Exception:
            max_mps, max_mode_name = 0.0, "Mode 1"
        max_kmh = max_mps * 3.6

        try:
            v_mps = abs(float(getattr(self, "current_speed_mps", 0.0)))
        except Exception:
            v_mps = 0.0
        v_kmh = v_mps * 3.6

        normal_row_spacing = bottom_value_y - bottom_label_y

        # Use the centre Current Speed rows as the master reference so
        # To Near / To Far match the same font rows and spacing.
        row1_y = bottom_label_y
        row2_y = bottom_value_y
        row3_y = row2_y + int(round(normal_row_spacing * 1.5))
        row4_y = row3_y + normal_row_spacing

        c.create_text(
            bar_left,
            row1_y,
            text="To Near",
            anchor="nw",
            fill="white",
            font=font_bold,
        )

        c.create_text(
            bar_right,
            row1_y,
            text="To Far",
            anchor="ne",
            fill="white",
            font=font_bold,
        )

        c.create_text(
            bar_left,
            row2_y,
            text=f"{d_near:07.2f} m",
            anchor="nw",
            fill="#dddddd",
            font=font_main,
        )

        c.create_text(
            bar_right,
            row2_y,
            text=f"{d_far:07.2f} m",
            anchor="ne",
            fill="#dddddd",
            font=font_main,
        )

        c.create_text(
            x_center,
            row1_y,
            text="Current Speed",
            anchor="n",
            fill="white",
            font=font_bold,
        )
        c.create_text(
            x_center,
            row2_y,
            text=f"{v_mps:0.2f} m/s | {v_kmh:0.2f} km/h",
            anchor="n",
            fill="#dddddd",
            font=font_main,
        )
        c.create_text(
            x_center,
            row3_y,
            text="Maximum Speed",
            anchor="n",
            fill="white",
            font=font_bold,
        )
        c.create_text(
            x_center,
            row4_y,
            text=f"{max_mps:0.2f} m/s | {max_kmh:0.2f} km/h | {max_mode_name}",
            anchor="n",
            fill="#dddddd",
            font=font_main,
        )

    # ---------------- Limit sync & commands ----------------

    def _sync_motion_profile_to_winch(self, force: bool = False):
        """Synchronise all motion-profile settings to W1P.

        Dynamic mode means joystick position is a requested constant cable speed.
        W1P still obeys Max Accel / De-Accel / Cross-Over / Stop De-Accel, but
        it uses feedback to keep the velocity command tied to the actual winch
        speed rather than behaving like a raw throttle pedal.

        Power mode is the simpler throttle-style profile: joystick input behaves
        more like applied power/open command, so the operator manages the feel.

        Speed mode is the closed speed-hold profile: joystick position is the
        requested cable speed, with feedback correction to hold that speed.
        """
        try:
            mode_ui = self._normalise_accel_type(getattr(self, "accel_type", "Dynamic"))
            mode_cmd = self._accel_type_command(mode_ui)
            cfg = (
                round(float(getattr(self, "max_accel_mps2", 2.0)), 3),
                round(float(getattr(self, "max_decel_mps2", 2.0)), 3),
                round(float(getattr(self, "max_crossover_mps2", 4.0)), 3),
                round(float(getattr(self, "max_stop_decel_mps2", getattr(self, "max_decel_mps2", 2.0))), 3),
                mode_cmd,
            )
            if (not force) and cfg == getattr(self, "_last_winch_motion_cfg", None):
                return
            self._last_winch_motion_cfg = cfg
            self.accel_type = mode_ui
            display_mode = self._display_accel_type(mode_ui)
            try:
                if hasattr(self, "_drive_accel_type") and isinstance(self._drive_accel_type, tk.StringVar):
                    self._drive_accel_type.set(display_mode)
                if hasattr(self, "run_accel_mode_var"):
                    self.run_accel_mode_var.set(display_mode)
            except Exception:
                pass
            self.arduino_client.send(f"SET_ACCEL {cfg[0]:.3f}")
            self.arduino_client.send(f"SET_DECEL {cfg[1]:.3f}")
            self.arduino_client.send(f"SET_CROSSOVER {cfg[2]:.3f}")
            self.arduino_client.send(f"SET_STOP_DECEL {cfg[3]:.3f}")
            self.arduino_client.send(f"SET_ACCEL_MODE {cfg[4]}")
        except Exception:
            pass

    def _sync_limits_to_winch(self):
        nl = self.state.near_limit.position_m or 0.0
        fl = self.state.far_limit.position_m or self.state.total_length_m
        span = max(0.1, fl - nl)

        self.arduino_client.send(f"SET_SPAN {span:.3f}")
        self.arduino_client.send(f"SET_LIMIT_NEAR {nl:.3f}")
        self.arduino_client.send(f"SET_LIMIT_FAR {fl:.3f}")
        try:
            self.arduino_client.send(f"SET_UNITS_PER_M {float(self.winch_units_per_m):.1f}")
            self.arduino_client.send(f"SET_MOTOR_REVERSE {1 if bool(getattr(self, 'reverse_motor', False)) else 0}")
            self._sync_motion_profile_to_winch(force=True)
        except Exception:
            pass
        self._sync_service_mode_to_winch()

        self.state.total_length_m = span

    def _sync_service_mode_to_winch(self):
        try:
            enabled = 1 if self._service_override_active() else 0
            self.arduino_client.send(f"SERVICE_MODE {enabled}")
        except Exception:
            pass

    def _battery_change_speed_limit_mps(self) -> float:
        return self._service_speed_limit_mps()

    def _limit_velocity_for_hard_limits(self, pos_m: float, requested_vel_mps: float, nl_pos: float, fl_pos: float) -> float:
        """Clamp a requested velocity so the winch starts braking before a hard limit.

        Earlier builds only prevented a single control-loop step from crossing
        Near/Far.  That was not enough at speed because the drive still needs
        real braking distance.  This version uses the active Stop De-Accel value
        as a stopping-distance limit: v <= sqrt(2*a*d), with a small guard band
        for network/drive latency.  The same helper is used by manual joystick
        motion and preset/limit Goto moves.
        """
        try:
            pos = float(pos_m)
            req = float(requested_vel_mps)
            nl = float(nl_pos)
            fl = float(fl_pos)
        except Exception:
            return 0.0

        if abs(req) < 1e-9:
            return 0.0
        if fl < nl:
            nl, fl = fl, nl

        try:
            stop_decel = max(0.10, float(getattr(self, "max_stop_decel_mps2", getattr(self, "max_decel_mps2", 2.0)) or 2.0))
        except Exception:
            stop_decel = 2.0
        try:
            fb_speed = abs(float(getattr(self, "current_speed_mps", 0.0) or 0.0))
        except Exception:
            fb_speed = abs(req)

        # Guard covers one or two display/control packets plus a small fixed margin.
        # It deliberately grows with speed so high-speed approaches begin tapering
        # earlier rather than reaching the limit then reacting.
        guard_m = max(0.03, min(0.35, 0.03 + 0.12 * fb_speed))

        def _ramp_distance(which: str) -> float:
            try:
                lp = self.state.near_limit if which == "near" else self.state.far_limit
                if getattr(lp, 'ramp_mode', 'Distance') == 'Percentage' and getattr(lp, 'ramp_percentage', None) is not None:
                    return max(0.0, (fl - nl) * (float(lp.ramp_percentage) / 100.0))
                if getattr(lp, 'ramp_distance_m', None) is not None:
                    return max(0.0, float(lp.ramp_distance_m))
                return max(0.0, float(getattr(self.state, 'ramp_zone_near' if which == "near" else 'ramp_zone_far', 0.0) or 0.0))
            except Exception:
                return max(0.0, float(getattr(self.state, 'ramp_zone_near' if which == "near" else 'ramp_zone_far', 0.0) or 0.0))

        if req < 0.0:
            remaining = pos - nl
            if remaining <= guard_m:
                return 0.0
            effective = max(0.0, remaining - guard_m)
            allowed = math.sqrt(max(0.0, 2.0 * stop_decel * effective))
            near_ramp = _ramp_distance("near")
            if near_ramp > 1e-9 and pos < (nl + near_ramp):
                frac = max(0.0, min(1.0, remaining / near_ramp))
                allowed = min(allowed, abs(req) * frac)
            return -min(abs(req), allowed)

        if req > 0.0:
            remaining = fl - pos
            if remaining <= guard_m:
                return 0.0
            effective = max(0.0, remaining - guard_m)
            allowed = math.sqrt(max(0.0, 2.0 * stop_decel * effective))
            far_ramp = _ramp_distance("far")
            if far_ramp > 1e-9 and pos > (fl - far_ramp):
                frac = max(0.0, min(1.0, remaining / far_ramp))
                allowed = min(allowed, abs(req) * frac)
            return min(abs(req), allowed)

        return 0.0

    def _clamp_goto_target_inside_limits(self, target_m: float) -> float:
        """Keep Goto Near/Far a few cm inside the hard limits during normal mode."""
        try:
            target = float(target_m)
            if self._service_override_active():
                return target
            nl = getattr(self.state.near_limit, "position_m", None)
            fl = getattr(self.state.far_limit, "position_m", None)
            if nl is None or fl is None:
                return target
            nl = float(nl); fl = float(fl)
            lo, hi = (nl, fl) if nl <= fl else (fl, nl)
            stand_off = 0.03
            if hi - lo <= 2.0 * stand_off:
                return max(lo, min(hi, target))
            return max(lo + stand_off, min(hi - stand_off, target))
        except Exception:
            return target_m

    def _goto_velocity_for_distance(self, distance_m: float, requested_max_mps: float) -> float:
        """Predictive Goto cruise speed from remaining distance.

        v18 is rebuilt from the v16 base and intentionally plans much earlier than
        v16.  The goal is to arrive from the original travel direction, then creep
        the last part of the move, rather than fly past the target and reverse.
        """
        try:
            d = max(0.0, float(distance_m))
            vmax = max(0.0, float(requested_max_mps))
            stop_decel = max(0.05, float(getattr(self, "max_stop_decel_mps2", getattr(self, "max_decel_mps2", 2.0))))
            # Use a conservative planning decel.  This is deliberately below the
            # configured Stop De-Accel because the EL7/W1P chain has command/write
            # latency and the feedback speed can arrive a packet late.
            decel_plan = max(0.08, stop_decel * 0.10)
            guard_m = max(0.08, min(0.90, 0.10 + 0.06 * abs(float(getattr(self, "current_speed_mps", 0.0) or 0.0))))
            d_eff = max(0.0, d - guard_m)
            return min(vmax, math.sqrt(max(0.0, 2.0 * decel_plan * d_eff)))
        except Exception:
            return max(0.0, float(requested_max_mps or 0.0))

    def _goto_velocity_to_target(self, diff_m: float, requested_max_mps: float) -> tuple[float, bool]:
        """Return (velocity, reached) for an exact preset/limit Goto.

        v18 uses a one-direction predictive approach with a final creep stage.  It
        only reverses if the winch has already crossed the target and the feedback
        speed has settled; normal operation should ramp in, then creep onto the
        preset without passing it first.
        """
        try:
            diff = float(diff_m)
            d = abs(diff)
            fb_signed = float(getattr(self, "current_speed_mps", 0.0) or 0.0)
            fb = abs(fb_signed)
            vmax = max(0.02, float(requested_max_mps or 0.0))
        except Exception:
            return 0.0, True

        target_window = 0.010  # 1 cm operator target
        stop_speed = 0.030
        if d <= target_window and fb <= stop_speed:
            return 0.0, True

        direction = 1.0 if diff >= 0.0 else -1.0
        approaching = (fb_signed == 0.0) or (fb_signed * direction > -0.02)

        # Latch the original direction for the final approach.  This prevents the
        # target logic from changing direction while the winch is still carrying
        # momentum, which was the overshoot-and-creep-back behaviour seen in v16.
        last_dir = float(getattr(self, "_goto_approach_dir", 0.0) or 0.0)
        if last_dir == 0.0 or abs(diff) > 1.50:
            self._goto_approach_dir = direction
            last_dir = direction

        # If we crossed the target, stop first.  Only creep back once the drive is
        # almost stationary, otherwise a reversal just creates a hunt.
        if (direction != last_dir) and d > target_window:
            if fb > 0.06:
                return 0.0, False
            creep_back = min(0.12, max(0.025, d * 0.25))
            return direction * min(vmax, creep_back), False

        # Final approach zone: low speed only, with speed proportional to remaining
        # distance. This is what should land the preset without overshoot.
        if d <= 2.00:
            if d <= target_window:
                return 0.0, False
            # If the winch is still moving too quickly for the remaining distance,
            # command zero and wait for it to settle before creeping again.
            allowed_creep = min(0.38, max(0.025, 0.18 * d + 0.025))
            if fb > max(0.12, allowed_creep * 1.8):
                return 0.0, False
            return last_dir * min(vmax, allowed_creep), False

        # Approach zone: brake early using a conservative speed envelope.  If the
        # measured feedback is above the envelope, command zero until the drive
        # falls back inside it rather than continuing to push toward the preset.
        v_allowed = self._goto_velocity_for_distance(d, vmax)
        if d <= 8.0:
            v_allowed = min(v_allowed, max(0.38, d * 0.45))
        if fb > (v_allowed + 0.35) and d <= 10.0:
            return 0.0, False
        v_allowed = max(0.10, v_allowed)
        return last_dir * min(vmax, v_allowed), False

    def _goto_should_stop_now(self, diff_m: float, last_err_m: float | None = None) -> bool:
        """Legacy compatibility wrapper. v18 only completes inside the 1 cm window."""
        try:
            d = abs(float(diff_m))
            fb = abs(float(getattr(self, "current_speed_mps", 0.0) or 0.0))
            return d <= 0.010 and fb <= 0.030
        except Exception:
            return False


    def _log_motion_snapshot(self, vel_mps: float, force: bool = False):
        """Change-based motion-chain logging.

        v26.06.26.25: force=True is still allowed to send a safety zero, but it
        must not force a repeated [MOTION] line every UI tick. Log only when the
        command/state changes, when the joystick is moving, or occasionally during
        non-zero motion for operator confidence.
        """
        now = time.time()
        ctrl_pct = float(getattr(self, 'last_controller_value', 0.0) or 0.0)
        cmd = float(getattr(self, 'drive_command_speed_mps', 0.0) or 0.0)
        fb = float(getattr(self, 'current_speed_mps', 0.0) or 0.0)
        pos = float(getattr(self.state, 'pos_m', 0.0) or 0.0)
        snapshot = (
            round(ctrl_pct, 1),
            round(float(vel_mps or 0.0), 3),
            bool(getattr(self, 'winch_srvon_output', False)),
            bool(getattr(self, 'winch_sw_srvon', False)),
            bool(getattr(self, 'winch_srvon_ready', False)),
            bool(getattr(self, 'winch_drive_writes_enabled', False)),
            bool(getattr(self, 'winch_no_motion_feedback_fault', False)),
            round(cmd, 3),
            round(fb, 3),
            round(pos, 3),
            bool(getattr(self.state, 'estop_active', False)),
            str(getattr(self, 'winch_rs_status', '') or ''),
        )
        last_snapshot = getattr(self, '_last_motion_chain_log_snapshot', None)
        last_log = float(getattr(self, '_last_motion_chain_log_ts', 0.0) or 0.0)
        moving_or_commanded = (
            abs(ctrl_pct) >= 0.5 or
            abs(float(vel_mps or 0.0)) >= 0.002 or
            abs(cmd) >= 0.002 or
            abs(fb) >= 0.002
        )
        state_changed = snapshot != last_snapshot
        # Only heartbeat non-zero motion; never heartbeat an unchanged idle/safety zero.
        heartbeat_due = moving_or_commanded and (now - last_log) >= 2.0
        if not state_changed and not heartbeat_due:
            return
        # Suppress repeated idle snapshots caused by force=True safety zero calls.
        if not moving_or_commanded and last_snapshot is not None and not state_changed:
            return
        self._last_motion_chain_log_ts = now
        self._last_motion_chain_log_snapshot = snapshot
        _app_log(
            f"[MOTION] CTRL-JS={ctrl_pct:+0.1f}% "
            f"SRVR-VEL={float(vel_mps or 0.0):+0.3f}m/s "
            f"SRVON_OUT={'ON' if bool(getattr(self, 'winch_srvon_output', False)) else 'OFF'} "
            f"SW_SRVON={'ON' if bool(getattr(self, 'winch_sw_srvon', False)) else 'OFF'} "
            f"SRVON_READY={'1' if bool(getattr(self, 'winch_srvon_ready', False)) else '0'} "
            f"W1P-WRITE={'ON' if bool(getattr(self, 'winch_drive_writes_enabled', False)) else 'WAIT'} "
            f"NO_MOTION={'1' if bool(getattr(self, 'winch_no_motion_feedback_fault', False)) else '0'} "
            f"CMD={cmd:+0.3f}m/s FB={fb:+0.3f}m/s POS={pos:0.3f}m"
        )

    def _send_velocity_command(self, vel_mps: float, force: bool = False):
        if self.state.demo_mode:
            return
        self._sync_motion_profile_to_winch(force=False)
        if self.state.estop_active:
            vel_mps = 0.0
        now = time.time()
        last_send_ts = float(getattr(self, "_last_winch_vel_send_ts", 0.0) or 0.0)
        same_command = abs(vel_mps - self.last_sent_vel) < 0.01
        nonzero_command = abs(vel_mps) >= 0.001
        # v26.06.26.25: while the joystick is held steady, keep sending a slow
        # non-zero VEL heartbeat. W1P now requires a fresh non-zero request before
        # arming from WAIT, and this avoids a held joystick command going stale
        # while the drive is coasting or waiting to re-arm. Idle zero remains quiet.
        if not force and same_command:
            if (not nonzero_command) or ((now - last_send_ts) < 0.25):
                return
        self.last_sent_vel = vel_mps
        self.requested_speed_mps = vel_mps
        self._last_winch_vel_send_ts = now
        if abs(vel_mps) < 0.001:
            self.arduino_client.send("VEL 0")
        else:
            self.arduino_client.send(f"VEL {vel_mps:.3f}")
        try:
            self._log_motion_snapshot(vel_mps, force=force)
        except Exception:
            pass

    def _send_stop_command(self):
        self.last_sent_vel = 0.0
        self.requested_speed_mps = 0.0
        self.profile_speed_mps = 0.0
        self.drive_command_speed_mps = 0.0
        self.arduino_client.send("STOP")
        self.goto_target_m = None

    def _send_safety_stop_limited(self, force: bool = False):
        """Send an immediate safety STOP on a transition, then at most once per second.

        v26.06.15.01 sent STOP for every W1P fault-status packet. W1P then forced
        another status response, creating a self-sustaining STOP/status loop.
        """
        now = time.monotonic()
        last = float(getattr(self, "_last_safety_stop_ts", 0.0) or 0.0)
        if force or (now - last) >= 1.0:
            self._last_safety_stop_ts = now
            self._send_stop_command()

    # ---------------- Timers & updates ----------------

    def _aux_action_label(self, idx: int, source: str = "ctrl") -> str:
        try:
            prefix = "w1pts_" if str(source).lower() in ("w1pts", "w1p-ts", "w1p_ts") else ""
            action = str(getattr(self, f"{prefix}aux{idx+1}_action", "") or "").strip()
        except Exception:
            action = ""
        if not action:
            return "AUX"

        def preset_label(n: int) -> str:
            default_name = f"P{n}"
            try:
                if 0 <= (n - 1) < len(self.preset_names):
                    name = str(self.preset_names[n - 1] or "").strip()
                    return name if name else default_name
            except Exception:
                pass
            return default_name

        action_norm = self._normalise_setup_action(action) if hasattr(self, "_normalise_setup_action") else action
        if action_norm == "Limit Calibration":
            step = int(getattr(self, "_system_calibration_aux_step", 0) or 0)
            if not bool(getattr(self, "system_calibration_mode", False)):
                return "Limit Calibration"
            if step <= 0:
                return "Set Near Limit"
            if step == 1:
                return "Set Far Limit"
            return "Set Ref Point"
        if action_norm == "Winch Calibration":
            step = int(getattr(self, "_winch_calibration_aux_step", 0) or 0)
            if not bool(getattr(self, "winch_calibration_mode", False)):
                return "Winch Calibration"
            if step <= 0:
                return "Set Zero"
            return "Set 20m"
        if action_norm == "Accel Mode":
            return f"Accel Mode | {self._display_accel_type()}"
        if action_norm == "Drive Mode":
            return f"Drive Mode | {self._active_speed_mode_name()}"
        if action_norm == "Battery Change":
            return f"Battery Change | {'On' if bool(getattr(self, 'battery_change_mode', False)) else 'Off'}"
        if action.startswith("Goto P"):
            try:
                n = int(action[6:])
                return f"Goto {preset_label(n)}"
            except Exception:
                return action
        if action.startswith("Slip P"):
            try:
                n = int(action[6:])
                return f"Slip {preset_label(n)}"
            except Exception:
                return action
        return action


    def _build_controller_display_packet(self, target: str = "ctrl") -> str:
        pos_rel = self._current_position_relative_m()
        near_rel = 0.0
        ref_visible = getattr(self.state.ref_point, 'position_m', None) is not None
        ref_rel = self._limit_display_position_m(self.state.ref_point) if ref_visible else 0.0
        far_rel = self._limit_display_position_m(self.state.far_limit)
        if far_rel < 0:
            far_rel = abs(far_rel)
        service_mode = bool(getattr(self, "battery_change_mode", False) or getattr(self, "system_calibration_mode", False) or getattr(self, "winch_calibration_mode", False) or getattr(self, "not_calibrated_mode", False))
        pos_abs = float(getattr(self.state, "pos_m", 0.0) or 0.0)
        near_abs = float(getattr(self.state.near_limit, "position_m", 0.0) or 0.0)
        far_abs = float(getattr(self.state.far_limit, "position_m", near_abs + far_rel) or (near_abs + far_rel))
        if bool(getattr(self, "system_calibration_mode", False)):
            # In calibration the live raw winch count may be negative depending on
            # motor direction. The operator view is distance away from Near.
            to_near = float(pos_rel)
            to_far = max(0.0, float(far_rel) - float(pos_rel))
        elif service_mode:
            to_near = pos_abs - near_abs
            to_far = far_abs - pos_abs
        else:
            to_near = max(0.0, pos_abs - near_abs)
            to_far = max(0.0, far_abs - pos_abs)
        ramp_near = float(getattr(self.state, "ramp_zone_near", 0.0) or 0.0)
        ramp_far = float(getattr(self.state, "ramp_zone_far", 0.0) or 0.0)

        def _sanitize_field(text: str, limit: int = 8) -> str:
            s = str(text or "").replace("|", "/").replace(",", "/").strip()
            if not s:
                return ""
            return s[:limit]

        preset_names_all = []
        preset_pos_all = []
        preset_abs_all = []
        preset_vis_all = []
        for i in range(PRESET_COUNT):
            name = self.preset_names[i] if i < len(self.preset_names) else f"P{i+1}"
            preset_names_all.append(_sanitize_field(name))
            rel_pos = None
            if 0 <= i < len(self.preset_positions):
                rel_pos = self.preset_positions[i]
            preset_pos_all.append("" if rel_pos is None else f"{float(rel_pos):0.2f}")
            try:
                abs_pos = self._preset_absolute_position_m(i)
            except Exception:
                abs_pos = None
            preset_abs_all.append("" if abs_pos is None else f"{float(abs_pos):0.2f}")
            is_vis = False
            if 0 <= i < len(self.preset_visible):
                is_vis = bool(self.preset_visible[i])
            if rel_pos is None:
                is_vis = False
            preset_vis_all.append("1" if is_vis else "0")

        def _hmi_aux_label(i: int) -> str:
            # Send the same full AUX action labels shown in SRVR. CTRL-TS uses
            # CTRL-TS Aux Assign; W1P-TS uses W1P-TS Aux Assign.
            source = "w1pts" if str(target).lower() in ("w1pts", "w1p-ts", "w1p_ts") else "ctrl"
            return str(self._aux_action_label(i, source=source) or "").strip()

        labels = [_sanitize_field(_hmi_aux_label(i), limit=24) for i in range(4)]
        cs = get_controller_status()
        ctrl_link = 1 if cs.get("connected") else 0
        srvr_link = 1
        
        try:
            _wlast = float(getattr(self.arduino_status, "last_seen", 0.0) or 0.0)
            _wfresh = bool(getattr(self.arduino_status, "connected", False) and _wlast > 0 and (time.time() - _wlast) <= WINCH_STATUS_TIMEOUT_S)
        except Exception:
            _wfresh = False
        w1p_state = self._w1p_health_state(winch_connected_fresh=_wfresh)
        # Keep legacy w1p=1 during an internally reported W1P fault; w1p=0 is
        # reserved for loss of the W1P node itself. New touchscreens use the
        # explicit w1p_state field for OK / Fault / Error.
        w1p_link = 0 if w1p_state == "error" else 1
        try:
            max_mps, max_mode_name = self._current_max_speed_info()
        except Exception:
            max_mps, max_mode_name = 0.0, "Mode 1"
        max_mode_name = _sanitize_field(max_mode_name, limit=24)
        ctrl_flags = int(cs.get("flags", 0) or 0)

        # v26.06.26.25: both touchscreens receive the same authoritative
        # SRVR-resolved safety state, including RS485 and ADS1115 faults.
        is_red, resolved_status, resolved_sources = self._safety_status_summary(cs=cs, winch_connected_fresh=_wfresh, flags=ctrl_flags)
        if is_red:
            status_text = resolved_status
            status_level = "red"
            if "RS485" in resolved_sources:
                estop_src = "RS485"
            elif "ADS1115" in resolved_sources:
                estop_src = "ADS1115"
            else:
                estop_parts = [x for x in ("CTRL", "SRVR", "W1P") if x in resolved_sources]
                estop_src = "+".join(estop_parts) if estop_parts else ""
            hmi_estop = 1
        elif bool(getattr(self, "battery_change_mode", False)):
            status_text = "Battery Change"
            status_level = "yellow"
            estop_src = ""
            hmi_estop = 0
        elif bool(getattr(self, "winch_calibration_mode", False)):
            status_text = "Winch Calibration"
            status_level = "yellow"
            estop_src = ""
            hmi_estop = 0
        elif bool(getattr(self, "system_calibration_mode", False)):
            status_text = "Limit Calibration"
            status_level = "yellow"
            estop_src = ""
            hmi_estop = 0
        elif bool(getattr(self, "not_calibrated_mode", False)):
            status_text = "Un-Calibrated"
            status_level = "yellow"
            estop_src = ""
            hmi_estop = 0
        else:
            if bool(getattr(self, "winch_sw_srvon", False)) or bool(getattr(self, "winch_sw_srvon_ready", False)) or bool(getattr(self, "winch_srvon_ready", False)):
                status_text = "Active"
            else:
                status_text = "Active"
            status_level = "green"
            estop_src = ""
            hmi_estop = 0
        status_text = _sanitize_field(status_text, limit=36)
        estop_src = _sanitize_field(estop_src, limit=16)
        disp_pos_rel = self._quantize_display_value(pos_rel, HMI_DISPLAY_POS_QUANTUM_M)
        disp_to_near = self._quantize_display_value(to_near, HMI_DISPLAY_POS_QUANTUM_M)
        disp_to_far = self._quantize_display_value(to_far, HMI_DISPLAY_POS_QUANTUM_M)
        disp_speed = self._quantize_display_value(float(getattr(self, 'display_speed_mps', getattr(self, 'current_speed_mps', 0.0)) or 0.0), HMI_DISPLAY_SPEED_QUANTUM_MPS)
        parts = [
            "DSP1",
            f"pos={disp_pos_rel:0.3f}",
            f"to_near={disp_to_near:0.3f}",
            f"to_far={disp_to_far:0.3f}",
            f"speed_mps={disp_speed:0.2f}",
            f"speed_kmh={disp_speed*3.6:0.2f}",
            f"near={near_rel:0.2f}",
            f"ref={ref_rel:0.2f}",
            f"far={far_rel:0.2f}",
            f"ramp_near={ramp_near:0.2f}",
            f"ramp_far={ramp_far:0.2f}",
            f"ref_vis={1 if ref_visible else 0}",
            f"estop={hmi_estop}",
            f"estop_src={estop_src}",
            f"status={status_text}",
            f"status_level={status_level}",
            f"ctrl={ctrl_link}",
            f"srvr={srvr_link}",
            f"w1p={w1p_link}",
            f"w1p_state={w1p_state}",
            f"service={1 if service_mode else 0}",
            f"flags={ctrl_flags}",
            f"aux1={labels[0]}",
            f"aux2={labels[1]}",
            f"aux3={labels[2]}",
            f"aux4={labels[3]}",
            f"max_mps={float(max_mps):0.2f}",
            f"max_kmh={float(max_mps)*3.6:0.2f}",
            f"mode={max_mode_name}",
            f"preset_names={','.join(preset_names_all)}",
            f"preset_pos={','.join(preset_pos_all)}",
            f"preset_abs={','.join(preset_abs_all)}",
            f"preset_vis={','.join(preset_vis_all)}",
        ]
        return "|".join(parts) + "\n"

    def _update_display_speed_estimate(self):
        try:
            # v16: show the latest W1P/Leadshine feedback speed directly. Do not
            # keep the visual speed/progress alive from requested/profile command
            # values, because that made SRVR/CTRL-TS look like they were still
            # moving for a second after the motor had physically stopped.
            actual = abs(float(getattr(self, "current_speed_mps", 0.0) or 0.0))
            try:
                max_mps, _mode_name = self._current_max_speed_info()
                max_mps = abs(float(max_mps or 0.0))
            except Exception:
                max_mps = abs(float(getattr(self, "max_speed_mps", 0.0) or 0.0))
            if max_mps > 0.0:
                actual = min(actual, max_mps)
            # Snap very small feedback to zero immediately for display only.
            if actual < 0.04:
                actual = 0.0
            self.display_speed_mps = actual
            self._last_display_pos_m = getattr(self.state, "pos_m", None)
            self._last_display_pos_t = time.time()
        except Exception:
            self.display_speed_mps = abs(float(getattr(self, "current_speed_mps", 0.0) or 0.0))

    def _send_controller_display_packet(self, force: bool = False):
        """Send event-driven display packets to CTRL-TS and W1P-TS.

        Safety/control traffic remains on the fast CTRL/W1P paths.  This display
        path only pushes when the visible payload changes, with a slow keepalive
        so a touchscreen that boots later can recover without causing redraw
        pressure during long operating days.
        """
        self._update_display_speed_estimate()
        try:
            now = time.time()

            def _send_to_target(name: str, ip: str | None, tx_func):
                if not str(ip or "").strip():
                    return
                pkt_text = self._build_controller_display_packet(target=name)
                pkt = pkt_text.encode('ascii', errors='ignore')
                safe_name = ''.join(ch if ch.isalnum() else '_' for ch in name)
                last_pkt_attr = f'_last_{safe_name}_display_pkt'
                last_repeat_attr = f'_last_{safe_name}_display_repeat_tx'
                last_change_attr = f'_last_{safe_name}_display_change_tx'
                same_packet = (pkt == getattr(self, last_pkt_attr, b''))
                if not force:
                    if same_packet:
                        last_repeat = float(getattr(self, last_repeat_attr, 0.0) or 0.0)
                        if (now - last_repeat) < HMI_DISPLAY_KEEPALIVE_S:
                            return
                    else:
                        last_change = float(getattr(self, last_change_attr, 0.0) or 0.0)
                        if (now - last_change) < HMI_DISPLAY_MIN_CHANGE_INTERVAL_S:
                            return
                        setattr(self, last_change_attr, now)
                setattr(self, last_repeat_attr, now)
                setattr(self, last_pkt_attr, pkt)
                tx_func(pkt_text)

            ctrl_ip = str(getattr(self, 'controller_ip_ref', '') or '').strip()
            if ctrl_ip:
                def _tx_ctrl(pkt_text: str):
                    self.ctrl_display_sock.sendto(pkt_text.encode('ascii', errors='ignore'), (ctrl_ip, SERVER_BIND_PORT))
                _send_to_target('ctrl', ctrl_ip, _tx_ctrl)

            w1p_ip = str(getattr(self, 'winch_host', '') or '').strip()
            if w1p_ip:
                def _tx_w1pts(pkt_text: str):
                    # Use the existing W1P UDP client socket/queue so W1P keeps
                    # replying STATUS to the same SRVR receive socket.
                    self.arduino_client.send(pkt_text.strip())
                _send_to_target('w1pts', w1p_ip, _tx_w1pts)
        except Exception:
            pass

    @staticmethod
    def _freed_s24be(value: int) -> bytes:
        value = max(-8388608, min(8388607, int(value)))
        if value < 0:
            value = (1 << 24) + value
        return bytes([(value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF])

    @staticmethod
    def _freed_s24_to_int(b: bytes) -> int:
        if len(b) < 3:
            return 0
        v = (int(b[0]) << 16) | (int(b[1]) << 8) | int(b[2])
        if v & 0x800000:
            v -= 0x1000000
        return v

    def _freed_input_recent(self) -> bool:
        try:
            return (time.time() - float(getattr(self, "freed_input_last_rx", 0.0) or 0.0)) <= float(getattr(self, "freed_input_timeout_s", 2.0) or 2.0)
        except Exception:
            return False

    def _freed_input_native_sign(self, name: str) -> int:
        """Built-in correction for Free-D channels that are backwards on this system.

        The Free-D tab Invert checkboxes remain user trim controls and default OFF.
        Pan remains visually default-OFF and the previous
        double-invert behaviour; Focus remains natively corrected.
        """
        try:
            key = str(name).strip().lower()
            return -1 if key == "focus" else 1
        except Exception:
            return 1

    def _freed_input_sign(self, name: str) -> int:
        try:
            ui_sign = -1 if bool(dict(getattr(self, "freed_input_inverts", {}) or {}).get(str(name), False)) else 1
            return int(self._freed_input_native_sign(name)) * int(ui_sign)
        except Exception:
            return 1

    def _sync_freed_offsets_from_ui(self):
        """Pull editable Free-D offset Entry values into runtime state when valid."""
        try:
            input_vars = getattr(self, "_freed_input_offset_vars", {}) or {}
            if input_vars:
                current = dict(getattr(self, "freed_input_offsets", {}) or {})
                for name, var in input_vars.items():
                    try:
                        txt = str(var.get()).strip()
                        if txt not in ("", "-", ".", "-."):
                            current[str(name)] = float(txt)
                    except Exception:
                        pass
                self.freed_input_offsets = current
        except Exception:
            pass
        try:
            output_vars = getattr(self, "_freed_output_offset_vars", {}) or {}
            if output_vars:
                current = dict(getattr(self, "freed_output_offsets", {}) or {})
                for name, var in output_vars.items():
                    try:
                        txt = str(var.get()).strip()
                        if txt not in ("", "-", ".", "-."):
                            current[str(name)] = float(txt)
                    except Exception:
                        pass
                self.freed_output_offsets = current
        except Exception:
            pass

    def _current_freed_input_motion(self):
        # Use ShotOver input fields if fresh; otherwise fall back to manual defaults.
        try:
            with self._freed_input_lock:
                recent = self._freed_input_recent()
                if bool(getattr(self, "freed_input_enabled", False)) and recent:
                    return (
                        int(getattr(self, "freed_in_camera_id", getattr(self, "freed_camera_id", 1)) or 1),
                        float(getattr(self, "freed_in_pan", 0.0) or 0.0) * self._freed_input_sign("Pan") + self._freed_input_offset_value("Pan"),
                        float(getattr(self, "freed_in_tilt", 0.0) or 0.0) * self._freed_input_sign("Tilt") + self._freed_input_offset_value("Tilt"),
                        float(getattr(self, "freed_in_roll", 0.0) or 0.0) * self._freed_input_sign("Roll") + self._freed_input_offset_value("Roll"),
                        int(getattr(self, "freed_in_zoom", 0) or 0) * self._freed_input_sign("Zoom"),
                        int(getattr(self, "freed_in_focus", 0) or 0) * self._freed_input_sign("Focus"),
                    )
        except Exception:
            pass
        return (
            int(getattr(self, "freed_camera_id", 1) or 1),
            float(getattr(self, "freed_pan", 0.0) or 0.0) * self._freed_input_sign("Pan") + self._freed_input_offset_value("Pan"),
            float(getattr(self, "freed_tilt", 0.0) or 0.0) * self._freed_input_sign("Tilt") + self._freed_input_offset_value("Tilt"),
            float(getattr(self, "freed_roll", 0.0) or 0.0) * self._freed_input_sign("Roll") + self._freed_input_offset_value("Roll"),
            int(getattr(self, "freed_zoom", 0) or 0) * self._freed_input_sign("Zoom"),
            int(getattr(self, "freed_focus", 0) or 0) * self._freed_input_sign("Focus"),
        )

    def _freed_output_axis_sign(self, name: str) -> int:
        try:
            return -1 if bool(dict(getattr(self, "freed_output_inverts", {}) or {}).get(str(name), False)) else 1
        except Exception:
            return 1

    def _current_freed_xyz_for_output(self):
        x_m, y_m, z_m = self._current_freed_xyz()
        return (
            float(x_m) * self._freed_output_axis_sign("X"),
            float(y_m) * self._freed_output_axis_sign("Y"),
            float(z_m) * self._freed_output_axis_sign("Z"),
        )

    def _build_freed_d1_packet(self) -> bytes:
        x_m, y_m, z_m = self._current_freed_xyz_for_output()
        pos_scale = max(1.0, float(getattr(self, "freed_pos_scale", 640.0) or 640.0))
        cam_id, pan, tilt, roll, zoom, focus = self._current_freed_input_motion()
        cam_id = max(0, min(255, int(cam_id)))

        # D1 order used here: pan, tilt, roll, X, Y, Z, zoom, focus.
        # Pan/Tilt/Roll/Zoom/Focus are taken from Free-D input when a fresh ShotOver packet is received.
        payload = bytearray()
        payload.append(0xD1)
        payload.append(cam_id)
        for v in (pan, tilt, roll):
            payload.extend(self._freed_s24be(int(round(float(v) * 32768.0))))
        for v in (x_m, y_m, z_m):
            payload.extend(self._freed_s24be(int(round(float(v) * pos_scale))))
        payload.extend(self._freed_s24be(int(zoom or 0)))
        payload.extend(self._freed_s24be(int(focus or 0)))
        payload.extend(b"\x00\x00")  # Reserved bytes 26-27
        checksum = (0x40 - sum(payload[:28])) & 0xFF
        payload.append(checksum)
        return bytes(payload)

    def _send_freed_packet(self, force: bool = False):
        if not bool(getattr(self, "freed_output_enabled", False)):
            return
        try:
            ip = str(getattr(self, "freed_target_ip", "") or "").strip()
            if not ip:
                return
            port = int(getattr(self, "freed_target_port", 40000) or 40000)
            hz = max(1.0, min(100.0, float(getattr(self, "freed_rate_hz", 25.0) or 25.0)))
            now = time.perf_counter()
            if (not force) and (now - float(getattr(self, "_last_freed_tx", 0.0) or 0.0) < (1.0 / hz)):
                return
            self._last_freed_tx = now
            pkt = self._build_freed_d1_packet()
            self.freed_sock.sendto(pkt, (ip, port))
            try:
                now2 = time.perf_counter()
                self._freed_output_fps_times.append(now2)
                cutoff = now2 - 1.0
                recent = [t for t in self._freed_output_fps_times if t >= cutoff]
                if len(recent) >= 2 and (recent[-1] - recent[0]) > 1e-6:
                    self.freed_out_fps = float((len(recent) - 1) / (recent[-1] - recent[0]))
                else:
                    self.freed_out_fps = float(len(recent))
            except Exception:
                pass
        except Exception:
            pass

    def _freed_input_worker(self, sock):
        while not self._freed_input_stop.is_set():
            try:
                data, addr = sock.recvfrom(2048)
                self._handle_freed_input_packet(data, addr)
            except socket.timeout:
                continue
            except OSError:
                break
            except Exception:
                continue

    def _ensure_freed_input_listener(self):
        try:
            # Stop existing listener first; this also handles port/IP changes cleanly.
            self._freed_input_stop.set()
            old_sock = getattr(self, "_freed_input_sock", None)
            if old_sock is not None:
                try:
                    old_sock.close()
                except Exception:
                    pass
            self._freed_input_sock = None
            if not bool(getattr(self, "freed_input_enabled", False)):
                return
            self._freed_input_stop = threading.Event()
            bind_ip = str(getattr(self, "freed_input_bind_ip", "0.0.0.0") or "0.0.0.0").strip()
            port = int(getattr(self, "freed_input_port", 40001) or 40001)
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((bind_ip, port))
            sock.settimeout(0.25)
            self._freed_input_sock = sock
            th = threading.Thread(target=self._freed_input_worker, args=(sock,), daemon=True)
            self._freed_input_thread = th
            th.start()
        except Exception as e:
            try:
                self.freed_input_enabled = False
                self._set_status(f"Free-D input listener failed: {e}")
            except Exception:
                pass

    def _handle_freed_input_packet(self, data: bytes, addr):
        try:
            if not data or len(data) < 29 or data[0] != 0xD1:
                return
            cam_id = int(data[1])
            raw_pan = self._freed_s24_to_int(data[2:5])
            raw_tilt = self._freed_s24_to_int(data[5:8])
            raw_roll = self._freed_s24_to_int(data[8:11])
            raw_zoom_s24 = self._freed_s24_to_int(data[20:23])
            raw_focus_s24 = self._freed_s24_to_int(data[23:26])
            raw_zoom_u24 = self._freed_u24_to_int(data[20:23])
            raw_focus_u24 = self._freed_u24_to_int(data[23:26])
            pan = raw_pan / 32768.0
            tilt = raw_tilt / 32768.0
            roll = raw_roll / 32768.0
            zoom = self._decode_lens_raw_value(raw_zoom_s24, raw_zoom_u24)
            focus = self._decode_lens_raw_value(raw_focus_s24, raw_focus_u24)
            self._remember_lens_auto_value("zoom", zoom)
            self._remember_lens_auto_value("focus", focus)
            now = time.time()
            with self._freed_input_lock:
                self.freed_in_camera_id = cam_id
                self.freed_in_pan = pan
                self.freed_in_tilt = tilt
                self.freed_in_roll = roll
                self.freed_in_zoom = zoom
                self.freed_in_focus = focus
                self.freed_in_raw_camera_id = cam_id
                self.freed_in_raw_pan = raw_pan
                self.freed_in_raw_tilt = raw_tilt
                self.freed_in_raw_roll = raw_roll
                self.freed_in_raw_zoom = raw_zoom_u24
                self.freed_in_raw_focus = raw_focus_u24
                self.freed_input_last_rx = now
                try:
                    self.freed_input_last_addr = f"{addr[0]}:{addr[1]}"
                except Exception:
                    self.freed_input_last_addr = "--"
                self._freed_input_fps_times.append(now)
                cutoff = now - 1.0
                recent = [t for t in self._freed_input_fps_times if t >= cutoff]
                if len(recent) >= 2 and (recent[-1] - recent[0]) > 1e-6:
                    fps_est = float((len(recent) - 1) / (recent[-1] - recent[0]))
                else:
                    fps_est = float(len(recent))
                self.freed_in_fps = fps_est
                self.freed_in_raw_fps = fps_est
        except Exception:
            pass

    def _update_freed_input_ui(self):
        try:
            fields = getattr(self, "_freed_input_field_vars", None)
            if fields:
                with self._freed_input_lock:
                    recent = self._freed_input_recent()
                    age = time.time() - float(getattr(self, "freed_input_last_rx", 0.0) or 0.0)
                    self._sync_freed_offsets_from_ui()
                    values = {
                        "Cam ID": (getattr(self, "freed_in_raw_camera_id", 0), f"{int(getattr(self, 'freed_in_camera_id', 0) or 0)}"),
                        "Pan": (getattr(self, "freed_in_raw_pan", 0), f"{float(getattr(self, 'freed_in_pan', 0.0) or 0.0) * self._freed_input_sign('Pan') + self._freed_input_offset_value('Pan'):0.3f} deg"),
                        "Tilt": (getattr(self, "freed_in_raw_tilt", 0), f"{float(getattr(self, 'freed_in_tilt', 0.0) or 0.0) * self._freed_input_sign('Tilt') + self._freed_input_offset_value('Tilt'):0.3f} deg"),
                        "Roll": (getattr(self, "freed_in_raw_roll", 0), f"{float(getattr(self, 'freed_in_roll', 0.0) or 0.0) * self._freed_input_sign('Roll') + self._freed_input_offset_value('Roll'):0.3f} deg"),
                        "Zoom": (getattr(self, "freed_in_raw_zoom", 0), f"{int(getattr(self, 'freed_in_zoom', 0) or 0) * self._freed_input_sign('Zoom')}"),
                        "Focus": (getattr(self, "freed_in_raw_focus", 0), f"{int(getattr(self, 'freed_in_focus', 0) or 0) * self._freed_input_sign('Focus')}"),
                        "FPS": (f"{float(getattr(self, 'freed_in_raw_fps', 0.0) or 0.0):0.3f}", f"{float(getattr(self, 'freed_in_fps', 0.0) or 0.0):0.3f}"),
                    }
                    src = getattr(self, "freed_input_last_addr", "--")
                for name, (raw_var, dec_var) in fields.items():
                    raw, dec = values.get(name, ("--", "--"))
                    raw_var.set(str(raw))
                    dec_var.set(str(dec))
                if hasattr(self, "_freed_input_status_var"):
                    self._freed_input_status_var.set(f"{'LIVE' if recent else 'NO INPUT'}  Age {age:0.2f}s  Source {src}")
                self._update_lens_live_vars()
                self._update_freed_output_ui()
                return
        except Exception:
            pass

        # Legacy one-label fallback.
        if not hasattr(self, "_freed_input_status_var"):
            return
        try:
            with self._freed_input_lock:
                recent = self._freed_input_recent()
                age = time.time() - float(getattr(self, "freed_input_last_rx", 0.0) or 0.0)
                txt = (
                    f"Cam {int(getattr(self, 'freed_in_camera_id', 0) or 0)}  "
                    f"Pan {float(getattr(self, 'freed_in_pan', 0.0) or 0.0):0.3f}  "
                    f"Tilt {float(getattr(self, 'freed_in_tilt', 0.0) or 0.0):0.3f}  "
                    f"Roll {float(getattr(self, 'freed_in_roll', 0.0) or 0.0):0.3f}\n"
                    f"Zoom {int(getattr(self, 'freed_in_zoom', 0) or 0)}  "
                    f"Focus {int(getattr(self, 'freed_in_focus', 0) or 0)}  "
                    f"FPS {float(getattr(self, 'freed_in_fps', 0.0) or 0.0):0.3f}  "
                    f"{'LIVE' if recent else 'NO INPUT'}  "
                    f"Source {getattr(self, 'freed_input_last_addr', '--')}"
                )
            self._freed_input_status_var.set(txt)
        except Exception:
            pass


    def _update_freed_output_ui(self):
        try:
            self._sync_freed_offsets_from_ui()
            fields = getattr(self, "_freed_output_field_vars", None)
            if not fields:
                return
            pos_scale = max(1.0, float(getattr(self, "freed_pos_scale", 640.0) or 640.0))
            x_m, y_m, z_m = self._current_freed_xyz_for_output() if hasattr(self, "_current_freed_xyz_for_output") else self._current_freed_xyz()
            values = {
                "X": (int(round(float(x_m) * pos_scale)), f"{float(x_m):0.3f} m"),
                "Y": (int(round(float(y_m) * pos_scale)), f"{float(y_m):0.3f} m"),
                "Z": (int(round(float(z_m) * pos_scale)), f"{float(z_m):0.3f} m"),
                "FPS": (f"{float(getattr(self, 'freed_rate_hz', 25.0) or 25.0):0.3f}", f"{float(getattr(self, 'freed_out_fps', 0.0) or 0.0):0.3f}"),
            }
            for name, (raw_var, dec_var) in fields.items():
                raw, dec = values.get(name, ("--", "--"))
                if name != "FPS":
                    raw_var.set(str(raw))
                dec_var.set(str(dec))
            if hasattr(self, "_freed_output_scale_note"):
                self._freed_output_scale_note.set(f"Free-D scale: {pos_scale:0.1f} counts/m")
        except Exception:
            pass

    def _freed_output_worker(self):
        """High-rate Free-D output loop independent of the Tkinter GUI refresh loop."""
        next_tx = time.perf_counter()
        while not self._freed_output_stop.is_set():
            try:
                if not bool(getattr(self, "freed_output_enabled", False)):
                    next_tx = time.perf_counter()
                    self._freed_output_stop.wait(0.02)
                    continue
                hz = max(1.0, min(100.0, float(getattr(self, "freed_rate_hz", 25.0) or 25.0)))
                period = 1.0 / hz
                now = time.perf_counter()
                if now < next_tx:
                    self._freed_output_stop.wait(min(0.005, max(0.0, next_tx - now)))
                    continue
                self._send_freed_packet(force=True)
                next_tx += period
                # If the app was suspended or the system was busy, skip missed periods rather than bunching packets.
                if next_tx < now - period:
                    next_tx = now + period
            except Exception:
                self._freed_output_stop.wait(0.02)

    def _ensure_freed_output_thread(self):
        try:
            th = getattr(self, "_freed_output_thread", None)
            if th is not None and th.is_alive():
                return
            self._freed_output_stop = threading.Event()
            th = threading.Thread(target=self._freed_output_worker, daemon=True)
            self._freed_output_thread = th
            th.start()
        except Exception:
            pass


    def _start_timers(self):
        self._ensure_freed_input_listener()
        self._ensure_freed_output_thread()
        self._update_timer()
        self._arduino_poll_timer()
        self._controller_event_timer()
        self._drain_log_queue()

    def _update_demo_position_from_controller(self):
        cs = get_controller_status()
        axis, axis_pct = _controller_axis_normalized(cs)
        # Joystick Invert changes operator/UI direction.
        # Winch/Motor Invert is handled inside W1P so the motor sign can be
        # reversed without reversing the SRVR/CTRL-TS progress direction.
        if self.reverse_joystick:
            axis = -axis
            axis_pct = -axis_pct
        if abs(axis_pct) < JOY_DEADBAND_PCT:
            axis = 0.0
            axis_pct = 0.0
        self.last_controller_value = axis_pct
        dt = float(CONTROL_LOOP_DT_S)

        nl_pos = (
            self.state.near_limit.position_m
            if self.state.near_limit.position_m is not None
            else 0.0
        )
        fl_pos = (
            self.state.far_limit.position_m
            if self.state.far_limit.position_m is not None
            else self.state.total_length_m
        )
        span = max(0.1, fl_pos - nl_pos)

        if self.goto_target_m is not None:
            if self.state.pos_m is None:
                self.state.pos_m = nl_pos
            if abs(axis_pct) >= max(JOY_DEADBAND_PCT, 3.0):
                self.goto_target_m = None
            else:
                target = float(self.goto_target_m)
                pos = float(self.state.pos_m)
                diff = target - pos
                v_max_mps = min(float(getattr(self, "goto_speed_mps", self.max_speed_mps)), self.max_speed_mps)
                if self._service_override_active():
                    v_max_mps = min(v_max_mps, self._service_speed_limit_mps())
                vel, reached = self._goto_velocity_to_target(diff, v_max_mps)
                if reached:
                    self.current_speed_mps = 0.0
                    self.last_winch_output = 0.0
                    self.state.pos_m = target
                    self.goto_target_m = None
                    self._goto_stop_zone = False
                    return
                if not self._service_override_active():
                    vel = self._limit_velocity_for_hard_limits(pos, vel, nl_pos, fl_pos)
                self.state.pos_m += vel * dt
                if not self._service_override_active():
                    if self.state.pos_m < nl_pos:
                        self.state.pos_m = nl_pos
                    if self.state.pos_m > fl_pos:
                        self.state.pos_m = fl_pos
                self.current_speed_mps = vel
                self.last_winch_output = self.current_speed_mps
                self._goto_last_error_m = diff
                return

        if abs(axis) < 1e-3:
            self.current_speed_mps = 0.0
            return

        if self._service_override_active():
            v_max_mps = self._service_speed_limit_mps()
        else:
            v_max_mps = self.max_speed_mps
        if self.state.pos_m is None:
            self.state.pos_m = nl_pos + span / 2.0
        if self._service_override_active():
            vel = axis * v_max_mps
            self.state.pos_m += vel * dt
        else:
            vel = self._limit_velocity_for_hard_limits(self.state.pos_m, axis * v_max_mps, nl_pos, fl_pos)
            self.state.pos_m += vel * dt
            if self.state.pos_m < nl_pos:
                self.state.pos_m = nl_pos
            if self.state.pos_m > fl_pos:
                self.state.pos_m = fl_pos

        self.current_speed_mps = vel
        self.last_winch_output = self.current_speed_mps

    def _apply_joystick_to_winch(self):
        cs = get_controller_status()
        try:
            safety_sources = self._estop_source_list(cs=cs, flags=int(cs.get("flags", 0) or 0))
        except Exception:
            safety_sources = ["SRVR"]
        if safety_sources:
            self.state.estop_active = True
            self.current_speed_mps = 0.0
            self.requested_speed_mps = 0.0
            self.goto_target_m = None
            self._send_velocity_command(0.0, force=True)
            return
        axis, axis_pct = _controller_axis_normalized(cs)
        # Joystick Invert changes operator/UI direction.
        # Winch/Motor Invert is handled inside W1P so the motor sign can be
        # reversed without reversing the SRVR/CTRL-TS progress direction.
        if self.reverse_joystick:
            axis = -axis
            axis_pct = -axis_pct
        if abs(axis_pct) < JOY_DEADBAND_PCT:
            axis = 0.0
            axis_pct = 0.0
        self.last_controller_value = axis_pct

        if self.state.estop_active:
            self.current_speed_mps = 0.0
            self._send_velocity_command(0.0, force=True)
            return

        pos = self.state.pos_m
        nl_pos = (
            self.state.near_limit.position_m
            if self.state.near_limit.position_m is not None
            else 0.0
        )
        fl_pos = (
            self.state.far_limit.position_m
            if self.state.far_limit.position_m is not None
            else self.state.total_length_m
        )
        margin = 0.02

        if pos is None:
            self.current_speed_mps = 0.0
            self._send_velocity_command(0.0, force=True)
            return

        if self.goto_target_m is not None and abs(axis_pct) >= max(JOY_DEADBAND_PCT, 3.0):
            self._cancel_goto_for_manual()

        if self.goto_target_m is not None:
            target = float(self.goto_target_m)
            diff = target - pos
            base_max = min(float(getattr(self, "goto_speed_mps", self.max_speed_mps)), self.max_speed_mps)
            if self._service_override_active():
                base_max = min(base_max, self._service_speed_limit_mps())
            vel_req, reached = self._goto_velocity_to_target(diff, base_max)
            if reached:
                self.last_winch_output = 0.0
                self.requested_speed_mps = 0.0
                self._send_velocity_command(0.0, force=True)
                self.goto_target_m = None
                self._goto_settle_since = 0.0
                self._goto_stop_zone = False
                self._goto_approach_dir = 0.0
                self._set_status("Goto reached")
                self._goto_last_error_m = diff
                return
            if not self._service_override_active():
                vel_req = self._limit_velocity_for_hard_limits(pos, vel_req, nl_pos, fl_pos)
            self.last_winch_output = vel_req
            self.requested_speed_mps = vel_req
            self._goto_last_error_m = diff
            self._send_velocity_command(vel_req, force=(abs(vel_req) < 0.001))
            return

        if not cs["connected"]:
            self.current_speed_mps = 0.0
            self._send_velocity_command(0.0, force=True)
            return

        if self._service_override_active():
            v_max = self._service_speed_limit_mps()
            vel = axis * v_max
        else:
            v_max = self.max_speed_mps
            if pos <= nl_pos + margin and axis < 0.0:
                axis = 0.0
            if pos >= fl_pos - margin and axis > 0.0:
                axis = 0.0
            vel = self._limit_velocity_for_hard_limits(pos, axis * v_max, nl_pos, fl_pos)

        self.last_winch_output = vel
        self.requested_speed_mps = vel
        self._send_velocity_command(vel)

    
    def _handle_aux_action(self, idx: int, source: str = "ctrl"):
        try:
            prefix = "w1pts_" if str(source).lower() in ("w1pts", "w1p-ts", "w1p_ts") else ""
            action = getattr(self, f"{prefix}aux{idx+1}_action", "None")
            label = f"{'W1P-TS Aux' if prefix else 'Aux'} {idx+1}"
        except Exception:
            action = "None"
            label = f"Aux {idx+1}"

        try:
            action_norm = self._normalise_setup_action(action) if hasattr(self, "_normalise_setup_action") else action
            action = action_norm
            if action_norm in ("Limit Calibration", "Winch Calibration"):
                self._execute_setup_direct_action(action_norm)
                self._set_status(f"{label}: {self._setup_direct_action_label(action_norm)}")
                self._refresh_run_aux_buttons()
                return
            if action == "__legacy_disabled__":
                step = int(getattr(self, "_system_calibration_aux_step", 0) or 0)
                if not bool(getattr(self, "system_calibration_mode", False)):
                    # Run-tab Aux calibration must not create or hide a modal popup.
                    # A hidden Toplevel with grab_set() was able to block mouse clicks
                    # while UDP/status updates kept running, which looked like an SRVR freeze.
                    try:
                        popup = getattr(self, "_system_calibration_popup", None)
                        if popup is not None:
                            try:
                                popup.grab_release()
                            except Exception:
                                pass
                            try:
                                popup.destroy()
                            except Exception:
                                pass
                    except Exception:
                        pass
                    self._system_calibration_popup = None
                    self._system_calibration_aux_step = 0
                    self._enter_system_calibration_mode()
                    self._force_hmi_display_update()
                    self._refresh_run_aux_buttons()
                    self._set_status(f"{label}: Start Calibration")
                elif step <= 0:
                    pos = self.state.pos_m
                    if pos is not None:
                        self._set_system_calibration_point(self.state.near_limit, 0, pos)
                        self._system_calibration_aux_step = 1
                        self._update_limits_ui()
                        self._redraw_progress()
                        self._sync_limits_to_winch()
                        self._save_config()
                        self._force_hmi_display_update()
                        self._set_status(f"{label}: Set Near")
                        self._refresh_run_aux_buttons()
                elif step == 1:
                    pos = self.state.pos_m
                    if pos is not None:
                        self._set_system_calibration_point(self.state.far_limit, 1, pos)
                        self._system_calibration_aux_step = 2
                        self._update_limits_ui()
                        self._redraw_progress()
                        self._sync_limits_to_winch()
                        self._save_config()
                        self._force_hmi_display_update()
                        self._set_status(f"{label}: Set Far")
                        self._refresh_run_aux_buttons()
                else:
                    pos = self.state.pos_m
                    if pos is not None:
                        self._set_system_calibration_point(self.state.ref_point, 2, pos)
                        self._system_calibration_aux_step = 0
                        self._update_limits_ui()
                        self._redraw_progress()
                        self._sync_limits_to_winch()
                        self._save_config()
                        self._force_hmi_display_update()
                        self._exit_not_calibrated_mode()
                        self._exit_system_calibration_mode()
                        self._set_status(f"{label}: Set Ref")
                        self._refresh_run_aux_buttons()
            elif action == "Drive Mode":
                new_idx = 1 if int(getattr(self, "active_drive_mode", 0)) == 0 else 0
                if hasattr(self, "_set_active_drive_mode"):
                    self._set_active_drive_mode(new_idx)
                else:
                    self.active_drive_mode = new_idx
                self._set_status(f"{label}: Drive Mode -> {self._active_speed_mode_name()}")
            elif action == "Battery Change":
                new_state = not bool(getattr(self, "battery_change_mode", False))
                self._set_battery_change_mode(new_state, save_config=True)
                self._set_status(f"{label}: Battery Change -> {'ON' if new_state else 'OFF'}")
            elif action == "Accel Mode":
                new_type = self._toggle_accel_type(save_config=True)
                self._set_status(f"{label}: Accel Mode -> {new_type}")
            elif action == "Goto Ref":
                if self.state.ref_point.position_m is not None:
                    self._start_goto_target(float(self.state.ref_point.position_m), f"{label}: Goto Ref")
            elif action == "Goto Near":
                if self.state.near_limit.position_m is not None:
                    self._start_goto_target(float(self.state.near_limit.position_m), f"{label}: Goto Near")
            elif action == "Goto Far":
                if self.state.far_limit.position_m is not None:
                    self._start_goto_target(float(self.state.far_limit.position_m), f"{label}: Goto Far")
            elif action.startswith("Goto P"):
                try:
                    p_idx = int(action[6:]) - 1
                except Exception:
                    p_idx = -1
                if 0 <= p_idx < len(self.preset_positions):
                    abs_pos = self._preset_absolute_position_m(p_idx)
                    if abs_pos is not None:
                        if self.state.pos_m is None:
                            self.state.pos_m = float(abs_pos)
                        self._start_goto_target(float(abs_pos), f"{label}: Goto P{p_idx+1}")
            elif action == "Slip Near":
                if self.state.near_limit.position_m is not None:
                    self.state.pos_m = float(self.state.near_limit.position_m)
                    try:
                        self._sync_winch_position(self.state.pos_m)
                    except Exception:
                        pass
                    if getattr(self, "not_calibrated_mode", False):
                        self._exit_not_calibrated_mode()
                    self._set_status(f"{label}: Slip Near")
            elif action == "Slip Ref":
                if self.state.ref_point.position_m is not None:
                    self.state.pos_m = float(self.state.ref_point.position_m)
                    try:
                        self._sync_winch_position(self.state.pos_m)
                    except Exception:
                        pass
                    if getattr(self, "not_calibrated_mode", False):
                        self._exit_not_calibrated_mode()
                    self._set_status(f"{label}: Slip Ref")
            elif action == "Slip Far":
                if self.state.far_limit.position_m is not None:
                    self.state.pos_m = float(self.state.far_limit.position_m)
                    try:
                        self._sync_winch_position(self.state.pos_m)
                    except Exception:
                        pass
                    if getattr(self, "not_calibrated_mode", False):
                        self._exit_not_calibrated_mode()
                    self._set_status(f"{label}: Slip Far")
            elif action.startswith("Slip P"):
                try:
                    p_idx = int(action[6:]) - 1
                except Exception:
                    p_idx = -1
                if 0 <= p_idx < len(self.preset_positions):
                    abs_pos = self._preset_absolute_position_m(p_idx)
                    if abs_pos is not None:
                        self.state.pos_m = float(abs_pos)
                        try:
                            self._sync_winch_position(self.state.pos_m)
                        except Exception:
                            pass
                        if getattr(self, "not_calibrated_mode", False):
                            self._exit_not_calibrated_mode()
                        self._set_status(f"{label}: Slip P{p_idx+1}")
        except Exception:
            pass

    def _controller_event_timer(self):
        # Process controller events (UDP packets from HV P2P CTRL)
        try:
            while True:
                ts, addr, msg = controller_events.get_nowait()
                if not isinstance(msg, dict):
                    continue
                if msg.get("type") != "controller_data":
                    continue

                # Update shared controller_state
                try:
                    controller_state["last_seen"] = ts
                    controller_state["last_ip"] = addr[0]
                    controller_state["last_port"] = addr[1]
                    controller_state["flags"] = int(msg.get("flags", 0))
                    controller_state["joystick_raw"] = float(
                        msg.get("joystick_raw", msg.get("joystick", msg.get("axis", controller_state.get("joystick_raw", 0.0)))) or 0.0
                    )
                    controller_state["joystick"] = float(_calibrate_joystick(controller_state["joystick_raw"]))
                except Exception:
                    pass

                flags = int(msg.get("flags", 0))

                # Edge-detect the MODE_TOGGLE button
                pressed = (flags & FLAG_MODE_TOGGLE) != 0
                if pressed and not getattr(self, "_mode_toggle_last", False):
                    try:
                        new_idx = 1 if int(getattr(self, "active_drive_mode", 0)) == 0 else 0
                        if hasattr(self, "_set_active_drive_mode"):
                            self._set_active_drive_mode(new_idx)
                        else:
                            self.active_drive_mode = new_idx
                        self._set_status(f"Drive Mode toggled -> {new_idx+1}")
                    except Exception:
                        pass
                self._mode_toggle_last = pressed

                # Edge-detect the Battery Change toggle button
                batt_pressed = (flags & FLAG_BATT_CHANGE_TOGGLE) != 0
                if batt_pressed and not getattr(self, "_batt_toggle_last", False):
                    try:
                        new_state = not bool(getattr(self, "battery_change_mode", False))
                        self._set_battery_change_mode(new_state, save_config=True)
                        self._set_status(f"Battery Change -> {'ON' if new_state else 'OFF'}")
                    except Exception:
                        pass
                self._batt_toggle_last = batt_pressed

                                # Edge-detect AUX switches (physical + touchscreen AUX 1/2/3/4)
                if not hasattr(self, "_aux_last"):
                    self._aux_last = [False, False, False, False]
                if not hasattr(self, "_aux_toggle"):
                    self._aux_toggle = [False, False, False, False]  # False=State1, True=State2

                aux_bits = [FLAG_AUX1, FLAG_AUX2, FLAG_AUX3, FLAG_AUX4]
                for i, bit in enumerate(aux_bits):
                    ap = (flags & bit) != 0
                    if ap and not self._aux_last[i]:
                        self._aux_toggle[i] = not self._aux_toggle[i]
                        try:
                            self._set_status(f"Aux {i+1}: State -> {2 if self._aux_toggle[i] else 1}")
                        except Exception:
                            pass
                        self._handle_aux_action(i)
                    self._aux_last[i] = ap




        except queue.Empty:
            pass
        except Exception:
            pass

        self.root.after(100, self._controller_event_timer)

    def _log_live_io_state(self, cs: dict, winch_connected_fresh: bool, winch_age: float, flags: int):
        """Write live connection, E-Stop and joystick status to the Log tab."""
        try:
            now = time.time()
            ctrl_connected = bool(cs.get("connected", False))
            ctrl_estop = bool(flags & FLAG_ESTOP_PRESSED)
            w1p_estop = bool(getattr(self, "_w1p_estop_active", False))
            srvr_estop = bool(getattr(self.state, "estop_active", False))

            def log_changed(attr: str, value: bool, label: str, true_text: str = "CONNECTED", false_text: str = "DISCONNECTED"):
                old = getattr(self, attr, None)
                if old is None or bool(old) != bool(value):
                    setattr(self, attr, bool(value))
                    _app_log(f"[{label}] {true_text if value else false_text}")

            log_changed("_log_ctrl_connected", ctrl_connected, "CTRL-Link")
            log_changed("_log_w1p_connected", bool(winch_connected_fresh), "W1P-Link")
            log_changed("_log_ads1115_connected", bool(cs.get("ads1115_connected", False)), "ADS1115-Link")
            log_changed("_log_rs485_connected", bool(self._rs485_connected()), "RS485-Link")
            log_changed("_log_ctrl_estop", ctrl_estop, "CTRL-E-Stop", "ACTIVE", "CLEAR")
            log_changed("_log_w1p_estop", w1p_estop, "W1P-E-Stop", "ACTIVE", "CLEAR")
            log_changed("_log_srvr_estop", srvr_estop, "SRVR-E-Stop", "ACTIVE", "CLEAR")

            if ctrl_connected:
                jr = float(cs.get("joystick_raw", 0.0) or 0.0)
                jp = float(cs.get("joystick", 0.0) or 0.0)
                lip = cs.get("last_ip") or "-"

                # v26.06.26.25: event-based joystick logging only.
                # Do not periodically print identical centred packets such as:
                #   [CTRL-JS] raw=+0.000 cal=+0.0% flags=0x00
                # Log when the joystick becomes active, moves by a meaningful step,
                # button/safety flags change, or it returns to centre once.
                flag_i = int(flags)
                centred = abs(jp) < 2.0 and flag_i == 0
                bucket = 0 if centred else int(round(jp / 2.0) * 2)
                state_key = (bucket, flag_i)
                last_key = getattr(self, "_log_last_joystick_key", None)

                should_log = False
                if last_key is None:
                    # First connected sample is only useful if not centred/idle.
                    should_log = not centred
                elif state_key != last_key:
                    # Log active movement or a single return-to-centre event.
                    should_log = True

                if should_log:
                    self._log_last_joystick = now
                    self._log_last_joystick_percent = jp
                    self._log_last_joystick_key = state_key
                    if centred:
                        _app_log(f"[CTRL-JS] ip={lip} CENTERED flags=0x{flag_i:02X} ({_decode_controller_flags(flag_i)})")
                    else:
                        _app_log(f"[CTRL-JS] ip={lip} raw={jr:+.3f} cal={jp:+.1f}% flags=0x{flag_i:02X} ({_decode_controller_flags(flag_i)})")
                elif last_key is None:
                    # Remember the idle state without writing it to the Log tab.
                    self._log_last_joystick_key = state_key
        except Exception:
            pass

    def _update_timer(self):
        self._refresh_freed_io_toggle_buttons()
        if self.state.demo_mode:
            self._update_demo_position_from_controller()
        else:
            self._apply_joystick_to_winch()

        self._service_auto_cancel_battery_change_if_returned_inside()
        self._update_limit_state()
        self._send_controller_display_packet()

        # Speed section removed; live speed is refreshed in the Run tab and display packet.

        now_ts = time.time()
        winch_last_seen = float(getattr(self.arduino_status, "last_seen", 0.0) or 0.0)
        winch_age = (now_ts - winch_last_seen) if winch_last_seen > 0 else 9999.0
        winch_connected_fresh = bool(self.arduino_status.connected and winch_age <= WINCH_STATUS_TIMEOUT_S)
        if self.arduino_status.connected and not winch_connected_fresh:
            self.arduino_status.connected = False
            self.arduino_status.last_error = "timeout"
            try:
                self.arduino_client.force_reconnect()
            except Exception:
                pass

        try:
            apply_grace_active = time.time() < float(getattr(self, "_settings_apply_grace_until", 0.0) or 0.0)
        except Exception:
            apply_grace_active = False
        if winch_connected_fresh or apply_grace_active:
            self.winch_status_label.config(text="Connected", bg="#206620")
        else:
            self.winch_status_label.config(text="Not Connected", bg="#662222")
            if not self.state.estop_active:
                self.state.estop_active = True
                self._send_stop_command()

        cs = get_controller_status()
        self._refresh_drive_control_button()

        try:
            if hasattr(self, "_tab_ctrl_ts_ip"):
                if apply_grace_active and self._tab_ctrl_ts_ip.get() == "Connected":
                    pass
                else:
                    self._tab_ctrl_ts_ip.set("Connected" if cs.get("hmi_connected") else "Disconnected")
            if hasattr(self, "_tab_ads1115_link"):
                if apply_grace_active and self._tab_ads1115_link.get() == "Connected":
                    pass
                else:
                    self._tab_ads1115_link.set("Connected" if cs.get("ads1115_connected") else "Disconnected")
            if hasattr(self, "_tab_w1pts_link_var"):
                age = (time.time() - float(getattr(self, "w1pts_last_seen", 0.0) or 0.0)) if float(getattr(self, "w1pts_last_seen", 0.0) or 0.0) > 0 else 9999.0
                connected = bool(getattr(self, "w1pts_connected_reported", False)) and age <= 3.5
                if apply_grace_active and self._tab_w1pts_link_var.get() == "Connected":
                    pass
                else:
                    self._tab_w1pts_link_var.set("Connected" if connected else "Disconnected")
        except Exception:
            pass


        try:

            # Keep SRVR response matched closely to the live controller feed

            raw = float(cs.get('joystick', 0.0) or 0.0)
            prev_f = float(getattr(self, '_joy_filt', 0.0))
            alpha = JOY_FILTER_ALPHA
            filt = (1.0 - alpha) * prev_f + alpha * raw
            self._joy_filt = filt

            joystick_display = filt if cs.get("connected") else 0.0

            # Deadband around 0 to prevent jitter
            if abs(joystick_display) < JOY_DEADBAND_PCT:
                joystick_display = 0.0

            self.last_controller_value = float(joystick_display)

        except Exception:

            pass
        if cs["connected"] or bool(getattr(self, "_settings_apply_grace_until", 0.0) and time.time() < float(getattr(self, "_settings_apply_grace_until", 0.0) or 0.0)):
            self.ctrl_status_label.config(text="Connected", bg="#206620")
        else:
            self.ctrl_status_label.config(text="Not Connected", bg="#662222")

                # Interpret controller flags
        flags = cs.get("flags", 0)

        estop_pressed = bool(flags & FLAG_ESTOP_PRESSED)
        self._ctrl_estop_active = bool(estop_pressed)
        cancel_pressed = bool(flags & FLAG_CANCEL_PRESSED)

        # ---- E-Stop behavior (FAIL-SAFE SOURCE PRIORITY) ----
        # Red state is derived from live CTRL/W1P sources first.  This prevents
        # a clear/debounce path from briefly showing yellow Un-Calibrated while
        # either E-Stop loop is open or either safety link is missing.
        self._sync_fail_safe_estop_state(cs=cs, winch_connected_fresh=winch_connected_fresh, flags=flags)
        self._refresh_estop_bar()


        try:
            self._log_live_io_state(cs, winch_connected_fresh, winch_age, flags)
        except Exception:
            pass

        # Cancel button from controller: cancel current motion (edge-triggered)
        last_cancel = bool(getattr(self, "_ctrl_cancel_last", False))
        if cancel_pressed and not last_cancel:
            self._cancel_motion()
        self._ctrl_cancel_last = cancel_pressed


        # Motion Active = winch connected AND controller connected AND not estop
        motion_active = (
            winch_connected_fresh
            and cs["connected"]
            and self._rs485_connected()
            and bool(cs.get("ads1115_connected", False))
            and not self.state.estop_active
        )
        if motion_active:
            if self.motion_status_label is not None:
                self.motion_status_label.config(
                                text="MOTION: Active",
                                bg="#206620",  # Green = Motion Active
                )
        else:
            if self.motion_status_label is not None:
                self.motion_status_label.config(
                                text="MOTION: Inactive",
                                bg="#662222",  # Red = Motion Inactive
                )

        expected = self.controller_ip_ref
        lastip = cs.get("last_ip")
        if expected and lastip and expected != lastip:
            ip_display = expected
        elif expected:
            ip_display = expected
        elif lastip:
            ip_display = lastip
        else:
            ip_display = "-"
        self.ctrl_ip_label.config(text=f"IP: {ip_display}")

        try:
            winch_ip_display = (getattr(self, "winch_host", "") or "").strip() or "-"
            self.winch_ip_label.config(text=f"IP: {winch_ip_display}")
        except Exception:
            pass
        try:
            if hasattr(self, "_tab_winch_possrc_var"):
                self._tab_winch_possrc_var.set(getattr(self, 'winch_pos_source', '--'))
            if hasattr(self, "_tab_winch_rs_var"):
                self._tab_winch_rs_var.set(getattr(self, 'winch_rs_status', '--'))
        except Exception:
            pass

        # Update live controller/joystick display fields
        try:
            joy_pct = float(cs.get("joystick", 0.0) or 0.0)
            joy_raw = float(cs.get("joystick_raw", 0.0) or 0.0)
            if hasattr(self, "_tab_joy_current_var"):
                self._tab_joy_current_var.set(f"{joy_raw:+.3f}")
            if hasattr(self, "_tab_ctrl_pos_var"):
                self._tab_ctrl_pos_var.set(f"{joy_pct:+.1f}%")
        except Exception:
            pass
        try:
            if hasattr(self, "_tab_winch_pos_var"):
                p = self.state.pos_m
                self._tab_winch_pos_var.set("--" if p is None else f"{p:0.3f} m")
        except Exception:
            pass

        self._redraw_freed_top_view()
        self._redraw_freed_side_view()
        self._update_freed_input_ui()
        self._redraw_run_live_section()
        self._refresh_setup_action_buttons()
        # Update top position + speed display
        try:
            pos = getattr(self.state, "pos_m", None)
            if hasattr(self, "top_pos_var"):
                if pos is None:
                    self.top_pos_var.set("--")
                else:
                    self.top_pos_var.set(f"{self._current_position_relative_m():0.2f} m")
            v = abs(float(getattr(self, "current_speed_mps", 0.0)))
            if hasattr(self, "top_speed_var"):
                self.top_speed_var.set(f"{v:0.2f} m/s   |   {v*3.6:0.2f} km/h")
        except Exception:
            pass


        self.root.after(50, self._update_timer)

    def _arduino_poll_timer(self):
        try:
            while True:
                line = self.arduino_rx.get_nowait()
                self._handle_arduino_line(line)
        except queue.Empty:
            pass
        self.root.after(50, self._arduino_poll_timer)

    def _handle_arduino_line(self, line: str):
        self.arduino_status.last_seen = time.time()
        self._last_winch_status_rx_ts = self.arduino_status.last_seen
        self.arduino_status.connected = True
        line = str(line or "").strip()
        if line.startswith("W1PTS_AUX"):
            try:
                idx = int(line.replace("W1PTS_AUX", "").strip()) - 1
                if 0 <= idx < 4:
                    self._handle_aux_action(idx, source="w1pts")
                    self._force_hmi_display_update()
            except Exception:
                pass
            return
        if line.startswith("W1P_HMI_STATUS|"):
            try:
                fields = _parse_kv_line(line)
                now_hmi = time.time()
                self.w1pts_last_seen = now_hmi
                self.w1pts_connected_reported = str(fields.get("w1p_ts", fields.get("w1pts", "0"))).strip() == "1"
                self.w1pts_version = fields.get("version", "")
                try:
                    self.w1pts_age_ms = int(float(fields.get("age_ms", 999999)))
                except Exception:
                    self.w1pts_age_ms = 999999
            except Exception:
                pass
            return
        if line.startswith(("OK", "ERR")):
            try:
                now_log = time.time()
                last_line = str(getattr(self, "_last_w1p_okerr_log_line", "") or "")
                last_ts = float(getattr(self, "_last_w1p_okerr_log_ts", 0.0) or 0.0)
                # Safety STOP acknowledgements can arrive repeatedly while SRVR is holding a faulted zero state.
                # Log the first one and then only if a different OK/ERR appears or enough time has passed.
                suppress = False
                if line == "OK STOP" and last_line == line and (now_log - last_ts) < 60.0:
                    suppress = True
                elif line.startswith("OK AUTO_DRIVE") and last_line == line and (now_log - last_ts) < 30.0:
                    suppress = True
                elif line.startswith("OK SW_SRVON") and last_line == line and (now_log - last_ts) < 5.0:
                    suppress = True
                elif line == last_line and line.startswith("OK") and (now_log - last_ts) < 2.0:
                    suppress = True
                if not suppress:
                    self._last_w1p_okerr_log_line = line
                    self._last_w1p_okerr_log_ts = now_log
                    _app_log(f"[W1P] {line}")
            except Exception:
                _app_log(f"[W1P] {line}")
            if line.startswith("ERR"):
                self._set_status(line)
            self._refresh_drive_control_button()
            return
        if not line.startswith("STATUS"):
            return
        parts = line.split()
        fields = {}
        for p in parts[1:]:
            if "=" in p:
                k, v = p.split("=", 1)
                fields[k] = v

        try:
            if "POS_M" in fields:
                _new_pos = float(fields["POS_M"])
                if self._sanity_accept_winch_position(_new_pos, fields):
                    self.state.pos_m = _new_pos
            if "SPAN_M" in fields:
                self.state.total_length_m = float(fields["SPAN_M"])
            if "NL" in fields:
                self.state.near_limit.position_m = float(fields["NL"])
            if "FL" in fields:
                self.state.far_limit.position_m = float(fields["FL"])
            if "RAW_POS" in fields:
                self.winch_raw_pos_units = int(float(fields["RAW_POS"]))
            if "UPM" in fields:
                self.winch_units_per_m = float(fields["UPM"])
                if hasattr(self, "_tab_winch_units_var"):
                    editing_units = bool(getattr(self, "_tab_winch_units_user_editing", False))
                    try:
                        entry = getattr(self, "_tab_winch_units_entry", None)
                        if entry is not None and self.root.focus_get() is entry:
                            editing_units = True
                    except Exception:
                        pass
                    try:
                        if time.time() < float(getattr(self, "_tab_winch_units_hold_until", 0.0) or 0.0):
                            editing_units = True
                    except Exception:
                        pass
                    if not editing_units:
                        self._tab_winch_units_var.set(f"{self.winch_units_per_m:0.1f}")
            if "WRITE_EN" in fields:
                self.winch_drive_writes_enabled = str(fields.get("WRITE_EN", "0")).strip() in ("1", "true", "True", "ON", "on")
                self._refresh_drive_control_button()
            if "NO_MOTION" in fields:
                self.winch_no_motion_feedback_fault = str(fields.get("NO_MOTION", "0")).strip() in ("1", "true", "True", "ON", "on")
            if "SRVON_OUT" in fields:
                self.winch_srvon_output = str(fields.get("SRVON_OUT", "0")).strip() in ("1", "true", "True", "ON", "on")
            if "SRVON_READY" in fields:
                self.winch_srvon_ready = str(fields.get("SRVON_READY", "0")).strip() in ("1", "true", "True", "ON", "on")
            if "SRVON_IN" in fields:
                self.winch_srvon_input = str(fields.get("SRVON_IN", "0")).strip() in ("1", "true", "True", "ON", "on")
            if "SW_SRVON" in fields:
                self.winch_sw_srvon = str(fields.get("SW_SRVON", "0")).strip() in ("1", "true", "True", "ON", "on")
            if "SW_SRVON_READY" in fields:
                self.winch_sw_srvon_ready = str(fields.get("SW_SRVON_READY", "0")).strip() in ("1", "true", "True", "ON", "on")
                if self.winch_sw_srvon_ready:
                    self.winch_srvon_ready = True
            if "LEAD_CFG" in fields:
                self.winch_leadshine_config = str(fields.get("LEAD_CFG", "--")).strip()
                self.winch_leadshine_actual = {
                    "P00.01": str(fields.get("CTRL_MODE", "--")).strip(),
                    "P05.29": str(fields.get("RS_FMT", "--")).strip(),
                    "P05.30": str(fields.get("RS_BAUD", "--")).strip(),
                    "P05.31": str(fields.get("RS_ID", "--")).strip(),
                    "P00.01_read": str(fields.get("CFG_CTRL", "--")).strip(),
                    "P05.29_read": str(fields.get("CFG_FMT", "--")).strip(),
                    "P05.30_read": str(fields.get("CFG_BAUD", "--")).strip(),
                    "P05.31_read": str(fields.get("CFG_ID", "--")).strip(),
                    "P04.00": str(fields.get("DI1_ASSIGN", fields.get("DI5_ASSIGN", "--"))).strip(),
                    "P04.00_ok": str(fields.get("DI1_CFG", fields.get("DI5_CFG", "0"))).strip(),
                    "P04.04": str(fields.get("LEGACY_DI5_ASSIGN", "--")).strip(),
                    "P04.04_conflict": str(fields.get("LEGACY_DI5_CONFLICT", "0")).strip(),
                    "P04.04_clear": str(fields.get("LEGACY_DI5_CLEAR", "0")).strip(),
                    "SRVON_OUT": str(fields.get("SRVON_OUT", "0")).strip(),
                    "SRVON_READY": str(fields.get("SRVON_READY", "0")).strip(),
                    "SRVON_IN": str(fields.get("SRVON_IN", "0")).strip(),
                    "SRVON_PIN": str(fields.get("SRVON_PIN", "--")).strip(),
                    "SW_SRVON": str(fields.get("SW_SRVON", "0")).strip(),
                    "SW_SRVON_READY": str(fields.get("SW_SRVON_READY", "0")).strip(),
                    "P04.10": str(fields.get("DO1_ASSIGN", "--")).strip(),
                    "P04.10_ok": str(fields.get("DO1_CFG", "0")).strip(),
                    "position_read": str(fields.get("POS_READ", "0")).strip(),
                    "output_io_read": str(fields.get("IO_READ", "0")).strip(),
                    "SRDY": str(fields.get("SRDY", "0")).strip(),
                    "READY": str(fields.get("READY", "0")).strip(),
                    "OUT_IO": str(fields.get("OUT_IO", "--")).strip(),
                    "exception": str(fields.get("MB_EX", "0")).strip(),
                }
            if "VEL_MPS" in fields:
                self.current_speed_mps = float(fields["VEL_MPS"])
            if "REQ_VEL_MPS" in fields:
                self.requested_speed_mps = float(fields["REQ_VEL_MPS"])
            if "PROFILE_VEL_MPS" in fields:
                self.profile_speed_mps = float(fields["PROFILE_VEL_MPS"])
            if "CMD_VEL_MPS" in fields:
                self.drive_command_speed_mps = float(fields["CMD_VEL_MPS"])
                self.last_winch_output = self.drive_command_speed_mps
            if "ACC_MODE" in fields:
                self.winch_accel_mode_reported = str(fields["ACC_MODE"])
            if "ACCEL" in fields:
                self.winch_accel_reported = float(fields["ACCEL"])
            if "DECEL" in fields:
                self.winch_decel_reported = float(fields["DECEL"])
            if "CROSS" in fields:
                self.winch_crossover_reported = float(fields["CROSS"])
            if "POS_SRC" in fields:
                _src = str(fields["POS_SRC"]).strip()
                if _src.upper() == "SIM":
                    self.winch_pos_source = "Software"
                elif _src.upper() == "DRIVE":
                    if bool(getattr(self, "winch_no_motion_feedback_fault", False)):
                        self.winch_pos_source = "Drive (No Motion Feedback)"
                    elif self.winch_drive_writes_enabled:
                        self.winch_pos_source = "Drive (Command Armed)"
                    elif bool(getattr(self, "winch_srvon_output", False)) and not bool(getattr(self, "winch_srvon_ready", False)):
                        self.winch_pos_source = "Drive (Servo Enable Settling)"
                    elif bool(getattr(self, "winch_srvon_output", False)):
                        self.winch_pos_source = "Drive (Servo Enable Output ON)"
                    elif bool(getattr(self, "winch_sw_srvon_ready", False)):
                        self.winch_pos_source = "Drive (DI1 SRV-ON NC Ready / Waiting Arm)"
                    else:
                        self.winch_pos_source = "Drive (Read / Waiting Enable)"
                else:
                    self.winch_pos_source = _src
            if "ESTOP" in fields:
                # ESTOP is the physical W1P E-stop input only. Newer W1P firmware
                # also reports SAFETY/SAFETY_SRC for derived fail-safe conditions
                # such as RS485 loss. Older builds used ESTOP=1 for both, so use
                # ESTOP_SRC to avoid mislabelling an RS485 fault as E-Stop W1P.
                prev_w1p_estop = bool(getattr(self, "_w1p_estop_active", False))
                estop_asserted = str(fields.get("ESTOP", "0")).strip() not in ("0", "false", "False", "OFF", "off")
                estop_source = str(fields.get("ESTOP_SRC", "")).strip().upper()
                self._w1p_estop_active = bool(estop_asserted and estop_source in ("", "W1P", "LOCAL"))
                if self._w1p_estop_active != prev_w1p_estop:
                    _app_log(f"[W1P-E-Stop] {'ACTIVE' if self._w1p_estop_active else 'CLEAR'}")
                if self._w1p_estop_active:
                    self.state.estop_active = True
                    self._send_safety_stop_limited(force=(not prev_w1p_estop))
            modbus_val = fields.get("RS_STAT", fields.get("MODBUS", None))
            if modbus_val is not None:
                prev_rs = str(getattr(self, "winch_rs_status", "Disconnected"))
                rs_raw = str(modbus_val).strip().upper()
                cfg_state = str(fields.get("LEAD_CFG", "MISMATCH")).strip().upper()
                cfg_ok = cfg_state == "OK"
                cfg_read_fault = cfg_state in ("READ_FAULT", "READ-FAULT", "READFAULT")
                feedback_ok = str(fields.get("MODBUS", "0")).strip().upper() in ("1", "OK", "CONNECTED", "TRUE", "ON")
                drive_ready_ok = str(fields.get("READY", "0")).strip().upper() in ("1", "OK", "READY", "TRUE", "ON")
                position_read_ok = str(fields.get("POS_READ", "0")).strip().upper() in ("1", "OK", "TRUE", "ON")
                output_io_read_ok = str(fields.get("IO_READ", "0")).strip().upper() in ("1", "OK", "TRUE", "ON")
                do1_cfg_ok = str(fields.get("DO1_CFG", "0")).strip().upper() in ("1", "OK", "TRUE", "ON")
                sready_ok = str(fields.get("SRDY", "0")).strip().upper() in ("1", "OK", "READY", "TRUE", "ON")
                strict_feedback_ok = (
                    feedback_ok and drive_ready_ok and position_read_ok and
                    output_io_read_ok and do1_cfg_ok and sready_ok
                )

                if rs_raw in ("1", "OK", "CONNECTED") and cfg_ok and strict_feedback_ok:
                    self.winch_rs_status = "Connected"
                elif rs_raw in ("1", "OK", "CONNECTED") and cfg_read_fault:
                    self.winch_rs_status = "Configuration Read Fault"
                elif rs_raw in ("1", "OK", "CONNECTED") and not cfg_ok:
                    self.winch_rs_status = "Configuration Fault"
                elif rs_raw in ("1", "OK", "CONNECTED") and cfg_ok and not strict_feedback_ok:
                    self.winch_rs_status = "Feedback Fault"
                elif rs_raw in ("WAIT", "WAITING", "--"):
                    self.winch_rs_status = "Waiting"
                else:
                    self.winch_rs_status = "Disconnected"

                changed = self.winch_rs_status != prev_rs
                if changed:
                    _app_log(f"[RS485-Link] {self.winch_rs_status}")
                    actual = getattr(self, "winch_leadshine_actual", {}) or {}
                    if self.winch_rs_status == "Configuration Read Fault":
                        failed = []
                        for param in ("P00.01", "P05.29", "P05.30", "P05.31"):
                            read_flag = str(actual.get(f"{param}_read", "--")).strip().lower()
                            if read_flag in ("0", "false", "off", "no"):
                                failed.append(param)
                        failed_text = ", ".join(failed) if failed else "not identified by older W1P firmware"
                        _app_log(
                            "[RS485-Config-Read] Failed register(s): "
                            f"{failed_text}; last Modbus exception={actual.get('exception', '0')}"
                        )
                    elif self.winch_rs_status == "Configuration Fault":
                        _app_log(
                            "[RS485-Config] Actual "
                            f"P00.01={actual.get('P00.01', '--')}, "
                            f"P05.29={actual.get('P05.29', '--')}, "
                            f"P05.30={actual.get('P05.30', '--')}, "
                            f"P05.31={actual.get('P05.31', '--')}, "
                            f"P04.00={actual.get('P04.00', '--')} "
                            f"(DI1 SRV-ON NC OK={actual.get('P04.00_ok', '0')}), "
                            f"legacy P04.04/DI5={actual.get('P04.04', '--')} "
                            f"(conflict={actual.get('P04.04_conflict', '0')}, clear={actual.get('P04.04_clear', '0')}); "
                            "required P00.01=6, P05.29=4 (8N1), P05.30=6 (115200), P05.31=1, P04.00=0x83/131, legacy P04.04/DI5 not SRV-ON"
                        )
                    elif self.winch_rs_status == "Feedback Fault":
                        _app_log(
                            "[RS485-Feedback] Link/config valid but drive feedback is not safe: "
                            f"POS_READ={actual.get('position_read', '0')}, "
                            f"IO_READ={actual.get('output_io_read', '0')}, "
                            f"P04.10={actual.get('P04.10', '--')} "
                            f"(SRDY assignment OK={actual.get('P04.10_ok', '0')}), "
                            f"SRDY={actual.get('SRDY', '0')}, "
                            f"READY={actual.get('READY', '0')}, "
                            f"OUT_IO={actual.get('OUT_IO', '--')}, "
                            f"NO_MOTION={getattr(self, 'winch_no_motion_feedback_fault', False)}"
                        )

                if self.winch_rs_status != "Connected":
                    self.state.estop_active = True
                    self.goto_target_m = None
                    self._send_safety_stop_limited(force=changed)
                else:
                    self._last_safety_stop_ts = 0.0
            self._update_limits_ui()
        except Exception:
            pass


# ------------------------------------------------------------
# v26.08.17.01 modern locked-design UI skin
# ------------------------------------------------------------
from hv_p2p_modern_ui import install_modern_ui as _install_modern_ui
_install_modern_ui(HVP2PServerApp, globals())


# ------------------------------------------------------------
# Entry point
# ------------------------------------------------------------

def main():
    _hide_windows_console()
    root = tk.Tk()
    HVP2PServerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
