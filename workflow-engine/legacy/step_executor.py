# -*- coding: utf-8 -*-
"""
Step Executor - DEPRECATED

This module is DEPRECATED and superseded by the orchestrator–worker pattern.

The mechanical driver loop (execute_workflow, _execute_step) is retired.
The dispatch mechanics (skill_invoker, devin_cli_adapter) are retained and extended.

New approach:
- Cascade follows ORCHESTRATION-RUNBOOK.md directly as the orchestrator
- Devin workers execute skills as stateless neutral actors
- Deterministic tools (floor_validator, audit_helpers) provide audit rails
- See: ORCHESTRATION-RUNBOOK.md, CASCADE-PIPELINE-DESIGN.md

This file is kept for reference but should not be used in new workflows.
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from manifest_loader import ManifestLoader, Manifest
from session_manager import SessionManager, SessionState
from skill_invoker import SkillInvoker
from skill_evaluator import SkillEvaluator, EvaluationResult


@dataclass
class StepResult:
    """Result of step execution"""
    step: str
    success: bool
    message: str
    artifacts_created: List[str]


class StepExecutor:
    """Executes workflow steps with manual skill invocation"""

    def __init__(self, harness_root: Path, work_dir: Path, interactive: bool = True, devin_cli_path: Optional[str] = None, model: Optional[str] = None, permission_mode: str = "dangerous", max_retries: int = 2):
        """
        Initialize step executor

        Args:
            harness_root: Root directory of the harness
            work_dir: Work directory for session files
            interactive: If True, prompt for manual skill execution. If False, use automated dispatch.
            devin_cli_path: Optional path to devin.exe for automated dispatch
            model: Optional model to use (e.g., "claude-sonnet-4", "claude-opus-4.6")
            permission_mode: Permission mode (auto, smart, dangerous) - defaults to dangerous for automated dispatch
            max_retries: Maximum number of retry attempts on evaluation failure (default: 2)
        """
        self.harness_root = harness_root
        self.work_dir = work_dir
        self.manifest_loader = ManifestLoader(harness_root)
        self.session_manager: Optional[SessionManager] = None
        self.manifest: Optional[Manifest] = None
        self.interactive = interactive
        self.devin_cli_path = devin_cli_path
        self.model = model
        self.permission_mode = permission_mode
        self.max_retries = max_retries
        self.skill_invoker: Optional[SkillInvoker] = None
        self.skill_evaluator = SkillEvaluator(harness_root, enable_semantic=False, devin_cli_path=devin_cli_path)

        if devin_cli_path:
            self.skill_invoker = SkillInvoker(harness_root, devin_cli_path, model, permission_mode)

    def _build_feedback_prompt(self, original_prompt: str, issues: List[str]) -> str:
        """
        Build a feedback prompt for retrying a skill with evaluation feedback

        Args:
            original_prompt: The original skill invocation prompt
            issues: List of evaluation issues to address

        Returns:
            Feedback prompt with issue context
        """
        feedback = f"""Your previous output failed validation for the following reasons:

{chr(10).join(f"- {issue}" for issue in issues)}

Please regenerate the artifact(s) fixing ONLY these problems. Do not introduce placeholders (PLACEHOLDER/TODO/TBD). Follow the skill instructions strictly.

---

Original task:
{original_prompt}
"""
        return feedback

    def execute_workflow(self, manifest_name: str, session_id: str) -> bool:
        """
        Execute a complete workflow

        Args:
            manifest_name: Name of the manifest file (e.g., 'feature.manifest.yaml')
            session_id: Session identifier (e.g., FEATURE-001)

        Returns:
            True if workflow completed successfully, False otherwise
        """
        try:
            # Load manifest
            self.manifest = self.manifest_loader.load(manifest_name)
            print(f"Loaded manifest: {self.manifest.description}")

            # Initialize session
            self.session_manager = SessionManager(self.harness_root, self.work_dir)
            self.session_manager.initialize_session(session_id, self.manifest)
            print(f"Initialized session: {session_id}")

            # Execute step_0 (session init)
            self._execute_step_0()

            # Execute remaining steps
            steps = self._get_step_order()
            for step in steps:
                if not self._execute_step(step):
                    print(f"Step {step} failed")
                    return False

            # Complete session
            self.session_manager.complete_session()
            print(f"Session {session_id} completed successfully")
            return True

        except Exception as e:
            print(f"Workflow execution failed: {e}")
            if self.session_manager:
                self.session_manager.fail_session(str(e))
            return False

    def _get_step_order(self) -> List[str]:
        """Get ordered list of steps from manifest"""
        # Extract step keys from required_artefacts
        steps = list(self.manifest.required_artefacts.keys())
        # Sort to ensure step_0 is first, then step_1, step_2, etc.
        steps.sort()
        # Remove step_0 as it's handled separately
        if 'step_0' in steps:
            steps.remove('step_0')
        return steps

    def _execute_step_0(self) -> StepResult:
        """
        Execute step_0 (session init)

        Returns:
            StepResult indicating success/failure
        """
        print("\n=== Step 0: Session Init ===")
        print(f"Session directory: {self.session_manager.get_session_dir()}")
        print("Initial artifacts created: request.md, status.md, session-audit.md")

        # Update phase to context
        self.session_manager.update_phase('step_0', 'context', 'context')

        # For automated dispatch, pre-populate request.md with a test request
        if not self.interactive and self.skill_invoker:
            request_path = self.session_manager.get_session_dir() / 'request.md'
            test_request = """# Test Request for Automated Dispatch

This is a test request for validating the orchestrator's automated dispatch capability.

## Goal
Test the workflow engine's ability to:
- Dispatch skills via devin-cli --print mode
- Evaluate skill outputs with confidence scoring
- Make confidence-based decisions (auto-approve vs user gate)

## Topic
Workflow engine automated dispatch with skill evaluation

## Success Criteria
- All skills execute successfully
- Artifacts are created without placeholders
- Evaluation confidence scores are reasonable
- Workflow completes without manual intervention
"""
            request_path.write_text(test_request, encoding='utf-8')
            print("Pre-populated request.md with test request for automated dispatch")

            # Also pre-populate requirement.md since brainstorming is interactive
            # In automated mode, we skip the interactive brainstorming phase
            requirement_path = self.session_manager.get_session_dir() / 'requirement.md'
            test_requirement = """# Requirement: Workflow Engine Automated Dispatch

## Summary
Implement and validate the orchestrator's skill evaluation system with confidence-based decision logic.

## Acceptance Criteria
- Skill evaluator with confidence scoring (0.0-1.0)
- Automated checks for structural, Iron Law, and test result compliance
- User gate mechanism for subjective decisions
- Confidence-based auto-approval (>=0.9) vs user review (<0.7)
- Integration with step_executor for real-time evaluation

## Affected Layers
- workflow-engine/skill_evaluator.py (new)
- workflow-engine/step_executor.py (modified)
- workflow-engine/skill_invoker.py (modified)

## Out of Scope
- Interactive brainstorming (skipped in automated mode)
- Subjective quality evaluation (requires human judgment)
"""
            requirement_path.write_text(test_requirement, encoding='utf-8')
            print("Pre-populated requirement.md for automated mode (skipping interactive brainstorming)")

        return StepResult(
            step='step_0',
            success=True,
            message='Session initialized',
            artifacts_created=['request.md', 'status.md', 'session-audit.md']
        )

    def _execute_step(self, step: str) -> bool:
        """
        Execute a single step with manual skill invocation

        Args:
            step: Step identifier (e.g., step_1)

        Returns:
            True if step completed successfully, False otherwise
        """
        print(f"\n=== {step.upper()} ===")

        # Get skills for this step
        skills = self._get_skills_for_step(step)
        if not skills:
            print(f"No skills assigned to {step}")
            return True

        # Execute each skill (usually one per step)
        for skill_config in skills:
            skill_name = skill_config['name']
            announcement = skill_config.get('announcement', f'Using {skill_name} skill')

            # Announce skill invocation
            print(f"\n{announcement}")

            # Update phase
            self.session_manager.update_phase(step, skill_name, skill_name)

            # Wait for manual skill execution (Architect executes in Cascade)
            if self.interactive:
                print("\n[MANUAL EXECUTION REQUIRED]")
                print(f"Please execute the {skill_name} skill manually in Cascade.")
                print("Press Enter when complete, or 'skip' to skip this step...")

                user_input = input().strip()

                if user_input.lower() == 'skip':
                    print(f"Skipped {skill_name} skill")
                    continue
            elif self.skill_invoker:
                # Automated dispatch using skill invoker
                print("\n[AUTOMATED DISPATCH - Invoking skill via devin-cli]")
                print(f"Dispatching {skill_name} skill...")

                context = {
                    'session_id': self.session_manager.state.session_id,
                    'step': step,
                    'session_dir': str(self.session_manager.get_session_dir()),
                    'required_artifacts': self.manifest.required_artefacts.get(step, [])
                }

                # Build the original prompt for potential retry
                skill_def = self.skill_invoker.load_skill_definition(skill_name)
                skill_narrative = self.skill_invoker.load_skill_narrative(skill_name)
                original_prompt = self.skill_invoker.build_skill_prompt(skill_name, skill_def, skill_narrative, context)

                # Retry loop with feedback
                attempt = 0
                max_attempts = self.max_retries + 1  # initial attempt + retries
                step_evaluation = None

                while attempt < max_attempts:
                    attempt += 1
                    if attempt > 1:
                        print(f"\n[RETRY ATTEMPT {attempt}/{max_attempts}]")

                    result = self.skill_invoker.invoke_skill(
                        skill_name=skill_name,
                        context=context,
                        workspace=str(self.session_manager.get_session_dir()),
                        custom_prompt=None if attempt == 1 else self._build_feedback_prompt(original_prompt, step_evaluation.issues if step_evaluation else [])
                    )

                    if result.success:
                        print(f"Skill {skill_name} invoked successfully")
                        print(f"Session ID: {result.session_id}")
                        print(f"Output: {result.output[:200]}...")  # Truncate output

                        # Evaluate skill output with confidence scoring
                        required_artifacts = self.manifest.required_artefacts.get(step, [])
                        if required_artifacts:
                            # Evaluate ALL required artifacts (not just the first)
                            evaluations = []
                            all_issues = []
                            min_confidence = 1.0
                            all_auto_approvable = True

                            for artifact_name in required_artifacts:
                                artifact_path = self.session_manager.get_session_dir() / artifact_name
                                if artifact_path.exists():
                                    evaluation = self.skill_evaluator.evaluate_skill_output(
                                        skill_name=skill_name,
                                        artifact_path=artifact_path,
                                        context={'session_id': self.session_manager.state.session_id, 'step': step}
                                    )
                                    evaluations.append((artifact_name, evaluation))
                                    min_confidence = min(min_confidence, evaluation.confidence)
                                    all_auto_approvable = all_auto_approvable and evaluation.auto_approvable

                                    if evaluation.issues:
                                        for issue in evaluation.issues:
                                            all_issues.append(f"{artifact_name}: {issue}")
                                else:
                                    all_issues.append(f"{artifact_name}: Artifact does not exist")
                                    all_auto_approvable = False
                                    min_confidence = 0.0

                            # Aggregate step evaluation
                            step_evaluation = EvaluationResult(
                                confidence=min_confidence,
                                passed=len(all_issues) == 0,
                                issues=all_issues,
                                auto_approvable=all_auto_approvable,
                                requires_user_input=min_confidence < 0.7 or len(all_issues) > 0,
                                details={'per_artifact': evaluations, 'attempt': attempt}
                            )

                            print(f"\n[EVALUATION - Confidence: {step_evaluation.confidence:.2f}]")
                            if step_evaluation.issues:
                                print(f"Issues: {', '.join(step_evaluation.issues)}")

                            # Confidence-based decision logic
                            if step_evaluation.auto_approvable:
                                print("✓ Auto-approved (high confidence, no issues)")
                                break  # Success, exit retry loop
                            elif step_evaluation.requires_user_input:
                                print(f"\n⚠ Requires user review (confidence: {step_evaluation.confidence:.2f})")
                                print(f"Issues: {step_evaluation.issues}")

                                # If we have retries left, try automatic retry
                                if attempt < max_attempts:
                                    print(f"Retrying with feedback ({attempt}/{self.max_retries})...")
                                    continue
                                else:
                                    # No more retries, escalate to user or abort
                                    print(f"\nMax retries ({self.max_retries}) exhausted.")
                                    print("\nOptions:")
                                    print("  1. Proceed anyway")
                                    print("  2. Abort workflow")

                                    if self.interactive:
                                        choice = input("Your choice (1/2): ").strip()
                                        if choice == '2':
                                            print("Workflow aborted by user")
                                            # Record escalation to session audit
                                            self.session_manager.append_audit_entry(
                                                f"ESCALATE: {step} failed after {max_attempts} attempts with issues: {step_evaluation.issues}"
                                            )
                                            return False
                                        else:
                                            print("Proceeding with user approval")
                                            break
                                    else:
                                        # Non-interactive mode: abort after retries
                                        print("Non-interactive mode: aborting workflow after max retries")
                                        # Record escalation to session audit
                                        self.session_manager.append_audit_entry(
                                            f"ESCALATE: {step} failed after {max_attempts} attempts with issues: {step_evaluation.issues}"
                                        )
                                        return False
                            else:
                                # Medium confidence - quick confirmation
                                print(f"⚠ Medium confidence ({step_evaluation.confidence:.2f})")
                                if self.interactive:
                                    proceed = input("Proceed? (y/n): ").strip().lower()
                                    if proceed != 'y':
                                        print("Workflow aborted by user")
                                        return False
                                    else:
                                        break
                                else:
                                    # Non-interactive mode: abort on medium confidence
                                    print("Non-interactive mode: aborting workflow due to medium confidence")
                                    return False
                    else:
                        print(f"Skill {skill_name} invocation failed: {result.error}")
                        # Fall back to placeholder creation
                        print("Creating placeholder artifacts as fallback...")
                        required_artifacts = self.manifest.required_artefacts.get(step, [])
                        for artifact in required_artifacts:
                            artifact_path = self.session_manager.get_session_dir() / artifact
                            if not artifact_path.exists():
                                artifact_path.write_text(f"# Placeholder for {artifact}\n\n# Created after dispatch failure\n", encoding='utf-8')
                        print(f"Created placeholder artifacts: {', '.join(required_artifacts)}")
                        break  # Invocation failed, no point retrying
            else:
                print("\n[NON-INTERACTIVE MODE - Skipping manual execution]")
                print("Creating placeholder artifacts for testing...")

                # Create placeholder artifacts for testing
                required_artifacts = self.manifest.required_artefacts.get(step, [])
                for artifact in required_artifacts:
                    artifact_path = self.session_manager.get_session_dir() / artifact
                    if not artifact_path.exists():
                        artifact_path.write_text(f"# Placeholder for {artifact}\n\n# Created in non-interactive test mode\n", encoding='utf-8')
                print(f"Created placeholder artifacts: {', '.join(required_artifacts)}")
                continue

            # Validate required artifacts
            required_artifacts = self.manifest.required_artefacts.get(step, [])
            missing_artifacts = self._validate_artifacts(required_artifacts)

            if missing_artifacts:
                print(f"Missing artifacts: {', '.join(missing_artifacts)}")
                if self.interactive:
                    print("Please create the missing artifacts and press Enter to retry...")
                    retry_input = input().strip()
                    if retry_input.lower() == 'abort':
                        return False

                    # Re-validate
                    missing_artifacts = self._validate_artifacts(required_artifacts)
                    if missing_artifacts:
                        print(f"Still missing artifacts: {', '.join(missing_artifacts)}")
                        return False
                else:
                    # Non-interactive mode: abort on missing artifacts
                    print("Non-interactive mode: aborting workflow due to missing artifacts")
                    return False

            print(f"{step} completed successfully")

        # Check for gates after this step
        if self._has_gate_after_step(step):
            return self._handle_gate(step)

        return True

    def _get_skills_for_step(self, step: str) -> List[Dict[str, Any]]:
        """Get skills assigned to a specific step"""
        skills = []
        for skill in self.manifest.skills:
            phases = skill.get('phases', [])
            if step in phases:
                skills.append(skill)
        return skills

    def _validate_artifacts(self, required_artifacts: List[str]) -> List[str]:
        """
        Validate that required artifacts exist

        Args:
            required_artifacts: List of required artifact names

        Returns:
            List of missing artifact names
        """
        missing = []
        for artifact in required_artifacts:
            if not self.session_manager.artifact_exists(artifact):
                missing.append(artifact)
        return missing

    def _has_gate_after_step(self, step: str) -> bool:
        """Check if there's a gate after a specific step"""
        for gate in self.manifest.gates:
            if gate['after_step'] == step:
                return True
        return False

    def _handle_gate(self, step: str) -> bool:
        """
        Handle gate after a step

        Args:
            step: Step identifier

        Returns:
            True if gate passed, False otherwise
        """
        gate = self._get_gate_after_step(step)
        if not gate:
            return True

        gate_type = gate['type']
        gate_description = gate.get('description', '')

        print(f"\n=== GATE: {gate['id']} ===")
        print(f"Type: {gate_type}")
        print(f"Description: {gate_description}")

        if gate_type == 'user_gate':
            if self.interactive:
                print("\n[USER APPROVAL REQUIRED]")
                print("Please review and approve to continue.")
                print("Press Enter to approve, or 'reject'/'no' to reject...")

                user_input = input().strip()

                if user_input.lower() in ['reject', 'no']:
                    print("Gate rejected by user")
                    return False

                print("Gate approved by user")
                return True
            else:
                print("\n[NON-INTERACTIVE MODE - Auto-approving gate]")
                print(f"Gate {gate['id']} auto-approved")
                return True

        elif gate_type == 'auto_gate':
            # Auto-gate - automatically pass for Phase 1
            print("Auto-gate passed")
            return True

        return True

    def _get_gate_after_step(self, step: str) -> Optional[Dict[str, Any]]:
        """Get gate configuration after a specific step"""
        for gate in self.manifest.gates:
            if gate['after_step'] == step:
                return gate
        return None
