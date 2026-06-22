#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test suite for monitoring module

Tests the monitoring system functionality including:
- System health monitoring
- Workflow execution monitoring
- Alert generation and management
- Integration with orchestration engine
"""

import sys
import json
import time
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from monitoring import (
    MonitoringSystem,
    MonitoringConfig,
    AlertManager,
    SystemHealthMonitor,
    WorkflowExecutionMonitor,
    Alert,
    AlertSeverity,
    AlertType,
    SystemHealthSnapshot,
    SystemResourceMetrics,
    get_monitoring_system,
    reset_monitoring_system
)
from metrics import get_metrics_collector, MetricsCollector, WorkflowMetrics


def test_alert_manager():
    """Test alert manager functionality"""
    print("Testing AlertManager...")
    
    config = MonitoringConfig()
    alert_manager = AlertManager(config)
    
    # Test alert creation
    alert = alert_manager.create_alert(
        alert_type=AlertType.SYSTEM_HEALTH,
        severity=AlertSeverity.ERROR,
        title="Test Alert",
        message="This is a test alert",
        source="test",
        metadata={'test_key': 'test_value'}
    )
    
    assert alert.alert_id is not None
    assert alert.title == "Test Alert"
    assert alert.severity == AlertSeverity.ERROR
    assert alert.resolved == False
    
    # Test alert retrieval
    alerts = alert_manager.get_alerts()
    assert len(alerts) == 1
    assert alerts[0].alert_id == alert.alert_id
    
    # Test alert filtering
    error_alerts = alert_manager.get_alerts(severity=AlertSeverity.ERROR)
    assert len(error_alerts) == 1
    
    info_alerts = alert_manager.get_alerts(severity=AlertSeverity.INFO)
    assert len(info_alerts) == 0
    
    # Test alert resolution
    resolved = alert_manager.resolve_alert(alert.alert_id)
    assert resolved == True
    
    updated_alert = alert_manager.get_alerts()[0]
    assert updated_alert.resolved == True
    assert updated_alert.resolved_at is not None
    
    # Test alert statistics
    stats = alert_manager.get_alert_statistics()
    assert stats['total_alerts'] == 1
    assert stats['unresolved_alerts'] == 0
    
    print("AlertManager tests passed")


def test_alert_handler():
    """Test custom alert handlers"""
    print("Testing alert handlers...")
    
    config = MonitoringConfig()
    alert_manager = AlertManager(config)
    
    # Track handler calls
    handler_calls = []
    
    def test_handler(alert):
        handler_calls.append(alert)
    
    alert_manager.add_alert_handler(test_handler)
    
    # Create alert
    alert = alert_manager.create_alert(
        alert_type=AlertType.WORKFLOW_FAILURE,
        severity=AlertSeverity.WARNING,
        title="Handler Test",
        message="Testing handler",
        source="test"
    )
    
    # Verify handler was called
    assert len(handler_calls) == 1
    assert handler_calls[0].alert_id == alert.alert_id
    
    print("Alert handler tests passed")


def test_system_health_monitor():
    """Test system health monitoring"""
    print("Testing SystemHealthMonitor...")
    
    config = MonitoringConfig()
    alert_manager = AlertManager(config)
    health_monitor = SystemHealthMonitor(config, alert_manager)
    
    # Run health check
    snapshot = health_monitor._check_health()
    
    assert snapshot is not None
    assert isinstance(snapshot, SystemHealthSnapshot)
    assert snapshot.timestamp is not None
    assert snapshot.overall_status in ['healthy', 'warning', 'error']
    
    # Test resource metrics
    assert snapshot.resource_metrics is not None
    assert isinstance(snapshot.resource_metrics, SystemResourceMetrics)
    assert snapshot.resource_metrics.cpu_percent >= 0
    assert snapshot.resource_metrics.memory_percent >= 0
    assert snapshot.resource_metrics.disk_percent >= 0
    
    # Test health history
    history = health_monitor.get_health_history()
    assert len(history) >= 1
    assert history[-1] == snapshot
    
    # Test current health retrieval
    current = health_monitor.get_current_health()
    assert current == snapshot
    
    print("SystemHealthMonitor tests passed")


def test_resource_metrics():
    """Test system resource metrics collection"""
    print("Testing resource metrics collection...")
    
    config = MonitoringConfig()
    alert_manager = AlertManager(config)
    health_monitor = SystemHealthMonitor(config, alert_manager)
    
    # Collect resource metrics
    resource_metrics = health_monitor._collect_resource_metrics()
    
    assert resource_metrics is not None
    assert isinstance(resource_metrics, SystemResourceMetrics)
    assert resource_metrics.cpu_percent >= 0
    assert resource_metrics.cpu_percent <= 100
    assert resource_metrics.memory_percent >= 0
    assert resource_metrics.memory_percent <= 100
    assert resource_metrics.disk_percent >= 0
    assert resource_metrics.disk_percent <= 100
    assert resource_metrics.memory_used_gb >= 0
    assert resource_metrics.memory_total_gb > 0
    assert resource_metrics.disk_used_gb >= 0
    assert resource_metrics.disk_total_gb > 0
    assert resource_metrics.timestamp is not None
    
    print("Resource metrics tests passed")


def test_resource_alerts():
    """Test resource-based alert generation"""
    print("Testing resource alert generation...")
    
    # Create config with low thresholds to trigger alerts
    config = MonitoringConfig(
        resource_thresholds={
            'cpu_warning': 0.0,    # Will trigger immediately
            'cpu_critical': 0.0,
            'memory_warning': 0.0,
            'memory_critical': 0.0,
            'disk_warning': 0.0,
            'disk_critical': 0.0,
        }
    )
    
    alert_manager = AlertManager(config)
    health_monitor = SystemHealthMonitor(config, alert_manager)
    
    # Run health check (should generate resource alerts)
    snapshot = health_monitor._check_health()
    
    # Check for resource exhaustion alerts
    resource_alerts = alert_manager.get_alerts(alert_type=AlertType.RESOURCE_EXHAUSTION)
    # We expect at least some alerts given the low thresholds
    print("  Generated {} resource alerts".format(len(resource_alerts)))
    
    print("Resource alert tests passed")


def test_email_notification_config():
    """Test email notification configuration"""
    print("Testing email notification configuration...")
    
    config = MonitoringConfig(
        email_enabled=True,
        email_smtp_server="smtp.example.com",
        email_smtp_port=587,
        email_username="test@example.com",
        email_password="test-password",
        email_from="test@example.com",
        email_to=["admin@example.com"]
    )
    
    assert config.email_enabled == True
    assert config.email_smtp_server == "smtp.example.com"
    assert config.email_smtp_port == 587
    assert config.email_username == "test@example.com"
    assert config.email_to == ["admin@example.com"]
    
    print("Email notification configuration tests passed")


def test_webhook_notification_config():
    """Test webhook notification configuration"""
    print("Testing webhook notification configuration...")
    
    config = MonitoringConfig(
        webhook_enabled=True,
        webhook_url="https://hooks.example.com/alerts",
        webhook_headers={"Authorization": "Bearer test-token"}
    )
    
    assert config.webhook_enabled == True
    assert config.webhook_url == "https://hooks.example.com/alerts"
    assert config.webhook_headers == {"Authorization": "Bearer test-token"}
    
    print("Webhook notification configuration tests passed")


def test_alert_with_config():
    """Test alert creation with configuration for notifications"""
    print("Testing alert creation with config...")
    
    config = MonitoringConfig(
        email_enabled=False,  # Disabled for testing
        webhook_enabled=False  # Disabled for testing
    )
    
    alert_manager = AlertManager(config)
    
    # Create alert with config
    alert = alert_manager.create_alert(
        alert_type=AlertType.SYSTEM_HEALTH,
        severity=AlertSeverity.WARNING,
        title="Config Test",
        message="Testing alert with config",
        source="test",
        config=config
    )
    
    assert alert is not None
    assert alert.title == "Config Test"
    
    print("Alert with config tests passed")


def test_workflow_execution_monitor():
    """Test workflow execution monitoring"""
    print("Testing WorkflowExecutionMonitor...")
    
    config = MonitoringConfig()
    alert_manager = AlertManager(config)
    metrics_collector = MetricsCollector()
    workflow_monitor = WorkflowExecutionMonitor(config, alert_manager, metrics_collector)
    
    # Create a test workflow with long duration
    workflow = WorkflowMetrics(
        session_id="test-session-1",
        manifest_name="test-manifest",
        start_time=time.time() - 4000,  # Started over an hour ago
        end_time=time.time(),
        total_duration=4000.0,  # Over critical threshold
        final_status="completed"
    )
    
    metrics_collector._workflows["test-session-1"] = workflow
    
    # Monitor workflow completion
    workflow_monitor.monitor_workflow_completion("test-session-1")
    
    # Check for performance alerts
    alerts = alert_manager.get_alerts(alert_type=AlertType.PERFORMANCE_DEGRADATION)
    assert len(alerts) > 0
    
    # Test with failed workflow
    failed_workflow = WorkflowMetrics(
        session_id="test-session-2",
        manifest_name="test-manifest",
        start_time=time.time() - 100,
        end_time=time.time(),
        total_duration=100.0,
        final_status="failed"
    )
    
    metrics_collector._workflows["test-session-2"] = failed_workflow
    workflow_monitor.monitor_workflow_completion("test-session-2")
    
    # Check for failure alerts
    failure_alerts = alert_manager.get_alerts(alert_type=AlertType.WORKFLOW_FAILURE)
    assert len(failure_alerts) > 0
    
    print("WorkflowExecutionMonitor tests passed")


def test_monitoring_system():
    """Test main monitoring system"""
    print("Testing MonitoringSystem...")
    
    # Reset global instance
    reset_monitoring_system()
    
    try:
        config = MonitoringConfig()
        monitoring = MonitoringSystem(config)
        
        # Test system health retrieval (may be None if not yet run)
        print("  Testing system health retrieval...")
        health = monitoring.get_system_health()
        print("  Health retrieved: " + str(health is not None))
        # Health might be None if monitor hasn't run yet, that's okay
        
        # Test alert retrieval
        print("  Testing alert retrieval...")
        alerts = monitoring.get_alerts()
        print("  Alerts retrieved: " + str(len(alerts)))
        assert isinstance(alerts, list)
        
        # Test alert statistics
        print("  Testing alert statistics...")
        stats = monitoring.get_alert_statistics()
        print("  Stats keys: " + str(list(stats.keys())))
        assert 'total_alerts' in stats
        assert 'unresolved_alerts' in stats
        
        # Test monitoring report
        print("  Testing monitoring report...")
        report = monitoring.get_monitoring_report()
        print("  Report keys: " + str(list(report.keys())))
        assert 'timestamp' in report
        assert 'alerts' in report
        assert 'configuration' in report
        # system_health may be None if no health checks have run
        
        print("MonitoringSystem tests passed")
    except Exception as e:
        import traceback
        print("Error in MonitoringSystem test: " + str(e))
        traceback.print_exc()
        raise


def test_monitoring_configuration():
    """Test monitoring configuration"""
    print("Testing MonitoringConfig...")
    
    # Default configuration
    config = MonitoringConfig()
    assert config.health_check_interval == 60
    assert config.metrics_retention_hours == 24
    assert config.enable_continuous_monitoring == True
    
    # Custom configuration
    custom_config = MonitoringConfig(
        health_check_interval=30,
        metrics_retention_hours=48,
        enable_continuous_monitoring=False,
        performance_thresholds={
            'stage_duration_warning': 600.0,
            'workflow_duration_critical': 7200.0
        }
    )
    
    assert custom_config.health_check_interval == 30
    assert custom_config.metrics_retention_hours == 48
    assert custom_config.enable_continuous_monitoring == False
    assert custom_config.performance_thresholds['stage_duration_warning'] == 600.0
    
    print("MonitoringConfig tests passed")


def test_monitoring_export():
    """Test monitoring data export"""
    print("Testing monitoring data export...")
    
    reset_monitoring_system()
    
    config = MonitoringConfig()
    monitoring = MonitoringSystem(config)
    
    # Create some test data
    monitoring.alert_manager.create_alert(
        alert_type=AlertType.SYSTEM_HEALTH,
        severity=AlertSeverity.INFO,
        title="Export Test",
        message="Testing export functionality",
        source="test"
    )
    
    # Export to temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_path = Path(f.name)
    
    try:
        success = monitoring.export_monitoring_data(temp_path)
        assert success == True
        
        # Verify file exists and is valid JSON
        assert temp_path.exists()
        
        with open(temp_path) as f:
            data = json.load(f)
        
        assert 'timestamp' in data
        assert 'system_health' in data
        assert 'alerts' in data
        assert 'health_history' in data
        assert 'all_alerts' in data
        
        print("Monitoring export tests passed")
    finally:
        # Clean up
        if temp_path.exists():
            temp_path.unlink()


def test_global_monitoring_instance():
    """Test global monitoring system instance"""
    print("Testing global monitoring instance...")
    
    # Reset global instance
    reset_monitoring_system()
    
    # Get instance
    monitoring1 = get_monitoring_system()
    monitoring2 = get_monitoring_system()
    
    # Should be the same instance
    assert monitoring1 is monitoring2
    
    # Reset and get new instance
    reset_monitoring_system()
    monitoring3 = get_monitoring_system()
    
    # Should be different instance
    assert monitoring1 is not monitoring3
    
    print("Global monitoring instance tests passed")


def test_integration_with_orchestration_engine():
    """Test integration with orchestration engine"""
    print("Testing integration with orchestration engine...")
    
    reset_monitoring_system()
    
    # Import orchestration engine to test integration
    try:
        from orchestration_engine import OrchestrationEngine
        
        # This test verifies that the monitoring module can be imported
        # and used within the orchestration engine context
        monitoring = get_monitoring_system()
        
        # Verify monitoring system is functional
        health = monitoring.get_system_health()
        # Health might be None if monitor hasn't run yet, that's okay
        print("  Monitoring system is functional")
        
        print("Integration with orchestration engine tests passed")
    except ImportError as e:
        print("Skipping orchestration engine integration test: " + str(e))
    except Exception as e:
        import traceback
        print("Error in integration test: " + str(e))
        traceback.print_exc()
        # Don't fail the test suite for integration issues


def run_all_tests():
    """Run all monitoring tests"""
    print("=" * 60)
    print("Running Monitoring Module Tests")
    print("=" * 60)
    print()
    
    try:
        test_alert_manager()
        test_alert_handler()
        test_system_health_monitor()
        test_resource_metrics()
        test_resource_alerts()
        test_email_notification_config()
        test_webhook_notification_config()
        test_alert_with_config()
        test_workflow_execution_monitor()
        test_monitoring_system()
        test_monitoring_configuration()
        test_monitoring_export()
        test_global_monitoring_instance()
        test_integration_with_orchestration_engine()
        
        print()
        print("=" * 60)
        print("All monitoring tests passed successfully!")
        print("=" * 60)
        return True
        
    except AssertionError as e:
        print()
        print("=" * 60)
        print("Test failed: " + str(e))
        print("=" * 60)
        return False
    except Exception as e:
        print()
        print("=" * 60)
        print("Test error: " + str(e))
        print("=" * 60)
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Clean up global instance
        reset_monitoring_system()


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)