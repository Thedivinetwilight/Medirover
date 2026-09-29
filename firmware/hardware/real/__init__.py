"""Real-hardware driver skeletons with safety interlocks (milestone M8).

Everything here is deterministic and testable without hardware (inject a
MemoryBoard). Physical wiring/ports are the M9/M10 boundary.
"""

from firmware.hardware.real.battery import BatteryMonitor, BatteryState
from firmware.hardware.real.encoders import EncoderPair
from firmware.hardware.real.estop import EstopLatch
from firmware.hardware.real.hardware import DEFAULT_CHANNELS, RealHardware
from firmware.hardware.real.motor_driver import DualMotorDriver, MotorCommandResult, MotorFault
from firmware.hardware.real.ports import Board, MemoryBoard

__all__ = [
    "BatteryMonitor",
    "BatteryState",
    "Board",
    "DEFAULT_CHANNELS",
    "DualMotorDriver",
    "EncoderPair",
    "EstopLatch",
    "MemoryBoard",
    "MotorCommandResult",
    "MotorFault",
    "RealHardware",
]
