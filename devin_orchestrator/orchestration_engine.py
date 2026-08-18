from __future__ import annotations

import logging
import time  # noqa: F401
from typing import TYPE_CHECKING, Any

from devin_orchestrator.artifact_validator import ArtifactValidator
from devin_orchestrator.deterministic_tools import (
    create_placeholder_artifact,
    load_manifest,
    load_skill,
    update_status,
    validate_structural,
    wait_for_file_change,
)
from devin_orchestrator.gate_controller import GateController
from devin_orchestrator.metrics import MetricsCollector
from devin_orchestrator.models import Manifest, Stage
from devin_orchestrator.monitoring import MonitoringSystem
from devin_orchestrator.orchestration_interactive import OrchestrationInteractiveMixin
from devin_orchestrator.orchestration_workflow import OrchestrationWorkflowMixin
from devin_orchestrator.security_utils import (
    InvalidInputError,
    PathTraversalError,
    validate_path_safe,
)
from devin_orchestrator.session_manager import resolve_session
from devin_orchestrator.skill_invoker import SkillInvoker
from devin_orchestrator.stage_skill_dispatcher import StageSkillDispatcher
from devin_orchestrator.state_store import JsonlStateStore
from devin_orchestrator.triage_evaluator import (  # noqa: F401
    TriageDecision,
    TriageEvaluator,
)
from devin_orchestrator.workflow_stage_executor import WorkflowStageExecutor

if TYPE_CHECKING:
    from pathlib import Path

    from devin_orchestrator.state_store import StateStore

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class OrchestrationEngine(OrchestrationWorkflowMixin, OrchestrationInteractiveMixin):
    """Actual orchestration engine for workflow execution"""

    # Explicit delegation methods. Keeping the original module-level names as
    # instance methods lets tests monkeypatch ``orchestration_engine.<name>`` and
    # the engine will call the patched version via ``self.<name>``.
    def update_status(self, *args: Any, **kwargs: Any) -> Any:
        return update_status(*args, **kwargs)

    def load_skill(self, *args: Any, **kwargs: Any) -> Any:
        return load_skill(*args, **kwargs)

    def validate_path_safe(self, *args: Any, **kwargs: Any) -> Any:
        return validate_path_safe(*args, **kwargs)

    def validate_structural(self, *args: Any, **kwargs: Any) -> Any:
        return validate_structural(*args, **kwargs)

    def load_manifest(self, *args: Any, **kwargs: Any) -> Any:
        return load_manifest(*args, **kwargs)

    def create_placeholder_artifact(self, *args: Any, **kwargs: Any) -> Any:
        return create_placeholder_artifact(*args, **kwargs)

    def wait_for_file_change(self, *args: Any, **kwargs: Any) -> Any:
        return wait_for_file_change(*args, **kwargs)

    def resume_from_state_store(self, session_id: str) -> dict[str, Any] | None:
        """Rebuild the current session state from disk without re-running any stages."""
        try:
            session_dir = resolve_session(self.work_dir, session_id)
        except (InvalidInputError, PathTraversalError, FileNotFoundError):
            return None
        self._state_store.init(session_id, session_dir)
        return self._state_store.as_dict()

    def __init__(
        self,
        work_dir: Path,
        config: dict[str, Any] | None = None,
        metrics: MetricsCollector | None = None,
        monitoring: MonitoringSystem | None = None,
        state_store: StateStore | None = None,
    ):
        """
        Initialize orchestration engine

        Args:
            work_dir: Base work directory for sessions
            config: Optional configuration dictionary
            metrics: Optional metrics collector (creates a fresh instance by default)
            monitoring: Optional monitoring system (creates a fresh instance by default)
            state_store: Optional workflow state store (defaults to JsonlStateStore)
        """
        try:
            self.work_dir = work_dir
            self.config = config or {}
            self.metrics = metrics if metrics is not None else MetricsCollector()
            self.monitoring = (
                monitoring
                if monitoring is not None
                else MonitoringSystem(metrics_collector=self.metrics)
            )
            self.skill_invoker = SkillInvoker(
                demo_mode=self.config.get("demo_mode", False), metrics=self.metrics
            )
            self.artifact_validator = ArtifactValidator(self)
            self.triage_evaluator = TriageEvaluator(self)
            self.stage_skill_dispatcher = StageSkillDispatcher(self)
            self.gate_controller = GateController(self)
            self._state_store = state_store or JsonlStateStore()
            self.workflow_stage_executor = WorkflowStageExecutor(
                self,
                artifact_validator=self.artifact_validator,
                triage_evaluator=self.triage_evaluator,
                stage_skill_dispatcher=self.stage_skill_dispatcher,
                state_store=self._state_store,
            )
            logger.info(f"OrchestrationEngine initialized with work_dir: {work_dir}")
        except Exception as e:
            logger.error(f"Error initializing OrchestrationEngine: {e}")
            raise










    def _execute_stage(
        self,
        stage: Stage,
        manifest: Manifest,
        session_dir: Path,
        session_id: str,
        config_overrides: dict[str, Any] | None = None,
        correction_artifact: str | None = None,
        resume: bool = False,
    ) -> dict[str, Any]:
        """Delegate to WorkflowStageExecutor._execute_stage."""
        stage = Stage.ensure(stage)
        manifest = Manifest.ensure(manifest)
        return self.workflow_stage_executor._execute_stage(
            stage,
            manifest,
            session_dir,
            session_id,
            config_overrides,
            correction_artifact,
            resume,
        )

    def _handle_gate(
        self,
        gate_id: str,
        stage_name: str,
        session_dir: Path,
        manifest: Manifest | None = None,
        stage_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Delegate gate handling to GateController."""
        if manifest is not None:
            manifest = Manifest.ensure(manifest)
        return self.gate_controller.handle_gate(
            gate_id, stage_name, session_dir, manifest, stage_result
        )

    def _validate_artifact_path(self, artifact_name: str, session_dir: Path) -> Path:
        """Delegate to ArtifactValidator."""
        return self.artifact_validator.validate_artifact_path(
            artifact_name, session_dir
        )

    def _validate_stage_artifacts(
        self,
        stage_name: str,
        session_dir: Path,
        output_artifacts: list[str],
    ) -> tuple[dict[str, Any], list[Path]]:
        """Delegate to ArtifactValidator."""
        return self.artifact_validator.validate_stage_artifacts(
            stage_name, session_dir, output_artifacts
        )

    def _resolve_max_retries(self, stage: Stage) -> int:
        """Delegate to WorkflowStageExecutor._resolve_max_retries."""
        stage = Stage.ensure(stage)
        return self.workflow_stage_executor._resolve_max_retries(stage)

    def _skip_stage(
        self, stage: Stage, session_dir: Path, session_id: str
    ) -> dict[str, Any]:
        """Delegate to WorkflowStageExecutor._skip_stage."""
        stage = Stage.ensure(stage)
        return self.workflow_stage_executor._skip_stage(stage, session_dir, session_id)

















