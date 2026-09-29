"""Fault-injection suite for the real-hardware driver skeletons (M8).

Deterministic: MemoryBoard + explicit input sequences, no timing, no
hardware. These tests pin the safety interlock behavior that the physical
build (M10) must preserve:

- no motion before explicit enable (rule 4/10)
- E-stop latch: immediate, latching, never clearable by software alone
  (rules 5/6)
- zero-velocity stop bypasses every interlock (rule 6)
- over-current latching fault with explicit clear (rule 5/10)
- unknown readings are UNKNOWN, never guessed (rule 11)
- source_kind label integrity end-to-end (rule 13)
"""

from __future__ import annotations

import asyncio

import pytest

from firmware.common.node_context import NodeConfig
from firmware.communication.simulated_transport import MemoryLink
from firmware.hardware.real import (
    BatteryMonitor,
    BatteryState,
    DualMotorDriver,
    EncoderPair,
    EstopLatch,
    MemoryBoard,
    MotorCommandResult,
    MotorFault,
    RealHardware,
)
from firmware.hardware.simulated import SimulatedHardware
from firmware.motion_node.node import MotionNode
from shared.types import SourceKind

# channel map (defaults)
ESTOP, LPWM, LDIR, LEN, RPWM, RDIR, REN, ENC_L, ENC_R, BAT, CUR = range(11)


# ------------------------------------------------------------------ motor


def test_no_motion_before_enable():
    board = MemoryBoard()
    drv = DualMotorDriver(
        board, left_pwm=LPWM, left_dir=LDIR, left_en=LEN,
        right_pwm=RPWM, right_dir=RDIR, right_en=REN, v_max_mps=1.0,
    )
    result = drv.set_speed(0.5, 0.5)
    assert result is MotorCommandResult.REJECTED_NOT_ENABLED
    assert board.pwm_read_duty(LPWM) == 0.0
    assert board.pwm_read_duty(RPWM) == 0.0
    assert board.gpio_read(LEN) is False
    assert board.gpio_read(REN) is False


def test_enable_allows_motion_with_direction():
    board = MemoryBoard()
    drv = DualMotorDriver(
        board, left_pwm=LPWM, left_dir=LDIR, left_en=LEN,
        right_pwm=RPWM, right_dir=RDIR, right_en=REN, v_max_mps=1.0,
    )
    drv.enable()
    assert drv.set_speed(0.5, -1.0) is MotorCommandResult.APPLIED
    assert board.pwm_read_duty(LPWM) == pytest.approx(0.5)
    assert board.gpio_read(LDIR) is False  # + = forward
    assert board.pwm_read_duty(RPWM) == pytest.approx(1.0)  # clamped at v_max
    assert board.gpio_read(RDIR) is True  # - = reverse
    drv.stop()
    assert board.pwm_read_duty(LPWM) == 0.0 and board.gpio_read(LEN) is False


def test_estop_blocks_commands_mid_motion():
    board = MemoryBoard()
    drv = DualMotorDriver(
        board, left_pwm=LPWM, left_dir=LDIR, left_en=LEN,
        right_pwm=RPWM, right_dir=RDIR, right_en=REN,
    )
    drv.enable()
    assert drv.set_speed(0.5, 0.5) is MotorCommandResult.APPLIED
    drv.set_estop_latched(True)
    assert board.pwm_read_duty(LPWM) == 0.0  # zeroed immediately
    assert drv.set_speed(0.5, 0.5) is MotorCommandResult.REJECTED_E_STOP
    # software fault-clear must NOT lift the E-stop latch
    assert drv.clear_fault() is False
    drv.enable()
    assert drv.set_speed(0.5, 0.5) is MotorCommandResult.REJECTED_E_STOP
    # release is only legal after physical de-assertion (facade does this)
    drv.set_estop_latched(False)
    assert drv.enabled is False  # fresh explicit enable required
    assert drv.set_speed(0.5, 0.5) is MotorCommandResult.REJECTED_NOT_ENABLED
    drv.enable()
    assert drv.set_speed(0.5, 0.5) is MotorCommandResult.APPLIED


def test_overcurrent_fault_latches_and_clears():
    board = MemoryBoard()
    drv = DualMotorDriver(
        board, left_pwm=LPWM, left_dir=LDIR, left_en=LEN,
        right_pwm=RPWM, right_dir=RDIR, right_en=REN,
    )
    drv.enable()
    assert drv.set_speed(0.5, 0.5) is MotorCommandResult.APPLIED
    drv.trip(MotorFault.OVERCURRENT)
    assert drv.fault is MotorFault.OVERCURRENT
    assert drv.set_speed(0.5, 0.5) is MotorCommandResult.REJECTED_FAULT
    assert board.pwm_read_duty(LPWM) == 0.0
    assert drv.clear_fault() is True
    assert drv.enabled is False  # operator must re-enable explicitly
    assert drv.set_speed(0.5, 0.5) is MotorCommandResult.REJECTED_NOT_ENABLED
    drv.enable()
    assert drv.set_speed(0.2, 0.2) is MotorCommandResult.APPLIED


def test_stop_bypasses_all_interlocks():
    board = MemoryBoard()
    drv = DualMotorDriver(
        board, left_pwm=LPWM, left_dir=LDIR, left_en=LEN,
        right_pwm=RPWM, right_dir=RDIR, right_en=REN,
    )
    drv.enable()
    drv.set_speed(0.5, 0.5)
    drv.trip(MotorFault.OVERCURRENT)
    drv.set_estop_latched(True)
    # outputs are zero in this state, but stop() must also work when they
    # were left live by a port that refused the zero write:
    board.pwm_set_duty(LPWM, 0.7)  # simulate a stuck output
    drv.stop()
    assert board.pwm_read_duty(LPWM) == 0.0
    assert board.gpio_read(LEN) is False


# ------------------------------------------------------------------ e-stop


def test_estop_latch_engages_and_holds():
    board = MemoryBoard()
    latch = EstopLatch(board, ESTOP)
    assert latch.poll() is False
    board.set_input(ESTOP, True)
    assert latch.poll() is True
    board.set_input(ESTOP, False)  # momentary de-assert
    assert latch.engaged is True  # latched: still engaged


def test_estop_latch_cannot_be_cleared_by_software_while_asserted():
    board = MemoryBoard()
    latch = EstopLatch(board, ESTOP)
    board.set_input(ESTOP, True)
    latch.poll()
    assert latch.hardware_reset() is False  # input still asserted
    assert latch.engaged is True
    board.set_input(ESTOP, False)
    assert latch.hardware_reset() is True
    assert latch.engaged is False


# --------------------------------------------------------------- encoders


def test_encoder_velocity_zero_and_stall():
    board = MemoryBoard()
    enc = EncoderPair(board, ENC_L, ENC_R, ticks_per_meter=1000.0)
    enc.prime()
    board.set_counter(ENC_L, 500)  # 0.5 m in 0.5 s = 1 m/s
    board.set_counter(ENC_R, 500)
    v_l, v_r = enc.velocity(0.5)
    assert v_l == pytest.approx(1.0)
    assert v_r == pytest.approx(1.0)
    # no movement -> zero velocity
    assert enc.zero_velocity(0.5) is True
    # stall: commanded motion, no encoder motion
    board.set_counter(ENC_L, 500)
    board.set_counter(ENC_R, 500)
    enc.velocity(0.5)  # consume the flat segment
    l_stall, r_stall = enc.stalled((0.5, 0.0), 0.5)
    assert l_stall is True
    assert r_stall is False


def test_encoder_rejects_unknown_ticks_per_meter():
    board = MemoryBoard()
    with pytest.raises(ValueError):
        EncoderPair(board, ENC_L, ENC_R, ticks_per_meter=0)


# ---------------------------------------------------------------- battery


def test_battery_states_and_unknown():
    board = MemoryBoard()
    mon = BatteryMonitor(board, BAT, low_v=11.5, critical_v=10.5, mv_per_v=1)
    board.set_adc_mv(BAT, 12600)
    assert mon.state() is BatteryState.OK
    board.set_adc_mv(BAT, 11200)
    assert mon.state() is BatteryState.LOW
    board.set_adc_mv(BAT, 10200)
    assert mon.state() is BatteryState.CRITICAL
    board.set_adc_mv(BAT, None)
    assert mon.voltage() is None
    assert mon.state() is BatteryState.UNKNOWN  # never guessed


# --------------------------------------------------------------- facade


def test_facade_estop_auto_stops_motors_and_latches():
    board = MemoryBoard()
    hw = RealHardware("motion-r", board, source_kind=SourceKind.SIMULATED)
    hw.motors_driver.enable()
    hw.motors.set_speed(0.5, 0.5)
    assert board.pwm_read_duty(LPWM) > 0
    board.set_input(ESTOP, True)
    hw.step(0.05)
    assert hw.safety_input.e_stop_engaged() is True
    assert hw.motors_driver.estop_latched is True
    assert board.pwm_read_duty(LPWM) == 0.0
    assert hw.motors.get_speeds() == (0.0, 0.0)
    # a fresh command is rejected while latched
    assert hw.motors_driver.set_speed(0.5, 0.5) is MotorCommandResult.REJECTED_E_STOP


def test_facade_estop_full_lifecycle():
    board = MemoryBoard()
    hw = RealHardware("motion-r", board, source_kind=SourceKind.SIMULATED)
    hw.motors_driver.enable()
    hw.motors.set_speed(0.5, 0.5)
    # operator presses the E-stop
    board.set_input(ESTOP, True)
    hw.step(0.05)
    assert hw.safety_input.e_stop_engaged() is True
    assert hw.acknowledge_estop_reset() is False  # still pressed: cannot release
    assert hw.motors_driver.set_speed(0.5, 0.5) is MotorCommandResult.REJECTED_E_STOP
    # operator releases the button; latch holds until acknowledged
    board.set_input(ESTOP, False)
    assert hw.safety_input.e_stop_engaged() is True
    assert hw.acknowledge_estop_reset() is True
    assert hw.safety_input.e_stop_engaged() is False
    hw.motors_driver.enable()  # fresh explicit enable after an E-stop
    assert hw.motors_driver.set_speed(0.5, 0.5) is MotorCommandResult.APPLIED


def test_facade_overcurrent_trips_on_step():
    board = MemoryBoard()
    hw = RealHardware(
        "motion-r", board, source_kind=SourceKind.SIMULATED, current_limit_a=5.0
    )
    hw.motors_driver.enable()
    hw.motors.set_speed(0.5, 0.5)
    board.set_adc_mv(CUR, 800)  # 8 A > 5 A limit
    hw.step(0.05)
    assert hw.motors_driver.fault is MotorFault.OVERCURRENT
    assert board.pwm_read_duty(LPWM) == 0.0


def test_facade_sensors_never_fabricate_readings():
    board = MemoryBoard()
    hw = RealHardware("motion-r", board, source_kind=SourceKind.SIMULATED)
    sensors = {s.sensor_id: s for s in hw.sensors()}
    # no ADC readings at all: current sensor is unhealthy, value stays 0.0
    assert sensors["motor_current"].healthy() is False
    assert sensors["motor_current"].read() == 0.0
    assert hw.battery_voltage() is None
    board.set_adc_mv(BAT, 12600)
    assert sensors["battery_voltage"].healthy() is True
    assert sensors["battery_voltage"].read() == pytest.approx(12.6)
    # encoders always readable
    board.set_counter(ENC_L, 123)
    assert sensors["encoder_left"].read() == 123.0


def test_facade_indicator_mapping():
    board = MemoryBoard()
    hw = RealHardware("motion-r", board, source_kind=SourceKind.SIMULATED, indicators={"e_stop": 20})
    hw.set_indicators({"e_stop": True, "unknown_indicator": True})
    assert board.gpio_read(20) is True


# ------------------------------------------------- source kind end-to-end


def test_real_hardware_node_identifies_as_hardware():
    board = MemoryBoard()
    hw = RealHardware("motion-real", board, source_kind=SourceKind.HARDWARE)
    client_end, _server_end = MemoryLink.pair()
    config = NodeConfig(
        node_id="motion-real",
        node_name="Real Motion Node",
        node_type="motion",
        capabilities=["telemetry"],
        drive_every_s=0,
        heartbeat_interval_s=0.1,
        telemetry_interval_s=0.1,
    )
    node = MotionNode(config, hw, client_end)
    stop = asyncio.Event()
    stop.set()  # don't run the loop; check the derived identity

    assert node.config.source_kind is SourceKind.HARDWARE
    assert hw.source_kind is SourceKind.HARDWARE
    # and the simulation path still self-labels correctly
    sim_hw = SimulatedHardware("motion-sim", seed=1)
    sim_config = NodeConfig(
        node_id="motion-sim", node_name="Sim", node_type="motion", drive_every_s=0
    )
    sim_node = MotionNode(sim_config, sim_hw, client_end)
    assert sim_node.config.source_kind is SourceKind.SIMULATED


def test_facade_defaults_and_label_policy():
    board = MemoryBoard()
    # default is HARDWARE (this class exists for real wiring)
    assert RealHardware("n", board).source_kind is SourceKind.HARDWARE
    # integrators using a MemoryBoard must relabel SIMULATED (rule 13)
    assert RealHardware("n", board, source_kind=SourceKind.SIMULATED).source_kind is (
        SourceKind.SIMULATED
    )
