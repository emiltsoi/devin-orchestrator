#!/usr/bin/env python3
"""Alert data classes and AlertManager."""

from __future__ import annotations

import json
import logging
import smtplib
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import Enum
from typing import TYPE_CHECKING, Any

import requests

if TYPE_CHECKING:
    from collections.abc import Callable

    from devin_orchestrator.monitoring_config import MonitoringConfig

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
    metadata: dict[str, Any] = field(default_factory=dict)
    resolved: bool = False
    resolved_at: datetime | None = None


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
        self._alert_handlers: list[Callable[[Alert], None]] = []
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
            msg["From"] = config.email_from
            msg["To"] = ", ".join(config.email_to)
            msg["Subject"] = f"[{alert.severity.value.upper()}] {alert.title}"

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

            msg.attach(MIMEText(body, "plain"))

            # Send email
            with smtplib.SMTP(
                config.email_smtp_server, config.email_smtp_port
            ) as server:
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
                "alert_id": alert.alert_id,
                "alert_type": alert.alert_type.value,
                "severity": alert.severity.value,
                "title": alert.title,
                "message": alert.message,
                "timestamp": alert.timestamp.isoformat(),
                "source": alert.source,
                "metadata": alert.metadata,
                "resolved": alert.resolved,
            }

            # Send webhook
            headers = {"Content-Type": "application/json"}
            headers.update(config.webhook_headers)

            response = requests.post(
                config.webhook_url, json=payload, headers=headers, timeout=10
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
        metadata: dict[str, Any] | None = None,
        config: MonitoringConfig | None = None,
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
                metadata=metadata or {},
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
        severity: AlertSeverity | None = None,
        alert_type: AlertType | None = None,
        resolved: bool | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[Alert]:
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

    def get_alert_statistics(self) -> dict[str, Any]:
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
            by_severity[severity.value] = len(
                [a for a in alerts if a.severity == severity]
            )

        by_type = {}
        for alert_type in AlertType:
            by_type[alert_type.value] = len(
                [a for a in alerts if a.alert_type == alert_type]
            )

        recent_24h = len(
            [a for a in alerts if a.timestamp >= datetime.now() - timedelta(hours=24)]
        )

        return {
            "total_alerts": total,
            "unresolved_alerts": unresolved,
            "by_severity": by_severity,
            "by_type": by_type,
            "recent_24h": recent_24h,
        }


