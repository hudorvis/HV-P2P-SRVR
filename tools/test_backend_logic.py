#!/usr/bin/env python3
"""Focused regression tests for safety/motion/calibration protocol behaviour."""
from __future__ import annotations

import math
import os
import tempfile
import time
from pathlib import Path

# Keep test config isolated from the runner account.
TMP_HOME = tempfile.TemporaryDirectory(prefix="hvp2p-test-home-")
os.environ["HOME"] = TMP_HOME.name

from PySide6.QtCore import QCoreApplication
from backend import (
    HVP2PBackend,
    CONTROL_PACKET_CODE,
    FLAG_ADS1115_FAULT,
)

app = QCoreApplication.instance() or QCoreApplication([])
b = HVP2PBackend(version="26.08.17.05", smoke_test=True)

try:
    # CTRL packet compatibility (A6 and extended A7).
    import struct
    a6 = bytes([CONTROL_PACKET_CODE, 0x04]) + struct.pack("!f", 0.5) + b"\x00\x00"
    flags, joy = b._parse_control_packet(a6)
    assert flags == 0x04 and abs(joy - 0.5) < 1e-6
    a7 = bytes([0xA7, 0x02, 0x10]) + struct.pack("!f", -0.25) + b"\x00\x00\x00"
    flags, joy = b._parse_control_packet(a7)
    assert flags == 0x0210 and abs(joy + 0.25) < 1e-6

    # Simulate healthy live links for motion tests.
    now = time.time()
    b._ctrl_rx_times.extend([now - 0.05, now])
    b.w1p.last_seen = now
    b.winch_rs_status = "Connected"
    b._ctrl_flags = 0
    b._ctrl_axis = 1.0
    b.state.near_limit.position_m = 0.0
    b.state.far_limit.position_m = 100.0
    b.state.pos_m = 50.0

    # Not Calibrated must be a 5 km/h service state, not an E-stop.
    b._not_calibrated = True
    b._motion_tick()
    assert not b.state.estop_active, "Not Calibrated incorrectly triggered E-stop"
    assert 0.0 < b.requested_speed_mps <= (5.0 / 3.6 + 1e-6), b.requested_speed_mps

    # In normal mode the hard Near limit must block outward travel.
    b._not_calibrated = False
    b.state.pos_m = 0.0
    b._ctrl_axis = -1.0
    b._motion_tick()
    assert abs(b.requested_speed_mps) < 1e-9, "Near hard limit allowed outward motion"

    # ADS1115 fault flag is a fail-safe source.
    b.state.pos_m = 50.0
    b._ctrl_axis = 1.0
    b._ctrl_flags = FLAG_ADS1115_FAULT
    b._motion_tick()
    assert b.state.estop_active, "ADS1115 fault did not enter safety state"
    assert abs(b.requested_speed_mps) < 1e-9
    b._ctrl_flags = 0

    # Presets are stored relative to Near and recalled as absolute positions.
    b.state.near_limit.position_m = 10.0
    b.state.far_limit.position_m = 110.0
    b.state.pos_m = 35.0
    b.savePreset(0)
    assert abs(b.preset_positions[0] - 25.0) < 1e-9
    b.recallPreset(0)
    assert b.goto_target_m is not None and abs(b.goto_target_m - 35.0) < 1e-9

    # Slip re-references to the known saved physical point and clears the
    # startup Not-Calibrated service state.
    b.goto_target_m = None
    b.state.ref_point.position_m = 60.0
    b._not_calibrated = True
    b.slipLimit("Ref")
    assert abs(float(b.state.pos_m) - 60.0) < 1e-9
    assert not b._not_calibrated

    # Battery Change only auto-cancels after going outside then safely returning.
    b.state.near_limit.position_m = 0.0
    b.state.far_limit.position_m = 100.0
    b._not_calibrated = False
    b.calibration_open = False
    b.setBatteryChange(True)
    b.state.pos_m = -0.2
    b._update_battery_change_auto_cancel()
    assert b.battery_change_mode and b._battery_change_went_outside_limits
    b.state.pos_m = 50.0
    b._update_battery_change_auto_cancel()
    assert not b.battery_change_mode

    # Limit Calibration coordinate contract: Near=0, Far positive, Ref inside,
    # and normal calibrated state only after the reference step is saved.
    b._not_calibrated = True
    b.state.pos_m = 12.0
    b.openLimitCalibration()
    b.calibrationNext()  # Near
    assert b.calibration_step == 1 and abs(b.state.near_limit.position_m) < 1e-9
    b.state.pos_m = -100.0
    b.calibrationNext()  # Far
    assert b.calibration_step == 2 and abs(b.state.far_limit.position_m - 100.0) < 1e-9
    b.state.pos_m = 40.0
    b.calibrationNext()  # Ref
    assert b.calibration_step == 3 and abs(b.state.ref_point.position_m - 40.0) < 1e-9
    assert not b._not_calibrated
    b.calibrationNext()  # Done
    assert not b.calibration_open

    # Position sanity filter rejects a physically implausible stationary jump.
    b._not_calibrated = False
    b.state.near_limit.position_m = 0.0
    b.state.far_limit.position_m = 100.0
    b.state.pos_m = 50.0
    b.last_winch_output = 0.0
    b.goto_target_m = None
    b._winch_position_accept_jump_until = 0.0
    b._winch_last_pos_accept_t = time.time()
    assert not b._sanity_accept_winch_position(80.0, {}), "implausible position jump accepted"

    print("BACKEND REGRESSION PASS")
finally:
    b.shutdown()
    TMP_HOME.cleanup()
