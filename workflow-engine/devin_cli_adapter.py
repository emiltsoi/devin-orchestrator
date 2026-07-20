"""
Devin CLI Simple Adapter
Uses devin-cli's native --print flag for non-interactive execution
Much simpler and more reliable than ACP for basic usage

Supports skill loading via description matching (Devin CLI feature).
Skills are loaded from workflow-engine/skills/ and injected into prompts
when their description matches prompt content.
"""

import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from transport_adapter import InvocationResult, TransportAdapter

# Allowlist of valid devin-cli permission modes. The CLI only accepts these
# values; any other string must be rejected before being passed to a subprocess
# to avoid argument-injection or unexpected interactive prompts during
# automated dispatch.
ALLOWED_PERMISSION_MODES = frozenset({"dangerous", "smart", "auto"})


class DevinCliAdapter(TransportAdapter):
    """
    Devin CLI simple adapter using --print mode

    Uses devin-cli's native non-interactive mode for automated execution.
    Simpler and more reliable than ACP for basic skill invocation.

    Supports skill loading via description matching. Skills are loaded from
    workflow-engine/skills/ and injected into prompts when their description
    matches prompt content.
    """

    def __init__(
        self,
        devin_cli_path: str,
        workspace: str | None = None,
        model: str | None = None,
        permission_mode: str = "dangerous",
        skills_dir: str | None = None,
        **_kwargs: Any,
    ):
        """
        Initialize devin-cli adapter

        Args:
            devin_cli_path: Path to devin.exe binary
            workspace: Optional workspace path (defaults to current directory)
            model: Optional model to use (e.g., "swe-1.6", "claude-sonnet-4")
            permission_mode: Permission mode (auto, smart, dangerous) - defaults
                to dangerous for automated dispatch. Only values in
                ALLOWED_PERMISSION_MODES are accepted; an invalid value raises
                ValueError. An unset/empty value falls back to "dangerous".
            skills_dir: Optional path to skills directory (defaults to config_loader skills_dir)

        Raises:
            ValueError: If ``permission_mode`` is a non-empty value that is not
                in ``ALLOWED_PERMISSION_MODES``.
        """
        from config_loader import ConfigLoader

        config = ConfigLoader.load()
        self.devin_cli_path = devin_cli_path
        self.workspace = workspace or str(Path.cwd())
        self.model = (
            model  # None means no --model flag; caller can pass 'swe-1.6' if desired
        )
        self.permission_mode = self._validate_permission_mode(permission_mode)
        self.skills_dir = Path(skills_dir) if skills_dir else config.skills_dir
        self.skills = self._load_skills()

    @staticmethod
    def _validate_permission_mode(permission_mode: str | None) -> str:
        """
        Validate the permission mode against the allowlist.

        Unset/empty values fall back to ``"dangerous"`` for automated dispatch.
        Any other value must be present in ``ALLOWED_PERMISSION_MODES``;
        otherwise a ``ValueError`` is raised so an unvalidated string is never
        forwarded to the devin-cli subprocess.

        Args:
            permission_mode: Raw permission mode value to validate.

        Returns:
            A validated permission mode string.

        Raises:
            ValueError: If the value is non-empty and not in the allowlist.
        """
        if permission_mode is None or permission_mode == "":
            return "dangerous"
        if permission_mode not in ALLOWED_PERMISSION_MODES:
            raise ValueError(
                f"Invalid permission_mode {permission_mode!r}; "
                f"must be one of {sorted(ALLOWED_PERMISSION_MODES)}"
            )
        return permission_mode

    def capabilities(self) -> list[str]:
        """Return the capabilities supported by this adapter"""
        return ["native_subagent_dispatch", "file_operations", "terminal_commands"]

    def _load_skills(self) -> dict[str, dict[str, str]]:
        """
        Load skills from skills directory

        Returns:
            Dict mapping skill name to {description, content}
        """
        skills = {}
        if not self.skills_dir.exists():
            return skills

        for skill_dir in self.skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue

            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue

            try:
                content = skill_file.read_text(encoding="utf-8")
                # Extract description from YAML frontmatter
                description_match = re.search(r'description:\s*"([^"]+)"', content)
                if description_match:
                    description = description_match.group(1)
                    skills[skill_dir.name] = {
                        "description": description,
                        "content": content,
                    }
            except Exception:
                # Skip skills that fail to load
                continue

        return skills

    def _inject_skills(self, prompt: str) -> str:
        """
        Inject skills into prompt based on description matching

        Args:
            prompt: Original prompt

        Returns:
            Prompt with skill content injected if description matches
        """
        prompt_lower = prompt.lower()
        injected_skills = []

        for skill_name, skill_data in self.skills.items():
            # Match on specific trigger phrases to avoid false positives
            # ponytail: "coding dispatch and implementation task"
            # swe-compliance: "compliance review task, code verification, artifact audit, and quality check"
            if skill_name == "ponytail":
                # Trigger on "coding dispatch" or "implementation task"
                if (
                    "coding dispatch" in prompt_lower
                    or "implementation task" in prompt_lower
                ):
                    injected_skills.append(skill_data["content"])
            elif skill_name == "swe-compliance" and (
                "compliance review" in prompt_lower
                or "code verification" in prompt_lower
                or "artifact audit" in prompt_lower
            ):
                # Trigger on "compliance review" or "code verification" or "artifact audit"
                injected_skills.append(skill_data["content"])

        if injected_skills:
            # Inject skills at the beginning of the prompt
            skill_block = "\n\n".join(injected_skills)
            return f"{skill_block}\n\n---\n\n{prompt}"

        return prompt

    def invoke(
        self,
        prompt: str,
        timeout: int = 120,
        focused_context: list | None = None,
        correction_artifact: str | None = None,
        enable_skills: bool = True,
    ) -> InvocationResult:
        """
        Invoke devin-cli with a prompt in non-interactive mode

        Args:
            prompt: The prompt to send to devin
            timeout: Timeout in seconds (default: 120)
            focused_context: Optional list of artifact paths to inject into worker dispatch
            correction_artifact: Optional path to correction artifact for retry loops
            enable_skills: Whether to inject skills via description matching (default: True)

        Returns:
            InvocationResult with success status, output, and error
        """
        # Inject skills if enabled
        if enable_skills:
            prompt = self._inject_skills(prompt)

        # Add focused context artifacts if provided
        # Note: Devin CLI doesn't support --context, so we inject into prompt instead
        if focused_context:
            prompt += "\n\n## Focused Context Artifacts\n"
            for artifact_path in focused_context:
                prompt += f"- {artifact_path}\n"

        # Add correction artifact if provided
        # Note: Devin CLI doesn't support --correction, so we inject into prompt instead
        if correction_artifact:
            prompt += f"\n\n## Correction Artifact\n- {correction_artifact}\n"

        # Build command. The prompt is written to a temporary .md file inside
        # the workspace and passed via --prompt-file to avoid platform command
        # line length limits and to keep the prompt contents out of the process
        # table / shell history.
        cmd = [self.devin_cli_path, "--permission-mode", self.permission_mode]

        # Add model if specified
        if self.model:
            cmd.extend(["--model", self.model])

        prompt_file: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".md",
                prefix="devin_prompt_",
                dir=self.workspace,
                delete=False,
                encoding="utf-8",
            ) as f:
                f.write(prompt)
                prompt_file = Path(f.name)

            cmd.extend(["--prompt-file", str(prompt_file), "--print"])

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",  # Handle encoding errors gracefully
                    timeout=timeout,
                    cwd=self.workspace,
                )

                return InvocationResult(
                    success=result.returncode == 0,
                    output=result.stdout,
                    error=result.stderr,
                    exit_code=result.returncode,
                )

            except subprocess.TimeoutExpired:
                return InvocationResult(
                    success=False,
                    output="",
                    error=f"Command timed out after {timeout} seconds",
                    exit_code=-1,
                )
            except (OSError, FileNotFoundError) as e:
                return InvocationResult(
                    success=False,
                    output="",
                    error=(
                        f"Failed to execute devin-cli "
                        f"({type(e).__name__}): {e}"
                    ),
                    exit_code=-1,
                )
            except Exception as e:
                return InvocationResult(
                    success=False,
                    output="",
                    error=f"Unexpected error invoking devin-cli: {e}",
                    exit_code=-1,
                )
        finally:
            # Clean up the temporary prompt file; best-effort.
            if prompt_file is not None:
                try:
                    if prompt_file.exists():
                        prompt_file.unlink()
                except OSError:
                    pass

    def __enter__(self):
        """Context manager entry (no-op for simple adapter)"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit (no-op for simple adapter)"""
        pass
