"""Hardware interface contracts.

Application/node logic depends only on these interfaces, never on a
specific board (master directive §9). Simulated implementations ship
with v0.1; real drivers (M10) implement the same contracts.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from shared.types import SourceKind


class ISensor(ABC):
    @property
    @abstractmethod
    def sensor_id(self) -> str: ...

    @property
    @abstractmethod
    def unit(self) -> str: ...

    @abstractmethod
    def read(self) -> float:
        """Latest value. Raises nothing; health is reported via healthy()."""

    @abstractmethod
    def healthy(self) -> bool: ...


class IMotorController(ABC):
    @abstractmethod
    def set_speed(self, left_mps: float, right_mps: float) -> None:
        """Target speeds in m/s (signed, + = forward). Safety-gated upstream."""

    @abstractmethod
    def get_speeds(self) -> tuple[float, float]:
        """Current (actual) speeds in m/s."""

    @abstractmethod
    def stop(self) -> None:
        """Immediate commanded stop (coast to zero)."""


class IPowerMonitor(ABC):
    @abstractmethod
    def battery_voltage(self) -> float | None:
        """Latest battery voltage, or None when no reading is available.

        None must be surfaced as degraded/unknown, never replaced by a guess.
        """

    @abstractmethod
    def current_draw(self) -> float: ...


class ISafetyInput(ABC):
    """E-stop input. The single highest-priority hardware signal."""

    @abstractmethod
    def e_stop_engaged(self) -> bool: ...


class IStatusOutput(ABC):
    @abstractmethod
    def set_indicators(self, indicators: dict[str, bool]) -> None: ...


class IStorage(ABC):
    @abstractmethod
    def append_jsonl(self, path: str, obj: object) -> None: ...


class ICommunication(ABC):
    """Transport for protocol frames (one JSON object per send)."""

    @property
    @abstractmethod
    def connected(self) -> bool: ...

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...

    @abstractmethod
    async def send(self, frame: str) -> None: ...

    @abstractmethod
    async def recv(self) -> str | None:
        """Next frame, or None when the link was closed."""


class IHardware(ABC):
    """The physical world of one node.

    Both SimulatedHardware and the real-hardware facade implement this;
    node logic depends only on it. ``source_kind`` is the single source of
    truth for where this node's data comes from and is reported to the
    backend in every identify.
    """

    node_id: str
    motors: IMotorController
    safety_input: ISafetyInput

    @property
    @abstractmethod
    def source_kind(self) -> SourceKind: ...

    @abstractmethod
    def step(self, dt: float) -> None:
        """Advance the physical layer by dt seconds (no-op semantics allowed)."""

    @abstractmethod
    def battery_voltage(self) -> float | None:
        """Latest battery voltage, or None when no reading is available.

        None must be surfaced as degraded/unknown, never replaced by a guess.
        """

    @abstractmethod
    def sensors(self) -> list[ISensor]: ...

    @abstractmethod
    def set_indicators(self, indicators: dict[str, bool]) -> None: ...
