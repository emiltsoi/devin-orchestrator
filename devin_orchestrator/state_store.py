"""Workflow session state store with append-only JSONL persistence."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from pathlib import Path


def _json_default(obj: Any) -> Any:
    """JSON encoder default that writes enum values instead of enum names."""
    if isinstance(obj, Enum):
        return obj.value
    return str(obj)


@runtime_checkable
class StateStore(Protocol):
    """Protocol for durable workflow session state."""

    def init(self, session_id: str, session_dir: Path) -> None:
        """Initialize the store for a session, creating the backing file/table."""
        ...

    def set_status(self, status: str, message: str = "") -> None:
        """Append a workflow status record."""
        ...

    def get_status(self) -> str:
        """Return the latest workflow status."""
        ...

    def is_final(self) -> bool:
        """Return True if the workflow has reached a terminal state."""
        ...

    def save_stage(self, stage_name: str, stage_result: dict[str, Any]) -> None:
        """Persist a stage result."""
        ...

    def load_stage(self, stage_name: str) -> dict[str, Any] | None:
        """Return the latest stored result for a given stage."""
        ...

    def list_stages(self) -> list[dict[str, Any]]:
        """Return all stage results in chronological order."""
        ...

    def as_dict(self, manifest_name: str = "") -> dict[str, Any]:
        """Return a results-style dict for the current session."""
        ...


class JsonlStateStore:
    """Append-only JSONL state store backed by state.jsonl in the session dir."""

    def __init__(self) -> None:
        self.session_id: str = ""
        self.session_dir: Path | None = None
        self._path: Path | None = None

    def init(self, session_id: str, session_dir: Path) -> None:
        self.session_id = session_id
        self.session_dir = session_dir
        self._path = session_dir / "state.jsonl"
        session_dir.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.write_text("", encoding="utf-8")

    def _append(self, record: dict[str, Any]) -> None:
        if self._path is None:
            raise RuntimeError("StateStore has not been initialized")
        record["timestamp"] = datetime.now(timezone.utc).isoformat()
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=_json_default) + "\n")

    def set_status(self, status: str, message: str = "") -> None:
        self._append({"type": "status", "status": status, "message": message})

    def get_status(self) -> str:
        status = "unknown"
        for record in self._records():
            if record.get("type") == "status":
                status = record.get("status", "unknown")
        return status

    def is_final(self) -> bool:
        return self.get_status() in {"completed", "failed", "escalated", "cancelled"}

    def save_stage(self, stage_name: str, stage_result: dict[str, Any]) -> None:
        self._append({"type": "stage", "name": stage_name, "result": stage_result})

    def load_stage(self, stage_name: str) -> dict[str, Any] | None:
        latest: dict[str, Any] | None = None
        for record in self._records():
            if record.get("type") == "stage" and record.get("name") == stage_name:
                latest = record.get("result")
        return latest

    def list_stages(self) -> list[dict[str, Any]]:
        by_name: dict[str, dict[str, Any]] = {}
        for record in self._records():
            if record.get("type") == "stage":
                name = record.get("name")
                if isinstance(name, str):
                    by_name[name] = record.get("result", {})
        return list(by_name.values())

    def _records(self) -> list[dict[str, Any]]:
        if self._path is None or not self._path.exists():
            return []
        records: list[dict[str, Any]] = []
        with open(self._path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError as e:
                        # Skip corrupt lines; the file is append-only and
                        # line-oriented, so one bad line should not break recovery.
                        raise RuntimeError(
                            f"Corrupt state line in {self._path}: {e}"
                        ) from e
        return records

    def as_dict(self, manifest_name: str = "") -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "manifest": manifest_name,
            "stages": self.list_stages(),
            "final_status": self.get_status(),
        }


class SqliteStateStore:
    """SQLite-backed state store with WAL for concurrent access."""

    def __init__(self) -> None:
        self.session_id: str = ""
        self.session_dir: Path | None = None
        self._db: Path | None = None

    def init(self, session_id: str, session_dir: Path) -> None:
        self.session_id = session_id
        self.session_dir = session_dir
        self._db = session_dir / "state.db"
        session_dir.mkdir(parents=True, exist_ok=True)
        conn = self._connect()
        try:
            with conn:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS state ("
                    "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                    "ts TEXT,"
                    "kind TEXT,"
                    "name TEXT,"
                    "payload TEXT"
                    ")"
                )
        finally:
            conn.close()

    def _connect(self) -> sqlite3.Connection:
        if self._db is None:
            raise RuntimeError("StateStore has not been initialized")
        conn = sqlite3.connect(str(self._db))
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _insert(self, kind: str, name: str | None, payload: dict[str, Any]) -> None:
        if self._db is None:
            raise RuntimeError("StateStore has not been initialized")
        conn = self._connect()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO state (ts, kind, name, payload) VALUES (?, ?, ?, ?)",
                    (
                        datetime.now(timezone.utc).isoformat(),
                        kind,
                        name,
                        json.dumps(payload, default=_json_default),
                    ),
                )
        finally:
            conn.close()

    def set_status(self, status: str, message: str = "") -> None:
        self._insert("status", None, {"status": status, "message": message})

    def get_status(self) -> str:
        status = "unknown"
        conn = self._connect()
        try:
            with conn:
                row = conn.execute(
                    "SELECT payload FROM state WHERE kind='status' "
                    "ORDER BY id DESC LIMIT 1"
                ).fetchone()
                if row:
                    payload = json.loads(row[0])
                    status = payload.get("status", "unknown")
        finally:
            conn.close()
        return status

    def is_final(self) -> bool:
        return self.get_status() in {"completed", "failed", "escalated", "cancelled"}

    def save_stage(self, stage_name: str, stage_result: dict[str, Any]) -> None:
        self._insert("stage", stage_name, stage_result)

    def load_stage(self, stage_name: str) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            with conn:
                row = conn.execute(
                    "SELECT payload FROM state WHERE kind='stage' AND name=? "
                    "ORDER BY id DESC LIMIT 1",
                    (stage_name,),
                ).fetchone()
                if row:
                    return json.loads(row[0])
        finally:
            conn.close()
        return None

    def list_stages(self) -> list[dict[str, Any]]:
        conn = self._connect()
        by_name: dict[str, dict[str, Any]] = {}
        try:
            with conn:
                rows = conn.execute(
                    "SELECT name, payload FROM state WHERE kind='stage' ORDER BY id"
                ).fetchall()
                for name, payload in rows:
                    data = json.loads(payload)
                    if isinstance(name, str):
                        by_name[name] = data
        finally:
            conn.close()
        return list(by_name.values())

    def as_dict(self, manifest_name: str = "") -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "manifest": manifest_name,
            "stages": self.list_stages(),
            "final_status": self.get_status(),
        }
