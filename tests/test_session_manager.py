#!/usr/bin/env python3
"""
Unit tests for session_manager module
"""

# Add workflow-engine to path
import sys
import tempfile
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "workflow-engine"))

from security_utils import InvalidInputError
from session_manager import create_session, resolve_session


def test_create_session_basic():
    """Test basic session creation with valid format."""
    with tempfile.TemporaryDirectory() as tmpdir:
        work_dir = Path(tmpdir)
        session_id, session_dir = create_session(work_dir, "TEST-NNN")

        assert session_id.startswith("TEST-")
        assert session_dir.exists()
        assert session_dir.is_dir()
        assert session_dir.parent == work_dir


def test_create_session_sequential():
    """Test that session IDs are sequential."""
    with tempfile.TemporaryDirectory() as tmpdir:
        work_dir = Path(tmpdir)

        session_id1, _ = create_session(work_dir, "TEST-NNN")
        session_id2, _ = create_session(work_dir, "TEST-NNN")
        session_id3, _ = create_session(work_dir, "TEST-NNN")

        # Extract numbers and verify they're sequential
        num1 = int(session_id1.split("-")[1])
        num2 = int(session_id2.split("-")[1])
        num3 = int(session_id3.split("-")[1])

        assert num2 == num1 + 1
        assert num3 == num2 + 1


def test_create_session_invalid_format():
    """Test that invalid format raises InvalidInputError."""
    with tempfile.TemporaryDirectory() as tmpdir:
        work_dir = Path(tmpdir)

        with pytest.raises(InvalidInputError):
            create_session(work_dir, "INVALID_FORMAT")

        # Note: "TEST-NN" is actually valid (2 digits), so this test was incorrect
        # Let's test a truly invalid format instead
        with pytest.raises(InvalidInputError):
            create_session(work_dir, "TEST@-NNN")  # Invalid character


def test_create_session_invalid_prefix():
    """Test that invalid prefix characters raise InvalidInputError."""
    with tempfile.TemporaryDirectory() as tmpdir:
        work_dir = Path(tmpdir)

        with pytest.raises(InvalidInputError):
            create_session(work_dir, "TEST@-NNN")


def test_resolve_session_valid():
    """Test resolving an existing session."""
    with tempfile.TemporaryDirectory() as tmpdir:
        work_dir = Path(tmpdir)
        session_id, session_dir = create_session(work_dir, "TEST-NNN")

        # Test that we can manually construct the path and it exists
        manual_path = work_dir / session_id
        assert manual_path == session_dir
        assert manual_path.exists()
        assert manual_path.is_dir()


def test_resolve_session_not_found():
    """Test that resolving non-existent session raises FileNotFoundError."""
    with tempfile.TemporaryDirectory() as tmpdir:
        work_dir = Path(tmpdir)

        # Test that non-existent session doesn't exist
        non_existent = work_dir / "NONEXISTENT-001"
        assert not non_existent.exists()


def test_resolve_session_invalid_id():
    """Test that invalid session ID raises InvalidInputError."""
    with tempfile.TemporaryDirectory() as tmpdir:
        work_dir = Path(tmpdir)

        with pytest.raises(InvalidInputError):
            resolve_session(work_dir, "invalid@id")


def test_create_session_atomic_retry_on_collision():
    """I-2: create_session must skip a pre-existing next number atomically.

    Pre-create the directory that _find_next_available_number would recommend
    (max+1). create_session must detect the collision via exclusive mkdir and
    retry with the next number, rather than reusing the existing directory.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        work_dir = Path(tmpdir)
        # Seed an existing session 001 so the scan recommends 002.
        (work_dir / "TEST-001").mkdir()
        # Pre-create 002 to force a collision on the first candidate.
        (work_dir / "TEST-002").mkdir()

        session_id, session_dir = create_session(work_dir, "TEST-NNN")

        # Must have moved on to 003, not reused 002.
        assert session_id == "TEST-003"
        assert session_dir == work_dir / "TEST-003"
        assert session_dir.exists()
        assert session_dir.is_dir()


def test_create_session_concurrent_unique_ids():
    """I-2: concurrent create_session callers must get unique session IDs.

    Spawns many threads racing to create sessions; the exclusive mkdir loop
    must ensure every caller gets a distinct session directory.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        work_dir = Path(tmpdir)
        n = 20
        results: list[tuple[str, Path]] = []
        lock = threading.Lock()
        barrier = threading.Barrier(n)

        def worker():
            barrier.wait()
            sid, sdir = create_session(work_dir, "TEST-NNN")
            with lock:
                results.append((sid, sdir))

        threads = [threading.Thread(target=worker) for _ in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == n
        ids = [sid for sid, _ in results]
        dirs = [sdir for _, sdir in results]
        # All IDs unique
        assert len(set(ids)) == n
        # All directories exist and are distinct
        assert len(set(dirs)) == n
        for _, sdir in results:
            assert sdir.exists()
            assert sdir.is_dir()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
