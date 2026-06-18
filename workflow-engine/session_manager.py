"""
Session Manager - Manages session lifecycle and state
"""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from dataclasses import dataclass, field


@dataclass
class SessionState:
    """Current session state"""
    session_id: str
    current_step: str
    current_phase: str
    status: str
    retries: int
    start_time: str
    end_time: Optional[str] = None


class SessionManager:
    """Manages session lifecycle and state tracking"""

    def __init__(self, harness_root: Path, work_dir: Path):
        """
        Initialize session manager

        Args:
            harness_root: Root directory of the harness
            work_dir: Work directory for session files
        """
        self.harness_root = harness_root
        self.work_dir = work_dir
        self.session_dir: Optional[Path] = None
        self.state: Optional[SessionState] = None

    def initialize_session(self, session_id: str, manifest) -> SessionState:
        """
        Initialize a new session

        Args:
            session_id: Session identifier (e.g., FEATURE-001)
            manifest: Loaded manifest object

        Returns:
            Initial SessionState
        """
        # Create session directory
        session_path = self.work_dir / session_id
        session_path.mkdir(parents=True, exist_ok=True)
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
            start_time=datetime.now(timezone.utc).isoformat(),
            end_time=None
        )

        # Write initial status
        self._update_status()

        return self.state

    def _initialize_artifacts(self, session_id: str, manifest) -> None:
        """Initialize session artifacts"""
        # Create request.md (placeholder)
        request_path = self.session_dir / 'request.md'
        if not request_path.exists():
            request_path.write_text(f"# Request for {session_id}\n\n<!-- Request content -->\n", encoding='utf-8')

        # Create status.md
        status_path = self.session_dir / 'status.md'
        if not status_path.exists():
            status_path.write_text(f"phase=step-0  skill=context  retries=0/0\n", encoding='utf-8')

        # Create session-audit.md
        audit_path = self.session_dir / 'session-audit.md'
        if not audit_path.exists():
            audit_content = f"""# Session Audit: {session_id}

## Session Start
- Session ID: {session_id}
- Start Time: {datetime.now(timezone.utc).isoformat()}
- Status: in_progress

## Phase Transitions
"""
            audit_path.write_text(audit_content, encoding='utf-8')

    def update_phase(self, step: str, phase: str, skill: str) -> None:
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

    def increment_retry(self) -> None:
        """Increment retry counter for current step"""
        if self.state is None:
            raise RuntimeError("Session not initialized")

        self.state.retries += 1
        self._update_status()

    def complete_session(self) -> None:
        """Mark session as completed"""
        if self.state is None:
            raise RuntimeError("Session not initialized")

        self.state.status = 'completed'
        self.state.end_time = datetime.now(timezone.utc).isoformat()
        self._update_status()

        # Log session completion in audit
        self._log_session_completion()

    def fail_session(self, reason: str) -> None:
        """
        Mark session as failed

        Args:
            reason: Failure reason
        """
        if self.state is None:
            raise RuntimeError("Session not initialized")

        self.state.status = 'failed'
        self.state.end_time = datetime.now(timezone.utc).isoformat()
        self._update_status()

        # Log session failure in audit
        self._log_session_failure(reason)

    def _update_status(self, skill: Optional[str] = None) -> None:
        """Update status.md file"""
        if self.state is None:
            return

        status_path = self.session_dir / 'status.md'
        skill_str = skill or self.state.current_phase
        status_line = f"phase={self.state.current_step}  skill={skill_str}  retries={self.state.retries}/2\n"
        status_path.write_text(status_line, encoding='utf-8')

    def _log_phase_transition(self, step: str, phase: str, skill: str) -> None:
        """Log phase transition in session-audit.md"""
        audit_path = self.session_dir / 'session-audit.md'
        timestamp = datetime.now(timezone.utc).isoformat()
        entry = f"\n- [{timestamp}] Phase transition: {step} → {phase} (skill: {skill})\n"
        with open(audit_path, 'a', encoding='utf-8') as f:
            f.write(entry)

    def _log_session_completion(self) -> None:
        """Log session completion in session-audit.md"""
        audit_path = self.session_dir / 'session-audit.md'
        timestamp = datetime.now(timezone.utc).isoformat()
        entry = f"\n## Session End\n- End Time: {timestamp}\n- Status: {self.state.status}\n"
        with open(audit_path, 'a', encoding='utf-8') as f:
            f.write(entry)

    def _log_session_failure(self, reason: str) -> None:
        """Log session failure in session-audit.md"""
        audit_path = self.session_dir / 'session-audit.md'
        timestamp = datetime.now(timezone.utc).isoformat()
        entry = f"\n## Session End\n- End Time: {timestamp}\n- Status: {self.state.status}\n- Reason: {reason}\n"
        with open(audit_path, 'a', encoding='utf-8') as f:
            f.write(entry)

    def artifact_exists(self, artifact_name: str) -> bool:
        """
        Check if an artifact exists

        Args:
            artifact_name: Name of the artifact (e.g., requirement.md)

        Returns:
            True if artifact exists, False otherwise
        """
        if self.session_dir is None:
            return False

        artifact_path = self.session_dir / artifact_name
        return artifact_path.exists()

    def get_session_dir(self) -> Path:
        """Get session directory path"""
        if self.session_dir is None:
            raise RuntimeError("Session not initialized")
        return self.session_dir
