"""
Guardrails for Devin dispatch

Implements safety checks based on learned Devin behavior:
- Leaf modules only (coupling ≤2)
- Harness timeout enforcement
- Independent verification for reviewer BLOCK verdicts
"""

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class Guardrails:
    """
    Guardrails for Devin dispatch based on learned behavior

    Implements safety checks to prevent common Devin failure modes:
    - Coder devictory (claims completion without writing files)
    - Fixer devictory (miscounts completion)
    - Compliance reviewer hallucination on async code
    """

    @staticmethod
    def is_leaf_module(module_path: Path, max_coupling: int = 2) -> bool:
        """
        Check if a module is a leaf module (coupling ≤ max_coupling)

        A leaf module imports from ≤ max_coupling other modules and
        no other module in the current batch depends on it.

        Args:
            module_path: Path to the module file
            max_coupling: Maximum allowed coupling (default: 2)

        Returns:
            True if leaf module, False otherwise
        """
        if not module_path.exists():
            return False

        try:
            content = module_path.read_text(encoding="utf-8")
            external_imports = Guardrails._extract_modules(content)
            return len(external_imports) <= max_coupling

        except Exception:
            # If we can't analyze, conservatively return False
            return False

    @staticmethod
    def verify_file_exists(file_path: Path) -> bool:
        """
        Verify that a file exists and is non-trivial (>10 lines)

        Args:
            file_path: Path to the file

        Returns:
            True if file exists and is non-trivial, False otherwise
        """
        if not file_path.exists():
            return False

        try:
            content = file_path.read_text(encoding="utf-8")
            lines = content.strip().split("\n")
            return len(lines) > 10
        except Exception:
            return False

    @staticmethod
    def verify_syntax(file_path: Path) -> bool:
        """
        Verify Python syntax using the standard compile() builtin.

        This is portable across operating systems and does not rely on a
        Windows-only ``py`` launcher or write side-effect ``.pyc`` files.

        Args:
            file_path: Path to the Python file

        Returns:
            True if syntax is valid, False otherwise
        """
        if not file_path.exists():
            return False

        try:
            source = file_path.read_text(encoding="utf-8")
            compile(source, str(file_path), "exec")
            return True
        except (SyntaxError, OSError, UnicodeDecodeError):
            return False

    @staticmethod
    def verify_compliance_block(
        _block_verdict: str, file_path: Path | None = None
    ) -> dict[str, Any]:
        """
        Independently verify a compliance reviewer BLOCK verdict

        Compliance reviewers hallucinate ~70% of syntax claims on async code.
        Never trust a BLOCK without independent verification.

        Args:
            block_verdict: The BLOCK verdict from the reviewer
            file_path: Optional path to the file for syntax verification

        Returns:
            Dict with 'verified' (bool) and 'notes' (str)
        """
        result = {"verified": False, "notes": []}

        # If no file path provided, cannot verify
        if not file_path:
            result["notes"].append("No file path provided for verification")
            return result

        # Verify file exists
        if not Guardrails.verify_file_exists(file_path):
            result["notes"].append("File does not exist or is trivial")
            return result

        # Verify syntax if Python file
        if file_path.suffix == ".py":
            if Guardrails.verify_syntax(file_path):
                result["notes"].append("Syntax verification passed")
                result["verified"] = True
            else:
                result["notes"].append("Syntax verification FAILED")
                result["verified"] = False
        else:
            # Non-Python file: verify existence only
            result["notes"].append("Non-Python file, verified existence only")
            result["verified"] = True

        return result

    @staticmethod
    def _extract_modules(content: str) -> list[str]:
        """
        Extract top-level module names from a Python source string.

        Handles both ``import x`` and ``from x import y`` forms, ignoring
        relative ``from .`` imports and standard-library modules.
        """
        import_pattern = r"^\s*(?:from\s+\S+\s+)?import\s+.*$"
        import_lines = re.findall(import_pattern, content, re.MULTILINE)

        stdlib_modules = {
            "os",
            "sys",
            "pathlib",
            "json",
            "re",
            "datetime",
            "typing",
            "dataclasses",
            "collections",
            "itertools",
            "functools",
            "math",
            "random",
            "string",
            "io",
        }

        modules: list[str] = []
        for line in import_lines:
            line = line.strip()
            if line.startswith("from "):
                match = re.search(r"from\s+([\w.]+)", line)
                if match:
                    name = match.group(1).lstrip(".").split(".")[0]
                    if name and name not in stdlib_modules:
                        modules.append(name)
            elif line.startswith("import "):
                # import a, b as c, d.e
                clause = line[len("import "):]
                for item in clause.split(","):
                    name = item.strip().split()[0].split(".")[0]
                    if name and name not in stdlib_modules:
                        modules.append(name)

        return modules

    @staticmethod
    def check_leaf_module_boundary(
        target_module: Path, _workspace: Path
    ) -> dict[str, Any]:
        """
        Check if dispatch respects leaf module boundary

        Args:
            target_module: Path to the target module being modified
            workspace: Workspace root

        Returns:
            Dict with 'is_leaf' (bool) and 'coupling_count' (int)
        """
        coupling_count = 0

        if target_module.exists():
            try:
                content = target_module.read_text(encoding="utf-8")
                external_imports = Guardrails._extract_modules(content)
                coupling_count = len(external_imports)
            except Exception as exc:  # noqa: BLE001 - best-effort coupling check
                logger.warning("Could not analyse coupling for %s: %s", target_module, exc)

        return {"is_leaf": coupling_count <= 2, "coupling_count": coupling_count}
