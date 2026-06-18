"""
Step Executor - Executes workflow steps with manual skill invocation
"""

import os

from manifest_loader import ManifestLoader, Manifest
from session_manager import SessionManager, SessionState


class StepResult:
    """Result of step execution"""

    def __init__(self, step, success, message, artifacts_created):
        self.step = step
        self.success = success
        self.message = message
        self.artifacts_created = artifacts_created


class StepExecutor:
    """Executes workflow steps with manual skill invocation"""

    def __init__(self, harness_root, work_dir):
        """
        Initialize step executor

        Args:
            harness_root: Root directory of the harness
            work_dir: Work directory for session files
        """
        self.harness_root = harness_root
        self.work_dir = work_dir
        self.manifest_loader = ManifestLoader(harness_root)
        self.session_manager = None
        self.manifest = None

    def execute_workflow(self, manifest_name, session_id):
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
            print("Loaded manifest: {}".format(self.manifest.description))

            # Initialize session
            self.session_manager = SessionManager(self.harness_root, self.work_dir)
            self.session_manager.initialize_session(session_id, self.manifest)
            print("Initialized session: {}".format(session_id))

            # Execute step_0 (session init)
            self._execute_step_0()

            # Execute remaining steps
            steps = self._get_step_order()
            for step in steps:
                if not self._execute_step(step):
                    print("Step {} failed".format(step))
                    return False

            # Complete session
            self.session_manager.complete_session()
            print("Session {} completed successfully".format(session_id))
            return True

        except Exception as e:
            print("Workflow execution failed: {}".format(e))
            if self.session_manager:
                self.session_manager.fail_session(str(e))
            return False

    def _get_step_order(self):
        """Get ordered list of steps from manifest"""
        # Extract step keys from required_artefacts
        steps = list(self.manifest.required_artefacts.keys())
        # Sort to ensure step_0 is first, then step_1, step_2, etc.
        steps.sort()
        # Remove step_0 as it's handled separately
        if 'step_0' in steps:
            steps.remove('step_0')
        return steps

    def _execute_step_0(self):
        """
        Execute step_0 (session init)

        Returns:
            StepResult indicating success/failure
        """
        print("\n=== Step 0: Session Init ===")
        print("Session directory: {}".format(self.session_manager.get_session_dir()))
        print("Initial artifacts created: request.md, status.md, session-audit.md")

        # Update phase to context
        self.session_manager.update_phase('step_0', 'context', 'context')

        return StepResult(
            step='step_0',
            success=True,
            message='Session initialized',
            artifacts_created=['request.md', 'status.md', 'session-audit.md']
        )

    def _execute_step(self, step):
        """
        Execute a single step with manual skill invocation

        Args:
            step: Step identifier (e.g., step_1)

        Returns:
            True if step completed successfully, False otherwise
        """
        print("\n=== {} ===".format(step.upper()))

        # Get skills for this step
        skills = self._get_skills_for_step(step)
        if not skills:
            print("No skills assigned to {}".format(step))
            return True

        # Execute each skill (usually one per step)
        for skill_config in skills:
            skill_name = skill_config['name']
            announcement = skill_config.get('announcement', 'Using {} skill'.format(skill_name))

            # Announce skill invocation
            print("\n{}".format(announcement))

            # Update phase
            self.session_manager.update_phase(step, skill_name, skill_name)

            # Wait for manual skill execution (Architect executes in Cascade)
            print("\n[MANUAL EXECUTION REQUIRED]")
            print("Please execute the {} skill manually in Cascade.".format(skill_name))
            print("Press Enter when complete, or 'skip' to skip this step...")

            user_input = input().strip()

            if user_input.lower() == 'skip':
                print("Skipped {} skill".format(skill_name))
                continue

            # Validate required artifacts
            required_artifacts = self.manifest.required_artefacts.get(step, [])
            missing_artifacts = self._validate_artifacts(required_artifacts)

            if missing_artifacts:
                print("Missing artifacts: {}".format(', '.join(missing_artifacts)))
                print("Please create the missing artifacts and press Enter to retry...")

                retry_input = input().strip()
                if retry_input.lower() == 'abort':
                    return False

                # Re-validate
                missing_artifacts = self._validate_artifacts(required_artifacts)
                if missing_artifacts:
                    print("Still missing artifacts: {}".format(', '.join(missing_artifacts)))
                    return False

            print("{} completed successfully".format(step))

        # Check for gates after this step
        if self._has_gate_after_step(step):
            return self._handle_gate(step)

        return True

    def _get_skills_for_step(self, step):
        """Get skills assigned to a specific step"""
        skills = []
        for skill in self.manifest.skills:
            phases = skill.get('phases', [])
            if step in phases:
                skills.append(skill)
        return skills

    def _validate_artifacts(self, required_artifacts):
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

    def _has_gate_after_step(self, step):
        """Check if there's a gate after a specific step"""
        for gate in self.manifest.gates:
            if gate['after_step'] == step:
                return True
        return False

    def _handle_gate(self, step):
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

        print("\n=== GATE: {} ===".format(gate['id']))
        print("Type: {}".format(gate_type))
        print("Description: {}".format(gate_description))

        if gate_type == 'user_gate':
            print("\n[USER APPROVAL REQUIRED]")
            print("Please review and approve to continue.")
            print("Press Enter to approve, or 'reject' to reject...")

            user_input = input().strip()

            if user_input.lower() == 'reject':
                print("Gate rejected by user")
                return False

            print("Gate approved by user")
            return True

        elif gate_type == 'auto_gate':
            # Auto-gate - automatically pass for Phase 1
            print("Auto-gate passed")
            return True

        return True

    def _get_gate_after_step(self, step):
        """Get gate configuration after a specific step"""
        for gate in self.manifest.gates:
            if gate['after_step'] == step:
                return gate
        return None
