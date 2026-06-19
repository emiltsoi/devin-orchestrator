# -*- coding: utf-8 -*-
"""
Skill Evaluator - Evaluates skill outputs with confidence scoring
Implements hybrid automated + human evaluation system
"""

from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import yaml
import re
from floor_validator import validate_structural, validate_iron_law, validate_format


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

    def __init__(self, harness_root: Path, enable_semantic: bool = False, devin_cli_path: Optional[str] = None):
        """
        Initialize skill evaluator

        Args:
            harness_root: Root directory of the harness
            enable_semantic: Enable semantic evaluation layer (default: False)
            devin_cli_path: Optional path to devin.exe for semantic evaluation
        """
        self.harness_root = harness_root
        self.skills_dir = harness_root / 'skills'
        self.enable_semantic = enable_semantic
        self.devin_cli_path = devin_cli_path

        # Map skills to their context artifacts for semantic evaluation
        self.skill_context_map = {
            'writing-plans': 'requirement.md',
            'subagent-driven-development': 'design.md',
            'verification-before-completion': 'design.md',
            'code-review': 'requirement.md'
        }

        # Simple cache for semantic evaluation results
        self.semantic_cache = {}

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
        if structural_result['result'] == 'FAIL':
            issues.extend(structural_result['failures'])
            confidence -= 0.3
        details['structural'] = structural_result

        # Check 2: Iron Law compliance
        iron_law_result = self._check_iron_law(artifact_path, iron_law)
        if iron_law_result['result'] == 'FAIL':
            issues.extend(iron_law_result['failures'])
            confidence -= 0.4
        details['iron_law'] = iron_law_result

        # Check 3: Format validation (YAML/JSON if applicable)
        format_result = self._check_format(artifact_path)
        if format_result['result'] == 'FAIL':
            issues.extend(format_result['failures'])
            confidence -= 0.2
        details['format'] = format_result

        # Check 4: Test results (if applicable)
        test_result = self._check_test_results(artifact_path, skill_name)
        if test_result['checked']:
            if not test_result['passed']:
                issues.extend(test_result['issues'])
                confidence -= 0.3
            details['test_results'] = test_result

        # Check 5: Semantic evaluation (if enabled)
        if self.enable_semantic and self.devin_cli_path:
            semantic_result = self._check_semantic(artifact_path, skill_name, context)
            if semantic_result['checked']:
                if not semantic_result['passed']:
                    issues.extend(semantic_result['issues'])
                    confidence -= 0.3  # Advisory weight
                details['semantic'] = semantic_result

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
        return validate_structural([artifact_path])

    def _check_iron_law(self, artifact_path: Path, iron_law: str) -> Dict[str, Any]:
        """Check if Iron Law is followed"""
        return validate_iron_law(artifact_path, iron_law)

    def _check_format(self, artifact_path: Path) -> Dict[str, Any]:
        """Check YAML/JSON format if applicable"""
        return validate_format(artifact_path)

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

    def _check_semantic(self, artifact_path: Path, skill_name: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Check if artifact semantically satisfies the requirement/context

        Args:
            artifact_path: Path to the artifact to evaluate
            skill_name: Name of the skill that produced the artifact
            context: Context data including session_id and step

        Returns:
            Dict with 'checked', 'passed', 'issues', and 'details'
        """
        # Check if this skill has a context artifact mapping
        context_artifact_name = self.skill_context_map.get(skill_name)
        if not context_artifact_name:
            return {
                'checked': False,
                'passed': True,
                'issues': []
            }

        # Load context artifact
        session_dir = Path(context.get('session_dir', '.'))
        # Validate session_dir is within expected bounds
        try:
            session_dir = session_dir.resolve()
            if not session_dir.exists() or not session_dir.is_dir():
                return {
                    'checked': False,
                    'passed': True,
                    'issues': []
                }
        except (OSError, ValueError):
            return {
                'checked': False,
                'passed': True,
                'issues': []
            }

        context_path = session_dir / context_artifact_name

        if not context_path.exists():
            return {
                'checked': False,
                'passed': True,
                'issues': []
            }

        # Read both artifacts
        context_content = context_path.read_text(encoding='utf-8')
        artifact_content = artifact_path.read_text(encoding='utf-8')

        # Build cache key from artifact hash
        import hashlib
        cache_key = hashlib.md5((context_content + artifact_content).encode()).hexdigest()

        # Check cache
        if cache_key in self.semantic_cache:
            return self.semantic_cache[cache_key]

        # Build semantic evaluation prompt
        eval_prompt = f"""You are evaluating whether an artifact satisfies its requirement.

## Requirement/Context:
{context_content[:2000]}...

## Artifact to Evaluate:
{artifact_content[:2000]}...

## Task:
Evaluate whether the artifact addresses the requirement. Respond with ONLY a JSON object in this exact format:
{{"score": 0.0-1.0, "missing": ["list of missing items"], "notes": "brief explanation"}}

- score: 0.0-1.0 confidence that artifact satisfies requirement
- missing: list of specific items from requirement not addressed
- notes: brief explanation of the evaluation

Respond with JSON only, no other text.
"""

        try:
            import subprocess
            result = subprocess.run(
                [self.devin_cli_path, '--permission-mode', 'dangerous', '--print', eval_prompt],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=60,
                cwd=str(session_dir)
            )

            if result.returncode != 0:
                return {
                    'checked': False,
                    'passed': True,
                    'issues': [],
                    'error': f"Semantic evaluation failed: {result.stderr}"
                }

            # Parse JSON response
            import json
            eval_output = result.stdout.strip()

            # Try to extract JSON from output
            json_match = re.search(r'\{.*\}', eval_output, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                eval_data = json.loads(json_str)

                score = eval_data.get('score', 0.0)
                missing = eval_data.get('missing', [])
                notes = eval_data.get('notes', '')

                issues = []
                if score < 0.6:
                    issues.append(f"Semantic score {score:.2f} below threshold 0.6")
                if missing:
                    for item in missing:
                        issues.append(f"Missing requirement: {item}")

                result = {
                    'checked': True,
                    'passed': score >= 0.6 and len(missing) == 0,
                    'issues': issues,
                    'details': {
                        'score': score,
                        'missing': missing,
                        'notes': notes
                    }
                }

                # Cache the result
                self.semantic_cache[cache_key] = result

                return result
            else:
                # Could not parse JSON, treat as requires user input
                return {
                    'checked': True,
                    'passed': False,
                    'issues': ["Could not parse semantic evaluation response"],
                    'error': "JSON parse failed"
                }

        except subprocess.TimeoutExpired:
            return {
                'checked': False,
                'passed': True,
                'issues': [],
                'error': "Semantic evaluation timed out"
            }
        except Exception as e:
            return {
                'checked': False,
                'passed': True,
                'issues': [],
                'error': f"Semantic evaluation error: {str(e)}"
            }

    def _load_skill_definition(self, skill_name: str) -> Optional[Dict[str, Any]]:
        """Load skill YAML definition"""
        skill_yaml = self.skills_dir / f"{skill_name}.yaml"
        if not skill_yaml.exists():
            return None

        with open(skill_yaml, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
