#!/usr/bin/env python3
"""
Backup script for devin-orchestrator
Creates timestamped backups of sessions, configurations, and logs
"""

import os
import shutil
import argparse
import datetime
import json
import sys
from pathlib import Path
import subprocess
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BackupManager:
    def __init__(self, project_root=None, backup_destination=None):
        """Initialize backup manager with paths"""
        if project_root is None:
            self.project_root = Path.cwd()
        else:
            self.project_root = Path(project_root)
        
        if backup_destination is None:
            self.backup_destination = self.project_root / "backups"
        else:
            self.backup_destination = Path(backup_destination)
        
        # Define paths to backup
        self.session_paths = [
            self.project_root / "work",
            Path.home() / ".devin-orchestrator" / "work"
        ]
        
        self.config_paths = [
            self.project_root / "config.yaml",
            self.project_root / ".devin",
            self.project_root / "skills",
            self.project_root / "workflows",
            self.project_root / "adapters",
            self.project_root / "contracts",
            Path.home() / ".devin-orchestrator" / "config.yaml",
            Path.home() / ".devin-orchestrator" / "skills",
            Path.home() / ".devin-orchestrator" / "workflows",
            Path.home() / ".devin-orchestrator" / "workflow-engine"
        ]
        
        self.log_paths = [
            Path.home() / ".devin-orchestrator" / "logs"
        ]
        
        # Retention policies (number of backups to keep)
        self.retention_policies = {
            'sessions': 7,      # Daily backups for 7 days
            'configs': 10,      # Last 10 config backups
            'logs': 30,         # 30 days of logs
            'all': 7            # Default for full backups
        }
    
    def create_backup_name(self, backup_type):
        """Generate timestamped backup name"""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"devin-orchestrator-{backup_type}-{timestamp}"
    
    def backup_directory(self, source_dir, backup_dir, compress=True):
        """Backup a directory to the backup destination"""
        if not source_dir.exists():
            logger.warning(f"Source directory does not exist: {source_dir}")
            return False
        
        try:
            if compress:
                # Create compressed archive
                archive_name = backup_dir.name + ".zip"
                archive_path = self.backup_destination / archive_name
                shutil.make_archive(
                    str(archive_path.with_suffix('')),
                    'zip',
                    str(source_dir.parent),
                    str(source_dir.name)
                )
                logger.info(f"Created compressed backup: {archive_path}")
                return archive_path
            else:
                # Create directory copy
                dest_dir = self.backup_destination / backup_dir.name
                shutil.copytree(source_dir, dest_dir)
                logger.info(f"Created directory backup: {dest_dir}")
                return dest_dir
        except Exception as e:
            logger.error(f"Failed to backup {source_dir}: {e}")
            return False
    
    def backup_file(self, source_file, backup_dir):
        """Backup a single file to the backup destination"""
        if not source_file.exists():
            logger.warning(f"Source file does not exist: {source_file}")
            return False
        
        try:
            dest_dir = self.backup_destination / backup_dir.name
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_file = dest_dir / source_file.name
            shutil.copy2(source_file, dest_file)
            logger.info(f"Backed up file: {source_file} -> {dest_file}")
            return dest_file
        except Exception as e:
            logger.error(f"Failed to backup {source_file}: {e}")
            return False
    
    def backup_sessions(self, compress=True):
        """Backup all session directories"""
        logger.info("Starting session backup...")
        backup_name = self.create_backup_name("sessions")
        backup_dir = self.backup_destination / backup_name
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        success_count = 0
        for session_path in self.session_paths:
            if session_path.exists():
                if self.backup_directory(session_path, backup_dir / session_path.name, compress):
                    success_count += 1
        
        if success_count > 0:
            self.apply_retention_policy('sessions')
            logger.info(f"Session backup completed: {backup_name}")
            return backup_name
        else:
            logger.warning("No session data backed up")
            return None
    
    def backup_configs(self, compress=True):
        """Backup all configuration files and directories"""
        logger.info("Starting configuration backup...")
        backup_name = self.create_backup_name("configs")
        backup_dir = self.backup_destination / backup_name
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        success_count = 0
        for config_path in self.config_paths:
            if config_path.exists():
                if config_path.is_dir():
                    if self.backup_directory(config_path, backup_dir / config_path.name, compress):
                        success_count += 1
                else:
                    if self.backup_file(config_path, backup_dir):
                        success_count += 1
        
        if success_count > 0:
            self.apply_retention_policy('configs')
            logger.info(f"Configuration backup completed: {backup_name}")
            return backup_name
        else:
            logger.warning("No configuration data backed up")
            return None
    
    def backup_logs(self, compress=True):
        """Backup all log files"""
        logger.info("Starting log backup...")
        backup_name = self.create_backup_name("logs")
        backup_dir = self.backup_destination / backup_name
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        success_count = 0
        for log_path in self.log_paths:
            if log_path.exists():
                if self.backup_directory(log_path, backup_dir / log_path.name, compress):
                    success_count += 1
        
        if success_count > 0:
            self.apply_retention_policy('logs')
            logger.info(f"Log backup completed: {backup_name}")
            return backup_name
        else:
            logger.warning("No log data backed up")
            return None
    
    def backup_all(self, compress=True):
        """Backup all data types"""
        logger.info("Starting full backup...")
        backup_name = self.create_backup_name("full")
        backup_dir = self.backup_destination / backup_name
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Backup each type
        results = {
            'sessions': self.backup_sessions(compress),
            'configs': self.backup_configs(compress),
            'logs': self.backup_logs(compress)
        }
        
        # Create metadata
        metadata = {
            'backup_name': backup_name,
            'timestamp': datetime.datetime.now().isoformat(),
            'backup_type': 'full',
            'components': results,
            'project_root': str(self.project_root)
        }
        
        metadata_file = backup_dir / "backup_metadata.json"
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        if compress:
            # Compress the full backup
            archive_name = backup_name + ".zip"
            archive_path = self.backup_destination / archive_name
            shutil.make_archive(str(archive_path.with_suffix('')), 'zip', str(backup_dir))
            shutil.rmtree(backup_dir)
            logger.info(f"Full backup completed and compressed: {archive_name}")
        else:
            logger.info(f"Full backup completed: {backup_name}")
        
        self.apply_retention_policy('all')
        return backup_name
    
    def apply_retention_policy(self, backup_type):
        """Remove old backups based on retention policy"""
        retention_count = self.retention_policies.get(backup_type, 7)
        
        # Get list of backups for this type
        pattern = f"devin-orchestrator-{backup_type}-*"
        backups = sorted(self.backup_destination.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        
        # Remove old backups
        if len(backups) > retention_count:
            old_backups = backups[retention_count:]
            for old_backup in old_backups:
                try:
                    if old_backup.is_dir():
                        shutil.rmtree(old_backup)
                    else:
                        old_backup.unlink()
                    logger.info(f"Removed old backup: {old_backup}")
                except Exception as e:
                    logger.error(f"Failed to remove old backup {old_backup}: {e}")
    
    def validate_backup(self, backup_name):
        """Validate a backup by checking its integrity"""
        backup_path = self.backup_destination / backup_name
        
        if not backup_path.exists():
            logger.error(f"Backup not found: {backup_path}")
            return False
        
        # Check if it's a compressed archive
        if backup_path.suffix == '.zip':
            try:
                # Test the zip file
                import zipfile
                with zipfile.ZipFile(backup_path, 'r') as zip_ref:
                    zip_ref.testzip()
                logger.info(f"Backup validation passed: {backup_path}")
                return True
            except Exception as e:
                logger.error(f"Backup validation failed: {backup_path} - {e}")
                return False
        else:
            # For directory backups, check if it exists and has content
            if backup_path.is_dir() and any(backup_path.iterdir()):
                logger.info(f"Backup validation passed: {backup_path}")
                return True
            else:
                logger.error(f"Backup validation failed: {backup_path} - empty or not a directory")
                return False


def main():
    parser = argparse.ArgumentParser(description='Backup devin-orchestrator data')
    parser.add_argument('--destination', '-d', 
                        help='Backup destination directory (default: ./backups)')
    parser.add_argument('--type', '-t', 
                        choices=['all', 'sessions', 'configs', 'logs'],
                        default='all',
                        help='Type of backup to perform (default: all)')
    parser.add_argument('--compress', '-c',
                        action='store_true',
                        default=True,
                        help='Enable compression (default: True)')
    parser.add_argument('--no-compress',
                        action='store_false',
                        dest='compress',
                        help='Disable compression')
    parser.add_argument('--project-root', '-p',
                        help='Project root directory (default: current directory)')
    parser.add_argument('--validate', '-v',
                        help='Validate an existing backup (provide backup name)')
    
    args = parser.parse_args()
    
    # Initialize backup manager
    manager = BackupManager(
        project_root=args.project_root,
        backup_destination=args.destination
    )
    
    # Create backup destination if it doesn't exist
    manager.backup_destination.mkdir(parents=True, exist_ok=True)
    
    # Validate backup if requested
    if args.validate:
        success = manager.validate_backup(args.validate)
        sys.exit(0 if success else 1)
    
    # Perform backup based on type
    backup_name = None
    if args.type == 'all':
        backup_name = manager.backup_all(args.compress)
    elif args.type == 'sessions':
        backup_name = manager.backup_sessions(args.compress)
    elif args.type == 'configs':
        backup_name = manager.backup_configs(args.compress)
    elif args.type == 'logs':
        backup_name = manager.backup_logs(args.compress)
    
    if backup_name:
        logger.info(f"Backup completed successfully: {backup_name}")
        sys.exit(0)
    else:
        logger.error("Backup failed")
        sys.exit(1)


if __name__ == '__main__':
    main()