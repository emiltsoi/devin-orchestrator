"""Devin Orchestrator workflow engine package."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("devin-orchestrator")
except PackageNotFoundError:
    __version__ = "0.1.7"
