#!/bin/bash
# One-click deploy for devin-orchestrator on Linux/macOS.
# This is a thin wrapper around the cross-platform deploy.py.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

python3 "${REPO_DIR}/deploy.py" "$@"
