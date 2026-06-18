"""
Session Manager - Manages session lifecycle and state
"""

import yaml
import os
from datetime import datetime


class SessionState:
    """Current session state"""

    def __init__(self, session_id, current_step, current_phase, status, retries, start_time, end_time=None):
        self.session_id = session_id
        self.current_step = current_step
        self.current_phase = current_phase
        self.status = status
        self.retries = retries
        self.start_time = start_time
        self.end_time = end_time


class SessionManager:
    """Manages session lifecycle and state tracking"""

    def __init__(self, harness_root, work_dir):
        """
        Initialize session manager

        Args:
            harness_root: Root directory of the harness
            work_dir: Work directory for session files
        """
        self.harness_root = harness_root
        self.work_dir = work_dir
        self.session_dir = None
        self.state = None

    def initialize_session(self, session_id, manifest):
        """
        Initialize a new session

        Args:
            session_id: Session identifier (e.g., FEATURE-001)
            manifest: Loaded manifest object

        Returns:
            Initial SessionState
        """
        # Create session directory
        session_path = os.path.join(self.work_dir, session_id)
        if not os.path.exists(session_path):
            os.makedirs(session_path)
        self.session_dir = session_path

        # Initialize artifacts
        self._initialize_artifacts(session_id, manifest)

        # Create initial state
        self.state = SessionState(
            session_id=session_id,
            current_step='step_0',
            current_phase='context',
            status='in_progress',
            retries=0,
            start_time=datetime.utcnow().isoformat(),
            end_time=None
        )

        # Write initial status
        self._update_status()

        return self.state

    def _initialize_artifacts(self, session_id, manifest):
        """Initialize session artifacts"""
        # Create request.md (placeholder)
        request_path = os.path.join(self.session_dir, 'request.md')
        if not os.path.exists(request_path):
            with open(request_path, 'w') as f:
                f.write("# Request for {}\n\n<!-- Request content -->\n".format(session_id))

        # Create status.md
        status_path = os.path.join(self.session_dir, 'status.md')
        if not os.path.exists(status_path):
            with open(status_path, 'w') as f:
                f.write("phase=step-0  skill=context  retries=0/0\n")

        # Create session-audit.md
        audit_path = os.path.join(self.session_dir, 'session-audit.md')
        if not os.path.exists(audit_path):
            audit_content = """# Session Audit: {}

## Session Start
- Session ID: {}
- Start Time: {}
- Status: in_progress

## Phase Transitions
""".format(session_id, session_id, datetime.utcnow().isoformat())
            with open(audit_path, 'w') as f:
                f.write(audit_content)

    def update_phase(self, step, phase, skill):
        """
        Update session phase

        Args:
            step: Current step (e.g., step_1)
            phase: Current phase (e.g., brainstorming)
            skill: Current skill (e.g., brainstorming)
        """
        if self.state is None:
            raise RuntimeError("Session not initialized")

        self.state.current_step = step
        self.state.current_phase = phase
        self.state.retries = 0
        self._update_status(skill=skill)

        # Log phase transition in audit
        self._log_phase_transition(step, phase, skill)

    def increment_retry(self):
        """Increment retry counter for current step"""
        if self.state is None:
            raise RuntimeError("Session not initialized")

        self.state.retries += 1
        self._update_status()

    def complete_session(self):
        """Mark session as completed"""
        if self.state is None:
            raise RuntimeError("Session not initialized")

        self.state.status = 'completed'
        self.state.end_time = datetime.utcnow().isoformat()
        self._update_status()

        # Log session completion in audit
        self._log_session_completion()

    def fail_session(self, reason):
        """
        Mark session as failed

        Args:
            reason: Failure reason
        """
        if self.state is None:
            raise RuntimeError("Session not initialized")

        self.state.status = 'failed'
        self.state.end_time = datetime.utcnow().isoformat()
        self._update_status()

        # Log session failure in audit
        self._log_session_failure(reason)

    def _update_status(self, skill=None):
        """Update status.md file"""
        if self.state is None:
            return

        status_path = os.path.join(self.session_dir, 'status.md')
        skill_str = skill or self.state.current_phase
        status_line = "phase={}  skill={}  retries={}/2\n".format(
            self.state.current_step, skill_str, self.state.retries
        )
        with open(status_path, 'w') as f:
            f.write(status_line)

    def _log_phase_transition(self, step, phase, skill):
        """Log phase transition in session-audit.md"""
        audit_path = os.path.join(self.session_dir, 'session-audit.md')
        timestamp = datetime.utcnow().isoformat()
        entry = "\n- [{}] Phase transition: {} → {} (skill: {})\n".format(timestamp, step, phase, skill)
        with open(audit_path, 'a') as f:
            f.write(entry)

    def _log_session_completion(self):
        """Log session completion in session-audit.md"""
        audit_path = os.path.join(self.session_dir, 'session-audit.md')
        timestamp = datetime.utcnow().isoformat()
        entry = "\n## Session End\n- End Time: {}\n- Status: {}\n".format(timestamp, self.state.status)
        with open(audit_path, 'a') as f:
            f.write(entry)

    def _log_session_failure(self, reason):
        """Log session failure in session-audit.md"""
        audit_path = os.path.join(self.session_dir, 'session-audit.md')
        timestamp = datetime.utcnow().isoformat()
        entry = "\n## Session End\n- End Time: {}\n- Status: {}\n- Reason: {}\n".format(timestamp, self.state.status, reason)
        with open(audit_path, 'a') as f:
            f.write(entry)

    def artifact_exists(self, artifact_name):
        """
        Check if an artifact exists

        Args:
            artifact_name: Name of the artifact (e.g., requirement.md)

        Returns:
            True if artifact exists, False otherwise
        """
        if self.session_dir is None:
            return False

        artifact_path = os.path.join(self.session_dir, artifact_name)
        return os.path.exists(artifact_path)

    def get_session_dir(self):
        """Get session directory path"""
        if self.session_dir is None:
            raise RuntimeError("Session not initialized")
        return self.session_dir
