#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Global Configuration Loader

Loads global configuration for devin-orchestrator.
Supports environment variables and config file.
"""

import yaml
import os
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class GlobalConfig:
    """Global configuration for devin-orchestrator"""
    global_root: Path
    skills_dir: Path
    workflows_dir: Path
    workflow_engine_dir: Path
    devin_cli_path: str
    default_model: str
    default_permission_mode: str
    session_work_dir: Path


class ConfigLoader:
    """Loads global configuration from config file and environment variables"""
    
    DEFAULT_CONFIG_PATH = Path.home() / ".devin-orchestrator" / "config.yaml"
    FALLBACK_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"
    
    @staticmethod
    def load(config_path: Optional[Path] = None) -> GlobalConfig:
        """
        Load global configuration
        
        Args:
            config_path: Optional path to config file
        
        Returns:
            GlobalConfig object
        """
        # Determine config file path
        if config_path is None:
            config_path = ConfigLoader.DEFAULT_CONFIG_PATH
            if not config_path.exists():
                config_path = ConfigLoader.FALLBACK_CONFIG_PATH
        
        # Load config file
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
        else:
            config_data = {}
        
        # Expand paths (support ~ for home directory)
        def expand_path(path_str: str) -> Path:
            path = Path(path_str).expanduser()
            if not path.is_absolute():
                path = Path.home() / path
            return path
        
        # Build configuration with environment variable overrides
        global_root = expand_path(os.getenv("DEVIN_ORCHESTRATOR_ROOT", config_data.get("global_root", "~/.devin-orchestrator")))
        skills_dir = expand_path(os.getenv("DEVIN_ORCHESTRATOR_SKILLS_DIR", config_data.get("skills_dir", "~/.devin-orchestrator/skills")))
        workflows_dir = expand_path(os.getenv("DEVIN_ORCHESTRATOR_WORKFLOWS_DIR", config_data.get("workflows_dir", "~/.devin-orchestrator/workflows")))
        workflow_engine_dir = expand_path(os.getenv("DEVIN_ORCHESTRATOR_WORKFLOW_ENGINE_DIR", config_data.get("workflow_engine_dir", "~/.devin-orchestrator/workflow-engine")))
        devin_cli_path = str(expand_path(os.getenv("DEVIN_CLI_PATH", config_data.get("devin_cli_path", "~/AppData/Local/devin/cli/bin/devin.exe"))))
        default_model = os.getenv("DEVIN_DEFAULT_MODEL", config_data.get("default_model", "swe-1.6"))
        default_permission_mode = os.getenv("DEVIN_DEFAULT_PERMISSION_MODE", config_data.get("default_permission_mode", "dangerous"))
        session_work_dir = expand_path(os.getenv("DEVIN_SESSION_WORK_DIR", config_data.get("session_work_dir", "~/.devin-orchestrator/work")))
        
        # Fallback to current directory for testing (if global paths don't exist)
        if not skills_dir.exists():
            skills_dir = Path(__file__).parent.parent / "skills"
        if not workflows_dir.exists():
            workflows_dir = Path(__file__).parent.parent / "workflows"
        if not workflow_engine_dir.exists():
            workflow_engine_dir = Path(__file__).parent
        if not session_work_dir.exists():
            session_work_dir = Path(__file__).parent / "work"
        
        return GlobalConfig(
            global_root=global_root,
            skills_dir=skills_dir,
            workflows_dir=workflows_dir,
            workflow_engine_dir=workflow_engine_dir,
            devin_cli_path=devin_cli_path,
            default_model=default_model,
            default_permission_mode=default_permission_mode,
            session_work_dir=session_work_dir
        )


if __name__ == "__main__":
    # Test config loader
    config = ConfigLoader.load()
    print("=== Global Configuration ===")
    print(f"Global Root: {config.global_root}")
    print(f"Skills Dir: {config.skills_dir}")
    print(f"Workflows Dir: {config.workflows_dir}")
    print(f"Workflow Engine Dir: {config.workflow_engine_dir}")
    print(f"Devin CLI Path: {config.devin_cli_path}")
    print(f"Default Model: {config.default_model}")
    print(f"Default Permission Mode: {config.default_permission_mode}")
    print(f"Session Work Dir: {config.session_work_dir}")
