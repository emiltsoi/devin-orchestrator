#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Monitoring Module for Devin Orchestrator

Provides comprehensive monitoring and observability capabilities:
- System health monitoring with continuous checks
- Workflow execution monitoring with real-time metrics
- Alerting system for failures and anomalies
- Integration with existing health checks, metrics, and logging
"""

import sys
import json
import time
import threading
import logging
import psutil
import smtplib
import requests
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
from collections import deque
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from health_check import HealthChecker, HealthCheckResult
from metrics import get_metrics_collector, MetricsCollector
from orchestration_logger import get_logger, LogLevel

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Severity levels for alerts"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertType(Enum):
    """Types of alerts"""
    SYSTEM_HEALTH = "system_health"
    WORKFLOW_FAILURE = "workflow_failure"
    PERFORMANCE_DEGRADATION = "performance_degradation"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    ANOMALY_DETECTED = "anomaly_detected"


@dataclass
class Alert:
    """Represents a monitoring alert"""
    alert_id: str
    alert_type: AlertType
    severity: AlertSeverity
    title: str
    message: str
    timestamp: datetime
    source: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    resolved: bool = False
    resolved_at: Optional[datetime] = None


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
    component_status: Dict[str, str]
    performance_metrics: Dict[str, float]
    active_workflows: int
    recent_failures: int
    resource_metrics: Optional[SystemResourceMetrics] = None


@dataclass
class MonitoringConfig:
    """Configuration for monitoring system"""
    health_check_interval: int = 60  # seconds
    metrics_retention_hours: int = 24
    alert_retention_hours: int = 168  # 7 days
    max_alerts: int = 1000
    enable_continuous_monitoring: bool = True
    performance_thresholds: Dict[str, float] = field(default_factory=lambda: {
        'stage_duration_warning': 300.0,  # 5 minutes
        'stage_duration_critical': 600.0,  # 10 minutes
        'workflow_duration_warning': 1800.0,  # 30 minutes
        'workflow_duration_critical': 3600.0,  # 1 hour
        'failure_rate_warning': 0.1,  # 10%
        'failure_rate_critical': 0.25,  # 25%
    })
    resource_thresholds: Dict[str, float] = field(default_factory=lambda: {
        'cpu_warning': 80.0,  # 80%
        'cpu_critical': 90.0,  # 90%
        'memory_warning': 80.0,  # 80%
        'memory_critical': 90.0,  # 90%
        'disk_warning': 80.0,  # 80%
        'disk_critical': 90.0,  # 90%
    })
    # Email notification configuration
    email_enabled: bool = False
    email_smtp_server: str = "smtp.gmail.com"
    email_smtp_port: int = 587
    email_username: str = ""
    email_password: str = ""
    email_from: str = ""
    email_to: List[str] = field(default_factory=list)
    # Webhook notification configuration
    webhook_enabled: bool = False
    webhook_url: str = ""
    webhook_headers: Dict[str, str] = field(default_factory=dict)


class AlertManager:
    """Manages alert generation, storage, and notification"""
    
    def __init__(self, config: MonitoringConfig):
        """
        Initialize alert manager
        
        Args:
            config: Monitoring configuration
        """
        self.config = config
        self._alerts: deque = deque(maxlen=config.max_alerts)
        self._alert_handlers: List[Callable[[Alert], None]] = []
        self._lock = threading.Lock()
        self._alert_counter = 0
        
    def add_alert_handler(self, handler: Callable[[Alert], None]) -> None:
        """
        Add a handler to be called when alerts are generated
        
        Args:
            handler: Function that takes an Alert and returns None
        """
        with self._lock:
            self._alert_handlers.append(handler)
    
    def send_email_notification(self, alert: Alert, config: MonitoringConfig) -> bool:
        """
        Send email notification for an alert
        
        Args:
            alert: Alert to send notification for
            config: Monitoring configuration with email settings
            
        Returns:
            True if email sent successfully, False otherwise
        """
        if not config.email_enabled:
            return False
        
        try:
            # Create email message
            msg = MIMEMultipart()
            msg['From'] = config.email_from
            msg['To'] = ', '.join(config.email_to)
            msg['Subject'] = f"[{alert.severity.value.upper()}] {alert.title}"
            
            # Email body
            body = f"""
Alert Notification
=================

Alert ID: {alert.alert_id}
Severity: {alert.severity.value.upper()}
Type: {alert.alert_type.value}
Title: {alert.title}
Source: {alert.source}
Timestamp: {alert.timestamp.isoformat()}

Message:
{alert.message}

Metadata:
{json.dumps(alert.metadata, indent=2)}
"""
            
            msg.attach(MIMEText(body, 'plain'))
            
            # Send email
            with smtplib.SMTP(config.email_smtp_server, config.email_smtp_port) as server:
                server.starttls()
                server.login(config.email_username, config.email_password)
                server.send_message(msg)
            
            logger.info(f"Email notification sent for alert {alert.alert_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email notification: {e}")
            return False
    
    def send_webhook_notification(self, alert: Alert, config: MonitoringConfig) -> bool:
        """
        Send webhook notification for an alert
        
        Args:
            alert: Alert to send notification for
            config: Monitoring configuration with webhook settings
            
        Returns:
            True if webhook sent successfully, False otherwise
        """
        if not config.webhook_enabled or not config.webhook_url:
            return False
        
        try:
            # Prepare webhook payload
            payload = {
                'alert_id': alert.alert_id,
                'alert_type': alert.alert_type.value,
                'severity': alert.severity.value,
                'title': alert.title,
                'message': alert.message,
                'timestamp': alert.timestamp.isoformat(),
                'source': alert.source,
                'metadata': alert.metadata,
                'resolved': alert.resolved
            }
            
            # Send webhook
            headers = {'Content-Type': 'application/json'}
            headers.update(config.webhook_headers)
            
            response = requests.post(
                config.webhook_url,
                json=payload,
                headers=headers,
                timeout=10
            )
            
            response.raise_for_status()
            logger.info(f"Webhook notification sent for alert {alert.alert_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send webhook notification: {e}")
            return False
    
    def create_alert(
        self,
        alert_type: AlertType,
        severity: AlertSeverity,
        title: str,
        message: str,
        source: str,
        metadata: Optional[Dict[str, Any]] = None,
        config: Optional[MonitoringConfig] = None
    ) -> Alert:
        """
        Create and store a new alert
        
        Args:
            alert_type: Type of alert
            severity: Severity level
            title: Alert title
            message: Alert message
            source: Source of the alert
            metadata: Additional metadata
            config: Optional monitoring configuration for notifications
            
        Returns:
            Created Alert object
        """
        with self._lock:
            self._alert_counter += 1
            alert = Alert(
                alert_id=f"alert-{self._alert_counter}-{int(time.time())}",
                alert_type=alert_type,
                severity=severity,
                title=title,
                message=message,
                timestamp=datetime.now(),
                source=source,
                metadata=metadata or {}
            )
            
            self._alerts.append(alert)
            
            # Call alert handlers
            for handler in self._alert_handlers:
                try:
                    handler(alert)
                except Exception as e:
                    logger.error(f"Error in alert handler: {e}")
            
            # Send notifications if configured
            if config:
                self.send_email_notification(alert, config)
                self.send_webhook_notification(alert, config)
            
            logger.warning(f"Alert created: {alert.alert_id} - {title}")
            return alert
    
    def get_alerts(
        self,
        severity: Optional[AlertSeverity] = None,
        alert_type: Optional[AlertType] = None,
        resolved: Optional[bool] = None,
        since: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Alert]:
        """
        Get alerts with optional filtering
        
        Args:
            severity: Filter by severity
            alert_type: Filter by alert type
            resolved: Filter by resolved status
            since: Only include alerts after this timestamp
            limit: Maximum number of alerts to return
            
        Returns:
            List of matching alerts
        """
        with self._lock:
            alerts = list(self._alerts)
        
        # Apply filters
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        if alert_type:
            alerts = [a for a in alerts if a.alert_type == alert_type]
        if resolved is not None:
            alerts = [a for a in alerts if a.resolved == resolved]
        if since:
            alerts = [a for a in alerts if a.timestamp >= since]
        
        # Sort by timestamp (newest first) and limit
        alerts.sort(key=lambda a: a.timestamp, reverse=True)
        return alerts[:limit]
    
    def resolve_alert(self, alert_id: str) -> bool:
        """
        Mark an alert as resolved
        
        Args:
            alert_id: ID of alert to resolve
            
        Returns:
            True if alert was found and resolved, False otherwise
        """
        with self._lock:
            for alert in self._alerts:
                if alert.alert_id == alert_id and not alert.resolved:
                    alert.resolved = True
                    alert.resolved_at = datetime.now()
                    logger.info(f"Alert resolved: {alert_id}")
                    return True
        return False
    
    def get_alert_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about alerts
        
        Returns:
            Dictionary with alert statistics
        """
        with self._lock:
            alerts = list(self._alerts)
        
        total = len(alerts)
        unresolved = len([a for a in alerts if not a.resolved])
        
        by_severity = {}
        for severity in AlertSeverity:
            by_severity[severity.value] = len([a for a in alerts if a.severity == severity])
        
        by_type = {}
        for alert_type in AlertType:
            by_type[alert_type.value] = len([a for a in alerts if a.alert_type == alert_type])
        
        recent_24h = len([a for a in alerts if a.timestamp >= datetime.now() - timedelta(hours=24)])
        
        return {
            'total_alerts': total,
            'unresolved_alerts': unresolved,
            'by_severity': by_severity,
            'by_type': by_type,
            'recent_24h': recent_24h
        }


class SystemHealthMonitor:
    """Continuous system health monitoring"""
    
    def __init__(
        self,
        config: MonitoringConfig,
        alert_manager: AlertManager,
        health_checker: Optional[HealthChecker] = None
    ):
        """
        Initialize system health monitor
        
        Args:
            config: Monitoring configuration
            alert_manager: Alert manager for generating alerts
            health_checker: Optional health checker instance
        """
        self.config = config
        self.alert_manager = alert_manager
        self.health_checker = health_checker or HealthChecker()
        
        self._monitoring_thread: Optional[threading.Thread] = None
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
            target=self._monitoring_loop,
            daemon=True,
            name="SystemHealthMonitor"
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
        for check in report['checks']:
            component_status[check['component']] = check['status']
        
        # Get performance metrics
        metrics_collector = get_metrics_collector()
        all_metrics = metrics_collector.get_all_metrics()
        
        performance_metrics = {
            'active_workflows': len(all_metrics),
            'total_workflows': len(all_metrics)
        }
        
        # Calculate average durations if workflows exist
        if all_metrics:
            completed_workflows = [m for m in all_metrics.values() if m.total_duration]
            if completed_workflows:
                avg_duration = sum(m.total_duration for m in completed_workflows) / len(completed_workflows)
                performance_metrics['avg_workflow_duration'] = avg_duration
        
        # Count recent failures
        recent_failures = 0
        for workflow in all_metrics.values():
            if workflow.final_status in ['failed', 'escalated', 'blocked']:
                recent_failures += 1
        
        # Collect system resource metrics
        resource_metrics = self._collect_resource_metrics()
        
        snapshot = SystemHealthSnapshot(
            timestamp=datetime.now(),
            overall_status=report['overall_status'],
            component_status=component_status,
            performance_metrics=performance_metrics,
            active_workflows=len(all_metrics),
            recent_failures=recent_failures,
            resource_metrics=resource_metrics
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
            disk = psutil.disk_usage('/')
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
                timestamp=datetime.now()
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
                timestamp=datetime.now()
            )
    
    def _generate_resource_alerts(self, resource_metrics: SystemResourceMetrics) -> None:
        """
        Generate alerts based on resource usage
        
        Args:
            resource_metrics: Current resource metrics
        """
        thresholds = self.config.resource_thresholds
        
        # CPU alerts
        if resource_metrics.cpu_percent >= thresholds['cpu_critical']:
            self.alert_manager.create_alert(
                alert_type=AlertType.RESOURCE_EXHAUSTION,
                severity=AlertSeverity.CRITICAL,
                title="CPU Usage Critical",
                message=f"CPU usage is at {resource_metrics.cpu_percent:.1f}%, exceeding critical threshold",
                source="SystemHealthMonitor",
                config=self.config,
                metadata={
                    'cpu_percent': resource_metrics.cpu_percent,
                    'threshold': thresholds['cpu_critical']
                }
            )
        elif resource_metrics.cpu_percent >= thresholds['cpu_warning']:
            self.alert_manager.create_alert(
                alert_type=AlertType.RESOURCE_EXHAUSTION,
                severity=AlertSeverity.WARNING,
                title="CPU Usage Warning",
                message=f"CPU usage is at {resource_metrics.cpu_percent:.1f}%, exceeding warning threshold",
                source="SystemHealthMonitor",
                config=self.config,
                metadata={
                    'cpu_percent': resource_metrics.cpu_percent,
                    'threshold': thresholds['cpu_warning']
                }
            )
        
        # Memory alerts
        if resource_metrics.memory_percent >= thresholds['memory_critical']:
            self.alert_manager.create_alert(
                alert_type=AlertType.RESOURCE_EXHAUSTION,
                severity=AlertSeverity.CRITICAL,
                title="Memory Usage Critical",
                message=f"Memory usage is at {resource_metrics.memory_percent:.1f}%, exceeding critical threshold",
                source="SystemHealthMonitor",
                config=self.config,
                metadata={
                    'memory_percent': resource_metrics.memory_percent,
                    'memory_used_gb': resource_metrics.memory_used_gb,
                    'memory_total_gb': resource_metrics.memory_total_gb,
                    'threshold': thresholds['memory_critical']
                }
            )
        elif resource_metrics.memory_percent >= thresholds['memory_warning']:
            self.alert_manager.create_alert(
                alert_type=AlertType.RESOURCE_EXHAUSTION,
                severity=AlertSeverity.WARNING,
                title="Memory Usage Warning",
                message=f"Memory usage is at {resource_metrics.memory_percent:.1f}%, exceeding warning threshold",
                source="SystemHealthMonitor",
                config=self.config,
                metadata={
                    'memory_percent': resource_metrics.memory_percent,
                    'memory_used_gb': resource_metrics.memory_used_gb,
                    'memory_total_gb': resource_metrics.memory_total_gb,
                    'threshold': thresholds['memory_warning']
                }
            )
        
        # Disk alerts
        if resource_metrics.disk_percent >= thresholds['disk_critical']:
            self.alert_manager.create_alert(
                alert_type=AlertType.RESOURCE_EXHAUSTION,
                severity=AlertSeverity.CRITICAL,
                title="Disk Usage Critical",
                message=f"Disk usage is at {resource_metrics.disk_percent:.1f}%, exceeding critical threshold",
                source="SystemHealthMonitor",
                config=self.config,
                metadata={
                    'disk_percent': resource_metrics.disk_percent,
                    'disk_used_gb': resource_metrics.disk_used_gb,
                    'disk_total_gb': resource_metrics.disk_total_gb,
                    'threshold': thresholds['disk_critical']
                }
            )
        elif resource_metrics.disk_percent >= thresholds['disk_warning']:
            self.alert_manager.create_alert(
                alert_type=AlertType.RESOURCE_EXHAUSTION,
                severity=AlertSeverity.WARNING,
                title="Disk Usage Warning",
                message=f"Disk usage is at {resource_metrics.disk_percent:.1f}%, exceeding warning threshold",
                source="SystemHealthMonitor",
                config=self.config,
                metadata={
                    'disk_percent': resource_metrics.disk_percent,
                    'disk_used_gb': resource_metrics.disk_used_gb,
                    'disk_total_gb': resource_metrics.disk_total_gb,
                    'threshold': thresholds['disk_warning']
                }
            )
    
    def _generate_health_alerts(self, snapshot: SystemHealthSnapshot, report: Dict[str, Any]) -> None:
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
                message=f"System health check failed with overall status: error",
                source="SystemHealthMonitor",
                config=self.config,
                metadata={'health_report': report}
            )
        elif snapshot.overall_status == "warning":
            self.alert_manager.create_alert(
                alert_type=AlertType.SYSTEM_HEALTH,
                severity=AlertSeverity.WARNING,
                title="System Health Warning",
                message=f"System health check reported warnings",
                source="SystemHealthMonitor",
                config=self.config,
                metadata={'health_report': report}
            )
        
        # Check for component-specific issues
        for check in report['checks']:
            if check['status'] == 'error':
                self.alert_manager.create_alert(
                    alert_type=AlertType.SYSTEM_HEALTH,
                    severity=AlertSeverity.ERROR,
                    title=f"Component Error: {check['component']}",
                    message=check['message'],
                    source="SystemHealthMonitor",
                    config=self.config,
                    metadata={'component': check['component'], 'details': check['details']}
                )
    
    def get_current_health(self) -> Optional[SystemHealthSnapshot]:
        """
        Get the most recent health snapshot
        
        Returns:
            Most recent SystemHealthSnapshot or None if no checks have been run
        """
        with self._lock:
            if self._health_history:
                return self._health_history[-1]
        return None
    
    def get_health_history(self, limit: int = 100) -> List[SystemHealthSnapshot]:
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
        metrics_collector: Optional[MetricsCollector] = None
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
        self.metrics_collector = metrics_collector or get_metrics_collector()
        
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
            if workflow_metrics.total_duration > thresholds['workflow_duration_critical']:
                self.alert_manager.create_alert(
                    alert_type=AlertType.PERFORMANCE_DEGRADATION,
                    severity=AlertSeverity.CRITICAL,
                    title="Workflow Duration Critical",
                    message=f"Workflow {session_id} took {workflow_metrics.total_duration:.2f}s, exceeding critical threshold",
                    source="WorkflowExecutionMonitor",
                    config=self.config,
                    metadata={
                        'session_id': session_id,
                        'duration': workflow_metrics.total_duration,
                        'threshold': thresholds['workflow_duration_critical']
                    }
                )
            elif workflow_metrics.total_duration > thresholds['workflow_duration_warning']:
                self.alert_manager.create_alert(
                    alert_type=AlertType.PERFORMANCE_DEGRADATION,
                    severity=AlertSeverity.WARNING,
                    title="Workflow Duration Warning",
                    message=f"Workflow {session_id} took {workflow_metrics.total_duration:.2f}s, exceeding warning threshold",
                    source="WorkflowExecutionMonitor",
                    config=self.config,
                    metadata={
                        'session_id': session_id,
                        'duration': workflow_metrics.total_duration,
                        'threshold': thresholds['workflow_duration_warning']
                    }
                )
        
        # Check for failed status
        if workflow_metrics.final_status in ['failed', 'escalated', 'blocked']:
            self.alert_manager.create_alert(
                alert_type=AlertType.WORKFLOW_FAILURE,
                severity=AlertSeverity.ERROR,
                title=f"Workflow {workflow_metrics.final_status}",
                message=f"Workflow {session_id} completed with status: {workflow_metrics.final_status}",
                source="WorkflowExecutionMonitor",
                config=self.config,
                metadata={
                    'session_id': session_id,
                    'manifest': workflow_metrics.manifest_name,
                    'status': workflow_metrics.final_status,
                    'duration': workflow_metrics.total_duration
                }
            )
        
        # Check stage durations
        thresholds = self.config.performance_thresholds
        for stage_metric in workflow_metrics.stage_metrics:
            if stage_metric.duration and stage_metric.duration > thresholds['stage_duration_critical']:
                self.alert_manager.create_alert(
                    alert_type=AlertType.PERFORMANCE_DEGRADATION,
                    severity=AlertSeverity.CRITICAL,
                    title="Stage Duration Critical",
                    message=f"Stage {stage_metric.stage_name} took {stage_metric.duration:.2f}s, exceeding critical threshold",
                    source="WorkflowExecutionMonitor",
                    config=self.config,
                    metadata={
                        'session_id': session_id,
                        'stage': stage_metric.stage_name,
                        'skill': stage_metric.skill_name,
                        'duration': stage_metric.duration,
                        'threshold': thresholds['stage_duration_critical']
                    }
                )
            elif stage_metric.duration and stage_metric.duration > thresholds['stage_duration_warning']:
                self.alert_manager.create_alert(
                    alert_type=AlertType.PERFORMANCE_DEGRADATION,
                    severity=AlertSeverity.WARNING,
                    title="Stage Duration Warning",
                    message=f"Stage {stage_metric.stage_name} took {stage_metric.duration:.2f}s, exceeding warning threshold",
                    source="WorkflowExecutionMonitor",
                    config=self.config,
                    metadata={
                        'session_id': session_id,
                        'stage': stage_metric.stage_name,
                        'skill': stage_metric.skill_name,
                        'duration': stage_metric.duration,
                        'threshold': thresholds['stage_duration_warning']
                    }
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
            m for m in all_metrics.values()
            if m.start_time >= cutoff_time
        ]
        
        if not recent_workflows:
            return
        
        # Calculate failure rate
        failed_count = len([
            m for m in recent_workflows
            if m.final_status in ['failed', 'escalated', 'blocked']
        ])
        failure_rate = failed_count / len(recent_workflows)
        
        thresholds = self.config.performance_thresholds
        if failure_rate > thresholds['failure_rate_critical']:
            self.alert_manager.create_alert(
                alert_type=AlertType.WORKFLOW_FAILURE,
                severity=AlertSeverity.CRITICAL,
                title="Critical Failure Rate",
                message=f"Failure rate {failure_rate:.1%} exceeds critical threshold in last {time_window_hours}h",
                source="WorkflowExecutionMonitor",
                config=self.config,
                metadata={
                    'failure_rate': failure_rate,
                    'threshold': thresholds['failure_rate_critical'],
                    'time_window_hours': time_window_hours,
                    'total_workflows': len(recent_workflows),
                    'failed_workflows': failed_count
                }
            )
        elif failure_rate > thresholds['failure_rate_warning']:
            self.alert_manager.create_alert(
                alert_type=AlertType.WORKFLOW_FAILURE,
                severity=AlertSeverity.WARNING,
                title="Elevated Failure Rate",
                message=f"Failure rate {failure_rate:.1%} exceeds warning threshold in last {time_window_hours}h",
                source="WorkflowExecutionMonitor",
                config=self.config,
                metadata={
                    'failure_rate': failure_rate,
                    'threshold': thresholds['failure_rate_warning'],
                    'time_window_hours': time_window_hours,
                    'total_workflows': len(recent_workflows),
                    'failed_workflows': failed_count
                }
            )


class MonitoringSystem:
    """
    Main monitoring system that integrates all monitoring components
    
    Provides unified interface for:
    - System health monitoring
    - Workflow execution monitoring
    - Alert management
    - Metrics collection
    """
    
    def __init__(self, config: Optional[MonitoringConfig] = None):
        """
        Initialize monitoring system
        
        Args:
            config: Optional monitoring configuration
        """
        self.config = config or MonitoringConfig()
        self.alert_manager = AlertManager(self.config)
        self.health_monitor = SystemHealthMonitor(self.config, self.alert_manager)
        self.workflow_monitor = WorkflowExecutionMonitor(self.config, self.alert_manager)
        
        # Set up default alert handler that logs alerts
        self.alert_manager.add_alert_handler(self._default_alert_handler)
        
        # Get structured logger
        self.logger = get_logger()
        
    def _default_alert_handler(self, alert: Alert) -> None:
        """
        Default alert handler that logs alerts to structured logger
        
        Args:
            alert: Alert to handle
        """
        log_level = {
            AlertSeverity.INFO: LogLevel.INFO,
            AlertSeverity.WARNING: LogLevel.WARNING,
            AlertSeverity.ERROR: LogLevel.ERROR,
            AlertSeverity.CRITICAL: LogLevel.CRITICAL
        }.get(alert.severity, LogLevel.INFO)
        
        self.logger._log_structured(
            log_level,
            'alert',
            alert.message,
            alert_id=alert.alert_id,
            alert_type=alert.alert_type.value,
            severity=alert.severity.value,
            title=alert.title,
            source=alert.source,
            metadata=alert.metadata
        )
    
    def start(self) -> None:
        """Start the monitoring system"""
        if self.config.enable_continuous_monitoring:
            self.health_monitor.start()
        self.logger.log_debug("Monitoring system started")
    
    def stop(self) -> None:
        """Stop the monitoring system"""
        self.health_monitor.stop()
        self.logger.log_debug("Monitoring system stopped")
    
    def get_system_health(self) -> Optional[SystemHealthSnapshot]:
        """Get current system health snapshot"""
        return self.health_monitor.get_current_health()
    
    def get_health_history(self, limit: int = 100) -> List[SystemHealthSnapshot]:
        """Get health history"""
        return self.health_monitor.get_health_history(limit)
    
    def get_alerts(
        self,
        severity: Optional[AlertSeverity] = None,
        alert_type: Optional[AlertType] = None,
        resolved: Optional[bool] = None,
        since: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Alert]:
        """Get alerts with optional filtering"""
        return self.alert_manager.get_alerts(severity, alert_type, resolved, since, limit)
    
    def get_alert_statistics(self) -> Dict[str, Any]:
        """Get alert statistics"""
        return self.alert_manager.get_alert_statistics()
    
    def resolve_alert(self, alert_id: str) -> bool:
        """Resolve an alert"""
        return self.alert_manager.resolve_alert(alert_id)
    
    def monitor_workflow(self, session_id: str) -> None:
        """Monitor a completed workflow"""
        self.workflow_monitor.monitor_workflow_completion(session_id)
    
    def check_failure_rates(self, time_window_hours: int = 1) -> None:
        """Check workflow failure rates"""
        self.workflow_monitor.check_failure_rates(time_window_hours)
    
    def get_monitoring_report(self) -> Dict[str, Any]:
        """
        Get comprehensive monitoring report
        
        Returns:
            Dictionary with monitoring system status and metrics
        """
        health_snapshot = self.get_system_health()
        alert_stats = self.get_alert_statistics()
        recent_alerts = self.get_alerts(limit=10)
        
        return {
            'timestamp': datetime.now().isoformat(),
            'system_health': {
                'overall_status': health_snapshot.overall_status if health_snapshot else 'unknown',
                'component_status': health_snapshot.component_status if health_snapshot else {},
                'active_workflows': health_snapshot.active_workflows if health_snapshot else 0,
                'recent_failures': health_snapshot.recent_failures if health_snapshot else 0,
                'resource_metrics': {
                    'cpu_percent': health_snapshot.resource_metrics.cpu_percent if health_snapshot and health_snapshot.resource_metrics else 0,
                    'memory_percent': health_snapshot.resource_metrics.memory_percent if health_snapshot and health_snapshot.resource_metrics else 0,
                    'memory_used_gb': health_snapshot.resource_metrics.memory_used_gb if health_snapshot and health_snapshot.resource_metrics else 0,
                    'memory_total_gb': health_snapshot.resource_metrics.memory_total_gb if health_snapshot and health_snapshot.resource_metrics else 0,
                    'disk_percent': health_snapshot.resource_metrics.disk_percent if health_snapshot and health_snapshot.resource_metrics else 0,
                    'disk_used_gb': health_snapshot.resource_metrics.disk_used_gb if health_snapshot and health_snapshot.resource_metrics else 0,
                    'disk_total_gb': health_snapshot.resource_metrics.disk_total_gb if health_snapshot and health_snapshot.resource_metrics else 0,
                } if health_snapshot and health_snapshot.resource_metrics else None
            } if health_snapshot else None,
            'alerts': {
                'statistics': alert_stats,
                'recent': [
                    {
                        'alert_id': a.alert_id,
                        'type': a.alert_type.value,
                        'severity': a.severity.value,
                        'title': a.title,
                        'message': a.message,
                        'timestamp': a.timestamp.isoformat(),
                        'resolved': a.resolved
                    }
                    for a in recent_alerts
                ]
            },
            'configuration': {
                'health_check_interval': self.config.health_check_interval,
                'continuous_monitoring': self.config.enable_continuous_monitoring,
                'performance_thresholds': self.config.performance_thresholds,
                'resource_thresholds': self.config.resource_thresholds,
                'email_enabled': self.config.email_enabled,
                'webhook_enabled': self.config.webhook_enabled
            }
        }
    
    def export_monitoring_data(self, output_path: Path) -> bool:
        """
        Export monitoring data to JSON file
        
        Args:
            output_path: Path to output file
            
        Returns:
            True if export succeeded, False otherwise
        """
        try:
            report = self.get_monitoring_report()
            
            # Add health history
            report['health_history'] = [
                {
                    'timestamp': h.timestamp.isoformat(),
                    'overall_status': h.overall_status,
                    'component_status': h.component_status,
                    'performance_metrics': h.performance_metrics,
                    'active_workflows': h.active_workflows,
                    'recent_failures': h.recent_failures,
                    'resource_metrics': {
                        'cpu_percent': h.resource_metrics.cpu_percent if h.resource_metrics else 0,
                        'memory_percent': h.resource_metrics.memory_percent if h.resource_metrics else 0,
                        'memory_used_gb': h.resource_metrics.memory_used_gb if h.resource_metrics else 0,
                        'memory_total_gb': h.resource_metrics.memory_total_gb if h.resource_metrics else 0,
                        'disk_percent': h.resource_metrics.disk_percent if h.resource_metrics else 0,
                        'disk_used_gb': h.resource_metrics.disk_used_gb if h.resource_metrics else 0,
                        'disk_total_gb': h.resource_metrics.disk_total_gb if h.resource_metrics else 0,
                    } if h.resource_metrics else None
                }
                for h in self.get_health_history()
            ]
            
            # Add all alerts
            report['all_alerts'] = [
                {
                    'alert_id': a.alert_id,
                    'type': a.alert_type.value,
                    'severity': a.severity.value,
                    'title': a.title,
                    'message': a.message,
                    'timestamp': a.timestamp.isoformat(),
                    'source': a.source,
                    'metadata': a.metadata,
                    'resolved': a.resolved,
                    'resolved_at': a.resolved_at.isoformat() if a.resolved_at else None
                }
                for a in self.alert_manager.get_alerts(limit=1000)
            ]
            
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            
            self.logger.log_debug(f"Exported monitoring data to {output_path}")
            return True
            
        except Exception as e:
            self.logger.log_error(f"Failed to export monitoring data: {str(e)}")
            return False


# Global monitoring system instance
_global_monitoring_system: Optional[MonitoringSystem] = None


def get_monitoring_system(config: Optional[MonitoringConfig] = None) -> MonitoringSystem:
    """
    Get or create global monitoring system instance
    
    Args:
        config: Optional monitoring configuration
        
    Returns:
        MonitoringSystem instance
    """
    global _global_monitoring_system
    
    if _global_monitoring_system is None:
        _global_monitoring_system = MonitoringSystem(config)
    
    return _global_monitoring_system


def reset_monitoring_system() -> None:
    """Reset global monitoring system instance (useful for testing)"""
    global _global_monitoring_system
    if _global_monitoring_system:
        _global_monitoring_system.stop()
    _global_monitoring_system = None