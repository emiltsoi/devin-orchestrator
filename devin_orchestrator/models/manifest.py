"""Pydantic models for workflow manifests."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class _DictModel(BaseModel):
    """Pydantic model that also supports dict-style item access for legacy code."""

    def __getitem__(self, key: str) -> Any:
        try:
            return getattr(self, key)
        except AttributeError as exc:
            raise KeyError(key) from exc

    def __setitem__(self, key: str, value: Any) -> None:
        if key not in self.model_fields:
            raise KeyError(key)
        setattr(self, key, value)

    def __contains__(self, key: str) -> bool:
        return key in self.model_fields

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return getattr(self, key)
        except AttributeError:
            return default


class Gate(_DictModel):
    """A workflow gate definition."""

    id: str
    name: str
    description: str = ""
    type: Literal["human", "auto"]
    # Optional runtime flag used by gate bypass logic.
    mandatory: bool = False


class Stage(_DictModel):
    """A single workflow stage definition."""

    @classmethod
    def ensure(cls, value: Stage | dict[str, Any]) -> Stage:
        """Return a Stage instance, coercing a raw dict if necessary."""
        if isinstance(value, cls):
            return value
        return cls.model_validate(value)

    step: int = 0
    name: str
    skill: str
    description: str = ""
    required_artifacts: list[str] = Field(default_factory=list)
    output_artifacts: list[str] = Field(default_factory=list)
    gate: str | None = Field(default="none")
    optional: bool = Field(default=False)
    # Optional execution caps; not part of the public schema but accepted.
    max_retries: int | str | None = None
    max_gate_request_changes: int | str | None = None


class Manifest(_DictModel):
    """A parsed workflow manifest."""

    @classmethod
    def ensure(cls, value: Manifest | dict[str, Any]) -> Manifest:
        """Return a Manifest instance, coercing a raw dict if necessary."""
        if isinstance(value, cls):
            return value
        return cls.model_validate(value)

    name: str = ""
    description: str = ""
    version: str = ""
    schema_version: int = 1
    session_shape: str = "feature"
    skip_brainstorming: bool = Field(default=False)
    stages: list[Stage] = Field(default_factory=list)
    gates: list[Gate] = Field(default_factory=list)

    @field_validator("schema_version")
    @classmethod
    def _check_schema_version(cls, value: int) -> int:
        if value != 1:
            raise ValueError(f"Unsupported schema version: {value}")
        return value
