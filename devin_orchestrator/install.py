#!/usr/bin/env python3
"""Deprecated launcher; use `devin-orchestrator install`."""
from __future__ import annotations

import sys

from devin_orchestrator.cli_install import install_py_main

if __name__ == "__main__":
    sys.exit(install_py_main(sys.argv[1:]))
