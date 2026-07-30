"""Shared base class for the composed McpServer and its mixins."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections import defaultdict

    from devin_orchestrator.models.config import GlobalConfig


class McpServerBase:
    """Base class providing cross-mixin attributes.

    Mixins inherit from this class so mypy can resolve ``self.<attr>``
    references without disabling attribute checking for whole files.
    ``__getattr__`` returns ``Any`` for any remaining missing attribute so
    type-checking degrades gracefully instead of raising ``attr-defined``.
    """

    # Server metadata
    PROTOCOL_VERSION: str
    SERVER_NAME: str
    SERVER_VERSION: str

    # Constants
    MAX_MESSAGE_SIZE: int
    MAX_OUTPUT_BYTES: int
    RATE_LIMIT_MAX_CALLS: int
    RATE_LIMIT_WINDOW_SECONDS: int
    DEFAULT_TIMEOUT_SECONDS: int
    MIN_TIMEOUT_SECONDS: int
    MAX_TIMEOUT_SECONDS: int

    # Runtime state
    workspace: str | None
    config: GlobalConfig
    stdin: Any
    stdout: Any
    _framing: str | None
    _tool_call_history: defaultdict[str, list[float]]
    _message_log: Any
    _calls_log: Any
    _closed: bool
    _tool_required: dict[str, list[str]]

    def __getattr__(self, name: str) -> Any:
        raise AttributeError(name)
