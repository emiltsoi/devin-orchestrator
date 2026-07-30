# mypy: disable-error-code=attr-defined

from __future__ import annotations

import json
import logging
import re
import sys
import threading
from pathlib import Path

from devin_orchestrator.deterministic_tools import session_init  # noqa: E402
from devin_orchestrator.mcp_artifacts import (  # noqa: E402
    SubprocessArtifactRunner,
)
from devin_orchestrator.security_utils import (  # noqa: E402
    InvalidInputError,
    PathTraversalError,
    parse_config_overrides,
    validate_path_safe,
    validate_session_id,
    validate_skill_name,
    validate_workspace_path,
)
from devin_orchestrator.session_manager import create_session  # noqa: E402

logger = logging.getLogger(__name__)


class McpDispatchMixin:

    def _tool_dispatch_devin(self, arguments: dict) -> list[dict]:
        """
        Dispatch a generic Devin run with a role and prompt file.

        Args:
            arguments: Tool arguments containing role, prompt_file, work_dir, etc.

        Returns:
            List containing dispatch result with exit code and output
        """
        # Validate work_dir is under global_root
        try:
            work_dir = validate_workspace_path(
                arguments["work_dir"], base_allowed_dir=self.config.global_root
            )
        except InvalidInputError as e:
            return [self._text_content(f"Invalid work_dir: {e}")]
        except (KeyError, TypeError) as e:
            return [self._text_content(f"Invalid work_dir parameter: {e}")]

        # Validate prompt_file is under work_dir. Relative paths resolve
        # against work_dir (not CWD) by joining first, mirroring the
        # _tool_read_artifact pattern.
        try:
            prompt_input = Path(arguments["prompt_file"])
            if prompt_input.is_absolute():
                prompt_file = validate_path_safe(
                    work_dir, prompt_input, allow_absolute=True
                )
            else:
                prompt_file = validate_path_safe(
                    work_dir, work_dir / prompt_input, allow_absolute=True
                )
        except InvalidInputError as e:
            return [self._text_content(f"Invalid prompt_file: {e}")]
        except (KeyError, TypeError) as e:
            return [self._text_content(f"Invalid prompt_file parameter: {e}")]

        # Validate output_file if provided is under work_dir, with the same
        # relative-path handling as prompt_file. Keep the validated path so we
        # read the output from work_dir rather than CWD (M-1).
        validated_output_file: Path | None = None
        if arguments.get("output_file"):
            try:
                output_input = Path(arguments["output_file"])
                if output_input.is_absolute():
                    validated_output_file = validate_path_safe(
                        work_dir, output_input, allow_absolute=True
                    )
                else:
                    validated_output_file = validate_path_safe(
                        work_dir, work_dir / output_input, allow_absolute=True
                    )
            except InvalidInputError as e:
                return [self._text_content(f"Invalid output_file: {e}")]

        # Validate role is either a short name or a path under global_root/roles.
        # Short names are restricted to safe characters (no path separators or
        # traversal) and resolved to global_root/roles/<role>.md before being
        # passed to the subprocess, so dispatch_devin.py never receives a raw
        # relative name that could resolve against CWD or escape roles/.
        role = arguments["role"]
        roles_dir = self.config.global_root / "roles"
        role_path = Path(role)
        if role_path.is_absolute():
            # If absolute, must be under global_root/roles
            try:
                resolved_role = validate_path_safe(
                    roles_dir, role_path, allow_absolute=True
                )
            except (InvalidInputError, PathTraversalError) as e:
                return [self._text_content(f"Invalid role path: {e}")]
        else:
            # Short name - validate it contains only safe characters (no path
            # separators, dots, or traversal segments).
            if not re.match(r"^[a-zA-Z0-9_-]+$", role):
                return [self._text_content(f"Invalid role name: {role}")]
            try:
                resolved_role = validate_path_safe(
                    roles_dir, roles_dir / f"{role}.md", allow_absolute=True
                )
            except (InvalidInputError, PathTraversalError) as e:
                return [self._text_content(f"Invalid role name: {e}")]
        if not resolved_role.is_file():
            return [self._text_content(f"Role file not found: {resolved_role}")]

        script = Path(__file__).parent / "dispatch_devin.py"
        cmd = [sys.executable, str(script)]
        if arguments.get("model"):
            cmd.extend(["--model", str(arguments["model"])])
        if arguments.get("agent"):
            cmd.extend(["--agent", str(arguments["agent"])])
        if arguments.get("phase"):
            cmd.extend(["--phase", str(arguments["phase"])])
        cmd.extend(["--role", str(resolved_role)])
        cmd.extend(["--prompt-file", str(prompt_file)])
        cmd.extend(["--work-dir", str(work_dir)])
        if validated_output_file is not None:
            cmd.extend(["--output-file", str(validated_output_file)])
        for ctx in arguments.get("focused_context", []):
            try:
                validated_ctx = validate_path_safe(
                    work_dir, Path(ctx), allow_absolute=True
                )
            except (InvalidInputError, PathTraversalError) as e:
                return [self._text_content(f"Invalid focused_context path: {e}")]
            cmd.extend(["--focused-context", str(validated_ctx)])

        if arguments.get("permission_mode"):
            cmd.extend(["--permission-mode", str(arguments["permission_mode"])])

        # Validate timeout
        try:
            timeout = self._validate_timeout(arguments.get("timeout"))
        except InvalidInputError as e:
            return [self._text_content(f"Invalid timeout: {e}")]

        cmd.extend(["--timeout", str(timeout)])

        # Create a dispatch session so the call is non-blocking and leaves
        # replayable artifacts (cmd.json, stdout.txt, stderr.txt, result.json).
        try:
            dispatch_id, dispatch_dir = create_session(
                self.config.session_work_dir, "DISPATCH-NNN"
            )
        except (InvalidInputError, OSError) as e:
            return [self._text_content(f"Failed to create dispatch session: {e}")]

        request_content = f"role={role}\nprompt={prompt_file}\nwork_dir={work_dir}"
        session_init(dispatch_id, self.config.session_work_dir, request_content)

        thread = threading.Thread(
            target=SubprocessArtifactRunner.run,
            args=(dispatch_dir, cmd, work_dir, timeout),
            daemon=True,
        )
        thread.start()

        result = {
            "session_id": dispatch_id,
            "workspace": str(dispatch_dir),
            "status": "started",
        }
        return [self._text_content(json.dumps(result, indent=2))]

    def _tool_dispatch_skill(self, arguments: dict) -> list[dict]:
        """
        Invoke a named skill in a target workspace.

        Args:
            arguments: Tool arguments containing skill_name, session_id, workspace, etc.

        Returns:
            List containing dispatch result with exit code and output
        """
        # Validate workspace is under global_root
        try:
            workspace = validate_workspace_path(
                arguments["workspace"], base_allowed_dir=self.config.global_root
            )
        except InvalidInputError as e:
            return [self._text_content(f"Invalid workspace: {e}")]
        except (KeyError, TypeError) as e:
            return [self._text_content(f"Invalid workspace parameter: {e}")]

        # Validate skill_name
        try:
            skill_name = validate_skill_name(arguments["skill_name"])
        except InvalidInputError as e:
            return [self._text_content(f"Invalid skill_name: {e}")]
        except (KeyError, TypeError) as e:
            return [self._text_content(f"Invalid skill_name parameter: {e}")]

        # Validate session_id
        try:
            session_id = validate_session_id(arguments["session_id"])
        except InvalidInputError as e:
            return [self._text_content(f"Invalid session_id: {e}")]
        except (KeyError, TypeError) as e:
            return [self._text_content(f"Invalid session_id parameter: {e}")]

        # Validate timeout
        try:
            timeout = self._validate_timeout(arguments.get("timeout"))
        except InvalidInputError as e:
            return [self._text_content(f"Invalid timeout: {e}")]

        # Validate and parse config_overrides
        try:
            overrides = parse_config_overrides(arguments.get("config_overrides"))
        except InvalidInputError as e:
            return [self._text_content(f"Invalid config_overrides: {e}")]

        script = Path(__file__).parent / "dispatch_skill.py"
        cmd = [
            sys.executable,
            str(script),
            str(skill_name),
            str(session_id),
            str(workspace),
            str(arguments.get("is_reviewer", False)).lower(),
            str(arguments.get("demo_mode", False)).lower(),
        ]
        if overrides:
            cmd.append(json.dumps(overrides))

        # Create a dispatch session so the call is non-blocking and leaves
        # replayable artifacts (cmd.json, stdout.txt, stderr.txt, result.json).
        try:
            dispatch_id, dispatch_dir = create_session(
                self.config.session_work_dir, "DISPATCH-NNN"
            )
        except (InvalidInputError, OSError) as e:
            return [self._text_content(f"Failed to create dispatch session: {e}")]

        request_content = f"skill={skill_name}\nsession_id={session_id}\nworkspace={workspace}"
        session_init(dispatch_id, self.config.session_work_dir, request_content)

        thread = threading.Thread(
            target=SubprocessArtifactRunner.run,
            args=(dispatch_dir, cmd, None, timeout),
            daemon=True,
        )
        thread.start()

        result = {
            "session_id": dispatch_id,
            "workspace": str(dispatch_dir),
            "status": "started",
        }
        return [self._text_content(json.dumps(result, indent=2))]
