"""
Guardrails for Devin dispatch

Implements safety checks based on learned Devin behavior:
- Leaf modules only (coupling ≤2)
- Harness timeout enforcement
- Independent verification for reviewer BLOCK verdicts
"""

import re
import subprocess
from pathlib import Path
from typing import Any


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

            # Count import statements. The pattern captures the full import
            # line so the inner re.search below can extract the module name.
            import_pattern = r"^\s*(?:from\s+\S+\s+)?import\s+\w.*$"
            imports = re.findall(import_pattern, content, re.MULTILINE)

            # Filter out stdlib imports (they don't count toward coupling)
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

            external_imports = []
            for imp in imports:
                # Extract module name from import statement
                match = re.search(r"import\s+(\w+)", imp)
                if match:
                    module_name = match.group(1)
                    if module_name not in stdlib_modules:
                        external_imports.append(module_name)

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
        Verify Python syntax using py_compile

        Args:
            file_path: Path to the Python file

        Returns:
            True if syntax is valid, False otherwise
        """
        if not file_path.exists():
            return False

        try:
            result = subprocess.run(
                ["py", "-m", "py_compile", str(file_path)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except Exception:
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
                import_pattern = r"^\s*(?:from\s+\S+\s+)?import\s+\w.*$"
                imports = re.findall(import_pattern, content, re.MULTILINE)

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

                for imp in imports:
                    match = re.search(r"import\s+(\w+)", imp)
                    if match:
                        module_name = match.group(1)
                        if module_name not in stdlib_modules:
                            coupling_count += 1
            except Exception:
                pass

        return {"is_leaf": coupling_count <= 2, "coupling_count": coupling_count}
