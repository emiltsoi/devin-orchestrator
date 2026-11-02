"""Shared pytest configuration for the devin-orchestrator test suite."""

import os
import sys
from pathlib import Path

import pytest

# Ensure the repository root is on sys.path so `import devin_orchestrator`
# works no matter where pytest is invoked from.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(autouse=True)
def _isolate_devin_env(monkeypatch):
    """Clear ambient DEVIN_* env vars so host config doesn't pollute tests.

    ConfigLoader honors DEVIN_* overrides by design; machines with a real
    ~/.devin-orchestrator install set them user-wide, which silently defeats
    file-based test configs (and path containment, when *_DIR vars point at
    the real global root). Tests that exercise the override path set vars
    explicitly via patch.dict/monkeypatch after this fixture runs.
    """
    for var in [k for k in os.environ if k.startswith("DEVIN_")]:
        monkeypatch.delenv(var, raising=False)
