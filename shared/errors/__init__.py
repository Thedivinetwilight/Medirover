"""Typed error model (master directive §18).

Errors carry a machine-readable code, a category, a severity, a
recoverability hint, and a recommended action. Nothing is swallowed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ErrorCategory(StrEnum):
    USER_ERROR = "USER_ERROR"
    CONFIG_ERROR = "CONFIG_ERROR"
    COMMUNICATION_ERROR = "COMMUNICATION_ERROR"
    HARDWARE_ERROR = "HARDWARE_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    PROTOCOL_ERROR = "PROTOCOL_ERROR"
    SAFETY_ERROR = "SAFETY_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass(frozen=True)
class ErrorCode:
    code: str
    category: ErrorCategory
    default_severity: str = "ERROR"
    recoverable: bool = True
    recommended_action: str = "inspect logs and retry"


# --- Configuration ---------------------------------------------------------
CONFIG_MISSING = ErrorCode(
    "CONFIG_MISSING",
    ErrorCategory.CONFIG_ERROR,
    "ERROR",
    False,
    "provide the missing configuration value",
)
CONFIG_INVALID = ErrorCode(
    "CONFIG_INVALID",
    ErrorCategory.CONFIG_ERROR,
    "ERROR",
    False,
    "fix the configuration and restart",
)

# --- Protocol --------------------------------------------------------------
PROTOCOL_MALFORMED = ErrorCode(
    "PROTOCOL_MALFORMED",
    ErrorCategory.PROTOCOL_ERROR,
    "WARNING",
    True,
    "sender must resend with a well-formed frame",
)
PROTOCOL_INVALID = ErrorCode(
    "PROTOCOL_INVALID",
    ErrorCategory.PROTOCOL_ERROR,
    "WARNING",
    True,
    "sender must fix the payload and resend",
)
PROTOCOL_STALE = ErrorCode(
    "PROTOCOL_STALE",
    ErrorCategory.PROTOCOL_ERROR,
    "WARNING",
    True,
    "sync clocks or discard the message",
)
PROTOCOL_DUPLICATE = ErrorCode(
    "PROTOCOL_DUPLICATE",
    ErrorCategory.PROTOCOL_ERROR,
    "DEBUG",
    True,
    "no action; message already processed",
)
PROTOCOL_OUT_OF_ORDER = ErrorCode(
    "PROTOCOL_OUT_OF_ORDER",
    ErrorCategory.PROTOCOL_ERROR,
    "WARNING",
    True,
    "resend in order or accept reordering policy",
)
PROTOCOL_UNKNOWN_TYPE = ErrorCode(
    "PROTOCOL_UNKNOWN_TYPE",
    ErrorCategory.PROTOCOL_ERROR,
    "WARNING",
    True,
    "upgrade firmware/backend to a matching version",
)
PROTOCOL_VERSION_MISMATCH = ErrorCode(
    "PROTOCOL_VERSION_MISMATCH",
    ErrorCategory.PROTOCOL_ERROR,
    "ERROR",
    False,
    "align protocol versions on both sides",
)

# --- Communication ---------------------------------------------------------
COMMUNICATION_LOST = ErrorCode(
    "COMMUNICATION_LOST",
    ErrorCategory.COMMUNICATION_ERROR,
    "WARNING",
    True,
    "wait for automatic reconnection",
)
COMMUNICATION_TIMEOUT = ErrorCode(
    "COMMUNICATION_TIMEOUT",
    ErrorCategory.COMMUNICATION_ERROR,
    "WARNING",
    True,
    "check link and retry",
)
COMMUNICATION_REJECTED = ErrorCode(
    "COMMUNICATION_REJECTED",
    ErrorCategory.COMMUNICATION_ERROR,
    "ERROR",
    False,
    "see reject payload for reason",
)

# --- Safety ----------------------------------------------------------------
SAFETY_E_STOP = ErrorCode(
    "SAFETY_E_STOP",
    ErrorCategory.SAFETY_ERROR,
    "CRITICAL",
    True,
    "release e-stop, then run recovery",
)
SAFETY_FAULT = ErrorCode(
    "SAFETY_FAULT",
    ErrorCategory.SAFETY_ERROR,
    "CRITICAL",
    True,
    "clear the fault cause and request recovery",
)
SAFETY_INVALID_TRANSITION = ErrorCode(
    "SAFETY_INVALID_TRANSITION",
    ErrorCategory.SAFETY_ERROR,
    "ERROR",
    False,
    "this is a software defect; report it",
)
SAFETY_CONSTRAINT = ErrorCode(
    "SAFETY_CONSTRAINT",
    ErrorCategory.SAFETY_ERROR,
    "ERROR",
    True,
    "command rejected by safety; no operator action needed",
)

# --- Database --------------------------------------------------------------
DB_UNAVAILABLE = ErrorCode(
    "DB_UNAVAILABLE",
    ErrorCategory.DATABASE_ERROR,
    "CRITICAL",
    True,
    "check database availability and disk space",
)
DB_INTEGRITY = ErrorCode(
    "DB_INTEGRITY",
    ErrorCategory.DATABASE_ERROR,
    "CRITICAL",
    False,
    "restore from last valid checkpoint",
)

# --- API / generic ---------------------------------------------------------
VALIDATION_FAILED = ErrorCode(
    "VALIDATION_FAILED",
    ErrorCategory.USER_ERROR,
    "WARNING",
    True,
    "correct the request and retry",
)
NOT_FOUND = ErrorCode(
    "NOT_FOUND",
    ErrorCategory.USER_ERROR,
    "WARNING",
    True,
    "check the identifier",
)
INTERNAL_UNEXPECTED = ErrorCode(
    "INTERNAL_UNEXPECTED",
    ErrorCategory.INTERNAL_ERROR,
    "CRITICAL",
    False,
    "report as software defect",
)


@dataclass
class MediroverError(Exception):
    """Base typed error. `code.code` is stable and safe to log/emit."""

    code: ErrorCode = INTERNAL_UNEXPECTED
    message: str = ""
    source: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        message: str = "",
        *,
        code: ErrorCode | None = None,
        source: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code or INTERNAL_UNEXPECTED
        self.message = message or self.code.code
        self.source = source
        self.details = details or {}
        super().__init__(self.message)

    @property
    def category(self) -> ErrorCategory:
        return self.code.category

    @property
    def severity(self) -> str:
        return self.code.default_severity

    @property
    def recoverable(self) -> bool:
        return self.code.recoverable

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.code,
            "message": self.message,
            "category": self.code.category.value,
            "severity": self.code.default_severity,
            "source": self.source,
            "recoverable": self.code.recoverable,
            "recommended_action": self.code.recommended_action,
            "details": self.details,
        }


class ConfigError(MediroverError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, code=CONFIG_INVALID, source="config", details=details)


class ConfigMissingError(MediroverError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, code=CONFIG_MISSING, source="config", details=details)
