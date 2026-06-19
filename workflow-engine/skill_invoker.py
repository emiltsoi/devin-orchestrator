# -*- coding: utf-8 -*-
"""
Skill Invoker - Invokes skills using transport adapters
"""

from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass

from devin_cli_adapter import DevinCliAdapter


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

    def __init__(self, harness_root: Path, devin_cli_path: Optional[str] = None, model: Optional[str] = None, permission_mode: str = "dangerous"):
        """
        Initialize skill invoker

        Args:
            harness_root: Root directory of the harness
            devin_cli_path: Optional path to devin.exe (for devin-cli adapter)
            model: Optional model to use (e.g., "claude-sonnet-4", "claude-opus-4.6")
            permission_mode: Permission mode (auto, smart, dangerous) - defaults to dangerous for automated dispatch
        """
        self.harness_root = harness_root
        self.skills_dir = harness_root / 'skills'
        self.devin_cli_path = devin_cli_path
        self.model = model
        self.permission_mode = permission_mode

    def invoke_skill(
        self,
        skill_name: str,
        context: Dict[str, Any],
        workspace: Optional[str] = None,
        custom_prompt: Optional[str] = None
    ) -> SkillInvocationResult:
        """
        Invoke a skill using the devin-cli transport adapter

        Args:
            skill_name: Name of the skill to invoke
            context: Context data for the skill (e.g., session_id, step, artifacts)
            workspace: Optional workspace path
            custom_prompt: Optional custom prompt (for retry with feedback)

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

        # Use custom prompt if provided (for retry), otherwise build standard prompt
        if custom_prompt:
            prompt = custom_prompt
        else:
            prompt = self._build_skill_prompt(skill_name, skill_def, skill_narrative, context)

        # Generate session ID for tracking
        session_id = f"{skill_name}-{context.get('session_id', 'unknown')}"

        try:
            # Use simple adapter with --print mode
            adapter = DevinCliAdapter(self.devin_cli_path, workspace, self.model, self.permission_mode)
            result = adapter.invoke(prompt, timeout=300)  # 5 minute timeout for skills

            return SkillInvocationResult(
                success=result.success,
                session_id=session_id,
                output=result.output,
                error=result.error
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
