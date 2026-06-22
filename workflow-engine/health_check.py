#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Health Check for Devin Orchestrator

Checks the health of all devin-orchestrator components:
- Config file validity
- Skills directory accessibility
- Workflows directory accessibility
- Devin CLI availability
"""

import sys
import subprocess
from pathlib import Path
from typing import List
from dataclasses import dataclass
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from config_loader import ConfigLoader


@dataclass
class HealthCheckResult:
    """Result of a single health check"""
    component: str
    status: str  # "healthy", "warning", "error"
    message: str
    details: dict


class HealthChecker:
    """Health checker for devin-orchestrator components"""
    
    def __init__(self):
        self.results: List[HealthCheckResult] = []
        self.config = None
    
    def check_config_file(self) -> HealthCheckResult:
        """Check config file validity"""
        try:
            config = ConfigLoader.load()
            self.config = config
            
            # Check if config file exists
            config_path = ConfigLoader.DEFAULT_CONFIG_PATH
            if not config_path.exists():
                config_path = ConfigLoader.FALLBACK_CONFIG_PATH
            
            if not config_path.exists():
                return HealthCheckResult(
                    component="config_file",
                    status="error",
                    message="Config file not found",
                    details={
                        "default_path": str(ConfigLoader.DEFAULT_CONFIG_PATH),
                        "fallback_path": str(ConfigLoader.FALLBACK_CONFIG_PATH)
                    }
                )
            
            # Validate config structure
            required_fields = [
                "global_root", "skills_dir", "workflows_dir", 
                "workflow_engine_dir", "devin_cli_path"
            ]
            
            missing_fields = []
            for field in required_fields:
                if not hasattr(config, field):
                    missing_fields.append(field)
            
            if missing_fields:
                return HealthCheckResult(
                    component="config_file",
                    status="error",
                    message=f"Config missing required fields: {', '.join(missing_fields)}",
                    details={
                        "missing_fields": missing_fields,
                        "config_path": str(config_path)
                    }
                )
            
            return HealthCheckResult(
                component="config_file",
                status="healthy",
                message="Config file loaded successfully",
                details={
                    "config_path": str(config_path),
                    "global_root": str(config.global_root),
                    "skills_dir": str(config.skills_dir),
                    "workflows_dir": str(config.workflows_dir),
                    "workflow_engine_dir": str(config.workflow_engine_dir),
                    "devin_cli_path": config.devin_cli_path,
                    "default_model": config.default_model,
                    "default_permission_mode": config.default_permission_mode
                }
            )
            
        except Exception as e:
            return HealthCheckResult(
                component="config_file",
                status="error",
                message=f"Failed to load config: {str(e)}",
                details={"error": str(e)}
            )
    
    def check_skills_directory(self) -> HealthCheckResult:
        """Check skills directory accessibility"""
        if not self.config:
            return HealthCheckResult(
                component="skills_directory",
                status="error",
                message="Config not loaded, cannot check skills directory",
                details={}
            )
        
        skills_dir = self.config.skills_dir
        
        if not skills_dir.exists():
            return HealthCheckResult(
                component="skills_directory",
                status="error",
                message="Skills directory does not exist",
                details={"skills_dir": str(skills_dir)}
            )
        
        if not skills_dir.is_dir():
            return HealthCheckResult(
                component="skills_directory",
                status="error",
                message="Skills path is not a directory",
                details={"skills_dir": str(skills_dir)}
            )
        
        # Check if directory is readable
        try:
            skill_count = len([d for d in skills_dir.iterdir() if d.is_dir()])
        except PermissionError:
            return HealthCheckResult(
                component="skills_directory",
                status="error",
                message="Skills directory is not readable (permission denied)",
                details={"skills_dir": str(skills_dir)}
            )
        
        # Check for at least one skill
        if skill_count == 0:
            return HealthCheckResult(
                component="skills_directory",
                status="warning",
                message="Skills directory is empty",
                details={
                    "skills_dir": str(skills_dir),
                    "skill_count": 0
                }
            )
        
        return HealthCheckResult(
            component="skills_directory",
            status="healthy",
            message=f"Skills directory accessible with {skill_count} skill(s)",
            details={
                "skills_dir": str(skills_dir),
                "skill_count": skill_count
            }
        )
    
    def check_workflows_directory(self) -> HealthCheckResult:
        """Check workflows directory accessibility"""
        if not self.config:
            return HealthCheckResult(
                component="workflows_directory",
                status="error",
                message="Config not loaded, cannot check workflows directory",
                details={}
            )
        
        workflows_dir = self.config.workflows_dir
        
        if not workflows_dir.exists():
            return HealthCheckResult(
                component="workflows_directory",
                status="error",
                message="Workflows directory does not exist",
                details={"workflows_dir": str(workflows_dir)}
            )
        
        if not workflows_dir.is_dir():
            return HealthCheckResult(
                component="workflows_directory",
                status="error",
                message="Workflows path is not a directory",
                details={"workflows_dir": str(workflows_dir)}
            )
        
        # Check if directory is readable
        try:
            workflow_files = list(workflows_dir.glob("*.yaml")) + list(workflows_dir.glob("*.yml"))
        except PermissionError:
            return HealthCheckResult(
                component="workflows_directory",
                status="error",
                message="Workflows directory is not readable (permission denied)",
                details={"workflows_dir": str(workflows_dir)}
            )
        
        # Check for at least one workflow
        if len(workflow_files) == 0:
            return HealthCheckResult(
                component="workflows_directory",
                status="warning",
                message="Workflows directory contains no workflow files",
                details={
                    "workflows_dir": str(workflows_dir),
                    "workflow_count": 0
                }
            )
        
        return HealthCheckResult(
            component="workflows_directory",
            status="healthy",
            message=f"Workflows directory accessible with {len(workflow_files)} workflow file(s)",
            details={
                "workflows_dir": str(workflows_dir),
                "workflow_count": len(workflow_files),
                "workflow_files": [f.name for f in workflow_files]
            }
        )
    
    def check_devin_cli(self) -> HealthCheckResult:
        """Check devin-cli availability"""
        if not self.config:
            return HealthCheckResult(
                component="devin_cli",
                status="error",
                message="Config not loaded, cannot check devin-cli",
                details={}
            )
        
        devin_cli_path = self.config.devin_cli_path
        
        # Check if devin-cli path exists
        cli_path = Path(devin_cli_path)
        if not cli_path.exists():
            return HealthCheckResult(
                component="devin_cli",
                status="error",
                message="Devin CLI executable not found",
                details={"devin_cli_path": devin_cli_path}
            )
        
        if not cli_path.is_file():
            return HealthCheckResult(
                component="devin_cli",
                status="error",
                message="Devin CLI path is not a file",
                details={"devin_cli_path": devin_cli_path}
            )
        
        # Try to run devin-cli --version
        try:
            result = subprocess.run(
                [str(cli_path), "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                version = result.stdout.strip() or "unknown"
                return HealthCheckResult(
                    component="devin_cli",
                    status="healthy",
                    message=f"Devin CLI is accessible (version: {version})",
                    details={
                        "devin_cli_path": devin_cli_path,
                        "version": version
                    }
                )
            else:
                return HealthCheckResult(
                    component="devin_cli",
                    status="warning",
                    message="Devin CLI exists but --version command failed",
                    details={
                        "devin_cli_path": devin_cli_path,
                        "returncode": result.returncode,
                        "stderr": result.stderr
                    }
                )
                
        except subprocess.TimeoutExpired:
            return HealthCheckResult(
                component="devin_cli",
                status="error",
                message="Devin CLI --version command timed out",
                details={"devin_cli_path": devin_cli_path}
            )
        except Exception as e:
            return HealthCheckResult(
                component="devin_cli",
                status="error",
                message=f"Failed to run devin-cli: {str(e)}",
                details={
                    "devin_cli_path": devin_cli_path,
                    "error": str(e)
                }
            )
    
    def run_all_checks(self) -> dict:
        """Run all health checks and return comprehensive report"""
        self.results = []
        
        # Run all checks
        self.results.append(self.check_config_file())
        self.results.append(self.check_skills_directory())
        self.results.append(self.check_workflows_directory())
        self.results.append(self.check_devin_cli())
        
        # Calculate overall status
        error_count = sum(1 for r in self.results if r.status == "error")
        warning_count = sum(1 for r in self.results if r.status == "warning")
        healthy_count = sum(1 for r in self.results if r.status == "healthy")
        
        if error_count > 0:
            overall_status = "error"
        elif warning_count > 0:
            overall_status = "warning"
        else:
            overall_status = "healthy"
        
        return {
            "timestamp": datetime.now().isoformat(),
            "overall_status": overall_status,
            "summary": {
                "total": len(self.results),
                "healthy": healthy_count,
                "warning": warning_count,
                "error": error_count
            },
            "checks": [
                {
                    "component": r.component,
                    "status": r.status,
                    "message": r.message,
                    "details": r.details
                }
                for r in self.results
            ]
        }
    
    def print_report(self, report: dict):
        """Print health check report in a human-readable format"""
        print("=" * 60)
        print("Devin Orchestrator Health Check Report")
        print("=" * 60)
        print(f"Timestamp: {report['timestamp']}")
        print(f"Overall Status: {report['overall_status'].upper()}")
        print()
        
        summary = report['summary']
        print(f"Summary: {summary['healthy']} healthy, {summary['warning']} warnings, {summary['error']} errors")
        print()
        
        for check in report['checks']:
            status_symbol = {
                "healthy": "[OK]",
                "warning": "[WARN]",
                "error": "[FAIL]"
            }.get(check['status'], "[?]")
            
            print(f"{status_symbol} {check['component'].upper()}: {check['status'].upper()}")
            print(f"  {check['message']}")
            
            if check['details']:
                for key, value in check['details'].items():
                    if isinstance(value, list):
                        print(f"  {key}: {', '.join(str(v) for v in value)}")
                    else:
                        print(f"  {key}: {value}")
            print()
        
        print("=" * 60)


def main():
    """Main entry point"""
    checker = HealthChecker()
    report = checker.run_all_checks()
    
    # Print report
    checker.print_report(report)
    
    # Exit with appropriate code
    if report['overall_status'] == "error":
        sys.exit(1)
    elif report['overall_status'] == "warning":
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
