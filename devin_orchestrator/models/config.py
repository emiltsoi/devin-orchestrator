"""Pydantic model for global configuration."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GlobalConfig(BaseModel):
    """Global configuration for devin-orchestrator."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="ignore")

    def __getitem__(self, key: str) -> Any:
        try:
            return getattr(self, key)
        except AttributeError as exc:
            raise KeyError(key) from exc

    def __contains__(self, key: str) -> bool:
        return hasattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return getattr(self, key)
        except AttributeError:
            return default

    global_root: Path
    skills_dir: Path
    workflows_dir: Path
    workflow_engine_dir: Path
    devin_cli_path: str
    default_model: str = "swe-1.6"
    default_permission_mode: str = "dangerous"
    session_work_dir: Path
    model_profile: str = ""
    models: dict[str, str] | None = Field(default=None)
    model_overrides: dict[str, str] | None = Field(default=None)
    agent_skills: dict[str, list[str]] | None = Field(default=None)
    dispatch_timeout_seconds: int = 300
    gate_mode: str = "auto"
    gate_bypass_conditions: dict[str, Any] | None = None
    log_max_bytes: int = 10 * 1024 * 1024
    log_backup_count: int = 5
