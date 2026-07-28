"""Devin Orchestrator workflow engine package."""

import sys
from pathlib import Path

# The workflow engine modules use legacy absolute imports such as
# ``from config_loader import ...`` that depend on the engine directory being
# on ``sys.path``. When this directory is installed as the
# ``devin_orchestrator`` package, make sure the package directory itself is on
# the path so those imports resolve in either layout.
_WORKFLOW_ENGINE_DIR = Path(__file__).parent
if str(_WORKFLOW_ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(_WORKFLOW_ENGINE_DIR))
