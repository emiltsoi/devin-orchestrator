#!/bin/bash
#
# Backup script for devin-orchestrator
# Creates timestamped backups of sessions, configurations, and logs
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
PROJECT_ROOT=""
BACKUP_DESTINATION=""
BACKUP_TYPE="all"
COMPRESS=true
VALIDATE_BACKUP=""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging function
log() {
    local level=$1
    shift
    local message="$@"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "${timestamp} - ${level} - ${message}"
}

# Help function
show_help() {
    grep '^#' "$0" | grep -v '#!/bin/bash' | sed 's/^# //; s/^#//'
    exit 0
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -d|--destination)
            BACKUP_DESTINATION="$2"
            shift 2
            ;;
        -t|--type)
            BACKUP_TYPE="$2"
            shift 2
            ;;
        -c|--compress)
            COMPRESS=true
            shift
            ;;
        --no-compress)
            COMPRESS=false
            shift
            ;;
        -p|--project-root)
            PROJECT_ROOT="$2"
            shift 2
            ;;
        -v|--validate)
            VALIDATE_BACKUP="$2"
            shift 2
            ;;
        -h|--help)
            show_help
            ;;
        *)
            log "ERROR" "Unknown option: $1"
            show_help
            ;;
    esac
done

# Validate backup type
if [[ ! "$BACKUP_TYPE" =~ ^(all|sessions|configs|logs)$ ]]; then
    log "ERROR" "Invalid backup type: $BACKUP_TYPE. Must be one of: all, sessions, configs, logs"
    exit 1
fi

# Set default project root
if [[ -z "$PROJECT_ROOT" ]]; then
    PROJECT_ROOT="$(pwd)"
fi

# Set default backup destination
if [[ -z "$BACKUP_DESTINATION" ]]; then
    BACKUP_DESTINATION="$PROJECT_ROOT/backups"
fi

# Create backup destination if it doesn't exist
mkdir -p "$BACKUP_DESTINATION"

# Define paths to backup
SESSION_PATHS=(
    "$PROJECT_ROOT/work"
    "$HOME/.devin-orchestrator/work"
)

CONFIG_PATHS=(
    "$PROJECT_ROOT/config.yaml"
    "$PROJECT_ROOT/.devin"
    "$PROJECT_ROOT/skills"
    "$PROJECT_ROOT/workflows"
    "$PROJECT_ROOT/adapters"
    "$PROJECT_ROOT/contracts"
    "$HOME/.devin-orchestrator/config.yaml"
    "$HOME/.devin-orchestrator/skills"
    "$HOME/.devin-orchestrator/workflows"
    "$HOME/.devin-orchestrator/workflow-engine"
)

LOG_PATHS=(
    "$HOME/.devin-orchestrator/logs"
)

# Retention policies
RETENTION_POLICIES=(
    ["sessions"]=7
    ["configs"]=10
    ["logs"]=30
    ["all"]=7
)

# Create backup name
create_backup_name() {
    local backup_type=$1
    local timestamp=$(date '+%Y%m%d_%H%M%S')
    echo "devin-orchestrator-${backup_type}-${timestamp}"
}

# Backup a directory
backup_directory() {
    local source_dir=$1
    local backup_dir=$2
    local compress=$3

    if [[ ! -d "$source_dir" ]]; then
        log "WARNING" "Source directory does not exist: $source_dir"
        return 1
    fi

    if [[ "$compress" == true ]]; then
        # Create compressed archive
        local archive_name="${backup_dir}.zip"
        local archive_path="$BACKUP_DESTINATION/$archive_name"
        local parent_dir=$(dirname "$source_dir")
        local dir_name=$(basename "$source_dir")

        if (cd "$parent_dir" && zip -r "$archive_path" "$dir_name" > /dev/null); then
            log "INFO" "Created compressed backup: $archive_path"
            return 0
        else
            log "ERROR" "Failed to create compressed backup: $source_dir"
            return 1
        fi
    else
        # Create directory copy
        local dest_dir="$BACKUP_DESTINATION/$backup_dir"
        if cp -r "$source_dir" "$dest_dir"; then
            log "INFO" "Created directory backup: $dest_dir"
            return 0
        else
            log "ERROR" "Failed to backup directory: $source_dir"
            return 1
        fi
    fi
}

# Backup a single file
backup_file() {
    local source_file=$1
    local backup_dir=$2

    if [[ ! -f "$source_file" ]]; then
        log "WARNING" "Source file does not exist: $source_file"
        return 1
    fi

    local dest_dir="$BACKUP_DESTINATION/$backup_dir"
    mkdir -p "$dest_dir"
    local dest_file="$dest_dir/$(basename "$source_file")"

    if cp "$source_file" "$dest_file"; then
        log "INFO" "Backed up file: $source_file -> $dest_file"
        return 0
    else
        log "ERROR" "Failed to backup file: $source_file"
        return 1
    fi
}

# Backup sessions
backup_sessions() {
    local compress=$1
    log "INFO" "Starting session backup..."
    local backup_name=$(create_backup_name "sessions")
    local backup_dir="$BACKUP_DESTINATION/$backup_name"
    mkdir -p "$backup_dir"

    local success_count=0
    for session_path in "${SESSION_PATHS[@]}"; do
        if [[ -e "$session_path" ]]; then
            local dir_name=$(basename "$session_path")
            if backup_directory "$session_path" "$backup_name/$dir_name" "$compress"; then
                ((success_count++))
            fi
        fi
    done

    if [[ $success_count -gt 0 ]]; then
        apply_retention_policy "sessions"
        log "INFO" "Session backup completed: $backup_name"
        echo "$backup_name"
        return 0
    else
        log "WARNING" "No session data backed up"
        return 1
    fi
}

# Backup configurations
backup_configs() {
    local compress=$1
    log "INFO" "Starting configuration backup..."
    local backup_name=$(create_backup_name "configs")
    local backup_dir="$BACKUP_DESTINATION/$backup_name"
    mkdir -p "$backup_dir"

    local success_count=0
    for config_path in "${CONFIG_PATHS[@]}"; do
        if [[ -e "$config_path" ]]; then
            local item_name=$(basename "$config_path")
            if [[ -d "$config_path" ]]; then
                if backup_directory "$config_path" "$backup_name/$item_name" "$compress"; then
                    ((success_count++))
                fi
            else
                if backup_file "$config_path" "$backup_name"; then
                    ((success_count++))
                fi
            fi
        fi
    done

    if [[ $success_count -gt 0 ]]; then
        apply_retention_policy "configs"
        log "INFO" "Configuration backup completed: $backup_name"
        echo "$backup_name"
        return 0
    else
        log "WARNING" "No configuration data backed up"
        return 1
    fi
}

# Backup logs
backup_logs() {
    local compress=$1
    log "INFO" "Starting log backup..."
    local backup_name=$(create_backup_name "logs")
    local backup_dir="$BACKUP_DESTINATION/$backup_name"
    mkdir -p "$backup_dir"

    local success_count=0
    for log_path in "${LOG_PATHS[@]}"; do
        if [[ -e "$log_path" ]]; then
            local dir_name=$(basename "$log_path")
            if backup_directory "$log_path" "$backup_name/$dir_name" "$compress"; then
                ((success_count++))
            fi
        fi
    done

    if [[ $success_count -gt 0 ]]; then
        apply_retention_policy "logs"
        log "INFO" "Log backup completed: $backup_name"
        echo "$backup_name"
        return 0
    else
        log "WARNING" "No log data backed up"
        return 1
    fi
}

# Backup all data
backup_all() {
    local compress=$1
    log "INFO" "Starting full backup..."
    local backup_name=$(create_backup_name "full")
    local backup_dir="$BACKUP_DESTINATION/$backup_name"
    mkdir -p "$backup_dir"

    # Backup each type
    local sessions_result=$(backup_sessions "$compress")
    local configs_result=$(backup_configs "$compress")
    local logs_result=$(backup_logs "$compress")

    # Create metadata
    local metadata_file="$backup_dir/backup_metadata.json"
    cat > "$metadata_file" << EOF
{
    "backup_name": "$backup_name",
    "timestamp": "$(date -Iseconds)",
    "backup_type": "full",
    "components": {
        "sessions": "$sessions_result",
        "configs": "$configs_result",
        "logs": "$logs_result"
    },
    "project_root": "$PROJECT_ROOT"
}
EOF

    if [[ "$compress" == true ]]; then
        # Compress the full backup
        local archive_name="${backup_name}.zip"
        local archive_path="$BACKUP_DESTINATION/$archive_name"
        (cd "$BACKUP_DESTINATION" && zip -r "$archive_name" "$backup_name" > /dev/null)
        rm -rf "$backup_dir"
        log "INFO" "Full backup completed and compressed: $archive_name"
    else
        log "INFO" "Full backup completed: $backup_name"
    fi

    apply_retention_policy "all"
    echo "$backup_name"
    return 0
}

# Apply retention policy
apply_retention_policy() {
    local backup_type=$1
    local retention_count=${RETENTION_POLICIES[$backup_type]}

    # Get list of backups for this type
    local pattern="devin-orchestrator-${backup_type}-*"
    local backups=($(ls -t "$BACKUP_DESTINATION"/$pattern 2>/dev/null || true))

    # Remove old backups
    if [[ ${#backups[@]} -gt $retention_count ]]; then
        local old_backups=("${backups[@]:$retention_count}")
        for old_backup in "${old_backups[@]}"; do
            if rm -rf "$old_backup"; then
                log "INFO" "Removed old backup: $(basename "$old_backup")"
            else
                log "ERROR" "Failed to remove old backup: $(basename "$old_backup")"
            fi
        done
    fi
}

# Validate backup
validate_backup() {
    local backup_name=$1
    local backup_path="$BACKUP_DESTINATION/$backup_name"

    if [[ ! -e "$backup_path" ]]; then
        log "ERROR" "Backup not found: $backup_path"
        return 1
    fi

    # Check if it's a compressed archive
    if [[ "$backup_path" =~ \.zip$ ]]; then
        if unzip -t "$backup_path" > /dev/null 2>&1; then
            log "INFO" "Backup validation passed: $backup_path"
            return 0
        else
            log "ERROR" "Backup validation failed: $backup_path"
            return 1
        fi
    else
        # For directory backups, check if it exists and has content
        if [[ -d "$backup_path" ]]; then
            if [[ -n "$(ls -A "$backup_path" 2>/dev/null)" ]]; then
                log "INFO" "Backup validation passed: $backup_path"
                return 0
            else
                log "ERROR" "Backup validation failed: $backup_path - empty directory"
                return 1
            fi
        else
            log "ERROR" "Backup validation failed: $backup_path - not a directory"
            return 1
        fi
    fi
}

# Main execution
main() {
    # Validate backup if requested
    if [[ -n "$VALIDATE_BACKUP" ]]; then
        if validate_backup "$VALIDATE_BACKUP"; then
            exit 0
        else
            exit 1
        fi
    fi

    # Perform backup based on type
    local backup_name=""
    case "$BACKUP_TYPE" in
        all)
            backup_name=$(backup_all "$COMPRESS")
            ;;
        sessions)
            backup_name=$(backup_sessions "$COMPRESS")
            ;;
        configs)
            backup_name=$(backup_configs "$COMPRESS")
            ;;
        logs)
            backup_name=$(backup_logs "$COMPRESS")
            ;;
    esac

    if [[ -n "$backup_name" ]]; then
        log "INFO" "Backup completed successfully: $backup_name"
        exit 0
    else
        log "ERROR" "Backup failed"
        exit 1
    fi
}

# Run main function
main