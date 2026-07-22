#!/usr/bin/env python3
"""
Global Installer for Devin Orchestrator

Installs devin-orchestrator to a global location (~/.devin-orchestrator/)
for use across all workspaces.
"""

import os
import shutil
import stat
from pathlib import Path


def _on_rm_error(func, path, exc_info):
    """Make paths writable and retry removal (Windows-friendly)."""
    os.chmod(path, stat.S_IWRITE)
    func(path)


def install(global_root: Path | None = None, source_dir: Path | None = None, dry_run: bool = False):
    """
    Install devin-orchestrator to global location

    Args:
        global_root: Optional global root path (defaults to ~/.devin-orchestrator/)
        source_dir: Optional source directory (defaults to current directory)
        dry_run: If True, only print what would be done without actually doing it
    """
    # Determine paths
    if global_root is None:
        global_root = Path.home() / ".devin-orchestrator"

    if source_dir is None:
        source_dir = Path(__file__).parent

    global_root = global_root.expanduser()
    source_dir = source_dir.expanduser()

    print("=== Installing Devin Orchestrator ===")
    if dry_run:
        print("DRY RUN MODE - No actual installation will be performed")
    print(f"Source: {source_dir}")
    print(f"Target: {global_root}")
    print()

    # Create global root
    if not dry_run:
        global_root.mkdir(parents=True, exist_ok=True)
    print(f"Would create global root: {global_root}")

    # Copy skills
    source_skills = source_dir / "skills"
    target_skills = global_root / "skills"
    if source_skills.exists():
        if not dry_run:
            if target_skills.exists():
                shutil.rmtree(target_skills, onexc=_on_rm_error)
            shutil.copytree(source_skills, target_skills)
        print(f"Would copy skills: {source_skills} -> {target_skills}")

    # Copy workflows
    source_workflows = source_dir / "workflows"
    target_workflows = global_root / "workflows"
    if source_workflows.exists():
        if not dry_run:
            if target_workflows.exists():
                shutil.rmtree(target_workflows, onexc=_on_rm_error)
            shutil.copytree(source_workflows, target_workflows)
        print(f"Would copy workflows: {source_workflows} -> {target_workflows}")

    # Copy workflow engine
    source_engine = source_dir / "workflow-engine"
    target_engine = global_root / "workflow-engine"
    if source_engine.exists():
        if not dry_run:
            if target_engine.exists():
                shutil.rmtree(target_engine, onexc=_on_rm_error)
            shutil.copytree(source_engine, target_engine)
        print(f"Would copy workflow engine: {source_engine} -> {target_engine}")

    # Copy config
    source_config = source_dir / "config.yaml"
    target_config = global_root / "config.yaml"
    if source_config.exists():
        if not dry_run:
            shutil.copy2(source_config, target_config)
        print(f"Would copy config: {source_config} -> {target_config}")

    # Copy dispatch and MCP entry-point scripts so any workspace can invoke them
    for script_name in ("dispatch_devin.py", "mcp_server.py"):
        source_script = source_dir / script_name
        target_script = global_root / script_name
        if source_script.exists():
            if not dry_run:
                shutil.copy2(source_script, target_script)
            print(f"Would copy entry script: {source_script} -> {target_script}")

    # Copy role files used by dispatch_devin.py
    source_roles = source_dir / "roles"
    target_roles = global_root / "roles"
    if source_roles.exists():
        if not dry_run:
            if target_roles.exists():
                shutil.rmtree(target_roles, onexc=_on_rm_error)
            shutil.copytree(source_roles, target_roles)
        print(f"Would copy roles: {source_roles} -> {target_roles}")

    # Create work directory
    work_dir = global_root / "work"
    if not dry_run:
        work_dir.mkdir(parents=True, exist_ok=True)
    print(f"Would create work directory: {work_dir}")

    if dry_run:
        print()
        print("=== Dry Run Complete ===")
        print("No changes were made.")
    else:
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
        print("  - Skills are available at: " + str(target_skills))
        print("  - Workflows are available at: " + str(target_workflows))
        print("  - Workflow engine is available at: " + str(target_engine))
        print("  - Config is available at: " + str(target_config))
        print()
        print("For Cascade integration, use the dispatch_skill.py script:")
        print("  python " + str(global_root / "dispatch_skill.py") + " <skill> <session_id> <workspace> <is_reviewer> <focused_context>")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Install devin-orchestrator to global location')
    parser.add_argument('global_root', nargs='?', help='Global root path (default: ~/.devin-orchestrator)')
    parser.add_argument('source_dir', nargs='?', help='Source directory (default: current directory)')
    parser.add_argument('--dry-run', action='store_true', help='Dry run - show what would be done without actually doing it')

    args = parser.parse_args()

    global_root = Path(args.global_root) if args.global_root else None
    source_dir = Path(args.source_dir) if args.source_dir else None

    install(global_root, source_dir, dry_run=args.dry_run)
