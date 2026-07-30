"""
Model routing resolver.

Resolves the final devin-cli model for a given (agent, phase_type) pair using
the precedence defined in config.yaml:

    1. model_overrides[agent]
    2. models[phase_type]
    3. model_profile
    4. default_model

All keys are optional. Empty strings and missing keys fall through to the
next layer. The final fallback is the ``default_model`` field on
``GlobalConfig``.
"""

from __future__ import annotations

from typing import Protocol


class _ConfigLike(Protocol):
    """Structural type for the subset of GlobalConfig used by resolve_model.

    Allows tests to pass a lightweight stand-in without constructing a full
    GlobalConfig (which requires Path fields).
    """

    default_model: str
    model_profile: str
    models: dict[str, str] | None
    model_overrides: dict[str, str] | None


def resolve_model(
    agent: str | None,
    phase_type: str | None,
    config: _ConfigLike,
) -> str:
    """Resolve the model to use for a dispatch.

    Precedence (first non-empty wins):
        1. ``config.model_overrides[agent]``
        2. ``config.models[phase_type]``
        3. ``config.model_profile``
        4. ``config.default_model``

    Args:
        agent: Optional agent name (e.g. "coder", "reviewer").
        phase_type: Optional phase type (e.g. "plan", "execute", "verify").
        config: A GlobalConfig (or compatible object) carrying the routing
            fields.

    Returns:
        A model ID string. Never empty unless ``default_model`` is itself
        empty, in which case that empty string is returned as-is.
    """
    overrides = config.model_overrides or {}
    if agent and agent in overrides:
        candidate = overrides[agent]
        if isinstance(candidate, str) and candidate:
            return candidate

    models = config.models or {}
    if phase_type and phase_type in models:
        candidate = models[phase_type]
        if isinstance(candidate, str) and candidate:
            return candidate

    profile = getattr(config, "model_profile", "") or ""
    if isinstance(profile, str) and profile:
        return profile

    return config.default_model


__all__ = ["resolve_model"]
