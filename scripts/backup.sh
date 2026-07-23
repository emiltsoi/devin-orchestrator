#!/bin/bash
#
# Backup script for devin-orchestrator
# Bash wrapper for Python backup script. Creates timestamped backups of sessions, configurations, and logs
#
# Usage: ./backup.sh [OPTIONS]
#
# Options:
#   -d, --destination DIR    Backup destination directory (default: ./backups)
#   -t, --type TYPE          Type of backup: all, sessions, configs, logs (default: all)
#   -c, --compress           Enable compression (default: True)
#   -p, --project-root DIR   Project root directory (default: current directory)
#   -v, --validate BACKUP    Validate an existing backup
#   -h, --help               Show this help message
#
# Examples:
#   ./backup.sh -t all -c
#   ./backup.sh -d /backups -t sessions
#   ./backup.sh -v devin-orchestrator-full-20240622_143000.zip

set -e

# Configuration
PYTHON_ARGS=("backup_script.py")

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -d|--destination)
            PYTHON_ARGS+=("--destination" "$2")
            shift 2
            ;;
        -t|--type)
            PYTHON_ARGS+=("--type" "$2")
            shift 2
            ;;
        -c|--compress)
            PYTHON_ARGS+=("--compress")
            shift
            ;;
        --no-compress)
            PYTHON_ARGS+=("--no-compress")
            shift
            ;;
        -p|--project-root)
            PYTHON_ARGS+=("--project-root" "$2")
            shift 2
            ;;
        -v|--validate)
            PYTHON_ARGS+=("--validate" "$2")
            shift 2
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

# Call Python backup script
python3 "${PYTHON_ARGS[@]}"
