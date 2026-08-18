#!/usr/bin/env python3
"""Shared dataclasses and configuration for the monitoring system."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MonitoringConfig:
    """Configuration for monitoring system"""

    health_check_interval: int = 60  # seconds
    metrics_retention_hours: int = 24
    max_alerts: int = 1000
    enable_continuous_monitoring: bool = True
    performance_thresholds: dict[str, float] = field(
        default_factory=lambda: {
            "stage_duration_warning": 300.0,  # 5 minutes
            "stage_duration_critical": 600.0,  # 10 minutes
            "workflow_duration_warning": 1800.0,  # 30 minutes
            "workflow_duration_critical": 3600.0,  # 1 hour
            "failure_rate_warning": 0.1,  # 10%
            "failure_rate_critical": 0.25,  # 25%
        }
    )
    resource_thresholds: dict[str, float] = field(
        default_factory=lambda: {
            "cpu_warning": 80.0,  # 80%
            "cpu_critical": 90.0,  # 90%
            "memory_warning": 80.0,  # 80%
            "memory_critical": 90.0,  # 90%
            "disk_warning": 80.0,  # 80%
            "disk_critical": 90.0,  # 90%
        }
    )
    # Email notification configuration
    email_enabled: bool = False
    email_smtp_server: str = "smtp.gmail.com"
    email_smtp_port: int = 587
    email_username: str = ""
    email_password: str = ""
    email_from: str = ""
    email_to: list[str] = field(default_factory=list)
    # Webhook notification configuration
    webhook_enabled: bool = False
    webhook_url: str = ""
    webhook_headers: dict[str, str] = field(default_factory=dict)
