"""Shared pytest configuration for the devin-orchestrator test suite."""

import sys
from pathlib import Path

# Ensure the repository root is on sys.path so `import devin_orchestrator`
# works no matter where pytest is invoked from.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
