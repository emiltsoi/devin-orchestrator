# -*- coding: utf-8 -*-
"""
Test multi-artifact evaluation - verify all artifacts are evaluated
"""

import sys
from pathlib import Path

# Add workflow-engine to path
sys.path.insert(0, str(Path(__file__).parent))

from skill_evaluator import SkillEvaluator, EvaluationResult


def test_multi_artifact_evaluation():
    """Test that multiple artifacts are evaluated correctly"""
    print("=" * 60)
    print("Multi-Artifact Evaluation Test")
    print("=" * 60)

    harness_root = Path(__file__).parent.parent
    evaluator = SkillEvaluator(harness_root)

    # Create test session directory
    test_dir = Path(__file__).parent / 'test_multi_artifacts'
    test_dir.mkdir(exist_ok=True)

    # Create 3 artifacts with varying quality
    # Artifact 1: Valid
    artifact1 = test_dir / 'artifact1.md'
    artifact1.write_text('# Valid Artifact\n\nAll tests passed: 70/70', encoding='utf-8')

    # Artifact 2: Placeholder
    artifact2 = test_dir / 'artifact2.md'
    artifact2.write_text('# PLACEHOLDER\n\nTODO: implement', encoding='utf-8')

    # Artifact 3: Valid
    artifact3 = test_dir / 'artifact3.md'
    artifact3.write_text('# Valid Artifact\n\nContent is complete', encoding='utf-8')

    # Evaluate all artifacts
    artifacts = ['artifact1.md', 'artifact2.md', 'artifact3.md']
    evaluations = []
    all_issues = []
    min_confidence = 1.0
    all_auto_approvable = True

    for artifact_name in artifacts:
        artifact_path = test_dir / artifact_name
        evaluation = evaluator.evaluate_skill_output(
            skill_name='verification-before-completion',  # Use a real skill name
            artifact_path=artifact_path,
            context={'session_id': 'test', 'step': 'test'}
        )
        evaluations.append((artifact_name, evaluation))
        min_confidence = min(min_confidence, evaluation.confidence)
        all_auto_approvable = all_auto_approvable and evaluation.auto_approvable

        if evaluation.issues:
            for issue in evaluation.issues:
                all_issues.append(f"{artifact_name}: {issue}")

    # Aggregate step evaluation
    step_evaluation = EvaluationResult(
        confidence=min_confidence,
        passed=len(all_issues) == 0,
        issues=all_issues,
        auto_approvable=all_auto_approvable,
        requires_user_input=min_confidence < 0.7 or len(all_issues) > 0,
        details={'per_artifact': evaluations}
    )

    print(f"\nAggregated Step Evaluation:")
    print(f"Confidence: {step_evaluation.confidence:.2f}")
    print(f"Passed: {step_evaluation.passed}")
    print(f"Auto-approvable: {step_evaluation.auto_approvable}")
    print(f"Requires user input: {step_evaluation.requires_user_input}")
    print(f"Issues: {step_evaluation.issues}")

    # Verify expectations
    assert step_evaluation.confidence == 0.70, f"Expected confidence 0.70, got {step_evaluation.confidence}"
    assert not step_evaluation.passed, "Expected step to fail due to placeholder"
    assert not step_evaluation.auto_approvable, "Expected not auto-approvable"
    assert step_evaluation.requires_user_input, "Expected requires user input"
    assert len(step_evaluation.issues) == 1, f"Expected 1 issue, got {len(step_evaluation.issues)}"

    print("\n✓ All assertions passed")

    # Cleanup
    try:
        artifact1.unlink()
        artifact2.unlink()
        artifact3.unlink()
        test_dir.rmdir()
    except PermissionError:
        # Windows file handle issue - directory will be cleaned up later
        pass

    print("\n" + "=" * 60)
    print("Multi-Artifact Evaluation Test: PASSED")
    print("=" * 60)
    return 0


if __name__ == '__main__':
    sys.exit(test_multi_artifact_evaluation())
