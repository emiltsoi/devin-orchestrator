#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Deterministic Tools - Provides deterministic, stateless operations for orchestration

These tools are designed to be idempotent and provide consistent behavior
across different orchestration contexts.
"""

import json
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime


def session_init(session_id: str, work_dir: Path, request_content: str = "") -> Path:
    """
    Scaffold session directory and initial artifacts
    
    Consolidated to reduce artifact bloat:
    - session.json: Single file with all session metadata, status, and audit log
    
    Args:
        session_id: Unique session identifier
        work_dir: Base work directory
        request_content: Initial request content to include
        
    Returns:
        Path to the created session directory
    """
    session_dir = work_dir / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    
    # Create consolidated session file
    session_file = session_dir / "session.json"
    if not session_file.exists():
        session_data = {
            'session_id': session_id,
            'created': datetime.now().isoformat(),
            'status': 'initialized',
            'request': request_content,
            'stages': [],
            'gates': [],
            'audit_log': []
        }
        with open(session_file, 'w', encoding='utf-8') as f:
            json.dump(session_data, f, indent=2)
    
    return session_dir


def validate_structural(artifacts: List[Path]) -> Dict[str, Any]:
    """
    Validate structural floor for output artifacts
    
    Checks:
    - File exists
    - File is not empty
    - No TODO placeholders
    - No PLACEHOLDER text
    
    Args:
        artifacts: List of artifact paths to validate
        
    Returns:
        Dictionary with validation results:
        {
            'valid': bool,
            'errors': List[str],
            'artifact_results': Dict[str, Dict]
        }
    """
    results = {
        'valid': True,
        'errors': [],
        'artifact_results': {}
    }
    
    for artifact in artifacts:
        artifact_name = artifact.name
        artifact_result = {
            'exists': False,
            'non_empty': False,
            'no_placeholders': False,
            'valid': False
        }
        
        # Check if file exists
        if not artifact.exists():
            artifact_result['exists'] = False
            results['errors'].append(f"{artifact_name}: File does not exist")
            results['valid'] = False
        else:
            artifact_result['exists'] = True
            content = artifact.read_text()
            
            # Check if file is not empty
            if content.strip():
                artifact_result['non_empty'] = True
            else:
                artifact_result['non_empty'] = False
                results['errors'].append(f"{artifact_name}: File is empty")
                results['valid'] = False
            
            # Check for placeholders
            if 'TODO' not in content and 'PLACEHOLDER' not in content:
                artifact_result['no_placeholders'] = True
            else:
                artifact_result['no_placeholders'] = False
                results['errors'].append(f"{artifact_name}: Contains TODO or PLACEHOLDER")
                results['valid'] = False
        
        artifact_result['valid'] = all([
            artifact_result['exists'],
            artifact_result['non_empty'],
            artifact_result['no_placeholders']
        ])
        
        results['artifact_results'][artifact_name] = artifact_result
    
    return results


def record_gate(gate_id: str, verdict: str, session_dir: Path, notes: str = "") -> None:
    """
    Record gate decision to session.json
    
    Args:
        gate_id: Unique gate identifier
        verdict: Gate verdict (approve/request_changes/block)
        session_dir: Session directory containing session.json
        notes: Optional notes about the gate decision
    """
    session_file = session_dir / "session.json"
    
    with open(session_file, 'r', encoding='utf-8') as f:
        session_data = json.load(f)
    
    gate_entry = {
        'gate_id': gate_id,
        'timestamp': datetime.now().isoformat(),
        'verdict': verdict,
        'notes': notes
    }
    
    session_data['gates'].append(gate_entry)
    session_data['audit_log'].append({
        'type': 'gate_decision',
        'timestamp': datetime.now().isoformat(),
        'details': gate_entry
    })
    
    with open(session_file, 'w', encoding='utf-8') as f:
        json.dump(session_data, f, indent=2)


def update_status(session_dir: Path, stage: str, status: str, notes: str = "") -> None:
    """
    Update session status in session.json
    
    Args:
        session_dir: Session directory containing session.json
        stage: Current stage name
        status: Current status (in_progress/completed/failed)
        notes: Optional notes about the status update
    """
    session_file = session_dir / "session.json"
    
    with open(session_file, 'r', encoding='utf-8') as f:
        session_data = json.load(f)
    
    stage_entry = {
        'stage': stage,
        'timestamp': datetime.now().isoformat(),
        'status': status,
        'notes': notes
    }
    
    session_data['stages'].append(stage_entry)
    session_data['status'] = status
    session_data['audit_log'].append({
        'type': 'status_update',
        'timestamp': datetime.now().isoformat(),
        'details': stage_entry
    })
    
    with open(session_file, 'w', encoding='utf-8') as f:
        json.dump(session_data, f, indent=2)


def create_placeholder_artifact(artifact_path: Path, content: str) -> None:
    """
    Create a placeholder artifact when skipping a stage
    
    Args:
        artifact_path: Path where artifact should be created
        content: Placeholder content
    """
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(content)


def load_manifest(manifest_path: Path) -> Dict[str, Any]:
    """
    Load and parse a workflow manifest
    
    Args:
        manifest_path: Path to manifest YAML file
        
    Returns:
        Parsed manifest as dictionary
    """
    import yaml
    
    with open(manifest_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def load_skill(skill_dir: Path, skill_name: str) -> Dict[str, Any]:
    """
    Load skill definition and narrative
    
    Supports two formats:
    1. Separate files: skill.yaml + skill.md (legacy)
    2. Single file: skill.md with YAML frontmatter (new)
    
    Args:
        skill_dir: Directory containing skills
        skill_name: Name of the skill to load
        
    Returns:
        Dictionary with 'definition' and 'narrative' keys
    """
    import yaml
    import re
    
    # Check for single file format (new)
    skill_md = skill_dir / f"{skill_name}.md"
    skill_md_subdir = skill_dir / skill_name / f"{skill_name}.md"
    
    md_path = None
    if skill_md.exists():
        md_path = skill_md
    elif skill_md_subdir.exists():
        md_path = skill_md_subdir
    
    if md_path:
        content = md_path.read_text()
        
        # Check for YAML frontmatter
        frontmatter_match = re.match(r'^---\n(.*?)\n---\n(.*)$', content, re.DOTALL)
        
        if frontmatter_match:
            # Single file format with frontmatter
            frontmatter_yaml = frontmatter_match.group(1)
            narrative = frontmatter_match.group(2)
            
            definition = yaml.safe_load(frontmatter_yaml)
            
            return {
                'definition': definition,
                'narrative': narrative,
                'format': 'single'
            }
    
    # Fall back to separate files format (legacy)
    skill_yaml = skill_dir / f"{skill_name}.yaml"
    skill_yaml_subdir = skill_dir / skill_name / f"{skill_name}.yaml"
    
    if skill_yaml.exists():
        yaml_path = skill_yaml
    elif skill_yaml_subdir.exists():
        yaml_path = skill_yaml_subdir
    else:
        raise FileNotFoundError(f"Skill YAML not found: {skill_yaml} or {skill_yaml_subdir}")
    
    if not md_path:
        if skill_md.exists():
            md_path = skill_md
        elif skill_md_subdir.exists():
            md_path = skill_md_subdir
        else:
            raise FileNotFoundError(f"Skill markdown not found: {skill_md} or {skill_md_subdir}")
    
    with open(yaml_path, 'r', encoding='utf-8') as f:
        definition = yaml.safe_load(f)
    
    with open(md_path, 'r', encoding='utf-8') as f:
        narrative = f.read()
    
    return {
        'definition': definition,
        'narrative': narrative,
        'format': 'separate'
    }
