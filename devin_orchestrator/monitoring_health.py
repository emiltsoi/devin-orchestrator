#!/usr/bin/env python3
"""System health and workflow execution monitoring."""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

import psutil

from devin_orchestrator.health_check import HealthChecker
from devin_orchestrator.metrics import MetricsCollector
from devin_orchestrator.monitoring_alerts import (
    AlertManager,
    AlertSeverity,
    AlertType,
)

if TYPE_CHECKING:
    from devin_orchestrator.monitoring_config import MonitoringConfig

logger = logging.getLogger(__name__)


@dataclass
class SystemResourceMetrics:
    """System resource usage metrics"""

    cpu_percent: float
    memory_percent: float
    memory_used_gb: float
    memory_total_gb: float
    disk_percent: float
    disk_used_gb: float
    disk_total_gb: float
    timestamp: datetime


@dataclass
class SystemHealthSnapshot:
    """Snapshot of system health at a point in time"""

    timestamp: datetime
    overall_status: str
    component_status: dict[str, str]
    performance_metrics: dict[str, float | int]
    active_workflows: int
    recent_failures: int
    resource_metrics: SystemResourceMetrics | None = None


class SystemHealthMonitor:
    """Continuous system health monitoring"""

    def __init__(
        self,
        config: MonitoringConfig,
        alert_manager: AlertManager,
        health_checker: HealthChecker | None = None,
        metrics_collector: MetricsCollector | None = None,
    ):
        """
        Initialize system health monitor

        Args:
            config: Monitoring configuration
            alert_manager: Alert manager for generating alerts
            health_checker: Optional health checker instance
            metrics_collector: Optional metrics collector instance
        """
        self.config = config
        self.alert_manager = alert_manager
        self.health_checker = health_checker or HealthChecker()
        self.metrics_collector = (
            metrics_collector if metrics_collector is not None else MetricsCollector()
        )

        self._monitoring_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._health_history: deque = deque(maxlen=100)  # Keep last 100 snapshots
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start continuous health monitoring"""
        if self._monitoring_thread and self._monitoring_thread.is_alive():
            logger.warning("Health monitoring already running")
            return

        self._stop_event.clear()
        self._monitoring_thread = threading.Thread(
            target=self._monitoring_loop, daemon=True, name="SystemHealthMonitor"
        )
        self._monitoring_thread.start()
        logger.info("Started system health monitoring")

    def stop(self) -> None:
        """Stop continuous health monitoring"""
        if self._monitoring_thread and self._monitoring_thread.is_alive():
            self._stop_event.set()
            self._monitoring_thread.join(timeout=5)
            logger.info("Stopped system health monitoring")

    def _monitoring_loop(self) -> None:
        """Main monitoring loop"""
        while not self._stop_event.is_set():
            try:
                self._check_health()
            except Exception as e:
                logger.error(f"Error in health monitoring loop: {e}")

            # Wait for next check or stop event
            self._stop_event.wait(self.config.health_check_interval)

    def _check_health(self) -> SystemHealthSnapshot:
        """
        Perform health check and create snapshot

        Returns:
            SystemHealthSnapshot with current health status
        """
        report = self.health_checker.run_all_checks()

        # Extract component status
        component_status = {}
        for check in report["checks"]:
            component_status[check["component"]] = check["status"]

        # Get performance metrics
        all_metrics = self.metrics_collector.get_all_metrics()

        performance_metrics: dict[str, float | int] = {
            "active_workflows": len(all_metrics),
            "total_workflows": len(all_metrics),
        }

        # Calculate average durations if workflows exist
        if all_metrics:
            durations: list[float] = [
                m.total_duration for m in all_metrics.values() if m.total_duration
            ]
            if durations:
                avg_duration = sum(durations) / len(durations)
                performance_metrics["avg_workflow_duration"] = avg_duration

        # Count recent failures
        recent_failures = 0
        for workflow in all_metrics.values():
            if workflow.final_status in ["failed", "escalated", "blocked"]:
                recent_failures += 1

        # Collect system resource metrics
        resource_metrics = self._collect_resource_metrics()

        snapshot = SystemHealthSnapshot(
            timestamp=datetime.now(),
            overall_status=report["overall_status"],
            component_status=component_status,
            performance_metrics=performance_metrics,
            active_workflows=len(all_metrics),
            recent_failures=recent_failures,
            resource_metrics=resource_metrics,
        )

        # Store snapshot
        with self._lock:
            self._health_history.append(snapshot)

        # Generate alerts for health issues
        self._generate_health_alerts(snapshot, report)

        # Generate alerts for resource issues
        self._generate_resource_alerts(resource_metrics)

        return snapshot

    def _collect_resource_metrics(self) -> SystemResourceMetrics:
        """
        Collect system resource usage metrics

        Returns:
            SystemResourceMetrics with current resource usage
        """
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)

            # Memory usage
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_used_gb = memory.used / (1024**3)
            memory_total_gb = memory.total / (1024**3)

            # Disk usage
            disk = psutil.disk_usage("/")
            disk_percent = disk.percent
            disk_used_gb = disk.used / (1024**3)
            disk_total_gb = disk.total / (1024**3)

            return SystemResourceMetrics(
                cpu_percent=cpu_percent,
                memory_percent=memory_percent,
                memory_used_gb=memory_used_gb,
                memory_total_gb=memory_total_gb,
                disk_percent=disk_percent,
                disk_used_gb=disk_used_gb,
                disk_total_gb=disk_total_gb,
                timestamp=datetime.now(),
            )
        except Exception as e:
            logger.error(f"Error collecting resource metrics: {e}")
            # Return default metrics on error
            return SystemResourceMetrics(
                cpu_percent=0.0,
                memory_percent=0.0,
                memory_used_gb=0.0,
                memory_total_gb=0.0,
                disk_percent=0.0,
                disk_used_gb=0.0,
                disk_total_gb=0.0,
                timestamp=datetime.now(),
            )

    def _generate_resource_alerts(
        self, resource_metrics: SystemResourceMetrics
    ) -> None:
        """
        Generate alerts based on resource usage

        Args:
            resource_metrics: Current resource metrics
        """
        thresholds = self.config.resource_thresholds

        # CPU alerts
        if resource_metrics.cpu_percent >= thresholds["cpu_critical"]:
            self.alert_manager.create_alert(
                alert_type=AlertType.RESOURCE_EXHAUSTION,
                severity=AlertSeverity.CRITICAL,
                title="CPU Usage Critical",
                message=f"CPU usage is at {resource_metrics.cpu_percent:.1f}%, exceeding critical threshold",
                source="SystemHealthMonitor",
                config=self.config,
                metadata={
                    "cpu_percent": resource_metrics.cpu_percent,
                    "threshold": thresholds["cpu_critical"],
                },
            )
        elif resource_metrics.cpu_percent >= thresholds["cpu_warning"]:
            self.alert_manager.create_alert(
                alert_type=AlertType.RESOURCE_EXHAUSTION,
                severity=AlertSeverity.WARNING,
                title="CPU Usage Warning",
                message=f"CPU usage is at {resource_metrics.cpu_percent:.1f}%, exceeding warning threshold",
                source="SystemHealthMonitor",
                config=self.config,
                metadata={
                    "cpu_percent": resource_metrics.cpu_percent,
                    "threshold": thresholds["cpu_warning"],
                },
            )

        # Memory alerts
        if resource_metrics.memory_percent >= thresholds["memory_critical"]:
            self.alert_manager.create_alert(
                alert_type=AlertType.RESOURCE_EXHAUSTION,
                severity=AlertSeverity.CRITICAL,
                title="Memory Usage Critical",
                message=f"Memory usage is at {resource_metrics.memory_percent:.1f}%, exceeding critical threshold",
                source="SystemHealthMonitor",
                config=self.config,
                metadata={
                    "memory_percent": resource_metrics.memory_percent,
                    "memory_used_gb": resource_metrics.memory_used_gb,
                    "memory_total_gb": resource_metrics.memory_total_gb,
                    "threshold": thresholds["memory_critical"],
                },
            )
        elif resource_metrics.memory_percent >= thresholds["memory_warning"]:
            self.alert_manager.create_alert(
                alert_type=AlertType.RESOURCE_EXHAUSTION,
                severity=AlertSeverity.WARNING,
                title="Memory Usage Warning",
                message=f"Memory usage is at {resource_metrics.memory_percent:.1f}%, exceeding warning threshold",
                source="SystemHealthMonitor",
                config=self.config,
                metadata={
                    "memory_percent": resource_metrics.memory_percent,
                    "memory_used_gb": resource_metrics.memory_used_gb,
                    "memory_total_gb": resource_metrics.memory_total_gb,
                    "threshold": thresholds["memory_warning"],
                },
            )

        # Disk alerts
        if resource_metrics.disk_percent >= thresholds["disk_critical"]:
            self.alert_manager.create_alert(
                alert_type=AlertType.RESOURCE_EXHAUSTION,
                severity=AlertSeverity.CRITICAL,
                title="Disk Usage Critical",
                message=f"Disk usage is at {resource_metrics.disk_percent:.1f}%, exceeding critical threshold",
                source="SystemHealthMonitor",
                config=self.config,
                metadata={
                    "disk_percent": resource_metrics.disk_percent,
                    "disk_used_gb": resource_metrics.disk_used_gb,
                    "disk_total_gb": resource_metrics.disk_total_gb,
                    "threshold": thresholds["disk_critical"],
                },
            )
        elif resource_metrics.disk_percent >= thresholds["disk_warning"]:
            self.alert_manager.create_alert(
                alert_type=AlertType.RESOURCE_EXHAUSTION,
                severity=AlertSeverity.WARNING,
                title="Disk Usage Warning",
                message=f"Disk usage is at {resource_metrics.disk_percent:.1f}%, exceeding warning threshold",
                source="SystemHealthMonitor",
                config=self.config,
                metadata={
                    "disk_percent": resource_metrics.disk_percent,
                    "disk_used_gb": resource_metrics.disk_used_gb,
                    "disk_total_gb": resource_metrics.disk_total_gb,
                    "threshold": thresholds["disk_warning"],
                },
            )

    def _generate_health_alerts(
        self, snapshot: SystemHealthSnapshot, report: dict[str, Any]
    ) -> None:
        """
        Generate alerts based on health check results

        Args:
            snapshot: Current health snapshot
            report: Health check report
        """
        # Check for error status
        if snapshot.overall_status == "error":
            self.alert_manager.create_alert(
                alert_type=AlertType.SYSTEM_HEALTH,
                severity=AlertSeverity.CRITICAL,
                title="System Health Critical",
                message="System health check failed with overall status: error",
                source="SystemHealthMonitor",
                config=self.config,
                metadata={"health_report": report},
            )
        elif snapshot.overall_status == "warning":
            self.alert_manager.create_alert(
                alert_type=AlertType.SYSTEM_HEALTH,
                severity=AlertSeverity.WARNING,
                title="System Health Warning",
                message="System health check reported warnings",
                source="SystemHealthMonitor",
                config=self.config,
                metadata={"health_report": report},
            )

        # Check for component-specific issues
        for check in report["checks"]:
            if check["status"] == "error":
                self.alert_manager.create_alert(
                    alert_type=AlertType.SYSTEM_HEALTH,
                    severity=AlertSeverity.ERROR,
                    title=f"Component Error: {check['component']}",
                    message=check["message"],
                    source="SystemHealthMonitor",
                    config=self.config,
                    metadata={
                        "component": check["component"],
                        "details": check["details"],
                    },
                )

    def get_current_health(self) -> SystemHealthSnapshot | None:
        """
        Get the most recent health snapshot

        Returns:
            Most recent SystemHealthSnapshot or None if no checks have been run
        """
        with self._lock:
            if self._health_history:
                return self._health_history[-1]
        return None

    def get_health_history(self, limit: int = 100) -> list[SystemHealthSnapshot]:
        """
        Get health history

        Args:
            limit: Maximum number of snapshots to return

        Returns:
            List of SystemHealthSnapshot objects
        """
        with self._lock:
            return list(self._health_history)[-limit:]


class WorkflowExecutionMonitor:
    """Monitor workflow execution with real-time metrics and anomaly detection"""

    def __init__(
        self,
        config: MonitoringConfig,
        alert_manager: AlertManager,
        metrics_collector: MetricsCollector | None = None,
    ):
        """
        Initialize workflow execution monitor

        Args:
            config: Monitoring configuration
            alert_manager: Alert manager for generating alerts
            metrics_collector: Optional metrics collector instance
        """
        self.config = config
        self.alert_manager = alert_manager
        self.metrics_collector = (
            metrics_collector if metrics_collector is not None else MetricsCollector()
        )

    def monitor_workflow_completion(self, session_id: str) -> None:
        """
        Monitor workflow completion and generate alerts if needed

        Args:
            session_id: Session ID of the completed workflow
        """
        workflow_metrics = self.metrics_collector.get_workflow_metrics(session_id)
        if not workflow_metrics:
            return

        # Check workflow duration
        if workflow_metrics.total_duration:
            thresholds = self.config.performance_thresholds
            if (
                workflow_metrics.total_duration
                > thresholds["workflow_duration_critical"]
            ):
                self.alert_manager.create_alert(
                    alert_type=AlertType.PERFORMANCE_DEGRADATION,
                    severity=AlertSeverity.CRITICAL,
                    title="Workflow Duration Critical",
                    message=f"Workflow {session_id} took {workflow_metrics.total_duration:.2f}s, exceeding critical threshold",
                    source="WorkflowExecutionMonitor",
                    config=self.config,
                    metadata={
                        "session_id": session_id,
                        "duration": workflow_metrics.total_duration,
                        "threshold": thresholds["workflow_duration_critical"],
                    },
                )
            elif (
                workflow_metrics.total_duration
                > thresholds["workflow_duration_warning"]
            ):
                self.alert_manager.create_alert(
                    alert_type=AlertType.PERFORMANCE_DEGRADATION,
                    severity=AlertSeverity.WARNING,
                    title="Workflow Duration Warning",
                    message=f"Workflow {session_id} took {workflow_metrics.total_duration:.2f}s, exceeding warning threshold",
                    source="WorkflowExecutionMonitor",
                    config=self.config,
                    metadata={
                        "session_id": session_id,
                        "duration": workflow_metrics.total_duration,
                        "threshold": thresholds["workflow_duration_warning"],
                    },
                )

        # Check for failed status
        if workflow_metrics.final_status in ["failed", "escalated", "blocked"]:
            self.alert_manager.create_alert(
                alert_type=AlertType.WORKFLOW_FAILURE,
                severity=AlertSeverity.ERROR,
                title=f"Workflow {workflow_metrics.final_status}",
                message=f"Workflow {session_id} completed with status: {workflow_metrics.final_status}",
                source="WorkflowExecutionMonitor",
                config=self.config,
                metadata={
                    "session_id": session_id,
                    "manifest": workflow_metrics.manifest_name,
                    "status": workflow_metrics.final_status,
                    "duration": workflow_metrics.total_duration,
                },
            )

        # Check stage durations
        thresholds = self.config.performance_thresholds
        for stage_metric in workflow_metrics.stage_metrics:
            if (
                stage_metric.duration
                and stage_metric.duration > thresholds["stage_duration_critical"]
            ):
                self.alert_manager.create_alert(
                    alert_type=AlertType.PERFORMANCE_DEGRADATION,
                    severity=AlertSeverity.CRITICAL,
                    title="Stage Duration Critical",
                    message=f"Stage {stage_metric.stage_name} took {stage_metric.duration:.2f}s, exceeding critical threshold",
                    source="WorkflowExecutionMonitor",
                    config=self.config,
                    metadata={
                        "session_id": session_id,
                        "stage": stage_metric.stage_name,
                        "skill": stage_metric.skill_name,
                        "duration": stage_metric.duration,
                        "threshold": thresholds["stage_duration_critical"],
                    },
                )
            elif (
                stage_metric.duration
                and stage_metric.duration > thresholds["stage_duration_warning"]
            ):
                self.alert_manager.create_alert(
                    alert_type=AlertType.PERFORMANCE_DEGRADATION,
                    severity=AlertSeverity.WARNING,
                    title="Stage Duration Warning",
                    message=f"Stage {stage_metric.stage_name} took {stage_metric.duration:.2f}s, exceeding warning threshold",
                    source="WorkflowExecutionMonitor",
                    config=self.config,
                    metadata={
                        "session_id": session_id,
                        "stage": stage_metric.stage_name,
                        "skill": stage_metric.skill_name,
                        "duration": stage_metric.duration,
                        "threshold": thresholds["stage_duration_warning"],
                    },
                )

    def check_failure_rates(self, time_window_hours: int = 1) -> None:
        """
        Check workflow failure rates and generate alerts if needed

        Args:
            time_window_hours: Time window in hours to check for failures
        """
        all_metrics = self.metrics_collector.get_all_metrics()
        if not all_metrics:
            return

        # Filter workflows within time window
        cutoff_time = time.time() - (time_window_hours * 3600)
        recent_workflows = [
            m for m in all_metrics.values() if m.start_time >= cutoff_time
        ]

        if not recent_workflows:
            return

        # Calculate failure rate
        failed_count = len(
            [
                m
                for m in recent_workflows
                if m.final_status in ["failed", "escalated", "blocked"]
            ]
        )
        failure_rate = failed_count / len(recent_workflows)

        thresholds = self.config.performance_thresholds
        if failure_rate > thresholds["failure_rate_critical"]:
            self.alert_manager.create_alert(
                alert_type=AlertType.WORKFLOW_FAILURE,
                severity=AlertSeverity.CRITICAL,
                title="Critical Failure Rate",
                message=f"Failure rate {failure_rate:.1%} exceeds critical threshold in last {time_window_hours}h",
                source="WorkflowExecutionMonitor",
                config=self.config,
                metadata={
                    "failure_rate": failure_rate,
                    "threshold": thresholds["failure_rate_critical"],
                    "time_window_hours": time_window_hours,
                    "total_workflows": len(recent_workflows),
                    "failed_workflows": failed_count,
                },
            )
        elif failure_rate > thresholds["failure_rate_warning"]:
            self.alert_manager.create_alert(
                alert_type=AlertType.WORKFLOW_FAILURE,
                severity=AlertSeverity.WARNING,
                title="Elevated Failure Rate",
                message=f"Failure rate {failure_rate:.1%} exceeds warning threshold in last {time_window_hours}h",
                source="WorkflowExecutionMonitor",
                config=self.config,
                metadata={
                    "failure_rate": failure_rate,
                    "threshold": thresholds["failure_rate_warning"],
                    "time_window_hours": time_window_hours,
                    "total_workflows": len(recent_workflows),
                    "failed_workflows": failed_count,
                },
            )
