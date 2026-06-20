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

    Caching: Skill definitions and narratives are cached in-memory
    after first load to avoid redundant file I/O. Cache is per-instance
    and can be cleared via clear_skill_cache() if needed.
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
        self.skills_dir = harness_root.parent / 'skills'
        self.devin_cli_path = devin_cli_path
        self.model = model
        self.permission_mode = permission_mode
        self._skill_definition_cache: Dict[str, Dict[str, Any]] = {}
        self._skill_narrative_cache: Dict[str, str] = {}
        self._cache_hits = 0
        self._cache_misses = 0

    def invoke_skill(
        self,
        skill_name: str,
        context: Dict[str, Any],
        workspace: Optional[str] = None,
        custom_prompt: Optional[str] = None,
        focused_context: Optional[list] = None,
        correction_artifact: Optional[str] = None,
        is_reviewer: bool = False
    ) -> SkillInvocationResult:
        """
        Invoke a skill using the devin-cli transport adapter

        Args:
            skill_name: Name of the skill to invoke
            context: Context data for the skill (e.g., session_id, step, artifacts)
            workspace: Optional workspace path
            custom_prompt: Optional custom prompt (for retry with feedback)
            focused_context: Optional list of artifact paths to inject into worker dispatch
            correction_artifact: Optional path to correction artifact for retry loops
            is_reviewer: Whether this is a reviewer dispatch (triggers swe-compliance skill)

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
        skill_def = self.load_skill_definition(skill_name)
        if not skill_def:
            return SkillInvocationResult(
                success=False,
                session_id=None,
                output=None,
                error=f"Skill definition not found: {skill_name}"
            )

        # Load skill narrative
        skill_narrative = self.load_skill_narrative(skill_name)
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
            prompt = self.build_skill_prompt(skill_name, skill_def, skill_narrative, context, focused_context, correction_artifact, is_reviewer)

        # Generate session ID for tracking
        session_id = f"{skill_name}-{context.get('session_id', 'unknown')}"

        try:
            # Use simple adapter with --print mode
            # Disable skill injection since we load skills directly via skill_invoker
            adapter = DevinCliAdapter(self.devin_cli_path, workspace, self.model, self.permission_mode)
            result = adapter.invoke(prompt, timeout=300, focused_context=focused_context, correction_artifact=correction_artifact, enable_skills=False)  # 5 minute timeout for skills

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

    def load_skill_definition(self, skill_name: str) -> Optional[Dict[str, Any]]:
        """Load skill YAML definition with caching"""
        # Check cache first
        if skill_name in self._skill_definition_cache:
            self._cache_hits += 1
            return self._skill_definition_cache[skill_name]

        import yaml

        # Try subdirectory structure first (skills/skill_name/skill_name.yaml)
        skill_yaml = self.skills_dir / skill_name / (skill_name + ".yaml")
        if not skill_yaml.exists():
            # Try flat structure (skills/skill_name.yaml)
            skill_yaml = self.skills_dir / (skill_name + ".yaml")

        if not skill_yaml.exists():
            return None

        with open(skill_yaml, 'r', encoding='utf-8') as f:
            skill_def = yaml.safe_load(f)

        # Cache the loaded definition
        self._cache_misses += 1
        self._skill_definition_cache[skill_name] = skill_def
        return skill_def

    def load_skill_narrative(self, skill_name: str) -> Optional[str]:
        """Load skill markdown narrative with caching"""
        # Check cache first
        if skill_name in self._skill_narrative_cache:
            self._cache_hits += 1
            return self._skill_narrative_cache[skill_name]

        # Try subdirectory structure first (skills/skill_name/skill_name.md)
        skill_md = self.skills_dir / skill_name / (skill_name + ".md")
        if not skill_md.exists():
            # Try flat structure (skills/skill_name.md)
            skill_md = self.skills_dir / (skill_name + ".md")

        if not skill_md.exists():
            return None

        with open(skill_md, 'r', encoding='utf-8') as f:
            skill_narrative = f.read()

        # Cache the loaded narrative
        self._cache_misses += 1
        self._skill_narrative_cache[skill_name] = skill_narrative
        return skill_narrative

    def clear_skill_cache(self) -> None:
        """
        Clear the skill definition and narrative caches

        Useful for testing or if skill files are updated during runtime
        """
        self._skill_definition_cache.clear()
        self._skill_narrative_cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0

    def build_skill_prompt(
        self,
        skill_name: str,
        skill_def: Dict[str, Any],
        skill_narrative: str,
        context: Dict[str, Any],
        focused_context: Optional[list] = None,
        correction_artifact: Optional[str] = None,
        is_reviewer: bool = False
    ) -> str:
        """
        Build prompt for skill invocation

        Args:
            skill_name: Name of the skill
            skill_def: Skill YAML definition
            skill_narrative: Skill markdown narrative
            context: Context data
            focused_context: Optional list of artifact paths to inject into worker dispatch
            correction_artifact: Optional path to correction artifact for retry loops
            is_reviewer: Whether this is a reviewer dispatch (triggers swe-compliance skill)

        Returns:
            Prompt string
        """
        # Add skill trigger phrases for description matching
        # These trigger the ponytail and swe-compliance skills via description matching
        trigger_phrase = ""
        if is_reviewer:
            trigger_phrase = "This is a compliance review task, code verification, artifact audit, and quality check."
        else:
            trigger_phrase = "This is a coding dispatch and implementation task."

        prompt = f"""# Skill Invocation: {skill_name}

{trigger_phrase}

## Context
"""
        # Add context information
        for key, value in context.items():
            prompt += f"- {key}: {value}\n"

        # Add focused context artifacts if provided
        if focused_context:
            prompt += "\n## Focused Context Artifacts\n"
            for artifact_path in focused_context:
                prompt += f"- {artifact_path}\n"

        # Add correction artifact if provided
        if correction_artifact:
            prompt += f"\n## Correction Artifact\n- {correction_artifact}\n"

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
