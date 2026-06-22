#!/bin/bash
#
# Recovery script for devin-orchestrator
# Bash wrapper for Python recovery script. Restores sessions, configurations, and logs from backups
#
# Usage: ./recovery.sh [OPTIONS]
#
# Options:
#   -b, --backup BACKUP      Backup name to restore from (required)
#   -t, --type TYPE          Type of recovery: all, sessions, configs, logs (default: all)
#   -s, --source DIR         Backup source directory (default: ./backups)
#   -p, --project-root DIR   Project root directory (default: current directory)
#   -d, --dry-run            Show what would be restored without actually restoring
#   --no-backup              Do not backup existing files before restore
#   -l, --list               List available backups
#   -v, --validate           Validate backup before recovery
#   --validate-only          Only validate backup, do not perform recovery
#   -h, --help               Show this help message
#
# Examples:
#   ./recovery.sh -b devin-orchestrator-full-20240622_143000.zip -t all
#   ./recovery.sh -l
#   ./recovery.sh -b devin-orchestrator-sessions-20240622_143000.zip -t sessions -d

set -e

# Configuration
PYTHON_ARGS=("recovery_script.py")

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -b|--backup)
            PYTHON_ARGS+=("--backup" "$2")
            shift 2
            ;;
        -t|--type)
            PYTHON_ARGS+=("--type" "$2")
            shift 2
            ;;
        -s|--source)
            PYTHON_ARGS+=("--source" "$2")
            shift 2
            ;;
        -p|--project-root)
            PYTHON_ARGS+=("--project-root" "$2")
            shift 2
            ;;
        -d|--dry-run)
            PYTHON_ARGS+=("--dry-run")
            shift
            ;;
        --no-backup)
            PYTHON_ARGS+=("--no-backup")
            shift
            ;;
        -l|--list)
            PYTHON_ARGS+=("--list")
            shift
            ;;
        -v|--validate)
            PYTHON_ARGS+=("--validate")
            shift
            ;;
        --validate-only)
            PYTHON_ARGS+=("--validate-only")
            shift
            ;;
        -h|--help)
            grep '^#' "$0" | grep -v '#!/bin/bash' | sed 's/^# //; s/^#//'
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Call Python recovery script
python3 "${PYTHON_ARGS[@]}"
