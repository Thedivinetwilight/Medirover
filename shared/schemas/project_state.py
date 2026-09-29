"""Schema for the canonical project state checkpoint (master directive §27).

The single file is recovery/PROJECT_STATE.json (rendered as
recovery/PROJECT_STATE.md). It is updated in place, never duplicated.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from shared.utils.timeutil import now_utc


class StatusLevel(StrEnum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"
    UNKNOWN = "UNKNOWN"


class MilestoneInfo(BaseModel):
    current: str = "M0"
    completed: list[str] = Field(default_factory=list)
    next: str | None = None


class TestStatus(BaseModel):
    last_run: datetime | None = None
    passed: int = 0
    failed: int = 0
    errors: int = 0
    total: int = 0
    history_path: str = "results/test_history.jsonl"


class RepositoryInfo(BaseModel):
    remote: str = "origin"
    branch: str = ""


class ProjectState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    updated_at: datetime
    version: str = "0.1.0"
    milestone: MilestoneInfo = Field(default_factory=MilestoneInfo)
    status: dict[str, StatusLevel] = Field(default_factory=dict)
    features: dict[str, Any] = Field(default_factory=lambda: {"completed": [], "active": None, "blocked": []})
    known_issues: list[str] = Field(default_factory=list)
    test_status: TestStatus = Field(default_factory=TestStatus)
    hardware_status: str = "NO_HARDWARE_ATTACHED"
    simulation_status: str = "NOT_STARTED"
    next_task: str = ""
    last_commit: str | None = None
    repository: RepositoryInfo = Field(default_factory=RepositoryInfo)
    decisions_index: str = "docs/LEGACY_DECISIONS.md"

    @field_validator("status")
    @classmethod
    def _status_keys(cls, v: dict[str, StatusLevel]) -> dict[str, StatusLevel]:
        allowed = {
            "architecture",
            "backend",
            "frontend",
            "firmware",
            "communication",
            "database",
            "safety",
            "testing",
            "simulation",
            "hardware",
            "security",
            "performance",
            "storage",
            "reproducibility",
        }
        unknown = set(v) - allowed
        if unknown:
            raise ValueError(f"unknown status keys: {sorted(unknown)}")
        return v

    @classmethod
    def new(
        cls,
        *,
        branch: str = "",
        version: str = "0.1.0",
        next_task: str = "",
        updated_at: datetime | None = None,
    ) -> ProjectState:
        return cls(
            updated_at=updated_at or now_utc(),
            version=version,
            repository=RepositoryInfo(branch=branch),
            next_task=next_task,
        )
