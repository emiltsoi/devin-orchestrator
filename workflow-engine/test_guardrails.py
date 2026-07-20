"""
Tests for guardrails.py

Covers leaf-module detection, file existence/syntax verification, and
compliance block verification. Subprocess calls are mocked for speed and
isolation.
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))

from guardrails import Guardrails


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


class TestIsLeafModule:
    def test_missing_module_is_not_leaf(self, tmp_path):
        assert Guardrails.is_leaf_module(tmp_path / "nope.py") is False

    def test_stdlib_only_module_is_leaf(self, tmp_path):
        path = _write(
            tmp_path / "leaf.py",
            "import os\nimport sys\nfrom pathlib import Path\nimport json\n",
        )
        assert Guardrails.is_leaf_module(path) is True

    def test_external_imports_above_threshold(self, tmp_path):
        path = _write(
            tmp_path / "coupled.py",
            "import os\nimport yaml\nimport requests\nimport pytest\n",
        )
        # 3 external imports > default max_coupling of 2
        assert Guardrails.is_leaf_module(path) is False

    def test_custom_max_coupling(self, tmp_path):
        path = _write(
            tmp_path / "coupled.py",
            "import os\nimport yaml\nimport requests\nimport pytest\n",
        )
        assert Guardrails.is_leaf_module(path, max_coupling=4) is True

    def test_from_import_form(self, tmp_path):
        path = _write(
            tmp_path / "mod.py",
            "from pathlib import Path\nimport yaml\nimport requests\n",
        )
        # The guardrails extractor pulls the imported name from `from X import Y`,
        # so "Path" counts as external (only "pathlib" is in the stdlib set).
        # External imports: Path, yaml, requests -> 3 total.
        assert Guardrails.is_leaf_module(path) is False
        assert Guardrails.is_leaf_module(path, max_coupling=3) is True

    def test_unreadable_file_returns_false(self, tmp_path):
        path = tmp_path / "bad.py"
        path.write_bytes(b"\xff\xfe\x00invalid")
        # read_text with utf-8 should raise; guardrail should swallow and
        # conservatively return False.
        assert Guardrails.is_leaf_module(path) is False


class TestVerifyFileExists:
    def test_missing_file(self, tmp_path):
        assert Guardrails.verify_file_exists(tmp_path / "nope.py") is False

    def test_trivial_file(self, tmp_path):
        path = _write(tmp_path / "small.py", "print('hi')\n")
        assert Guardrails.verify_file_exists(path) is False

    def test_nontrivial_file(self, tmp_path):
        path = _write(tmp_path / "big.py", "\n".join(f"# line {i}" for i in range(15)))
        assert Guardrails.verify_file_exists(path) is True


class TestVerifySyntax:
    def test_missing_file(self, tmp_path):
        assert Guardrails.verify_syntax(tmp_path / "nope.py") is False

    def test_valid_syntax(self, tmp_path):
        path = _write(tmp_path / "ok.py", "x = 1\n")
        with patch("guardrails.subprocess.run") as mock_run:
            mock_run.return_value = type("R", (), {"returncode": 0})()
            assert Guardrails.verify_syntax(path) is True

    def test_invalid_syntax(self, tmp_path):
        path = _write(tmp_path / "bad.py", "def (\n")
        with patch("guardrails.subprocess.run") as mock_run:
            mock_run.return_value = type("R", (), {"returncode": 1})()
            assert Guardrails.verify_syntax(path) is False

    def test_subprocess_exception_returns_false(self, tmp_path):
        path = _write(tmp_path / "ok.py", "x = 1\n")
        with patch("guardrails.subprocess.run", side_effect=OSError("boom")):
            assert Guardrails.verify_syntax(path) is False


class TestVerifyComplianceBlock:
    def test_no_file_path(self):
        result = Guardrails.verify_compliance_block("BLOCK", file_path=None)
        assert result["verified"] is False
        assert "No file path" in " ".join(result["notes"])

    def test_missing_file(self, tmp_path):
        result = Guardrails.verify_compliance_block("BLOCK", file_path=tmp_path / "x.py")
        assert result["verified"] is False
        assert "File does not exist" in " ".join(result["notes"])

    def test_trivial_file(self, tmp_path):
        path = _write(tmp_path / "small.py", "print('hi')\n")
        result = Guardrails.verify_compliance_block("BLOCK", file_path=path)
        assert result["verified"] is False

    def test_python_file_syntax_passes(self, tmp_path):
        path = _write(tmp_path / "ok.py", "\n".join(f"# {i}" for i in range(15)))
        with patch("guardrails.subprocess.run") as mock_run:
            mock_run.return_value = type("R", (), {"returncode": 0})()
            result = Guardrails.verify_compliance_block("BLOCK", file_path=path)
        assert result["verified"] is True
        assert "Syntax verification passed" in " ".join(result["notes"])

    def test_python_file_syntax_fails(self, tmp_path):
        path = _write(tmp_path / "bad.py", "\n".join(f"# {i}" for i in range(15)))
        with patch("guardrails.subprocess.run") as mock_run:
            mock_run.return_value = type("R", (), {"returncode": 1})()
            result = Guardrails.verify_compliance_block("BLOCK", file_path=path)
        assert result["verified"] is False
        assert "Syntax verification FAILED" in " ".join(result["notes"])

    def test_non_python_file_verifies_existence_only(self, tmp_path):
        path = _write(tmp_path / "doc.md", "\n".join(f"line {i}" for i in range(15)))
        result = Guardrails.verify_compliance_block("BLOCK", file_path=path)
        assert result["verified"] is True
        assert "Non-Python file" in " ".join(result["notes"])


class TestCheckLeafModuleBoundary:
    def test_missing_module_zero_coupling(self, tmp_path):
        result = Guardrails.check_leaf_module_boundary(
            tmp_path / "nope.py", tmp_path
        )
        assert result["is_leaf"] is True
        assert result["coupling_count"] == 0

    def test_counts_external_imports(self, tmp_path):
        path = _write(
            tmp_path / "mod.py",
            "import os\nimport yaml\nimport requests\nimport pytest\n",
        )
        result = Guardrails.check_leaf_module_boundary(path, tmp_path)
        assert result["coupling_count"] == 3  # yaml, requests, pytest
        assert result["is_leaf"] is False

    def test_stdlib_only_is_leaf(self, tmp_path):
        path = _write(tmp_path / "mod.py", "import os\nimport sys\nfrom pathlib import Path\n")
        result = Guardrails.check_leaf_module_boundary(path, tmp_path)
        # `from pathlib import Path` extracts "Path" (not in stdlib set), so
        # coupling_count is 1. Still within the leaf threshold of 2.
        assert result["coupling_count"] == 1
        assert result["is_leaf"] is True
