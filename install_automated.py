#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Automated Installation Script for Devin Orchestrator

This script automates the entire installation process for devin-orchestrator:
1. Clones the repository (if not already cloned)
2. Installs globally to ~/.devin-orchestrator/
3. Sets up the current workspace with workflow manifests

Run this script from any workspace to install devin-orchestrator.
"""

import os
import sys
import subprocess
from pathlib import Path


def run_command(cmd, cwd=None):
    """Run a command and return success status"""
    try:
        # Security: Avoid shell=True to prevent command injection
        # Convert string command to list if needed
        if isinstance(cmd, str):
            # For simple commands, split into list (basic approach)
            # For complex commands, caller should provide list directly
            cmd = cmd.split()
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)


def main():
    print("=== Automated Devin Orchestrator Installation ===")
    print()
    
    # Configuration
    repo_url = "https://github.com/your-username/devin-orchestrator.git"  # TODO: Update with actual repo URL
    install_dir = Path.home() / "devin-orchestrator"
    global_root = Path.home() / ".devin-orchestrator"
    current_dir = Path.cwd()
    
    # Step 1: Clone repository (if not already cloned)
    print("Step 1: Cloning repository...")
    if install_dir.exists():
        print(f"  Repository already exists at {install_dir}")
        print("  Pulling latest changes...")
        success, stdout, stderr = run_command(["git", "pull"], cwd=install_dir)
        if success:
            print("  Repository updated successfully")
        else:
            print(f"  Warning: Could not update repository: {stderr}")
    else:
        print(f"  Cloning repository to {install_dir}...")
        success, stdout, stderr = run_command(["git", "clone", repo_url, str(install_dir)])
        if success:
            print("  Repository cloned successfully")
        else:
            print(f"  Error: Could not clone repository: {stderr}")
            print("  Please clone manually and run install.py")
            sys.exit(1)
    print()
    
    # Step 2: Install globally
    print("Step 2: Installing globally...")
    install_script = install_dir / "install.py"
    if install_script.exists():
        print(f"  Running install.py...")
        success, stdout, stderr = run_command(["python", str(install_script)], cwd=install_dir)
        if success:
            print("  Global installation successful")
        else:
            print(f"  Error: Global installation failed: {stderr}")
            sys.exit(1)
    else:
        print(f"  Error: install.py not found at {install_script}")
        sys.exit(1)
    print()
    
    # Step 3: Setup current workspace
    print("Step 3: Setting up current workspace...")
    workflows_dir = current_dir / ".devin" / "workflows"
    workflows_dir.mkdir(parents=True, exist_ok=True)
    print(f"  Created {workflows_dir}")
    
    # Copy workflow manifests
    source_workflows = global_root / "workflows"
    if source_workflows.exists():
        print(f"  Copying workflow manifests...")
        for manifest in source_workflows.glob("*.yaml"):
            target = workflows_dir / manifest.name
            import shutil
            shutil.copy2(manifest, target)
            print(f"    Copied {manifest.name}")
        print("  Workflow manifests copied successfully")
    else:
        print(f"  Warning: Workflows directory not found at {source_workflows}")
    print()
    
    # Step 4: Verify installation
    print("Step 4: Verifying installation...")
    checks = [
        ("Global root", global_root),
        ("Skills directory", global_root / "skills"),
        ("Workflows directory", global_root / "workflows"),
        ("Workflow engine", global_root / "workflow-engine"),
        ("Config file", global_root / "config.yaml"),
        ("Dispatch script", global_root / "dispatch_skill.py"),
        ("Workspace workflows", workflows_dir),
    ]
    
    all_passed = True
    for name, path in checks:
        if path.exists():
            print(f"  ✓ {name}: {path}")
        else:
            print(f"  ✗ {name}: {path} (NOT FOUND)")
            all_passed = False
    print()
    
    if all_passed:
        print("=== Installation Complete ===")
        print()
        print("You can now use devin-orchestrator with Cascade:")
        print("  - Workflows are available in .devin/workflows/")
        print("  - Skills are available globally at ~/.devin-orchestrator/skills/")
        print("  - Dispatch script is available at ~/.devin-orchestrator/dispatch_skill.py")
        print()
        print("Example dispatch:")
        print("  python ~/.devin-orchestrator/dispatch_skill.py brainstorming SESSION-001 ~/.devin-orchestrator/work/SESSION-001 false true")
    else:
        print("=== Installation Incomplete ===")
        print("Some checks failed. Please review the errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
