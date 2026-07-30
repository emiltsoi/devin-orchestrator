# mypy: disable-error-code=attr-defined

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from devin_orchestrator.security_utils import (  # noqa: E402
    InvalidInputError,
)

if TYPE_CHECKING:
    from devin_orchestrator.stateless_orchestrator import StatelessOrchestrator

logger = logging.getLogger(__name__)


class McpSecurityMixin:

    def _check_rate_limit(self, tool_name: str) -> bool:
        """
        Check if the tool call is within rate limits.

        Args:
            tool_name: Name of the tool being called

        Returns:
            True if the call is allowed, False if rate limit is exceeded
        """
        current_time = time.time()
        # Clean up old calls outside the time window
        self._tool_call_history[tool_name] = [
            timestamp
            for timestamp in self._tool_call_history[tool_name]
            if current_time - timestamp < self.RATE_LIMIT_WINDOW_SECONDS
        ]

        # Check if under the limit
        if len(self._tool_call_history[tool_name]) >= self.RATE_LIMIT_MAX_CALLS:
            return False

        # Record this call
        self._tool_call_history[tool_name].append(current_time)
        return True

    def _validate_timeout(self, timeout: int | None) -> int:
        """
        Validate and normalize a timeout value.

        Args:
            timeout: Optional timeout value in seconds

        Returns:
            Validated timeout in seconds (clamped to MIN/MAX_TIMEOUT_SECONDS)

        Raises:
            InvalidInputError: If timeout is invalid
        """
        if timeout is None:
            return self.DEFAULT_TIMEOUT_SECONDS

        if not isinstance(timeout, int):
            raise InvalidInputError(
                f"Timeout must be an integer, got {type(timeout).__name__}"
            )

        if timeout < self.MIN_TIMEOUT_SECONDS:
            raise InvalidInputError(
                f"Timeout must be at least {self.MIN_TIMEOUT_SECONDS} seconds"
            )

        if timeout > self.MAX_TIMEOUT_SECONDS:
            raise InvalidInputError(
                f"Timeout cannot exceed {self.MAX_TIMEOUT_SECONDS} seconds"
            )

        return timeout

    def _orchestrator_for_call(
        self, arguments: dict, **overrides: Any
    ) -> StatelessOrchestrator:
        """
        Build a StatelessOrchestrator using the per-call workspace if provided,
        otherwise falling back to the server's pre-loaded workspace.
        """
        from devin_orchestrator.stateless_orchestrator import StatelessOrchestrator

        workspace = arguments.get("workspace") or self.workspace
        return StatelessOrchestrator(
            workspace=workspace,
            demo_mode=overrides.get("demo_mode", False),
            timeout=overrides.get("timeout"),
            gate_mode=overrides.get("gate_mode"),
        )
