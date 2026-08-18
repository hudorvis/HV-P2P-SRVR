#!/usr/bin/env python3
"""Focused regression tests for safety/motion/calibration protocol behaviour."""
from __future__ import annotations

import json
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
b = HVP2PBackend(version="26.08.17.15", smoke_test=True)

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

    # Setup is now a true draft. Editing it must not change the live values used
    # by Run, motion, networking or saved config until Apply is pressed.
    b.beginSetupEdit()
    original_ctrl_ip = b.ctrlIp
    original_mode_1 = b.driveMode1Name
    original_deadband = b.joystickDeadband
    original_ctrl_aux0 = b.ctrlAuxAssignments[0]
    original_w1p_aux4 = b.w1pAuxAssignments[4]
    b.setSetupNetwork("CTRL", "172.20.1.210")
    b.setSetupJoystickDeadband(3.5)
    b.setSetupDriveModeValue(0, "max_speed_mps", 18.0)
    b.setSetupDriveModeValue(0, "goto_speed_mps", 7.0)
    b.renameSetupDriveMode(0, "Shared Mode")
    b.setSetupAuxAssignment("CTRL", 0, "Preset 1 Save")
    b.setSetupAuxAssignment("W1P", 4, "Preset 10 Save")
    assert b.ctrlIp == original_ctrl_ip
    assert b.driveMode1Name == original_mode_1
    assert abs(float(b.joystickDeadband) - original_deadband) < 1e-9
    assert b.setupDraft["ctrl_ip"] == "172.20.1.210"
    assert b.setupDraft["drive_modes"][0]["name"] == "Shared Mode"
    assert abs(float(b.setupDraft["drive_modes"][0]["max_speed_mps"]) - 18.0) < 1e-9
    assert b.setupDraft["ctrl_aux_assignments"][0] == "Preset 1 Save"
    assert b.setupDraft["w1p_aux_assignments"][4] == "Preset 10 Save"
    assert b.ctrlAuxAssignments[0] == original_ctrl_aux0 and b.w1pAuxAssignments[4] == original_w1p_aux4
    # Re-entering Setup (page navigation) must preserve unapplied edits.
    b.beginSetupEdit()
    assert b.setupDraft["drive_modes"][0]["name"] == "Shared Mode"
    b.resetSetupSettings()
    assert b.setupDraft["ctrl_ip"] == original_ctrl_ip
    assert b.setupDraft["drive_modes"][0]["name"] == original_mode_1
    b.beginSetupEdit()
    b.setSetupJoystickDeadband(4.0)
    b.renameSetupDriveMode(0, "Applied Shared Mode")
    b.setSetupAuxAssignment("CTRL", 0, "Preset 1 Save")
    b.setSetupAuxAssignment("W1P", 4, "Preset 10 Save")
    b.applySetupSettings()
    assert abs(float(b.joystickDeadband) - 4.0) < 1e-9
    assert b.driveMode1Name == "Applied Shared Mode" == b.driveModes[0]["name"]
    assert b.ctrlAuxAssignments[0] == "Preset 1 Save" and b.w1pAuxAssignments[4] == "Preset 10 Save"
    # Run has immediate-save semantics. A later Setup Reset must use that latest
    # live/saved value rather than an older Setup snapshot.
    b.renameDriveMode(0, "Run Saved Mode")
    b.beginSetupEdit()
    b.renameSetupDriveMode(0, "Unapplied Setup Mode")
    b.resetSetupSettings()
    assert b.setupDraft["drive_modes"][0]["name"] == "Run Saved Mode"

    # Joystick Calibration is a real three-step Left/Centre/Right wizard. Moving
    # the stick while it is open must never generate motion, and the captured
    # values must produce a centred, full-scale corrected axis.
    b._not_calibrated = False
    now = time.time(); b._ctrl_rx_times.clear(); b._ctrl_rx_times.extend([now - 0.05, now])
    b.w1p.last_seen = now; b.winch_rs_status = "Connected"; b._ctrl_flags = 0
    b.state.near_limit.position_m = 0.0; b.state.far_limit.position_m = 100.0; b.state.pos_m = 50.0
    b._ctrl_axis = 0.75
    b.last_sent_vel = 1.0; b.requested_speed_mps = 1.0
    # If invoked after a service calibration, opening joystick calibration must
    # close that calibration and return W1P service mode to its normal state.
    b.calibration_open = True; b.calibration_type = "Limit"; b._last_service_mode_sent = 1
    b.openJoystickCalibration()
    assert not b.calibration_open and b._last_service_mode_sent == 0
    assert b.joystickCalibrationOpen and b.joystickCalibrationStep == 0
    b._motion_tick()
    assert abs(b.requested_speed_mps) < 1e-9, "joystick calibration allowed winch motion"
    b._ctrl_axis = -0.82; b.joystickCalibrationNext()
    assert b.joystickCalibrationStep == 1
    b._ctrl_axis = 0.08; b.joystickCalibrationNext()
    assert b.joystickCalibrationStep == 2
    # Reject an endpoint too close to Centre, then accept a proper Right point.
    b._ctrl_axis = 0.10; b.joystickCalibrationNext()
    assert b.joystickCalibrationOpen and b.joystickCalibrationError
    live_cal_before = (b.joystick_cal_left, b.joystick_cal_centre, b.joystick_cal_right)
    saved_before = json.loads(b._config_path.read_text())["joystick_calibration"]
    b._ctrl_axis = 0.91; b.joystickCalibrationNext()
    assert not b.joystickCalibrationOpen and not b.joystickCalibrationError
    # Wizard completion is staged like every other Setup setting.
    assert (b.joystick_cal_left, b.joystick_cal_centre, b.joystick_cal_right) == live_cal_before
    assert b.setupDraft["joystick_calibration"] == {"left":-0.82, "centre":0.08, "right":0.91}
    saved_mid = json.loads(b._config_path.read_text())["joystick_calibration"]
    assert saved_mid == saved_before
    b.applySetupSettings()
    assert abs(b._calibrated_joystick(-0.82) + 1.0) < 1e-9
    assert abs(b._calibrated_joystick(0.08)) < 1e-9
    assert abs(b._calibrated_joystick(0.91) - 1.0) < 1e-9
    saved = json.loads(b._config_path.read_text())["joystick_calibration"]
    assert abs(float(saved["left"]) + 0.82) < 1e-9
    assert abs(float(saved["centre"]) - 0.08) < 1e-9
    assert abs(float(saved["right"]) - 0.91) < 1e-9
    # Setup Apply deliberately reinitialises controller link state. Simulate the
    # next normal CTRL/W1P heartbeat before testing the neutral-return release.
    now = time.time(); b._ctrl_rx_times.clear(); b._ctrl_rx_times.extend([now - 0.05, now])
    b.w1p.last_seen = now; b.winch_rs_status = "Connected"; b._ctrl_flags = 0

    # Completing at full Right must not turn into an immediate live motion command.
    assert b._joystick_neutral_required
    b._ctrl_axis = 0.91; b.last_sent_vel = 1.0; b.requested_speed_mps = 1.0
    b._motion_tick()
    assert abs(b.requested_speed_mps) < 1e-9 and b._joystick_neutral_required
    b._ctrl_axis = 0.08; b._motion_tick()
    assert abs(b.requested_speed_mps) < 1e-9 and not b._joystick_neutral_required

    # Cancel while displaced has the same neutral-return interlock and does not
    # alter the last accepted calibration values.
    before_cancel = (b.joystick_cal_left, b.joystick_cal_centre, b.joystick_cal_right)
    b.openJoystickCalibration(); b._ctrl_axis = -0.70; b.joystickCalibrationNext(); b.cancelJoystickCalibration()
    assert (b.joystick_cal_left, b.joystick_cal_centre, b.joystick_cal_right) == before_cancel
    assert b._joystick_neutral_required
    b._ctrl_axis = b.joystick_cal_centre; b._motion_tick()
    assert not b._joystick_neutral_required and abs(b.requested_speed_mps) < 1e-9
    # A user-configured 0% operating deadband must not make the release interlock
    # impossible to clear at Centre.
    old_deadband = b.joystick_deadband_pct
    b.joystick_deadband_pct = 0.0; b._joystick_neutral_required = True
    b._ctrl_axis = b.joystick_cal_centre; b._motion_tick()
    assert not b._joystick_neutral_required and abs(b.requested_speed_mps) < 1e-9
    b.joystick_deadband_pct = old_deadband

    # Electrical reversal is also valid: physical Left must still map to -1.
    b.joystick_cal_left, b.joystick_cal_centre, b.joystick_cal_right = 0.80, 0.10, -0.70
    assert abs(b._calibrated_joystick(0.80) + 1.0) < 1e-9
    assert abs(b._calibrated_joystick(0.10)) < 1e-9
    assert abs(b._calibrated_joystick(-0.70) - 1.0) < 1e-9
    # Restore identity calibration so legacy motion assertions remain unchanged.
    b.joystick_cal_left, b.joystick_cal_centre, b.joystick_cal_right = -1.0, 0.0, 1.0
    b._save_config(); b._saved_setup_snapshot = b._setup_snapshot()

    # The deadband remains the proven 5% by default, but is now the Setup value.
    b._not_calibrated = False
    now = time.time(); b._ctrl_rx_times.clear(); b._ctrl_rx_times.extend([now - 0.05, now])
    b.w1p.last_seen = now; b.winch_rs_status = "Connected"; b._ctrl_flags = 0
    b.state.near_limit.position_m = 0.0; b.state.far_limit.position_m = 100.0; b.state.pos_m = 50.0
    b._ctrl_axis = 0.03
    b.goto_target_m = None
    b.last_sent_vel = 0.5
    b.requested_speed_mps = 0.5
    b._motion_tick()
    assert abs(b.requested_speed_mps) < 1e-9, "configured joystick deadband not applied"

    # Locked Log page filters operate over a parallel structured model while the
    # original plain text log remains available for Save Log.
    b._log("[W1P] RS485 disconnected warning")
    b._log("[Free-D] packet received")
    net = b.filteredLogEntries("Network", "Warning", "rs485")
    freed = b.filteredLogEntries("Free-D", "All", "packet")
    assert net and net[-1]["source"] == "W1P"
    assert freed and freed[-1]["source"] == "FREE-D"
    assert "RS485 disconnected warning" in b.logText

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

    # Free-D is also a true draft. Display-unit conversion and preview changes
    # happen in the draft only; the applied Free-D state remains unchanged.
    b.skate_weight_kg = 25.0
    b.beginFreeDEdit()
    applied_input_port = b.freeDInputPort
    applied_highline = b.highlineMode
    b.setWeightUnit("Skate", "lbs")
    assert abs(float(b.freeDDraft["skate_weight_value"]) - 55.1155655) < 1e-4
    b.setWeightValue("Skate", 44.0924524)
    assert abs(b.skate_weight_kg - 25.0) < 1e-9
    assert abs(float(b.freeDDraft["skate_weight_kg"]) - 20.0) < 1e-4
    b.setWeightUnit("Skate", "kg")
    assert abs(float(b.freeDDraft["skate_weight_value"]) - 20.0) < 1e-4

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
    assert b.freeDInputPort == applied_input_port and b.highlineMode == applied_highline
    assert b.freeDDraft["input_port"] == 5001 and b.freeDDraft["highline_mode"] == "Dual Highline"
    assert abs(float(b.freeDDraft["cable_weight_value"]) - 4.5) < 1e-4
    assert abs(float(b.freeDDraft["cable_tension_value"]) - 100.0) < 1e-4
    staged_highline = b.freeDDraft["highline_mode"]
    b.beginFreeDEdit()
    assert b.freeDDraft["highline_mode"] == staged_highline, "Free-D draft was lost on page navigation"
    b.resetFreeDSettings()

    # The operator banner rolls all lower-level faults up to CTRL/W1P names.
    # Connection loss to both must read exactly CTRL & W1P (no RS485/ADS text).
    now = time.time()
    b._srvr_estop = False
    b._ctrl_estop = False
    b._w1p_estop = False
    b._ctrl_flags = 0
    b._ctrl_rx_times.clear()
    b.w1p.last_seen = now
    b.winch_rs_status = "Connected"
    b.state.estop_active = True
    assert b.bannerText == "E-Stop | CTRL", b.bannerText
    b._ctrl_rx_times.extend([now - 0.05, now])
    b.w1p.last_seen = 0.0
    assert b.bannerText == "E-Stop | W1P", b.bannerText
    b._ctrl_rx_times.clear()
    assert b.bannerText == "E-Stop | CTRL & W1P", b.bannerText
    # Restore healthy links for the remaining tests.
    now = time.time()
    b._ctrl_rx_times.extend([now - 0.05, now])
    b.w1p.last_seen = now
    b.winch_rs_status = "Connected"

    # Skate/camera-package weight and Single/Dual Highline must materially
    # affect the Free-D sag calculation; these fields must not be decorative.
    b.state.near_limit.position_m = 0.0
    b.state.far_limit.position_m = 100.0
    b.state.pos_m = 50.0
    # Geometry points are deliberately inboard. Near/Far, not P1/P5, define
    # the physical cable supports and the complete Free-D X domain.
    b.geometry = [
        {"name":"P1","x":10.0,"y":0.0,"z":0.0},
        {"name":"P2","x":30.0,"y":0.0,"z":None},
        {"name":"P3","x":50.0,"y":0.0,"z":None},
        {"name":"P4","x":70.0,"y":0.0,"z":None},
        {"name":"P5","x":90.0,"y":0.0,"z":0.0},
    ]
    span_profile = b._cable_profile(samples=101)
    assert abs(span_profile[0]["x"] - 0.0) < 1e-9
    assert abs(span_profile[-1]["x"] - 100.0) < 1e-9
    b.cable_weight_kg100m = 0.0
    b.cable_tension_kg = 100.0
    b.skate_weight_kg = 20.0
    b.highline_mode = "Single Highline"
    single_y = b._xyz()[1]
    b.highline_mode = "Dual Highline"
    dual_y = b._xyz()[1]
    assert single_y < dual_y < 0.0, (single_y, dual_y)
    assert abs(single_y + 5.0) < 1e-6 and abs(dual_y + 2.5) < 1e-6

    # The loaded-path profile is independent of the current parked position.
    # This is important for offline Free-D configuration: changing Single/Dual
    # must visibly alter the whole-run sag preview even if the skate is at Near.
    b.state.pos_m = 0.0
    b.cable_weight_kg100m = 0.0
    b.cable_tension_kg = 100.0
    b.skate_weight_kg = 20.0
    b.highline_mode = "Single Highline"
    single_profile_mid = b._cable_profile(samples=101, moving_skate_path=True)[50]["y"]
    b.highline_mode = "Dual Highline"
    dual_profile_mid = b._cable_profile(samples=101, moving_skate_path=True)[50]["y"]
    assert single_profile_mid < dual_profile_mid < 0.0, (single_profile_mid, dual_profile_mid)

    # The Free-D loaded-path preview uses the same sag equation as live XYZ.
    # Changing cable tension must immediately change the calculated sag.
    b.skate_weight_kg = 0.0
    b.cable_weight_kg100m = 4.5
    b.highline_mode = "Single Highline"
    b.cable_tension_kg = 100.0
    nominal_self_weight_mid = b._cable_profile(samples=101, moving_skate_path=True)[50]["y"]
    assert abs(nominal_self_weight_mid + 0.5625) < 1e-9, nominal_self_weight_mid
    b.cable_tension_kg = 50.0
    low_tension_profile = b._cable_profile(samples=101, moving_skate_path=True)
    low_mid = low_tension_profile[len(low_tension_profile)//2]["y"]
    b.cable_tension_kg = 200.0
    high_tension_profile = b._cable_profile(samples=101, moving_skate_path=True)
    high_mid = high_tension_profile[len(high_tension_profile)//2]["y"]
    assert low_mid < high_mid <= 0.0, (low_mid, high_mid)

    # Every Free-D sag input must materially participate in the same canonical
    # model used by the UI and Free-D Y output.
    # Keep P1/P5 inboard for every physical-sag assertion below.
    b.state.pos_m = 50.0
    b.skate_weight_kg = 20.0
    b.cable_weight_kg100m = 4.5
    b.cable_tension_kg = 100.0
    b.highline_mode = "Single Highline"
    base_y = b._xyz()[1]

    b.skate_weight_kg = 40.0
    heavier_skate_y = b._xyz()[1]
    assert heavier_skate_y < base_y, (heavier_skate_y, base_y)

    b.skate_weight_kg = 20.0
    b.cable_weight_kg100m = 9.0
    heavier_cable_y = b._xyz()[1]
    assert heavier_cable_y < base_y, (heavier_cable_y, base_y)

    b.cable_weight_kg100m = 4.5
    b.cable_tension_kg = 200.0
    higher_tension_y = b._xyz()[1]
    assert higher_tension_y > base_y, (higher_tension_y, base_y)

    b.cable_tension_kg = 100.0
    b.highline_mode = "Dual Highline"
    dual_loaded_y = b._xyz()[1]
    assert dual_loaded_y > base_y, (dual_loaded_y, base_y)

    # Free-D Y at the live skate must be exactly the canonical sag curve value
    # (before output offset/inversion), not a second independent calculation.
    b.highline_mode = "Single Highline"
    direct_y = b._cable_y_at(50.0, b.geometry, b.cable_weight_kg100m,
                             b.cable_tension_kg, b.skate_weight_kg,
                             b.highline_mode, 50.0)
    assert abs(b._xyz()[1] - direct_y) < 1e-9

    # Top-view Z is a complete Near-to-Far line defined by P1/P5. Because P1
    # and P5 are inboard here, Z must extrapolate through them to both supports.
    # P2/P4 are deliberately moved outside P1/P5 in X to prove sorting the Y
    # interpolation cannot steal the P1/P5 identity from the Z definition.
    b.geometry[1]["x"] = 5.0
    b.geometry[3]["x"] = 95.0
    b.geometry[0]["z"] = 1.0
    b.geometry[4]["z"] = 5.0
    z_profile = b._cable_profile(samples=17)
    assert len(z_profile) >= 17
    assert abs(z_profile[0]["z"] - 0.5) < 1e-9
    assert abs(z_profile[len(z_profile)//2]["z"] - 3.0) < 1e-9
    assert abs(z_profile[-1]["z"] - 5.5) < 1e-9
    b.geometry[0]["z"] = 0.0
    b.geometry[4]["z"] = 0.0
    # Restore the requested nominal values for the staged Apply test.
    b.cable_weight_kg100m = 4.5
    b.cable_tension_kg = 100.0
    b.skate_weight_kg = 20.0
    b.highline_mode = "Dual Highline"

    b.beginFreeDEdit()
    previous_output_ip = b.freeDOutputIp
    previous_skate_kg = b.skate_weight_kg
    b.setFreeDNetwork("Output", "IP", "172.20.1.30")
    b.setFreeDNetwork("Output", "Port", "5002")
    b.setFreeDNetwork("Output", "FPS", "50")
    b.setFreeDOffset("Output", "X", 1.25)
    b.setFreeDInvert("Output", "Y", True)
    b.setFreeDOffset("Input", "Pan", -2.5)
    b.setFreeDInvert("Input", "Zoom", True)
    b.setGeometryPoint(1, "x", 26.0)
    b.setGeometryPoint(1, "y", 6.0)
    old_p2_z = b.freeDDraft["geometry"][1]["z"]
    b.setGeometryPoint(1, "z", 99.0)
    assert b.freeDDraft["geometry"][1]["z"] == old_p2_z is None, "P2 Z must remain disabled"

    # Every sag input must update the staged Free-D Side View immediately,
    # while the live/applied Free-D state remains untouched until Apply.
    b.setWeightValue("Skate", 20.0)
    b.setWeightValue("Cable", 4.5)
    b.setWeightValue("Tension", 100.0)
    b.setHighlineMode("Single Highline")
    draft_base = b.freeDPreviewCableProfile[len(b.freeDPreviewCableProfile)//2]["y"]
    b.setWeightValue("Skate", 40.0)
    assert b.freeDPreviewCableProfile[len(b.freeDPreviewCableProfile)//2]["y"] < draft_base
    b.setWeightValue("Skate", 20.0)
    b.setWeightValue("Cable", 9.0)
    assert b.freeDPreviewCableProfile[len(b.freeDPreviewCableProfile)//2]["y"] < draft_base
    b.setWeightValue("Cable", 4.5)
    b.setWeightValue("Tension", 200.0)
    assert b.freeDPreviewCableProfile[len(b.freeDPreviewCableProfile)//2]["y"] > draft_base
    b.setWeightValue("Tension", 100.0)
    b.setHighlineMode("Dual Highline")
    assert b.freeDPreviewCableProfile[len(b.freeDPreviewCableProfile)//2]["y"] > draft_base

    b.setLensType("i24")
    b.setLensScale("Manual")
    b.setLensCalibration("zoom_wide", -100.0)
    b.captureLens("zoom_tele", 1000.0)
    # Nothing above is live before Apply.
    assert b.freeDOutputIp == previous_output_ip
    assert abs(b.skate_weight_kg - previous_skate_kg) < 1e-9
    assert b.freeDDraft["target_ip"] == "172.20.1.30"
    b.applyFreeDSettings()
    assert b.freeDOutputIp == "172.20.1.30" and b.freeDOutputPort == 5002
    assert abs(b.freeDOutputRate - 50.0) < 1e-9
    assert abs(b.freeDOutputOffsets["X"] - 1.25) < 1e-9
    assert b.freeDOutputInverts["Y"] is True
    assert abs(b.freeDInputOffsets["Pan"] + 2.5) < 1e-9
    assert b.freeDInputInverts["Zoom"] is True
    assert b.lensType == "i24" and b.lensScale == "Manual"

    b.setFreeDNetwork("Output", "IP", "10.0.0.99")
    b.setWeightValue("Skate", 99.0)
    # An unrelated config save must not accidentally commit staged Free-D edits.
    b.setPresetName(1, "Unrelated Save")
    saved = json.loads(b._config_path.read_text())
    assert saved["free_d"]["target_ip"] == "172.20.1.30"
    assert abs(float(saved["free_d"]["skate_weight_kg"]) - float(b.skate_weight_kg)) < 1e-4
    b.resetFreeDSettings()
    assert b.freeDOutputIp == "172.20.1.30", "Free-D Reset changed applied state"
    assert b.freeDDraft["target_ip"] == "172.20.1.30", "Free-D Reset did not restore last Apply"

    # Transferable Save/Load Config uses an external JSON file. Loading is staged:
    # Setup Apply commits Setup + Run-only values, while Free-D remains pending
    # until its own Apply is pressed.
    transfer_dir = Path(TMP_HOME.name) / "transfer"
    transfer_dir.mkdir(parents=True, exist_ok=True)
    applied_export_mode = b.driveMode1Name
    applied_export_fd_ip = b.freeDOutputIp
    b.beginSetupEdit(); b.renameSetupDriveMode(0, "UNAPPLIED EXPORT MODE")
    b.beginFreeDEdit(); b.setFreeDNetwork("Output", "IP", "10.9.8.7")
    exported = b.exportConfigFile((transfer_dir / "camera_A").as_uri())
    assert exported.endswith(".hvp2p.json") and Path(exported).is_file()
    transfer = json.loads(Path(exported).read_text())
    assert transfer["drive_modes"][0]["name"] == applied_export_mode, "Save Config exported unapplied Setup draft"
    assert transfer["free_d"]["target_ip"] == applied_export_fd_ip, "Save Config exported unapplied Free-D draft"
    b.resetSetupSettings(); b.resetFreeDSettings()
    transfer["ctrl_ip"] = "172.20.1.222"
    transfer["drive_modes"][0]["name"] = "Imported Mode"
    transfer["preset_names"][0] = "Imported Preset"
    transfer["free_d"]["target_ip"] = "172.20.1.77"
    import_path = transfer_dir / "imported.hvp2p.json"
    import_path.write_text(json.dumps(transfer, indent=2))
    old_live_ctrl = b.ctrlIp
    old_live_fd_ip = b.freeDOutputIp
    assert b.stageConfigFile(import_path.as_uri())
    assert b.ctrlIp == old_live_ctrl and b.freeDOutputIp == old_live_fd_ip
    assert b.setupDraft["ctrl_ip"] == "172.20.1.222"
    assert b.freeDDraft["target_ip"] == "172.20.1.77"
    b.applySetupSettings()
    assert b.ctrlIp == "172.20.1.222" and b.driveMode1Name == "Imported Mode"
    assert b.preset_names[0] == "Imported Preset"
    assert b.freeDOutputIp == old_live_fd_ip, "Setup Apply prematurely applied imported Free-D settings"
    b.applyFreeDSettings()
    assert b.freeDOutputIp == "172.20.1.77"

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
