"""
STATE.md artifact helper.

Provides load/save/init helpers for the canonical project-memory artifact
described in work/GSD-ABSORB-001/PLAN.md. The preferred on-disk format is a
Markdown file with a YAML frontmatter block; a plain JSON fallback is also
supported for tooling that prefers JSON.

Schema (all fields always present after init_state):

    milestone: ""
    phase: ""
    status: "in_progress"
    decisions: []
    blockers: []
    completed_plans: []
    pending_plans: []
    metrics: {}
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import yaml

# Canonical field order. Preserving order makes the artifact diff-friendly
# and matches the schema documented above.
DEFAULT_STATE: dict[str, Any] = {
    "milestone": "",
    "phase": "",
    "status": "in_progress",
    "decisions": [],
    "blockers": [],
    "completed_plans": [],
    "pending_plans": [],
    "metrics": {},
}

REQUIRED_FIELDS = tuple(DEFAULT_STATE.keys())

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def _normalize(state: dict[str, Any]) -> dict[str, Any]:
    """Return a state dict with all required fields present and ordered.

    Missing fields are filled in with the defaults from ``DEFAULT_STATE``.
    Unknown fields are preserved (after the known ones) so callers can stash
    extra metadata without losing it on round-trip.
    """
    normalized: dict[str, Any] = {}
    for key in REQUIRED_FIELDS:
        if key in state:
            normalized[key] = copy.deepcopy(state[key])
        else:
            normalized[key] = copy.deepcopy(DEFAULT_STATE[key])
    for key, value in state.items():
        if key not in normalized:
            normalized[key] = value
    return normalized


def _dump_frontmatter(state: dict[str, Any]) -> str:
    """Serialize a state dict to a Markdown+YAML-frontmatter string."""
    body = yaml.safe_dump(state, sort_keys=False, allow_unicode=True)
    return f"---\n{body}---\n"


def _parse_frontmatter(text: str) -> dict[str, Any] | None:
    """Parse a leading YAML frontmatter block. Return None if absent."""
    if not text.startswith("---"):
        return None
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return None
    try:
        loaded = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return None
    return loaded if isinstance(loaded, dict) else None


def load_state(path: str | Path) -> dict[str, Any]:
    """Load a STATE artifact from disk.

    Supports both the preferred Markdown+YAML-frontmatter format and a plain
    JSON fallback (selected by ``.json`` extension or by file content).

    Args:
        path: Path to the artifact file.

    Returns:
        A normalized state dict with all required fields present.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file cannot be parsed as either format.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"State artifact not found: {p}")

    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() == ".json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON state artifact {p}: {e}") from e
        if not isinstance(data, dict):
            raise ValueError(f"JSON state artifact {p} must be a mapping")
        return _normalize(data)

    # Markdown + YAML frontmatter (preferred)
    frontmatter = _parse_frontmatter(text)
    if frontmatter is not None:
        return _normalize(frontmatter)

    # JSON fallback: a Markdown file whose body is JSON.
    stripped = text.strip()
    if stripped.startswith("{"):
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"State artifact {p} is not valid frontmatter or JSON: {e}"
            ) from e
        if not isinstance(data, dict):
            raise ValueError(f"State artifact {p} must be a mapping")
        return _normalize(data)

    raise ValueError(
        f"State artifact {p} has no YAML frontmatter and is not JSON"
    )


def save_state(path: str | Path, state: dict[str, Any]) -> None:
    """Save a state dict to disk.

    The format is selected by the file extension: ``.json`` writes plain
    JSON; any other extension (including ``.md``) writes the preferred
    Markdown + YAML frontmatter format.

    Args:
        path: Destination path. Parent directories are created if missing.
        state: State dict. Missing required fields are filled with defaults.
    """
    p = Path(path)
    if p.parent and not p.parent.exists():
        p.parent.mkdir(parents=True, exist_ok=True)

    normalized = _normalize(state)
    if p.suffix.lower() == ".json":
        p.write_text(
            json.dumps(normalized, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    else:
        p.write_text(_dump_frontmatter(normalized), encoding="utf-8")


def init_state(path: str | Path, milestone: str, phase: str) -> dict[str, Any]:
    """Initialize a new STATE artifact with the given milestone and phase.

    The remaining fields are seeded with their defaults (status="in_progress",
    empty lists for decisions/blockers/plans, empty metrics dict). The file is
    written immediately so callers can rely on it existing on return.

    Args:
        path: Destination path.
        milestone: Milestone identifier.
        phase: Phase identifier.

    Returns:
        The normalized state dict that was written.
    """
    state = copy.deepcopy(DEFAULT_STATE)
    state["milestone"] = milestone
    state["phase"] = phase
    normalized = _normalize(state)
    save_state(path, normalized)
    return normalized


__all__ = [
    "DEFAULT_STATE",
    "REQUIRED_FIELDS",
    "init_state",
    "load_state",
    "save_state",
]
