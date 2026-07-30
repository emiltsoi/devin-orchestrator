# mypy: disable-error-code=attr-defined

from __future__ import annotations

import base64
import binascii
import json
import logging
import mimetypes
import os
import re
from pathlib import Path

from devin_orchestrator.security_utils import (  # noqa: E402
    InvalidInputError,
    PathTraversalError,
    validate_path_safe,
    validate_workspace_path,
)

logger = logging.getLogger(__name__)


class McpArtifactMixin:

    def _tool_read_artifact(self, arguments: dict) -> list[dict]:
        """
        Read a file from a workspace or session directory.

        Text files support optional 1-based line offset/limit and are
        truncated to MAX_OUTPUT_BYTES. Binary files are returned as base64,
        with image types exposed as MCP image content.

        Args:
            arguments: Tool arguments containing path, optional session_id,
                workspace, offset, and limit.

        Returns:
            List containing file contents

        Raises:
            FileNotFoundError: If file is not found
        """
        try:
            path = Path(arguments["path"])
        except (KeyError, TypeError) as e:
            return [self._text_content(f"Invalid path parameter: {e}")]

        try:
            base = self._resolve_artifact_base(arguments)
        except (FileNotFoundError, InvalidInputError, PathTraversalError) as e:
            return [self._text_content(f"Invalid base: {e}")]

        try:
            if path.is_absolute():
                target = validate_path_safe(base, path, allow_absolute=True)
            else:
                target = validate_path_safe(base, base / path, allow_absolute=True)
        except (InvalidInputError, PathTraversalError) as e:
            return [self._text_content(f"Invalid path: {e}")]

        if not target.is_file():
            raise FileNotFoundError(f"File not found: {target}")

        try:
            offset = int(arguments.get("offset", 1))
        except (TypeError, ValueError) as e:
            return [self._text_content(f"Invalid offset: {e}")]

        limit = arguments.get("limit")
        try:
            if limit is not None:
                limit = int(limit)
        except (TypeError, ValueError) as e:
            return [self._text_content(f"Invalid limit: {e}")]

        if offset < 1:
            return [self._text_content("offset must be >= 1")]
        if limit is not None and limit < 0:
            return [self._text_content("limit must be >= 0")]

        try:
            text = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return self._read_binary_artifact(target)

        lines = text.splitlines()
        start = offset - 1
        end = None if limit is None else start + limit
        selected = lines[start:end]
        content = "\n".join(selected)

        raw = content.encode("utf-8")
        if len(raw) > self.MAX_OUTPUT_BYTES:
            truncated = raw[: self.MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")
            total = len(text.encode("utf-8"))
            content = (
                truncated
                + f"\n\n[... output truncated at {self.MAX_OUTPUT_BYTES} bytes; "
                f"total {total} bytes ...]"
            )

        return [self._text_content(content)]

    def _resolve_artifact_base(self, arguments: dict) -> Path:
        """Resolve the base directory for artifact operations."""
        from devin_orchestrator.session_manager import resolve_session

        session_id = arguments.get("session_id")
        if session_id:
            try:
                return resolve_session(self.config.session_work_dir, str(session_id))
            except (FileNotFoundError, ValueError, InvalidInputError, PathTraversalError) as e:
                raise FileNotFoundError(f"Failed to resolve session {session_id}: {e}") from e

        provided_workspace = arguments.get("workspace") or self.workspace
        if provided_workspace:
            try:
                return validate_workspace_path(
                    str(provided_workspace), base_allowed_dir=self.config.global_root
                )
            except (InvalidInputError, PathTraversalError) as e:
                raise InvalidInputError(f"Invalid workspace: {e}") from e

        return self.config.session_work_dir

    def _resolve_artifact_target(self, arguments: dict, base: Path) -> Path:
        """Resolve and validate a path relative to an artifact base directory."""
        try:
            path = Path(arguments["path"])
        except (KeyError, TypeError) as e:
            raise InvalidInputError(f"Invalid path parameter: {e}") from e

        try:
            if path.is_absolute():
                return validate_path_safe(base, path, allow_absolute=True)
            return validate_path_safe(base, base / path, allow_absolute=True)
        except (InvalidInputError, PathTraversalError) as e:
            raise InvalidInputError(f"Invalid path: {e}") from e

    def _read_binary_artifact(self, target: Path) -> list[dict]:
        """Return a binary artifact as base64 text, or as an image blob."""
        data = target.read_bytes()
        mime, _ = mimetypes.guess_type(str(target))
        mime = mime or "application/octet-stream"
        if len(data) > self.MAX_OUTPUT_BYTES:
            data = data[: self.MAX_OUTPUT_BYTES]
        b64 = base64.b64encode(data).decode("ascii")
        if mime.startswith("image/"):
            return [{"type": "image", "mimeType": mime, "data": b64}]
        payload = json.dumps({"encoding": "base64", "mime": mime, "data": b64})
        return [self._text_content(payload)]

    def _walk_directory(
        self, target: Path, recursive: bool, max_depth: int, files_only: bool
    ) -> list[dict]:
        """Walk a directory and return a list of sanitized entry records."""
        entries: list[dict] = []

        if not recursive:
            for entry in sorted(target.iterdir()):
                etype = "directory" if entry.is_dir() else "file"
                if files_only and etype == "directory":
                    continue
                rel = str(entry.relative_to(target))
                size = 0
                try:
                    if etype == "file" and entry.is_file():
                        size = entry.stat().st_size
                except OSError:
                    size = -1
                entries.append({"name": entry.name, "type": etype, "size": size, "path": rel})
            return entries

        for root, dirs, files in os.walk(target):
            rel_root = Path(os.path.relpath(root, target))
            depth = 0 if rel_root == Path(".") else len(rel_root.parts)
            if depth > max_depth:
                continue
            if depth == max_depth:
                dirs[:] = []

            if not files_only:
                for d in sorted(dirs):
                    full = Path(root) / d
                    entries.append(
                        {
                            "name": d,
                            "type": "directory",
                            "size": 0,
                            "path": str(rel_root / d),
                        }
                    )
            for f in sorted(files):
                full = Path(root) / f
                size = 0
                try:
                    if full.is_file():
                        size = full.stat().st_size
                except OSError:
                    size = -1
                entries.append(
                    {
                        "name": f,
                        "type": "file",
                        "size": size,
                        "path": str(rel_root / f),
                    }
                )
        return entries

    def _tool_list_directory(self, arguments: dict) -> list[dict]:
        """List files and directories under a validated workspace or session path."""
        try:
            base = self._resolve_artifact_base(arguments)
            target = self._resolve_artifact_target(arguments, base)
        except (FileNotFoundError, InvalidInputError, PathTraversalError) as e:
            return [self._text_content(f"Invalid base or path: {e}")]

        if not target.is_dir():
            raise NotADirectoryError(f"Not a directory: {target}")

        try:
            recursive = bool(arguments.get("recursive", False))
            max_depth = int(arguments.get("max_depth", 3 if recursive else 1))
        except (TypeError, ValueError) as e:
            return [self._text_content(f"Invalid list options: {e}")]

        if max_depth < 0:
            return [self._text_content("max_depth must be >= 0")]

        entries = self._walk_directory(target, recursive, max_depth, files_only=False)
        return [self._text_content(json.dumps(entries, indent=2, default=str))]

    def _tool_list_artifacts(self, arguments: dict) -> list[dict]:
        """List files recursively in a session directory or workspace."""
        try:
            base = self._resolve_artifact_base(arguments)
            target = self._resolve_artifact_target(arguments, base)
        except (FileNotFoundError, InvalidInputError, PathTraversalError) as e:
            return [self._text_content(f"Invalid base or path: {e}")]

        if not target.is_dir():
            raise NotADirectoryError(f"Not a directory: {target}")

        try:
            recursive = bool(arguments.get("recursive", True))
            max_depth = int(arguments.get("max_depth", 10))
        except (TypeError, ValueError) as e:
            return [self._text_content(f"Invalid list options: {e}")]

        if max_depth < 0:
            return [self._text_content("max_depth must be >= 0")]

        entries = self._walk_directory(target, recursive, max_depth, files_only=True)
        return [self._text_content(json.dumps(entries, indent=2, default=str))]

    def _tool_write_artifact(self, arguments: dict) -> list[dict]:
        """Write or overwrite a text or base64 file under a validated path."""
        try:
            content = arguments["content"]
            encoding = arguments.get("encoding", "utf-8")
        except (KeyError, TypeError) as e:
            return [self._text_content(f"Invalid arguments: {e}")]

        try:
            base = self._resolve_artifact_base(arguments)
            target = self._resolve_artifact_target(arguments, base)
        except (FileNotFoundError, InvalidInputError, PathTraversalError) as e:
            return [self._text_content(f"Invalid base or path: {e}")]

        if target.is_dir():
            return [self._text_content("Cannot write to a directory path")]

        if encoding not in ("utf-8", "base64"):
            return [self._text_content("encoding must be 'utf-8' or 'base64'")]

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if encoding == "base64":
                raw = base64.b64decode(content)
                target.write_bytes(raw)
            else:
                target.write_text(content, encoding="utf-8")
        except (OSError, binascii.Error, ValueError) as e:
            return [self._text_content(f"Failed to write {target}: {e}")]

        return [self._text_content(f"Wrote {target}")]

    def _tool_apply_patch(self, arguments: dict) -> list[dict]:
        """Apply a unified diff patch to a file under a validated path."""
        try:
            patch = arguments["patch"]
        except (KeyError, TypeError) as e:
            return [self._text_content(f"Invalid arguments: {e}")]

        try:
            base = self._resolve_artifact_base(arguments)
            target = self._resolve_artifact_target(arguments, base)
        except (FileNotFoundError, InvalidInputError, PathTraversalError) as e:
            return [self._text_content(f"Invalid base or path: {e}")]

        if not target.is_file():
            raise FileNotFoundError(f"File not found: {target}")

        try:
            self._apply_unified_diff(target, patch)
        except (InvalidInputError, OSError) as e:
            return [self._text_content(f"Failed to apply patch: {e}")]

        return [self._text_content(f"Patched {target}")]

    def _apply_unified_diff(self, file_path: Path, diff: str) -> None:
        """Apply a unified diff to a text file in-place."""
        if not file_path.is_file():
            raise FileNotFoundError(f"File not found: {file_path}")

        lines = file_path.read_text(encoding="utf-8").splitlines()
        diff_lines = diff.splitlines()
        hunks: list[tuple[int, list[str]]] = []

        i = 0
        while i < len(diff_lines):
            line = diff_lines[i]
            if line.startswith("@@"):
                m = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
                if not m:
                    raise InvalidInputError(f"Invalid hunk header: {line}")
                old_start = int(m.group(1))
                i += 1
                hunk: list[str] = []
                while (
                    i < len(diff_lines)
                    and not diff_lines[i].startswith("@@")
                    and not diff_lines[i].startswith("---")
                    and not diff_lines[i].startswith("+++")
                ):
                    hunk.append(diff_lines[i])
                    i += 1
                hunks.append((old_start, hunk))
            else:
                i += 1

        offset = 0
        for old_start, hunk in hunks:
            pos = old_start - 1 + offset
            if pos < 0 or pos > len(lines):
                raise InvalidInputError(f"Hunk starting at line {old_start} is out of range")
            old_idx = pos
            new_lines: list[str] = []
            for dl in hunk:
                if not dl:
                    continue
                if dl.startswith("\\"):
                    continue
                if dl.startswith(" "):
                    if old_idx >= len(lines) or lines[old_idx] != dl[1:]:
                        raise InvalidInputError(f"Context mismatch at line {old_idx + 1}")
                    new_lines.append(dl[1:])
                    old_idx += 1
                elif dl.startswith("-"):
                    if old_idx >= len(lines) or lines[old_idx] != dl[1:]:
                        raise InvalidInputError(f"Remove mismatch at line {old_idx + 1}")
                    old_idx += 1
                elif dl.startswith("+"):
                    new_lines.append(dl[1:])
                else:
                    raise InvalidInputError(f"Unexpected diff line: {dl!r}")
            lines[pos:old_idx] = new_lines
            offset += len(new_lines) - (old_idx - pos)

        file_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
