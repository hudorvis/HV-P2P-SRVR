#!/usr/bin/env python3
"""Focused regression tests for safety/motion/calibration protocol behaviour."""
from __future__ import annotations

import math
import os
import tempfile
import time
import sys
from pathlib import Path

# Make repository modules importable regardless of whether this test is run as
# `python tools/test_backend_logic.py`, `python -m tools.test_backend_logic`, or
# from a CI shell whose script directory becomes sys.path[0].
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
b = HVP2PBackend(version="26.08.17.08", smoke_test=True)

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

    # Operator-editable Run fields persist through the backend interface.
    b.setPresetName(0, "Wide Establish")
    assert b.preset_names[0] == "Wide Establish"
    b.setPresetPosition(0, 22.25)
    assert abs(b.preset_positions[0] - 22.25) < 1e-9
    b.setPresetPosition(0, 1234.0)
    assert abs(b.preset_positions[0] - 100.0) < 1e-9, "manual preset escaped cable span"
    b.setPresetPosition(0, 22.25)
    b.renameDriveMode(0, "Camera Move")
    b.renameDriveMode(1, "Cable Move")
    assert b.drive_modes[0]["name"] == "Camera Move"
    assert b.drive_modes[1]["name"] == "Cable Move"

    # Setup/System edit controls are real backend writes, not display-only fields.
    b.setNetwork("CTRL", "172.20.1.111")
    b.setNetwork("W1P", "172.20.1.112")
    b.setDirection("CTRL", True)
    b.setDirection("W1P", True)
    b.setUnitsPerM(22000.5)
    b.setAccelerationMode("Power")
    b.setDriveMode(1)
    assert b.ctrlIp == "172.20.1.111" and b.w1pIp == "172.20.1.112"
    assert b.ctrlInverted and b.w1pInverted
    assert abs(b.unitsPerM - 22000.5) < 1e-9
    assert b.accelerationMode == "Power" and b.activeDriveMode == 1

    old_vis = bool(b.preset_visible[0])
    b.togglePresetVisible(0)
    assert bool(b.preset_visible[0]) is (not old_vis)
    b.togglePresetVisible(0)
    b.state.pos_m = 5.0
    b.saveLimit("Near")
    assert abs(float(b.state.near_limit.position_m) - 5.0) < 1e-9
    b.state.pos_m = 105.0
    b.saveLimit("Far")
    assert abs(float(b.state.far_limit.position_m) - 105.0) < 1e-9
    b.state.pos_m = 55.0
    b.saveLimit("Ref")
    assert abs(float(b.state.ref_point.position_m) - 55.0) < 1e-9
    b.recallLimit("Ref")
    assert b.goto_target_m is not None

    # Ramping mode changes must convert the existing physical ramp instead of
    # reinterpreting the numeric value. 20 m on a 100 m span == 20%.
    b.state.near_limit.position_m = 0.0
    b.state.far_limit.position_m = 100.0
    b.setRamping("Near", "Distance", 20.0)
    assert abs(b.state.near_limit.ramp_distance_m - 20.0) < 1e-9
    b.changeRampingMode("Near", "Percentage")
    assert b.state.near_limit.ramp_mode == "Percentage"
    assert abs(b.nearRampValue - 20.0) < 1e-9
    b.setRamping("Near", "Percentage", 35.0)
    assert abs(b.state.near_limit.ramp_distance_m - 35.0) < 1e-9
    b.changeRampingMode("Near", "Distance")
    assert b.state.near_limit.ramp_mode == "Distance"
    assert abs(b.nearRampValue - 35.0) < 1e-9

    # Free-D staged page editing: unit changes convert display only, editable
    # values are interpreted in the selected unit, and Reset restores Apply.
    b.static_weight_kg = 25.0
    b.setWeightUnit("Static", "lbs")
    assert abs(b.staticWeightValue - 55.1155655) < 1e-4
    b.setWeightValue("Static", 44.0924524)
    assert abs(b.static_weight_kg - 20.0) < 1e-4
    b.setWeightUnit("Static", "kg")
    assert abs(b.staticWeightValue - 20.0) < 1e-4

    b.setFreeDEnabled("Input", True)
    b.setFreeDEnabled("Output", True)
    b.setFreeDNetwork("Input", "IP", "0.0.0.0")
    b.setFreeDNetwork("Input", "Port", "5001")
    b.setHighlineMode("Dual Highline")
    b.setWeightUnit("Cable", "lbs/100m")
    b.setWeightValue("Cable", b._kg_to_lb(4.5))
    b.setWeightUnit("Cable", "kg/100m")
    b.setWeightUnit("Tension", "lbs")
    b.setWeightValue("Tension", b._kg_to_lb(100.0))
    b.setWeightUnit("Tension", "kg")
    assert b.freeDInputEnabled is True and b.freeDOutputEnabled is True
    assert b.freeDInputPort == 5001 and b.highlineMode == "Dual Highline"
    assert abs(b.cableWeightValue - 4.5) < 1e-4
    assert abs(b.cableTensionValue - 100.0) < 1e-4

    # Static camera-package weight and Single/Dual Highline must materially
    # affect the Free-D sag calculation; these fields must not be decorative.
    b.state.near_limit.position_m = 0.0
    b.state.far_limit.position_m = 100.0
    b.state.pos_m = 50.0
    for idx, x in enumerate((0.0,25.0,50.0,75.0,100.0)):
        b.setGeometryPoint(idx, "x", x)
        b.setGeometryPoint(idx, "y", 0.0)
    b.cable_weight_kg100m = 0.0
    b.cable_tension_kg = 100.0
    b.static_weight_kg = 20.0
    b.highline_mode = "Single Highline"
    single_y = b._xyz()[1]
    b.highline_mode = "Dual Highline"
    dual_y = b._xyz()[1]
    assert single_y < dual_y < 0.0, (single_y, dual_y)
    assert abs(single_y + 5.0) < 1e-6 and abs(dual_y + 2.5) < 1e-6
    # Restore the requested nominal values for the staged Apply test.
    b.cable_weight_kg100m = 4.5
    b.cable_tension_kg = 100.0
    b.static_weight_kg = 20.0
    b.highline_mode = "Dual Highline"

    b.setFreeDNetwork("Output", "IP", "172.20.1.30")
    b.setFreeDNetwork("Output", "Port", "5002")
    b.setFreeDNetwork("Output", "FPS", "50")
    b.setFreeDOffset("Output", "X", 1.25)
    b.setFreeDInvert("Output", "Y", True)
    b.setFreeDOffset("Input", "Pan", -2.5)
    b.setFreeDInvert("Input", "Zoom", True)
    b.setGeometryPoint(1, "x", 26.0)
    b.setGeometryPoint(1, "y", 6.0)
    old_p2_z = b.geometry[1]["z"]
    b.setGeometryPoint(1, "z", 99.0)
    assert b.geometry[1]["z"] == old_p2_z is None, "P2 Z must remain disabled"
    b.setLensType("i24")
    b.setLensScale("Manual")
    b.setLensCalibration("zoom_wide", -100.0)
    b.captureLens("zoom_tele", 1000.0)
    b.applyFreeDSettings()
    assert b.freeDOutputIp == "172.20.1.30" and b.freeDOutputPort == 5002
    assert abs(b.freeDOutputRate - 50.0) < 1e-9
    assert abs(b.freeDOutputOffsets["X"] - 1.25) < 1e-9
    assert b.freeDOutputInverts["Y"] is True
    assert abs(b.freeDInputOffsets["Pan"] + 2.5) < 1e-9
    assert b.freeDInputInverts["Zoom"] is True
    assert b.lensType == "i24" and b.lensScale == "Manual"

    b.setFreeDNetwork("Output", "IP", "10.0.0.99")
    b.setWeightValue("Static", 99.0)
    # An unrelated config save must not accidentally commit staged Free-D edits.
    b.setPresetName(1, "Unrelated Save")
    import json
    saved = json.loads(b._config_path.read_text())
    assert saved["free_d"]["target_ip"] == "172.20.1.30"
    assert abs(float(saved["free_d"]["static_weight_kg"]) - 20.0) < 1e-4
    b.resetFreeDSettings()
    assert b.freeDOutputIp == "172.20.1.30", "Free-D Reset did not restore last Apply"
    assert abs(b.staticWeightValue - 20.0) < 1e-4

    # SRVR status banner E-stop toggles only the software latch and leaves
    # other safety sources to the normal safety aggregation.
    b._srvr_estop = False
    b.toggleSrvrEStop()
    assert b._srvr_estop is True
    b.toggleSrvrEStop()
    assert b._srvr_estop is False

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
