from __future__ import annotations

import base64
import logging
import mimetypes
import re
from pathlib import Path
from typing import Any

from devin_orchestrator.mcp._base import McpServerBase
from devin_orchestrator.security_utils import (  # noqa: E402
    InvalidInputError,
    PathTraversalError,
    validate_path_safe,
)

logger = logging.getLogger(__name__)


class McpResourcesMixin(McpServerBase):
    # --------------------------------------------------------------------- #
    # MCP resources support
    # --------------------------------------------------------------------- #
    def _is_session_dir_name(self, name: str) -> bool:
        return bool(re.match(r"^[A-Za-z0-9_-]+-\d+$", name))

    def _collect_resources(self, base: Path, uri_prefix: str) -> list[dict]:
        """Walk a directory and return file records as MCP resources."""
        resources: list[dict] = []
        for p in sorted(base.rglob("*"), key=lambda x: str(x)):
            if not p.is_file():
                continue
            rel = p.relative_to(base).as_posix()
            mime, _ = mimetypes.guess_type(str(p))
            try:
                size = p.stat().st_size
            except OSError:
                size = -1
            resources.append(
                {
                    "uri": f"{uri_prefix}{rel}",
                    "name": p.name,
                    "mimeType": mime or "application/octet-stream",
                    "size": size,
                }
            )
        return resources

    def _read_resource_contents(self, uri: str, target: Path) -> dict:
        """Return an MCP ResourceContents dict for a file."""
        try:
            text = target.read_text(encoding="utf-8")
            raw = text.encode("utf-8")
            if len(raw) > self.MAX_OUTPUT_BYTES:
                truncated = raw[: self.MAX_OUTPUT_BYTES].decode(
                    "utf-8", errors="replace"
                )
                text = truncated + "\n\n[... resource truncated ...]"
            mime = mimetypes.guess_type(str(target))[0] or "text/plain"
            return {"uri": uri, "mimeType": mime, "text": text}
        except UnicodeDecodeError:
            data = target.read_bytes()
            if len(data) > self.MAX_OUTPUT_BYTES:
                data = data[: self.MAX_OUTPUT_BYTES]
            b64 = base64.b64encode(data).decode("ascii")
            mime = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            return {"uri": uri, "mimeType": mime, "blob": b64}

    def _resources_list(self, request: dict) -> dict:
        """List workspace and session artifacts as MCP resources with pagination."""
        params = request.get("params", {})
        try:
            cursor = int(params.get("cursor", "0") or "0")
        except (TypeError, ValueError):
            return self._error(request, -32602, "Invalid cursor")
        page_size = 100

        resources: list[dict] = []
        if self.workspace:
            workspace_path = Path(self.workspace).expanduser()
            if workspace_path.is_dir():
                resources.extend(
                    self._collect_resources(workspace_path, "workspace://")
                )
        session_dir = self.config.session_work_dir
        if session_dir.is_dir():
            for entry in sorted(
                session_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True
            ):
                if not entry.is_dir() or not self._is_session_dir_name(entry.name):
                    continue
                resources.extend(
                    self._collect_resources(entry, f"session://{entry.name}/")
                )

        total = len(resources)
        page = resources[cursor : cursor + page_size]
        result: dict[str, Any] = {"resources": page}
        if cursor + page_size < total:
            result["nextCursor"] = str(cursor + page_size)
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": result,
        }

    def _resources_read(self, request: dict) -> dict:
        """Read a resource URI and return its contents."""
        params = request.get("params", {})
        uri = params.get("uri")
        if not uri or "://" not in uri:
            return self._error(request, -32602, "Missing or invalid uri")

        scheme, _, rest = uri.partition("://")
        if scheme == "workspace":
            if not self.workspace:
                return self._error(request, -32602, "Workspace not configured")
            base = Path(self.workspace).expanduser()
            if not base.is_dir():
                return self._error(request, -32602, "Workspace not found")
            try:
                target = validate_path_safe(base, base / rest, allow_absolute=False)
            except (InvalidInputError, PathTraversalError) as e:
                return self._error(request, -32602, f"Invalid workspace resource: {e}")
        elif scheme == "session":
            parts = rest.split("/", 1)
            if len(parts) != 2:
                return self._error(request, -32602, "Invalid session resource uri")
            session_id, path = parts
            from devin_orchestrator.session_manager import resolve_session

            try:
                base = resolve_session(self.config.session_work_dir, session_id)
            except (
                FileNotFoundError,
                ValueError,
                InvalidInputError,
                PathTraversalError,
            ) as e:
                return self._error(request, -32602, f"Invalid session: {e}")
            try:
                target = validate_path_safe(base, base / path, allow_absolute=False)
            except (InvalidInputError, PathTraversalError) as e:
                return self._error(request, -32602, f"Invalid session resource: {e}")
        else:
            return self._error(
                request, -32602, f"Unsupported resource scheme: {scheme}"
            )

        if not target.is_file():
            return self._error(request, -32602, f"Resource not found: {uri}")

        contents = self._read_resource_contents(uri, target)
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {"contents": [contents]},
        }

    def _resources_templates_list(self, request: dict) -> dict:
        """Return available resource URI templates."""
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {
                "resourceTemplates": [
                    {
                        "uriTemplate": "workspace://{path}",
                        "name": "Workspace file",
                    },
                    {
                        "uriTemplate": "session://{session_id}/{path}",
                        "name": "Session artifact",
                    },
                ]
            },
        }

    def _resources_subscribe(self, request: dict) -> dict:
        """Subscribe to resource changes (no-op; dynamic updates not supported)."""
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {},
        }

    def _resources_unsubscribe(self, request: dict) -> dict:
        """Unsubscribe from resource changes (no-op)."""
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {},
        }
