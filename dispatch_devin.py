#!/usr/bin/env python3
"""
Generic Devin dispatcher.

Dispatches a Devin run with a model, a predefined role markdown file, and a task
prompt markdown file. Replaces one-off per-wave dispatch scripts.

Usage example:
    py -3.14 dispatch_devin.py \
        --model glm-5-2 \
        --role coder \
        --prompt-file prompts/security_hardening.md \
        --output-file work/SECURITY-001/output.md \
        --focused-context workflow-engine/security_utils.py

A role name resolves to roles/<role>.md under the repo root. A full path to a
markdown file is also accepted.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add local workflow-engine to Python path for imports
WORKFLOW_ENGINE_DIR = Path(__file__).parent / "workflow-engine"
sys.path.insert(0, str(WORKFLOW_ENGINE_DIR))

from config_loader import ConfigLoader
from devin_cli_adapter import DevinCliAdapter
from model_resolver import resolve_model


def resolve_role_file(role: str) -> Path:
    """Resolve a role name or path to a markdown role file."""
    candidate = Path(role)
    if candidate.is_file():
        return candidate

    role_path = Path(__file__).parent / "roles" / f"{role}.md"
    if not role_path.is_file():
        raise FileNotFoundError(
            f"Role file not found: {role!r} (looked at {role_path})"
        )
    return role_path


def build_prompt(role_file: Path, prompt_file: Path) -> str:
    """Combine role and task prompt into a single prompt."""
    role_content = role_file.read_text(encoding="utf-8").strip()
    prompt_content = prompt_file.read_text(encoding="utf-8").strip()

    if not role_content:
        raise ValueError(f"Role file is empty: {role_file}")
    if not prompt_content:
        raise ValueError(f"Prompt file is empty: {prompt_file}")

    return f"{role_content}\n\n# Task\n\n{prompt_content}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generic Devin dispatcher with role and prompt files."
    )
    parser.add_argument(
        "--model",
        default=None,
        help=(
            "Devin model to use. If omitted, the model is resolved via "
            "resolve_model(agent, phase, config) using the new model routing "
            "config (model_overrides -> models -> model_profile -> default_model)."
        ),
    )
    parser.add_argument(
        "--agent",
        default=None,
        help=(
            "Agent name (e.g. 'coder', 'reviewer'). Used for model routing "
            "and to look up agent_skills in config.yaml."
        ),
    )
    parser.add_argument(
        "--phase",
        default=None,
        help=(
            "Phase type (e.g. 'plan', 'execute', 'verify'). Used for model "
            "routing via models.<phase_type> in config.yaml."
        ),
    )
    parser.add_argument(
        "--role",
        required=True,
        help="Role name (resolves to roles/<role>.md) or path to a role markdown file",
    )
    parser.add_argument(
        "--prompt-file", required=True, help="Path to the task prompt markdown file"
    )
    parser.add_argument(
        "--output-file",
        help="Path to write Devin output to; defaults to stdout",
    )
    parser.add_argument(
        "--work-dir",
        help="Workspace directory; defaults to current directory",
    )
    parser.add_argument(
        "--permission-mode",
        default=None,
        help="Devin permission mode (defaults to config or 'dangerous')",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Invocation timeout in seconds (default: 300)",
    )
    parser.add_argument(
        "--focused-context",
        action="append",
        default=[],
        help="Optional artifact path to include in the prompt; repeatable",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    role_file = resolve_role_file(args.role)
    prompt_file = Path(args.prompt_file)

    if not prompt_file.is_file():
        print(f"Prompt file not found: {prompt_file}", file=sys.stderr)
        return 1

    prompt = build_prompt(role_file, prompt_file)

    config = ConfigLoader.load()
    devin_cli_path = config.devin_cli_path
    work_dir = args.work_dir or str(Path.cwd())
    permission_mode = args.permission_mode or config.default_permission_mode

    # Model resolution: explicit --model wins; otherwise route via config.
    if args.model:
        model = args.model
    else:
        model = resolve_model(args.agent, args.phase, config)

    # Agent skill injection: if the agent is configured in agent_skills,
    # point the adapter at the configured skills_dir and pass the skill list
    # as a skill_filter so only the configured skills are eligible.
    agent_skills_map = config.agent_skills or {}
    selected_skills: list[str] | None = None
    skills_dir: str | None = None
    enable_skills = False
    if args.agent and args.agent in agent_skills_map:
        selected_skills = list(agent_skills_map[args.agent])
        skills_dir = str(config.skills_dir)
        enable_skills = True

    adapter = DevinCliAdapter(
        devin_cli_path=devin_cli_path,
        workspace=work_dir,
        model=model,
        permission_mode=permission_mode,
        skills_dir=skills_dir,
    )

    result = adapter.invoke(
        prompt,
        timeout=args.timeout,
        focused_context=args.focused_context or None,
        enable_skills=enable_skills,
        skill_filter=selected_skills,
    )

    if args.output_file:
        Path(args.output_file).write_text(result.output, encoding="utf-8")

    if result.output:
        print(result.output)
    if result.error:
        print(result.error, file=sys.stderr)

    return result.exit_code if result.exit_code is not None else (0 if result.success else 1)


if __name__ == "__main__":
    sys.exit(main())
