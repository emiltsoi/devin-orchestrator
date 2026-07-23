"""
Transport Adapter Interface

Defines the contract that all transport adapters must implement.
A transport adapter moves inputs to a sub-agent and returns outputs,
implementing the dispatch contract described in adapters/SCHEMA.md.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class InvocationResult:
    """Result from a transport adapter invocation"""

    success: bool
    output: str
    error: str
    exit_code: int


class TransportAdapter(ABC):
    """Abstract base class for transport adapters"""

    @abstractmethod
    def __init__(self, adapter_path: str, workspace: str | None = None, **kwargs: Any):
        """Initialize the adapter with platform-specific settings"""
        pass

    @abstractmethod
    def invoke(
        self,
        prompt: str,
        timeout: int = 120,
        focused_context: list[str] | None = None,
        correction_artifact: str | None = None,
        enable_skills: bool = True,
    ) -> InvocationResult:
        """
        Invoke the adapter with a prompt and return the result.

        Args:
            prompt: The prompt to send to the sub-agent
            timeout: Maximum time to wait for completion
            focused_context: Optional list of artifact paths to include
            correction_artifact: Optional path to correction artifact
            enable_skills: Whether to inject skills into the prompt

        Returns:
            InvocationResult with success status and output
        """
        pass

    @abstractmethod
    def capabilities(self) -> list[str]:
        """Return the capabilities supported by this adapter"""
        pass
