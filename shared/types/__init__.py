"""Enumerations shared across backend, firmware, and tooling.

Every state machine in Medirover uses these types (see shared.fsm).
"""

from __future__ import annotations

from enum import StrEnum


class Severity(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class SourceKind(StrEnum):
    """Where node data comes from. The UI must always display this."""

    SIMULATED = "SIMULATED"
    HARDWARE = "HARDWARE"


class ValidationOutcome(StrEnum):
    """Explicit protocol validation outcomes (master directive §11)."""

    VALID = "VALID"
    INVALID = "INVALID"
    MALFORMED = "MALFORMED"
    STALE = "STALE"
    DUPLICATE = "DUPLICATE"
    OUT_OF_ORDER = "OUT_OF_ORDER"
    UNKNOWN_TYPE = "UNKNOWN_TYPE"
    PROTOCOL_VERSION_MISMATCH = "PROTOCOL_VERSION_MISMATCH"


class SafetyState(StrEnum):
    SAFE = "SAFE"
    READY = "READY"
    ACTIVE = "ACTIVE"
    WARNING = "WARNING"
    FAULT = "FAULT"
    EMERGENCY_STOP = "EMERGENCY_STOP"
    RECOVERY = "RECOVERY"


class SafetyEvent(StrEnum):
    """Events that drive the safety state machine (see shared.safety)."""

    INIT_OK = "INIT_OK"
    COMMAND_ACCEPT = "COMMAND_ACCEPT"
    COMMAND_COMPLETE = "COMMAND_COMPLETE"
    ANOMALY = "ANOMALY"
    ANOMALY_CLEAR = "ANOMALY_CLEAR"
    FAULT = "FAULT"
    E_STOP = "E_STOP"
    E_STOP_RELEASED = "E_STOP_RELEASED"
    CLEAR_REQUESTED = "CLEAR_REQUESTED"
    RECOVERY_OK = "RECOVERY_OK"
    RECOVERY_FAILED = "RECOVERY_FAILED"


class ConnectivityState(StrEnum):
    """Backend's view of a node's connection (see backend.state.node_fsm)."""

    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    ONLINE = "ONLINE"
    STALE = "STALE"
    OFFLINE = "OFFLINE"


class ConnectivityEvent(StrEnum):
    WS_CONNECTED = "WS_CONNECTED"
    IDENTIFY_OK = "IDENTIFY_OK"
    IDENTIFY_FAILED = "IDENTIFY_FAILED"
    WS_CLOSED = "WS_CLOSED"
    HEARTBEAT_OK = "HEARTBEAT_OK"
    HEARTBEAT_LATE = "HEARTBEAT_LATE"
    HEARTBEAT_TIMEOUT = "HEARTBEAT_TIMEOUT"


class MessageDirection(StrEnum):
    NODE_TO_BACKEND = "node_to_backend"
    BACKEND_TO_NODE = "backend_to_node"
    BACKEND_TO_CLIENT = "backend_to_client"
    CLIENT_TO_BACKEND = "client_to_backend"


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TESTING = "testing"
    SIMULATION = "simulation"
    HARDWARE = "hardware"
