# -*- coding: utf-8 -*-
"""
Skill Evaluator - Evaluates skill outputs with confidence scoring
Implements hybrid automated + human evaluation system
"""

from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import re
import yaml


@dataclass
class EvaluationResult:
    """Result of skill evaluation"""
    confidence: float  # 0.0 to 1.0
    passed: bool
    issues: List[str]
    auto_approvable: bool
    requires_user_input: bool
    details: Dict[str, Any]


class SkillEvaluator:
    """
    Evaluates skill outputs with confidence scoring

    Implements hybrid evaluation:
    - Automated checks for objective criteria (structural, Iron Law, test results)
    - User gates for subjective decisions (design quality, strategic choices)
    - Confidence-based decision logic
    """

    def __init__(self, harness_root: Path):
        """
        Initialize skill evaluator

        Args:
            harness_root: Root directory of the harness
        """
        self.harness_root = harness_root
        self.skills_dir = harness_root / 'skills'

    def evaluate_skill_output(
        self,
        skill_name: str,
        artifact_path: Path,
        context: Dict[str, Any]
    ) -> EvaluationResult:
        """
        Evaluate skill output with confidence scoring

        Args:
            skill_name: Name of the skill that produced the artifact
            artifact_path: Path to the artifact file
            context: Context data (session_id, step, etc.)

        Returns:
            EvaluationResult with confidence and decision logic
        """
        issues = []
        confidence = 1.0
        details = {}

        # Load skill definition to get Iron Law
        skill_def = self._load_skill_definition(skill_name)
        if not skill_def:
            return EvaluationResult(
                confidence=0.0,
                passed=False,
                issues=["Skill definition not found"],
                auto_approvable=False,
                requires_user_input=True,
                details={}
            )

        iron_law = skill_def.get('iron_law', '')

        # Check 1: Structural (file exists, non-empty)
        structural_result = self._check_structural(artifact_path)
        if not structural_result['passed']:
            issues.extend(structural_result['issues'])
            confidence -= 0.3
        details['structural'] = structural_result

        # Check 2: Iron Law compliance
        iron_law_result = self._check_iron_law(artifact_path, iron_law)
        if not iron_law_result['passed']:
            issues.extend(iron_law_result['issues'])
            confidence -= 0.4
        details['iron_law'] = iron_law_result

        # Check 3: Format validation (YAML/JSON if applicable)
        format_result = self._check_format(artifact_path)
        if not format_result['passed']:
            issues.extend(format_result['issues'])
            confidence -= 0.2
        details['format'] = format_result

        # Check 4: Test results (if applicable)
        test_result = self._check_test_results(artifact_path, skill_name)
        if test_result['checked']:
            if not test_result['passed']:
                issues.extend(test_result['issues'])
                confidence -= 0.3
            details['test_results'] = test_result

        # Clamp confidence to [0, 1]
        confidence = max(0.0, min(1.0, confidence))

        # Determine if auto-approvable
        auto_approvable = confidence >= 0.9 and len(issues) == 0
        requires_user_input = confidence < 0.7 or len(issues) > 0

        return EvaluationResult(
            confidence=confidence,
            passed=len(issues) == 0,
            issues=issues,
            auto_approvable=auto_approvable,
            requires_user_input=requires_user_input,
            details=details
        )

    def _check_structural(self, artifact_path: Path) -> Dict[str, Any]:
        """Check if artifact exists and is non-empty"""
        if not artifact_path.exists():
            return {
                'passed': False,
                'issues': [f"Artifact does not exist: {artifact_path}"]
            }

        content = artifact_path.read_text(encoding='utf-8')
        if not content.strip():
            return {
                'passed': False,
                'issues': [f"Artifact is empty: {artifact_path}"]
            }

        # Check for placeholder patterns
        placeholder_patterns = [
            r'PLACEHOLDER',
            r'TODO',
            r'TBD',
            r'Created after dispatch failure',
            r'<!-- .* -->',  # HTML comment placeholders
        ]

        for pattern in placeholder_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                return {
                    'passed': False,
                    'issues': [f"Artifact contains placeholder pattern: {pattern}"]
                }

        return {
            'passed': True,
            'issues': []
        }

    def _check_iron_law(self, artifact_path: Path, iron_law: str) -> Dict[str, Any]:
        """Check if Iron Law is followed"""
        if not iron_law:
            return {
                'passed': True,
                'issues': []
            }

        content = artifact_path.read_text(encoding='utf-8')

        # Extract key requirements from Iron Law
        # This is a simplified check - real implementation would parse Iron Law text
        if 'test' in iron_law.lower() and 'test' not in content.lower():
            return {
                'passed': False,
                'issues': ["Iron Law requires tests but none found in artifact"]
            }

        if 'no placeholder' in iron_law.lower():
            if 'placeholder' in content.lower() or 'todo' in content.lower():
                return {
                    'passed': False,
                    'issues': ["Iron Law prohibits placeholders but found in artifact"]
                }

        return {
            'passed': True,
            'issues': []
        }

    def _check_format(self, artifact_path: Path) -> Dict[str, Any]:
        """Check YAML/JSON format if applicable"""
        suffix = artifact_path.suffix.lower()

        if suffix in ['.yaml', '.yml']:
            try:
                with open(artifact_path, 'r', encoding='utf-8') as f:
                    yaml.safe_load(f)
                return {
                    'passed': True,
                    'issues': []
                }
            except yaml.YAMLError as e:
                return {
                    'passed': False,
                    'issues': [f"YAML parsing error: {e}"]
                }

        if suffix == '.json':
            import json
            try:
                with open(artifact_path, 'r', encoding='utf-8') as f:
                    json.load(f)
                return {
                    'passed': True,
                    'issues': []
                }
            except json.JSONDecodeError as e:
                return {
                    'passed': False,
                    'issues': [f"JSON parsing error: {e}"]
                }

        # Markdown or other formats - no format check
        return {
            'passed': True,
            'issues': [],
            'checked': False
        }

    def _check_test_results(self, artifact_path: Path, skill_name: str) -> Dict[str, Any]:
        """Check test results if artifact contains test output"""
        content = artifact_path.read_text(encoding='utf-8')

        # Look for test result patterns - parse actual pass/fail counts
        # Pattern: "X passed, Y failed, Z errors" or "X/Y tests passed"
        summary_pattern = r'(\d+)\s+passed,\s*(\d+)\s+failed(?:,\s*(\d+)\s+errors?)?'
        ratio_pattern = r'(\d+)/(\d+)\s+tests?\s+passed'

        found_tests = False
        test_passed = True
        issues = []

        # Check ratio pattern (e.g., "70/70 tests passed")
        ratio_match = re.search(ratio_pattern, content, re.IGNORECASE)
        if ratio_match:
            found_tests = True
            passed = int(ratio_match.group(1))
            total = int(ratio_match.group(2))
            if passed < total:
                test_passed = False
                issues.append(f"Tests show {passed}/{total} passed ({total - passed} failed)")
            else:
                # All tests passed
                pass

        # Check summary pattern (e.g., "70 passed, 0 failed")
        summary_match = re.search(summary_pattern, content, re.IGNORECASE)
        if summary_match:
            found_tests = True
            passed = int(summary_match.group(1))
            failed = int(summary_match.group(2))
            errors = int(summary_match.group(3)) if summary_match.group(3) else 0

            if failed > 0:
                test_passed = False
                issues.append(f"Tests show {failed} failures")
            if errors > 0:
                test_passed = False
                issues.append(f"Tests show {errors} errors")

        # Fallback: look for simple "X passed" without failure context
        if not found_tests:
            simple_passed = re.search(r'(\d+)\s+passed', content, re.IGNORECASE)
            if simple_passed:
                found_tests = True
                # If we only see "passed" and no explicit failures, assume success
                pass

        if not found_tests:
            return {
                'checked': False,
                'passed': True,
                'issues': []
            }

        return {
            'checked': True,
            'passed': test_passed,
            'issues': issues
        }

    def _load_skill_definition(self, skill_name: str) -> Optional[Dict[str, Any]]:
        """Load skill YAML definition"""
        skill_yaml = self.skills_dir / f"{skill_name}.yaml"
        if not skill_yaml.exists():
            return None

        with open(skill_yaml, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
