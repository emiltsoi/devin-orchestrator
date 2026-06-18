# -*- coding: utf-8 -*-
"""
Skill Invoker - Invokes skills using transport adapters
"""

from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass

from devin_cli_adapter import DevinCliAdapter, SessionInfo


@dataclass
class SkillInvocationResult:
    """Result of skill invocation"""
    success: bool
    session_id: Optional[str]
    output: Optional[str]
    error: Optional[str]


class SkillInvoker:
    """
    Invokes skills using transport adapters
    
    Loads skill definitions and uses transport adapters to spawn
    agent sessions for skill execution.
    """

    def __init__(self, harness_root: Path, devin_cli_path: Optional[str] = None):
        """
        Initialize skill invoker

        Args:
            harness_root: Root directory of the harness
            devin_cli_path: Optional path to devin.exe (for devin-cli adapter)
        """
        self.harness_root = harness_root
        self.skills_dir = harness_root / 'skills'
        self.devin_cli_path = devin_cli_path
        self.active_sessions: Dict[str, SessionInfo] = {}

    def invoke_skill(
        self,
        skill_name: str,
        context: Dict[str, Any],
        workspace: Optional[str] = None
    ) -> SkillInvocationResult:
        """
        Invoke a skill using the devin-cli transport adapter

        Args:
            skill_name: Name of the skill to invoke
            context: Context data for the skill (e.g., session_id, step, artifacts)
            workspace: Optional workspace path

        Returns:
            SkillInvocationResult with success status and output
        """
        if not self.devin_cli_path:
            return SkillInvocationResult(
                success=False,
                session_id=None,
                output=None,
                error="Devin CLI path not configured"
            )

        # Load skill definition
        skill_def = self._load_skill_definition(skill_name)
        if not skill_def:
            return SkillInvocationResult(
                success=False,
                session_id=None,
                output=None,
                error=f"Skill definition not found: {skill_name}"
            )

        # Load skill narrative
        skill_narrative = self._load_skill_narrative(skill_name)
        if not skill_narrative:
            return SkillInvocationResult(
                success=False,
                session_id=None,
                output=None,
                error=f"Skill narrative not found: {skill_name}"
            )

        # Build prompt for the skill
        prompt = self._build_skill_prompt(skill_name, skill_def, skill_narrative, context)

        # Generate session ID
        session_id = f"{skill_name}-{context.get('session_id', 'unknown')}"

        try:
            # Start devin-cli adapter
            with DevinCliAdapter(self.devin_cli_path, workspace) as adapter:
                # Create session
                session_info = adapter.session_new(
                    session_id=session_id,
                    description=f"Skill invocation: {skill_name}"
                )
                self.active_sessions[session_id] = session_info

                # Send prompt
                response = adapter.session_prompt(session_id, prompt)

                return SkillInvocationResult(
                    success=True,
                    session_id=session_id,
                    output=str(response),
                    error=None
                )

        except Exception as e:
            return SkillInvocationResult(
                success=False,
                session_id=None,
                output=None,
                error=str(e)
            )

    def _load_skill_definition(self, skill_name: str) -> Optional[Dict[str, Any]]:
        """Load skill YAML definition"""
        import yaml

        skill_yaml = self.skills_dir / f"{skill_name}.yaml"
        if not skill_yaml.exists():
            return None

        with open(skill_yaml, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def _load_skill_narrative(self, skill_name: str) -> Optional[str]:
        """Load skill markdown narrative"""
        skill_md = self.skills_dir / f"{skill_name}.md"
        if not skill_md.exists():
            return None

        with open(skill_md, 'r', encoding='utf-8') as f:
            return f.read()

    def _build_skill_prompt(
        self,
        skill_name: str,
        skill_def: Dict[str, Any],
        skill_narrative: str,
        context: Dict[str, Any]
    ) -> str:
        """
        Build prompt for skill invocation

        Args:
            skill_name: Name of the skill
            skill_def: Skill YAML definition
            skill_narrative: Skill markdown narrative
            context: Context data

        Returns:
            Prompt string
        """
        prompt = f"""# Skill Invocation: {skill_name}

## Context
"""
        # Add context information
        for key, value in context.items():
            prompt += f"- {key}: {value}\n"

        prompt += f"""
## Skill Definition
**Iron Law:** {skill_def.get('iron_law', 'N/A')}
**Announcement:** {skill_def.get('announcement', f'Using {skill_name} skill')}

## Skill Narrative
{skill_narrative}

## Instructions
Execute this skill according to its definition and narrative. Follow the iron law strictly.
"""

        return prompt

    def cancel_session(self, session_id: str) -> bool:
        """
        Cancel an active session

        Args:
            session_id: Session identifier

        Returns:
            True if cancelled successfully
        """
        if not self.devin_cli_path:
            return False

        if session_id not in self.active_sessions:
            return False

        try:
            with DevinCliAdapter(self.devin_cli_path) as adapter:
                success = adapter.session_cancel(session_id)
                if success:
                    del self.active_sessions[session_id]
                return success
        except Exception:
            return False

    def list_active_sessions(self) -> Dict[str, SessionInfo]:
        """List all active sessions"""
        return self.active_sessions.copy()
