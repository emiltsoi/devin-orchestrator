#!/usr/bin/env python3
"""
Recovery script for devin-orchestrator
Restores sessions, configurations, and logs from backups
"""

import os
import shutil
import argparse
import datetime
import json
import sys
from pathlib import Path
import zipfile
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RecoveryManager:
    def __init__(self, project_root=None, backup_source=None):
        """Initialize recovery manager with paths"""
        if project_root is None:
            self.project_root = Path.cwd()
        else:
            self.project_root = Path(project_root)
        
        if backup_source is None:
            self.backup_source = self.project_root / "backups"
        else:
            self.backup_source = Path(backup_source)
        
        # Define restore paths
        self.session_restore_paths = {
            'work': self.project_root / "work",
            'devin-orchestrator-work': Path.home() / ".devin-orchestrator" / "work"
        }
        
        self.config_restore_paths = {
            'config.yaml': self.project_root / "config.yaml",
            '.devin': self.project_root / ".devin",
            'skills': self.project_root / "skills",
            'workflows': self.project_root / "workflows",
            'adapters': self.project_root / "adapters",
            'contracts': self.project_root / "contracts",
            'devin-orchestrator-config': Path.home() / ".devin-orchestrator" / "config.yaml",
            'devin-orchestrator-skills': Path.home() / ".devin-orchestrator" / "skills",
            'devin-orchestrator-workflows': Path.home() / ".devin-orchestrator" / "workflows",
            'devin-orchestrator-workflow-engine': Path.home() / ".devin-orchestrator" / "workflow-engine"
        }
        
        self.log_restore_paths = {
            'logs': Path.home() / ".devin-orchestrator" / "logs"
        }
    
    def list_backups(self, backup_type=None):
        """List available backups"""
        if backup_type:
            pattern = f"devin-orchestrator-{backup_type}-*"
        else:
            pattern = "devin-orchestrator-*"
        
        backups = sorted(self.backup_source.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        
        if not backups:
            logger.info(f"No backups found matching pattern: {pattern}")
            return []
        
        logger.info(f"Found {len(backups)} backup(s):")
        for backup in backups:
            size = self._get_size(backup)
            mtime = datetime.datetime.fromtimestamp(backup.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            logger.info(f"  {backup.name} - {size} - {mtime}")
        
        return backups
    
    def _get_size(self, path):
        """Get human-readable size of a file or directory"""
        if path.is_file():
            return self._format_size(path.stat().st_size)
        elif path.is_dir():
            total = sum(f.stat().st_size for f in path.rglob('*') if f.is_file())
            return self._format_size(total)
        return "0 B"
    
    def _format_size(self, size_bytes):
        """Format bytes to human-readable size"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} TB"
    
    def extract_backup(self, backup_name, extract_to=None):
        """Extract a backup archive"""
        backup_path = self.backup_source / backup_name
        
        if not backup_path.exists():
            logger.error(f"Backup not found: {backup_path}")
            return None
        
        if extract_to is None:
            extract_to = self.backup_source / f"temp_{backup_name}"
        else:
            extract_to = Path(extract_to)
        
        try:
            if backup_path.suffix == '.zip':
                logger.info(f"Extracting {backup_path} to {extract_to}")
                with zipfile.ZipFile(backup_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_to)
                logger.info(f"Extraction completed: {extract_to}")
                return extract_to
            elif backup_path.is_dir():
                # It's already a directory, just return it
                logger.info(f"Backup is already a directory: {backup_path}")
                return backup_path
            else:
                logger.error(f"Unknown backup format: {backup_path}")
                return None
        except Exception as e:
            logger.error(f"Failed to extract backup: {e}")
            return None
    
    def validate_backup(self, backup_name):
        """Validate a backup before recovery"""
        backup_path = self.backup_source / backup_name
        
        if not backup_path.exists():
            logger.error(f"Backup not found: {backup_path}")
            return False
        
        logger.info(f"Validating backup: {backup_name}")
        
        if backup_path.suffix == '.zip':
            try:
                with zipfile.ZipFile(backup_path, 'r') as zip_ref:
                    bad_file = zip_ref.testzip()
                    if bad_file:
                        logger.error(f"Corrupted file in backup: {bad_file}")
                        return False
                logger.info("Backup validation passed")
                return True
            except Exception as e:
                logger.error(f"Backup validation failed: {e}")
                return False
        elif backup_path.is_dir():
            # Check if directory has content
            if any(backup_path.iterdir()):
                logger.info("Backup validation passed")
                return True
            else:
                logger.error("Backup directory is empty")
                return False
        else:
            logger.error("Invalid backup format")
            return False
    
    def restore_directory(self, source_dir, dest_dir, backup_existing=True):
        """Restore a directory to its destination"""
        if not source_dir.exists():
            logger.warning(f"Source directory does not exist: {source_dir}")
            return False
        
        try:
            # Backup existing directory if it exists
            if dest_dir.exists() and backup_existing:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_name = f"{dest_dir.name}_backup_{timestamp}"
                backup_path = dest_dir.parent / backup_name
                logger.info(f"Backing up existing directory: {dest_dir} -> {backup_path}")
                shutil.copytree(dest_dir, backup_path)
            
            # Create destination parent directory if it doesn't exist
            dest_dir.parent.mkdir(parents=True, exist_ok=True)
            
            # Remove existing directory if it exists
            if dest_dir.exists():
                shutil.rmtree(dest_dir)
            
            # Copy source to destination
            shutil.copytree(source_dir, dest_dir)
            logger.info(f"Restored directory: {source_dir} -> {dest_dir}")
            return True
        except Exception as e:
            logger.error(f"Failed to restore directory {source_dir}: {e}")
            return False
    
    def restore_file(self, source_file, dest_file, backup_existing=True):
        """Restore a single file to its destination"""
        if not source_file.exists():
            logger.warning(f"Source file does not exist: {source_file}")
            return False
        
        try:
            # Backup existing file if it exists
            if dest_file.exists() and backup_existing:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_name = f"{dest_file.name}_backup_{timestamp}"
                backup_path = dest_file.parent / backup_name
                logger.info(f"Backing up existing file: {dest_file} -> {backup_path}")
                shutil.copy2(dest_file, backup_path)
            
            # Create destination parent directory if it doesn't exist
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy source to destination
            shutil.copy2(source_file, dest_file)
            logger.info(f"Restored file: {source_file} -> {dest_file}")
            return True
        except Exception as e:
            logger.error(f"Failed to restore file {source_file}: {e}")
            return False
    
    def restore_sessions(self, backup_name, dry_run=False, backup_existing=True):
        """Restore session data from backup"""
        logger.info(f"Restoring sessions from backup: {backup_name}")
        
        # Extract backup
        extracted_path = self.extract_backup(backup_name)
        if not extracted_path:
            return False
        
        try:
            success_count = 0
            for source_name, dest_path in self.session_restore_paths.items():
                source_path = extracted_path / source_name
                if source_path.exists():
                    if dry_run:
                        logger.info(f"[DRY RUN] Would restore: {source_path} -> {dest_path}")
                        success_count += 1
                    else:
                        if self.restore_directory(source_path, dest_path, backup_existing):
                            success_count += 1
            
            # Clean up extracted directory
            if not dry_run and extracted_path.name.startswith("temp_"):
                shutil.rmtree(extracted_path)
            
            if success_count > 0:
                logger.info(f"Session restoration completed: {success_count} directories restored")
                return True
            else:
                logger.warning("No session data restored")
                return False
        except Exception as e:
            logger.error(f"Failed to restore sessions: {e}")
            return False
    
    def restore_configs(self, backup_name, dry_run=False, backup_existing=True):
        """Restore configuration data from backup"""
        logger.info(f"Restoring configurations from backup: {backup_name}")
        
        # Extract backup
        extracted_path = self.extract_backup(backup_name)
        if not extracted_path:
            return False
        
        try:
            success_count = 0
            for source_name, dest_path in self.config_restore_paths.items():
                source_path = extracted_path / source_name
                if source_path.exists():
                    if dry_run:
                        logger.info(f"[DRY RUN] Would restore: {source_path} -> {dest_path}")
                        success_count += 1
                    else:
                        if source_path.is_dir():
                            if self.restore_directory(source_path, dest_path, backup_existing):
                                success_count += 1
                        else:
                            if self.restore_file(source_path, dest_path, backup_existing):
                                success_count += 1
            
            # Clean up extracted directory
            if not dry_run and extracted_path.name.startswith("temp_"):
                shutil.rmtree(extracted_path)
            
            if success_count > 0:
                logger.info(f"Configuration restoration completed: {success_count} items restored")
                return True
            else:
                logger.warning("No configuration data restored")
                return False
        except Exception as e:
            logger.error(f"Failed to restore configurations: {e}")
            return False
    
    def restore_logs(self, backup_name, dry_run=False, backup_existing=True):
        """Restore log data from backup"""
        logger.info(f"Restoring logs from backup: {backup_name}")
        
        # Extract backup
        extracted_path = self.extract_backup(backup_name)
        if not extracted_path:
            return False
        
        try:
            success_count = 0
            for source_name, dest_path in self.log_restore_paths.items():
                source_path = extracted_path / source_name
                if source_path.exists():
                    if dry_run:
                        logger.info(f"[DRY RUN] Would restore: {source_path} -> {dest_path}")
                        success_count += 1
                    else:
                        if self.restore_directory(source_path, dest_path, backup_existing):
                            success_count += 1
            
            # Clean up extracted directory
            if not dry_run and extracted_path.name.startswith("temp_"):
                shutil.rmtree(extracted_path)
            
            if success_count > 0:
                logger.info(f"Log restoration completed: {success_count} directories restored")
                return True
            else:
                logger.warning("No log data restored")
                return False
        except Exception as e:
            logger.error(f"Failed to restore logs: {e}")
            return False
    
    def restore_all(self, backup_name, dry_run=False, backup_existing=True):
        """Restore all data from backup"""
        logger.info(f"Starting full restoration from backup: {backup_name}")
        
        results = {
            'sessions': self.restore_sessions(backup_name, dry_run, backup_existing),
            'configs': self.restore_configs(backup_name, dry_run, backup_existing),
            'logs': self.restore_logs(backup_name, dry_run, backup_existing)
        }
        
        success_count = sum(1 for v in results.values() if v)
        logger.info(f"Full restoration completed: {success_count}/3 components restored")
        
        return all(results.values())


def main():
    parser = argparse.ArgumentParser(description='Recover devin-orchestrator data from backups')
    parser.add_argument('--backup', '-b',
                        required=True,
                        help='Backup name to restore from (e.g., devin-orchestrator-full-20240622_143000.zip)')
    parser.add_argument('--type', '-t',
                        choices=['all', 'sessions', 'configs', 'logs'],
                        default='all',
                        help='Type of recovery to perform (default: all)')
    parser.add_argument('--source', '-s',
                        help='Backup source directory (default: ./backups)')
    parser.add_argument('--project-root', '-p',
                        help='Project root directory (default: current directory)')
    parser.add_argument('--dry-run', '-d',
                        action='store_true',
                        help='Show what would be restored without actually restoring')
    parser.add_argument('--no-backup',
                        action='store_false',
                        dest='backup_existing',
                        help='Do not backup existing files before restore')
    parser.add_argument('--list', '-l',
                        action='store_true',
                        help='List available backups')
    parser.add_argument('--validate', '-v',
                        action='store_true',
                        help='Validate backup before recovery')
    parser.add_argument('--validate-only',
                        action='store_true',
                        help='Only validate backup, do not perform recovery')
    
    args = parser.parse_args()
    
    # Initialize recovery manager
    manager = RecoveryManager(
        project_root=args.project_root,
        backup_source=args.source
    )
    
    # List backups if requested
    if args.list:
        manager.list_backups()
        sys.exit(0)
    
    # Validate backup if requested
    if args.validate or args.validate_only:
        if not manager.validate_backup(args.backup):
            logger.error("Backup validation failed")
            sys.exit(1)
        logger.info("Backup validation passed")
        if args.validate_only:
            sys.exit(0)
    
    # Perform recovery based on type
    success = False
    if args.type == 'all':
        success = manager.restore_all(args.backup, args.dry_run, args.backup_existing)
    elif args.type == 'sessions':
        success = manager.restore_sessions(args.backup, args.dry_run, args.backup_existing)
    elif args.type == 'configs':
        success = manager.restore_configs(args.backup, args.dry_run, args.backup_existing)
    elif args.type == 'logs':
        success = manager.restore_logs(args.backup, args.dry_run, args.backup_existing)
    
    if success:
        logger.info("Recovery completed successfully")
        sys.exit(0)
    else:
        logger.error("Recovery failed")
        sys.exit(1)


if __name__ == '__main__':
    main()