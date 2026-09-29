"""Hardware interfaces and simulated implementations (master directive §9)."""

from firmware.hardware.interfaces import (
    ICommunication,
    IMotorController,
    IPowerMonitor,
    ISafetyInput,
    ISensor,
    IStatusOutput,
)
from firmware.hardware.simulated import SimulatedHardware

__all__ = [
    "ISensor",
    "IMotorController",
    "IPowerMonitor",
    "ISafetyInput",
    "IStatusOutput",
    "ICommunication",
    "SimulatedHardware",
]
