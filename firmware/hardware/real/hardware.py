"""Real-hardware facade (M8): drivers composed behind the IHardware contract.

This is the skeleton that real boards plug into: every subsystem is a
driver over the channel-based `Board` port. With a `MemoryBoard` it is
fully testable without hardware; with a real board implementation (M9/M10)
the same node code runs unchanged.

Label integrity (rule 13): `source_kind` is declared by the integrator.
The default is HARDWARE because this class only exists for real wiring;
tests that inject a MemoryBoard MUST pass source_kind=SIMULATED so the
label stays truthful end-to-end.
"""

from __future__ import annotations

from firmware.hardware.interfaces import IHardware, IMotorController, ISafetyInput, ISensor
from firmware.hardware.real.battery import BatteryMonitor, BatteryState
from firmware.hardware.real.encoders import EncoderPair
from firmware.hardware.real.estop import EstopLatch
from firmware.hardware.real.motor_driver import DualMotorDriver, MotorFault
from firmware.hardware.real.ports import Board
from shared.types import SourceKind

# Default channel map — a starting point the integrator overrides per wiring.
DEFAULT_CHANNELS = {
    "estop": 0,
    "left_pwm": 1,
    "left_dir": 2,
    "left_en": 3,
    "right_pwm": 4,
    "right_dir": 5,
    "right_en": 6,
    "enc_left": 7,
    "enc_right": 8,
    "battery_adc": 9,
    "current_adc": 10,
}


class _DriverMotors(IMotorController):
    """IMotorController adapter so node code stays driver-agnostic."""

    def __init__(self, driver: DualMotorDriver) -> None:
        self._driver = driver
        self._last: tuple[float, float] = (0.0, 0.0)

    def set_speed(self, left_mps: float, right_mps: float) -> None:
        result = self._driver.set_speed(left_mps, right_mps)
        if result.value == "APPLIED":
            self._last = (left_mps, right_mps)
        else:
            self._last = (0.0, 0.0)

    def get_speeds(self) -> tuple[float, float]:
        """Last applied command (actual wheel speeds come from encoders)."""
        return self._last

    def stop(self) -> None:
        self._driver.stop()
        self._last = (0.0, 0.0)


class _DriverSafetyInput(ISafetyInput):
    def __init__(self, latch: EstopLatch) -> None:
        self._latch = latch

    def e_stop_engaged(self) -> bool:
        return self._latch.poll()


class _ReadingSensor(ISensor):
    """Sensor over a callable reading that may be unavailable (-> degraded).

    Never fabricates: when the reading is None the value is the last valid
    reading (or 0.0 if none ever was) and the sensor is reported unhealthy
    so downstream quality is 'degraded'.
    """

    def __init__(self, sensor_id: str, unit: str, reading) -> None:
        self._id = sensor_id
        self._unit = unit
        self._reading = reading
        self._last_value = 0.0

    @property
    def sensor_id(self) -> str:
        return self._id

    @property
    def unit(self) -> str:
        return self._unit

    def read(self) -> float:
        value = self._reading()
        if value is None:
            return self._last_value
        self._last_value = float(value)
        return self._last_value

    def healthy(self) -> bool:
        return self._reading() is not None


class RealHardware(IHardware):
    def __init__(
        self,
        node_id: str,
        board: Board,
        *,
        source_kind: SourceKind = SourceKind.HARDWARE,
        channels: dict[str, int] | None = None,
        v_max_mps: float = 1.0,
        current_limit_a: float = 5.0,
        ticks_per_meter: float = 2000.0,
        battery_low_v: float = 11.5,
        battery_critical_v: float = 10.5,
        current_mv_per_a: float = 100.0,
        indicators: dict[str, int] | None = None,
    ) -> None:
        self.node_id = node_id
        self._source_kind = source_kind
        self._board = board
        ch = {**DEFAULT_CHANNELS, **(channels or {})}
        self.estop = EstopLatch(board, ch["estop"])
        self.motors_driver = DualMotorDriver(
            board,
            left_pwm=ch["left_pwm"],
            left_dir=ch["left_dir"],
            left_en=ch["left_en"],
            right_pwm=ch["right_pwm"],
            right_dir=ch["right_dir"],
            right_en=ch["right_en"],
            v_max_mps=v_max_mps,
        )
        self.motors = _DriverMotors(self.motors_driver)
        self.safety_input = _DriverSafetyInput(self.estop)
        self.encoders = EncoderPair(board, ch["enc_left"], ch["enc_right"], ticks_per_meter)
        self.battery = BatteryMonitor(
            board, ch["battery_adc"], low_v=battery_low_v, critical_v=battery_critical_v
        )
        self._current_ch = ch["current_adc"]
        self._current_mv_per_a = current_mv_per_a
        self._current_limit_a = current_limit_a
        self._indicator_channels = dict(indicators or {})
        self._sensors = [
            _ReadingSensor("battery_voltage", "V", self.battery_voltage),
            _ReadingSensor("motor_current", "A", self.current_draw),
            _ReadingSensor("encoder_left", "ticks", lambda: float(self.encoders.raw()[0])),
            _ReadingSensor("encoder_right", "ticks", lambda: float(self.encoders.raw()[1])),
        ]
        self.encoders.prime()

    # -- IHardware ---------------------------------------------------------

    @property
    def source_kind(self) -> SourceKind:
        return self._source_kind

    def step(self, dt: float) -> None:
        """Periodic interlock scan (call on the hardware loop cadence)."""
        if self.estop.poll() and not self.motors_driver.estop_latched:
            self.motors_driver.set_estop_latched(True)
            self.motors.stop()  # sync the controller's command cache to zero
        current_a = self.current_draw()
        if current_a is not None and current_a > self._current_limit_a:
            if self.motors_driver.fault is not MotorFault.OVERCURRENT:
                self.motors_driver.trip(MotorFault.OVERCURRENT)

    def battery_voltage(self) -> float | None:
        return self.battery.voltage()

    def sensors(self) -> list[ISensor]:
        return list(self._sensors)

    def set_indicators(self, indicators: dict[str, bool]) -> None:
        for name, on in indicators.items():
            channel = self._indicator_channels.get(name)
            if channel is not None:
                self._board.gpio_write(channel, bool(on))

    def acknowledge_estop_reset(self) -> bool:
        """Operator action: clear the E-stop latch after physically releasing it.

        Returns True only when the physical input was observed de-asserted.
        """
        cleared = self.estop.hardware_reset()
        if cleared:
            self.motors_driver.set_estop_latched(False)
        return cleared

    # -- helpers -----------------------------------------------------------

    def current_draw(self) -> float | None:
        """Motor current in amperes, or None when the ADC has no reading."""
        mv = self._board.adc_read_mv(self._current_ch)
        if mv is None:
            return None
        return mv / self._current_mv_per_a

    def battery_state(self) -> BatteryState:
        return self.battery.state()

    @property
    def commanded_speeds(self) -> tuple[float, float]:
        return self.motors.get_speeds()
