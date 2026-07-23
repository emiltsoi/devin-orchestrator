# Monitoring Dashboard Documentation

## Overview

The devin-orchestrator monitoring system provides comprehensive observability for workflow execution, system health, and performance metrics. This guide explains how to use the monitoring dashboard and interpret the data it provides.

## Architecture

The monitoring system consists of three main components:

1. **System Health Monitor** - Continuous health checks of system components
2. **Workflow Execution Monitor** - Real-time monitoring of workflow performance and failures
3. **Alert Manager** - Centralized alert generation and management

## Quick Start

### Basic Usage

```python
from monitoring import get_monitoring_system

# Get the monitoring system instance
monitoring = get_monitoring_system()

# Start monitoring (enables continuous health checks)
monitoring.start()

# Get current system health
health = monitoring.get_system_health()
print(f"System status: {health.overall_status}")

# Get recent alerts
alerts = monitoring.get_alerts(limit=10)
for alert in alerts:
    print(f"[{alert.severity.value}] {alert.title}: {alert.message}")

# Get comprehensive monitoring report
report = monitoring.get_monitoring_report()
print(json.dumps(report, indent=2))

# Stop monitoring when done
monitoring.stop()
```

### Integration with Orchestration Engine

The monitoring system is automatically integrated with the orchestration engine. When you execute workflows, they are automatically monitored for:

- Completion status (success, failure, escalation)
- Performance thresholds (duration limits)
- Failure rates across multiple workflows

## System Health Monitoring

### Health Checks

The system continuously monitors the following components:

- **Config File** - Validates configuration file existence and structure
- **Skills Directory** - Checks accessibility and skill availability
- **Workflows Directory** - Validates workflow file accessibility
- **Devin CLI** - Verifies Devin CLI availability and version

### Health Status Levels

- **healthy** - All components functioning normally
- **warning** - Non-critical issues detected (e.g., empty directories)
- **error** - Critical issues requiring attention

### Health Metrics

```python
health = monitoring.get_system_health()

print(f"Overall Status: {health.overall_status}")
print(f"Active Workflows: {health.active_workflows}")
print(f"Recent Failures: {health.recent_failures}")
print(f"Component Status: {health.component_status}")
print(f"Performance Metrics: {health.performance_metrics}")
```

### Health History

Access historical health data to identify trends:

```python
# Get last 100 health snapshots
history = monitoring.get_health_history(limit=100)

for snapshot in history:
    print(f"{snapshot.timestamp}: {snapshot.overall_status}")
```

## Workflow Execution Monitoring

### Monitored Metrics

The system tracks the following workflow metrics:

- **Workflow Duration** - Total execution time
- **Stage Duration** - Individual stage execution times
- **Skill Invocation Duration** - Time spent in skill calls
- **Retry Counts** - Number of retry attempts per stage
- **Final Status** - Workflow completion status

### Performance Thresholds

Default performance thresholds (configurable):

```python
# Duration thresholds (in seconds)
stage_duration_warning: 300.0      # 5 minutes
stage_duration_critical: 600.0     # 10 minutes
workflow_duration_warning: 1800.0 # 30 minutes
workflow_duration_critical: 3600.0 # 1 hour

# Failure rate thresholds (as percentage)
failure_rate_warning: 0.1         # 10%
failure_rate_critical: 0.25       # 25%
```

### Monitoring Workflow Completion

Workflows are automatically monitored when they complete. The system checks:

1. **Duration Thresholds** - Alerts if workflow/stage exceeded time limits
2. **Failure Status** - Alerts for failed, escalated, or blocked workflows
3. **Performance Anomalies** - Detects unusual performance patterns

### Failure Rate Monitoring

Check failure rates across multiple workflows:

```python
# Check failure rates in the last hour
monitoring.check_failure_rates(time_window_hours=1)

# Check failure rates in the last 24 hours
monitoring.check_failure_rates(time_window_hours=24)
```

## Alerting System

### Alert Types

- **system_health** - System component health issues
- **workflow_failure** - Workflow execution failures
- **performance_degradation** - Performance threshold violations
- **resource_exhaustion** - Resource limit warnings
- **anomaly_detected** - Unusual patterns detected

### Alert Severity Levels

- **info** - Informational alerts
- **warning** - Warning-level issues
- **error** - Error-level issues requiring attention
- **critical** - Critical issues requiring immediate action

### Alert Management

```python
# Get all alerts
all_alerts = monitoring.get_alerts()

# Filter by severity
error_alerts = monitoring.get_alerts(severity=AlertSeverity.ERROR)

# Filter by type
health_alerts = monitoring.get_alerts(alert_type=AlertType.SYSTEM_HEALTH)

# Filter by resolution status
unresolved_alerts = monitoring.get_alerts(resolved=False)

# Get alerts from the last 24 hours
from datetime import datetime, timedelta
since = datetime.now() - timedelta(hours=24)
recent_alerts = monitoring.get_alerts(since=since)

# Resolve an alert
monitoring.resolve_alert("alert-123-1712345678")
```

### Alert Statistics

```python
stats = monitoring.get_alert_statistics()

print(f"Total Alerts: {stats['total_alerts']}")
print(f"Unresolved: {stats['unresolved_alerts']}")
print(f"By Severity: {stats['by_severity']}")
print(f"By Type: {stats['by_type']}")
print(f"Recent 24h: {stats['recent_24h']}")
```

### Custom Alert Handlers

Add custom alert handlers for notifications:

```python
def slack_alert_handler(alert):
    """Send alerts to Slack"""
    if alert.severity in [AlertSeverity.ERROR, AlertSeverity.CRITICAL]:
        # Send to Slack webhook
        send_slack_message(f"[{alert.severity.value}] {alert.title}: {alert.message}")

def email_alert_handler(alert):
    """Send critical alerts via email"""
    if alert.severity == AlertSeverity.CRITICAL:
        send_email_alert(alert.title, alert.message)

# Add custom handlers
monitoring.alert_manager.add_alert_handler(slack_alert_handler)
monitoring.alert_manager.add_alert_handler(email_alert_handler)
```

## Monitoring Report

### Comprehensive Report

Get a comprehensive monitoring report:

```python
report = monitoring.get_monitoring_report()

print(f"Timestamp: {report['timestamp']}")
print(f"System Health: {report['system_health']}")
print(f"Alert Statistics: {report['alerts']['statistics']}")
print(f"Recent Alerts: {report['alerts']['recent']}")
print(f"Configuration: {report['configuration']}")
```

### Export Monitoring Data

Export monitoring data to JSON for analysis or dashboard visualization:

```python
from pathlib import Path

# Export to file
output_path = Path("monitoring_data.json")
success = monitoring.export_monitoring_data(output_path)

if success:
    print(f"Monitoring data exported to {output_path}")
```

The exported data includes:
- Current system health status
- Health history snapshots
- All alerts with metadata
- Configuration settings
- Performance metrics

## Configuration

### Monitoring Configuration

Customize monitoring behavior:

```python
from monitoring import MonitoringSystem, MonitoringConfig

config = MonitoringConfig(
    health_check_interval=30,  # Check health every 30 seconds
    metrics_retention_hours=48,  # Keep metrics for 48 hours
    alert_retention_hours=168,  # Keep alerts for 7 days
    max_alerts=2000,  # Store up to 2000 alerts
    enable_continuous_monitoring=True,
    performance_thresholds={
        'stage_duration_warning': 600.0,  # 10 minutes
        'stage_duration_critical': 1200.0,  # 20 minutes
        'workflow_duration_warning': 3600.0,  # 1 hour
        'workflow_duration_critical': 7200.0,  # 2 hours
        'failure_rate_warning': 0.15,  # 15%
        'failure_rate_critical': 0.30,  # 30%
    }
)

monitoring = MonitoringSystem(config)
```

### Environment Variables

Configure monitoring via environment variables:

```bash
# Health check interval (seconds)
export MONITORING_HEALTH_CHECK_INTERVAL=60

# Metrics retention (hours)
export MONITORING_METRICS_RETENTION_HOURS=24

# Alert retention (hours)
export MONITORING_ALERT_RETENTION_HOURS=168

# Maximum alerts to store
export MONITORING_MAX_ALERTS=1000

# Enable continuous monitoring
export MONITORING_ENABLE_CONTINUOUS=true
```

## Dashboard Integration

### Grafana Dashboard

To create a Grafana dashboard:

1. **Set up data source** - Configure JSON data source pointing to exported monitoring data
2. **Create panels**:
   - System health gauge
   - Active workflows count
   - Recent failures trend
   - Alert severity distribution
   - Workflow duration histogram
   - Failure rate over time

### Example Panel Queries

**System Health Status:**
```json
{
  "query": "data.system_health.overall_status",
  "type": "stat"
}
```

**Active Workflows:**
```json
{
  "query": "data.system_health.active_workflows",
  "type": "graph"
}
```

**Alert Count by Severity:**
```json
{
  "query": "data.alerts.statistics.by_severity",
  "type": "piechart"
}
```

**Health History Timeline:**
```json
{
  "query": "data.health_history[*].{timestamp: timestamp, status: overall_status}",
  "type": "timeseries"
}
```

## Troubleshooting

### Common Issues

**Monitoring not starting:**
- Check if continuous monitoring is enabled in configuration
- Verify health check interval is reasonable (≥ 10 seconds)
- Check logs for initialization errors

**Missing alerts:**
- Verify alert handlers are registered
- Check alert retention period (alerts may have been purged)
- Review alert severity filtering

**Health checks failing:**
- Run health check manually: `python health_check.py`
- Verify configuration file exists and is valid
- Check directory permissions for skills/workflows

**Performance threshold alerts not firing:**
- Verify thresholds are configured appropriately
- Check if workflow metrics are being collected
- Review alert severity filtering

### Debug Mode

Enable debug logging for troubleshooting:

```python
from orchestration_logger import get_logger, LogLevel

logger = get_logger(log_level=LogLevel.DEBUG)
```

## Best Practices

1. **Start monitoring early** - Initialize monitoring system when your application starts
2. **Configure appropriate thresholds** - Adjust thresholds based on your workflow characteristics
3. **Set up alert handlers** - Configure notifications for critical alerts
4. **Review alerts regularly** - Check and resolve alerts to prevent alert fatigue
5. **Export data regularly** - Export monitoring data for long-term analysis
6. **Monitor trends** - Use health history to identify degradation patterns
7. **Test alert handlers** - Verify custom alert handlers work correctly
8. **Adjust retention periods** - Balance storage needs with analysis requirements

## API Reference

### MonitoringSystem

Main monitoring system class.

#### Methods

- `start()` - Start continuous monitoring
- `stop()` - Stop continuous monitoring
- `get_system_health()` - Get current health snapshot
- `get_health_history(limit=100)` - Get health history
- `get_alerts(...)` - Get alerts with filtering
- `get_alert_statistics()` - Get alert statistics
- `resolve_alert(alert_id)` - Resolve an alert
- `monitor_workflow(session_id)` - Monitor workflow completion
- `check_failure_rates(time_window_hours=1)` - Check failure rates
- `get_monitoring_report()` - Get comprehensive report
- `export_monitoring_data(output_path)` - Export data to JSON

### AlertManager

Manages alert generation and storage.

#### Methods

- `create_alert(...)` - Create a new alert
- `get_alerts(...)` - Get alerts with filtering
- `resolve_alert(alert_id)` - Resolve an alert
- `get_alert_statistics()` - Get alert statistics
- `add_alert_handler(handler)` - Add custom alert handler

### SystemHealthMonitor

Continuous system health monitoring.

#### Methods

- `start()` - Start health monitoring
- `stop()` - Stop health monitoring
- `get_current_health()` - Get current health snapshot
- `get_health_history(limit=100)` - Get health history

### WorkflowExecutionMonitor

Workflow execution monitoring and anomaly detection.

#### Methods

- `monitor_workflow_completion(session_id)` - Monitor workflow completion
- `check_failure_rates(time_window_hours=1)` - Check failure rates

## Examples

### Example 1: Basic Monitoring Setup

```python
from monitoring import get_monitoring_system

# Initialize and start monitoring
monitoring = get_monitoring_system()
monitoring.start()

# Check system health
health = monitoring.get_system_health()
if health.overall_status != 'healthy':
    print(f"Warning: System health is {health.overall_status}")

# Check for critical alerts
critical_alerts = monitoring.get_alerts(
    severity=AlertSeverity.CRITICAL,
    resolved=False
)
if critical_alerts:
    print(f"Found {len(critical_alerts)} critical alerts")
    for alert in critical_alerts:
        print(f"  - {alert.title}: {alert.message}")

# Stop monitoring when done
monitoring.stop()
```

### Example 2: Custom Alert Handler

```python
import requests
from monitoring import get_monitoring_system, AlertSeverity

def webhook_alert_handler(alert):
    """Send alerts to webhook endpoint"""
    if alert.severity in [AlertSeverity.ERROR, AlertSeverity.CRITICAL]:
        payload = {
            'alert_id': alert.alert_id,
            'severity': alert.severity.value,
            'title': alert.title,
            'message': alert.message,
            'timestamp': alert.timestamp.isoformat(),
            'metadata': alert.metadata
        }
        
        try:
            response = requests.post(
                'https://your-webhook-url.com/alerts',
                json=payload,
                timeout=10
            )
            response.raise_for_status()
        except Exception as e:
            print(f"Failed to send webhook alert: {e}")

# Set up monitoring with custom handler
monitoring = get_monitoring_system()
monitoring.alert_manager.add_alert_handler(webhook_alert_handler)
monitoring.start()
```

### Example 3: Periodic Health Checks

```python
import time
from monitoring import get_monitoring_system

def periodic_health_check(interval_minutes=5):
    """Run periodic health checks and report status"""
    monitoring = get_monitoring_system()
    monitoring.start()
    
    try:
        while True:
            health = monitoring.get_system_health()
            print(f"\n=== Health Check at {health.timestamp} ===")
            print(f"Status: {health.overall_status}")
            print(f"Active Workflows: {health.active_workflows}")
            print(f"Recent Failures: {health.recent_failures}")
            
            # Check for new alerts
            recent_alerts = monitoring.get_alerts(limit=5, resolved=False)
            if recent_alerts:
                print(f"\nRecent Alerts ({len(recent_alerts)}):")
                for alert in recent_alerts:
                    print(f"  [{alert.severity.value}] {alert.title}")
            
            time.sleep(interval_minutes * 60)
    
    except KeyboardInterrupt:
        print("\nStopping periodic health checks")
        monitoring.stop()

if __name__ == "__main__":
    periodic_health_check(interval_minutes=5)
```

### Example 4: Export and Analyze Monitoring Data

```python
import json
from pathlib import Path
from datetime import datetime, timedelta
from monitoring import get_monitoring_system

def analyze_monitoring_data():
    """Export and analyze monitoring data"""
    monitoring = get_monitoring_system()
    
    # Export current monitoring data
    output_path = Path(f"monitoring_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    monitoring.export_monitoring_data(output_path)
    
    # Load and analyze
    with open(output_path) as f:
        data = json.load(f)
    
    print("=== Monitoring Data Analysis ===")
    
    # System health analysis
    if data['system_health']:
        health = data['system_health']
        print(f"\nSystem Health: {health['overall_status']}")
        print(f"Active Workflows: {health['active_workflows']}")
        print(f"Recent Failures: {health['recent_failures']}")
    
    # Alert analysis
    alert_stats = data['alerts']['statistics']
    print(f"\nAlert Statistics:")
    print(f"Total: {alert_stats['total_alerts']}")
    print(f"Unresolved: {alert_stats['unresolved_alerts']}")
    print(f"By Severity: {alert_stats['by_severity']}")
    
    # Health history analysis
    if data['health_history']:
        print(f"\nHealth History ({len(data['health_history'])} snapshots):")
        
        # Count status occurrences
        status_counts = {}
        for snapshot in data['health_history']:
            status = snapshot['overall_status']
            status_counts[status] = status_counts.get(status, 0) + 1
        
        print("Status Distribution:")
        for status, count in status_counts.items():
            print(f"  {status}: {count}")
    
    print(f"\nData exported to: {output_path}")

if __name__ == "__main__":
    analyze_monitoring_data()
```

## Support

For issues or questions about the monitoring system:

1. Check this documentation for common solutions
2. Review the monitoring module source code
3. Check application logs for detailed error messages
4. Run health checks manually to identify system issues

## Future Enhancements

Planned improvements to the monitoring system:

- [ ] Web-based dashboard UI
- [ ] Real-time WebSocket streaming of metrics
- [ ] Integration with Prometheus/Grafana
- [ ] Machine learning-based anomaly detection
- [ ] Custom alert rule builder
- [ ] Alert escalation policies
- [ ] Integration with incident management systems
- [ ] Performance trend analysis and forecasting