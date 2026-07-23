# Monitoring and Observability Guide

This document describes the comprehensive monitoring and observability capabilities of the devin-orchestrator system.

## Overview

The devin-orchestrator includes a robust monitoring system that provides:

- **System Health Monitoring**: Continuous monitoring of system components and resources
- **Workflow Execution Monitoring**: Real-time tracking of workflow performance and success/failure rates
- **Alerting System**: Configurable notifications via email and webhooks for failures and anomalies
- **Resource Monitoring**: CPU, memory, and disk usage tracking with threshold-based alerting
- **Metrics Collection**: Detailed performance metrics for workflows, stages, and skill invocations

## Architecture

The monitoring system consists of several key components:

### 1. MonitoringSystem
The main orchestrator that integrates all monitoring components:
- `SystemHealthMonitor`: Continuous health checks
- `WorkflowExecutionMonitor`: Workflow performance tracking
- `AlertManager`: Alert generation and notification
- Integration with existing `MetricsCollector` and `HealthChecker`

### 2. System Health Monitoring
Monitors the overall health of the orchestration system:
- Configuration file validity
- Skills directory accessibility
- Workflows directory accessibility
- Devin CLI availability
- System resource usage (CPU, memory, disk)

### 3. Workflow Execution Monitoring
Tracks workflow execution metrics:
- Active workflows count
- Success/failure rates
- Workflow duration tracking
- Stage duration tracking
- Skill invocation performance

### 4. Alert Management
Provides comprehensive alerting capabilities:
- Multiple severity levels (INFO, WARNING, ERROR, CRITICAL)
- Various alert types (SYSTEM_HEALTH, WORKFLOW_FAILURE, PERFORMANCE_DEGRADATION, RESOURCE_EXHAUSTION)
- Configurable thresholds for different metrics
- Email notifications
- Webhook notifications

## Configuration

The monitoring system is configured via the `MonitoringConfig` class:

```python
from monitoring import MonitoringConfig, get_monitoring_system

config = MonitoringConfig(
    # Health check interval in seconds
    health_check_interval=60,
    
    # Retention settings
    metrics_retention_hours=24,
    alert_retention_hours=168,  # 7 days
    max_alerts=1000,
    
    # Enable continuous monitoring
    enable_continuous_monitoring=True,
    
    # Performance thresholds
    performance_thresholds={
        'stage_duration_warning': 300.0,      # 5 minutes
        'stage_duration_critical': 600.0,      # 10 minutes
        'workflow_duration_warning': 1800.0,   # 30 minutes
        'workflow_duration_critical': 3600.0,  # 1 hour
        'failure_rate_warning': 0.1,            # 10%
        'failure_rate_critical': 0.25,          # 25%
    },
    
    # Resource thresholds
    resource_thresholds={
        'cpu_warning': 80.0,      # 80%
        'cpu_critical': 90.0,      # 90%
        'memory_warning': 80.0,    # 80%
        'memory_critical': 90.0,    # 90%
        'disk_warning': 80.0,      # 80%
        'disk_critical': 90.0,      # 90%
    },
    
    # Email notification settings
    email_enabled=False,
    email_smtp_server="smtp.gmail.com",
    email_smtp_port=587,
    email_username="your-email@gmail.com",
    email_password="your-app-password",
    email_from="your-email@gmail.com",
    email_to=["admin@example.com"],
    
    # Webhook notification settings
    webhook_enabled=False,
    webhook_url="https://hooks.example.com/alerts",
    webhook_headers={"Authorization": "Bearer your-token"}
)

# Get monitoring system with custom config
monitoring = get_monitoring_system(config)
```

## Usage

### Basic Monitoring

```python
from monitoring import get_monitoring_system

# Get the global monitoring system
monitoring = get_monitoring_system()

# Start monitoring
monitoring.start()

# Get current system health
health = monitoring.get_system_health()
print(f"System status: {health.overall_status}")
print(f"Active workflows: {health.active_workflows}")
print(f"Recent failures: {health.recent_failures}")

# Get resource metrics
if health.resource_metrics:
    print(f"CPU: {health.resource_metrics.cpu_percent}%")
    print(f"Memory: {health.resource_metrics.memory_percent}%")
    print(f"Disk: {health.resource_metrics.disk_percent}%")

# Get alerts
alerts = monitoring.get_alerts(limit=10)
for alert in alerts:
    print(f"[{alert.severity.value}] {alert.title}: {alert.message}")

# Stop monitoring when done
monitoring.stop()
```

### Workflow Monitoring

```python
# The monitoring system automatically tracks workflows
# when they are executed through the orchestration engine

from orchestration_engine import OrchestrationEngine

engine = OrchestrationEngine(work_dir=Path("/path/to/work"))
result = engine.execute_workflow(
    manifest_path=Path("/path/to/manifest.yaml"),
    session_id="session-123",
    request_content="Build a web application"
)

# The monitoring system will automatically:
# 1. Track workflow duration
# 2. Monitor stage performance
# 3. Check for failures
# 4. Generate alerts if thresholds are exceeded
```

### Manual Alert Creation

```python
from monitoring import get_monitoring_system, AlertType, AlertSeverity

monitoring = get_monitoring_system()

# Create a custom alert
alert = monitoring.alert_manager.create_alert(
    alert_type=AlertType.SYSTEM_HEALTH,
    severity=AlertSeverity.WARNING,
    title="Custom Alert",
    message="Something needs attention",
    source="ManualCheck",
    metadata={"custom_field": "value"}
)
```

### Checking Failure Rates

```python
# Check failure rates in the last hour
monitoring.check_failure_rates(time_window_hours=1)

# Check failure rates in the last 24 hours
monitoring.check_failure_rates(time_window_hours=24)
```

### Exporting Monitoring Data

```python
from pathlib import Path

# Export comprehensive monitoring report
monitoring.export_monitoring_data(Path("monitoring_report.json"))

# Get monitoring report as dictionary
report = monitoring.get_monitoring_report()
```

## Alert Types

### SYSTEM_HEALTH
Alerts related to system health issues:
- Configuration file problems
- Directory accessibility issues
- Devin CLI availability
- Overall system status changes

### WORKFLOW_FAILURE
Alerts related to workflow execution failures:
- Workflow completion with failed/escalated/blocked status
- Elevated failure rates across multiple workflows

### PERFORMANCE_DEGRADATION
Alerts related to performance issues:
- Stage duration exceeding thresholds
- Workflow duration exceeding thresholds
- Slow skill invocations

### RESOURCE_EXHAUSTION
Alerts related to system resource usage:
- CPU usage exceeding thresholds
- Memory usage exceeding thresholds
- Disk usage exceeding thresholds

### ANOMALY_DETECTED
Alerts for detected anomalies in system behavior

## Alert Severity Levels

- **INFO**: Informational alerts that don't require immediate action
- **WARNING**: Warning alerts that should be investigated soon
- **ERROR**: Error alerts that require attention
- **CRITICAL**: Critical alerts that require immediate action

## Email Notifications

To enable email notifications:

1. Set `email_enabled=True` in the configuration
2. Configure SMTP server settings:
   ```python
   email_smtp_server="smtp.gmail.com"
   email_smtp_port=587
   email_username="your-email@gmail.com"
   email_password="your-app-password"  # Use app-specific password
   email_from="your-email@gmail.com"
   email_to=["admin@example.com", "team@example.com"]
   ```

For Gmail, you'll need to:
- Enable 2-factor authentication
- Create an app-specific password
- Use the app password in the configuration

## Webhook Notifications

To enable webhook notifications:

1. Set `webhook_enabled=True` in the configuration
2. Configure webhook URL and optional headers:
   ```python
   webhook_url="https://hooks.example.com/alerts"
   webhook_headers={
       "Authorization": "Bearer your-token",
       "X-Custom-Header": "value"
   }
   ```

The webhook will receive a JSON payload with alert details:
```json
{
  "alert_id": "alert-1-1234567890",
  "alert_type": "workflow_failure",
  "severity": "error",
  "title": "Workflow failed",
  "message": "Workflow session-123 completed with status: failed",
  "timestamp": "2024-01-01T12:00:00",
  "source": "WorkflowExecutionMonitor",
  "metadata": {
    "session_id": "session-123",
    "manifest": "my-workflow",
    "status": "failed"
  },
  "resolved": false
}
```

## Monitoring Dashboard

The monitoring system provides comprehensive data that can be used to create dashboards:

### System Health Dashboard
- Overall system status
- Component health status
- Resource usage trends
- Active workflow count
- Recent failure count

### Workflow Performance Dashboard
- Workflow success/failure rates
- Average workflow duration
- Stage performance metrics
- Skill invocation metrics

### Alert Dashboard
- Recent alerts
- Alert statistics by severity
- Alert statistics by type
- Unresolved alerts

## Best Practices

1. **Configure Appropriate Thresholds**: Set thresholds based on your system's normal operating parameters
2. **Enable Notifications**: Configure email or webhook notifications for critical alerts
3. **Regular Review**: Review monitoring reports regularly to identify trends
4. **Export Data**: Export monitoring data periodically for long-term analysis
5. **Integrate with Existing Tools**: Use webhooks to integrate with your existing monitoring infrastructure (PagerDuty, Slack, etc.)

## Troubleshooting

### Monitoring Not Starting
- Ensure the monitoring system is properly initialized
- Check that `enable_continuous_monitoring` is set to `True`
- Verify that the health check interval is reasonable

### Alerts Not Being Sent
- Verify email/webhook configuration
- Check SMTP server accessibility for email notifications
- Verify webhook URL is accessible and returns 2xx status
- Check logs for notification errors

### Resource Metrics Not Available
- Ensure `psutil` is installed (`pip install psutil`)
- Check that the system has sufficient permissions to read resource metrics
- Verify disk path is correct (default is `/`)

## API Reference

### MonitoringSystem
- `start()`: Start the monitoring system
- `stop()`: Stop the monitoring system
- `get_system_health()`: Get current system health snapshot
- `get_health_history(limit)`: Get health history
- `get_alerts(severity, alert_type, resolved, since, limit)`: Get alerts with filtering
- `get_alert_statistics()`: Get alert statistics
- `resolve_alert(alert_id)`: Mark an alert as resolved
- `monitor_workflow(session_id)`: Monitor a completed workflow
- `check_failure_rates(time_window_hours)`: Check workflow failure rates
- `get_monitoring_report()`: Get comprehensive monitoring report
- `export_monitoring_data(output_path)`: Export monitoring data to JSON

### MonitoringConfig
Configuration parameters for the monitoring system. See the Configuration section above for details.

## Dependencies

The monitoring system requires the following additional dependencies:
- `psutil`: For system resource monitoring
- `requests`: For webhook notifications

Install them with:
```bash
pip install psutil requests
```

## Integration with Orchestration Engine

The monitoring system is automatically integrated with the orchestration engine:

```python
from orchestration_engine import OrchestrationEngine

# The monitoring system is automatically initialized
# and will track all workflow executions
engine = OrchestrationEngine(work_dir=Path("/path/to/work"))

# Workflows are automatically monitored
result = engine.execute_workflow(...)
```

The orchestration engine:
1. Starts the monitoring system on initialization
2. Tracks workflow execution metrics
3. Monitors workflow completion
4. Generates alerts for failures and performance issues
5. Exports metrics to session directories

## Security Considerations

- **Email Credentials**: Store email credentials securely (environment variables, secret management)
- **Webhook URLs**: Use HTTPS for webhook URLs
- **Webhook Authentication**: Include authentication headers in webhook configuration
- **Alert Data**: Be mindful of sensitive data in alert metadata
- **Access Control**: Implement appropriate access controls for monitoring data

## Performance Impact

The monitoring system is designed to have minimal performance impact:
- Health checks run at configurable intervals (default: 60 seconds)
- Resource monitoring uses efficient system calls
- Alert generation is asynchronous
- Metrics collection has minimal overhead

For high-throughput systems, consider:
- Increasing health check intervals
- Adjusting retention periods
- Filtering alerts to reduce notification volume

## Future Enhancements

Planned enhancements to the monitoring system:
- Integration with Prometheus/Grafana
- Machine learning-based anomaly detection
- Custom alert rules and conditions
- Alert aggregation and deduplication
- Historical trend analysis
- Predictive alerting
