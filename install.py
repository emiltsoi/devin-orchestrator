#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Global Installer for Devin Orchestrator

Installs devin-orchestrator to a global location (~/.devin-orchestrator/)
for use across all workspaces.
"""

import shutil
import os
from pathlib import Path
from typing import Optional


def install(global_root: Optional[Path] = None, source_dir: Optional[Path] = None):
    """
    Install devin-orchestrator to global location
    
    Args:
        global_root: Optional global root path (defaults to ~/.devin-orchestrator/)
        source_dir: Optional source directory (defaults to current directory)
    """
    # Determine paths
    if global_root is None:
        global_root = Path.home() / ".devin-orchestrator"
    
    if source_dir is None:
        source_dir = Path(__file__).parent
    
    global_root = global_root.expanduser()
    source_dir = source_dir.expanduser()
    
    print("=== Installing Devin Orchestrator ===")
    print(f"Source: {source_dir}")
    print(f"Target: {global_root}")
    print()
    
    # Create global root
    global_root.mkdir(parents=True, exist_ok=True)
    print(f"Created global root: {global_root}")
    
    # Copy skills
    source_skills = source_dir / "skills"
    target_skills = global_root / "skills"
    if source_skills.exists():
        if target_skills.exists():
            shutil.rmtree(target_skills)
        shutil.copytree(source_skills, target_skills)
        print(f"Copied skills: {source_skills} -> {target_skills}")
    
    # Copy workflows
    source_workflows = source_dir / "workflows"
    target_workflows = global_root / "workflows"
    if source_workflows.exists():
        if target_workflows.exists():
            shutil.rmtree(target_workflows)
        shutil.copytree(source_workflows, target_workflows)
        print(f"Copied workflows: {source_workflows} -> {target_workflows}")
    
    # Copy workflow engine
    source_engine = source_dir / "workflow-engine"
    target_engine = global_root / "workflow-engine"
    if source_engine.exists():
        if target_engine.exists():
            shutil.rmtree(target_engine)
        shutil.copytree(source_engine, target_engine)
        print(f"Copied workflow engine: {source_engine} -> {target_engine}")
    
    # Copy config
    source_config = source_dir / "config.yaml"
    target_config = global_root / "config.yaml"
    if source_config.exists():
        shutil.copy2(source_config, target_config)
        print(f"Copied config: {source_config} -> {target_config}")
    
    # Create work directory
    work_dir = global_root / "work"
    work_dir.mkdir(parents=True, exist_ok=True)
    print(f"Created work directory: {work_dir}")
    
    print()
    print("=== Installation Complete ===")
    print(f"Global root: {global_root}")
    print(f"Skills: {target_skills}")
    print(f"Workflows: {target_workflows}")
    print(f"Workflow engine: {target_engine}")
    print(f"Config: {target_config}")
    print(f"Work directory: {work_dir}")
    print()
    print("To use devin-orchestrator from any workspace:")
    print("  import sys")
    print("  sys.path.insert(0, '" + str(global_root) + "')")
    print("  from workflow_engine.orchestrator_executor import OrchestratorExecutor")


if __name__ == "__main__":
    import sys
    
    # Parse command line arguments
    global_root = None
    source_dir = None
    
    if len(sys.argv) > 1:
        global_root = Path(sys.argv[1])
    if len(sys.argv) > 2:
        source_dir = Path(sys.argv[2])
    
    install(global_root, source_dir)
