#!/bin/bash
# Set up environment variables for devin-orchestrator on Linux/Mac

set -e

# Default values
GLOBAL_INSTALL_PATH="$HOME/.devin-orchestrator"
PERSIST=false
DEVIN_CLI_PATH=""
DEFAULT_MODEL="swe-1.6"
PERMISSION_MODE="dangerous"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color

# Function to print colored output
print_color() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

# Function to set environment variable
set_env_var() {
    local name=$1
    local value=$2
    local persist=$3

    export "$name=$value"

    if [ "$persist" = true ]; then
        # Determine shell config file
        local shell_config=""
        if [ -n "$ZSH_VERSION" ]; then
            shell_config="$HOME/.zshrc"
        elif [ -n "$BASH_VERSION" ]; then
            shell_config="$HOME/.bashrc"
        else
            # Default to .profile for other shells
            shell_config="$HOME/.profile"
        fi

        # Check if variable already exists in config
        if grep -q "^export $name=" "$shell_config" 2>/dev/null; then
            # Update existing variable
            sed -i.bak "s|^export $name=.*|export $name=\"$value\"|g" "$shell_config"
            rm -f "$shell_config.bak"
        else
            # Add new variable
            echo "export $name=\"$value\"" >> "$shell_config"
        fi

        print_color "$GREEN" "✓ Set $name=$value (persistent)"
    else
        print_color "$YELLOW" "✓ Set $name=$value (current session)"
    fi
}

# Function to test installation
test_installation() {
    local install_path=$1

    print_color "$CYAN" "Checking installation at $install_path..."

    if [ ! -d "$install_path" ]; then
        print_color "$RED" "✗ Installation path not found: $install_path"
        print_color "$YELLOW" "Please run install.sh first"
        exit 1
    fi

    local required_dirs=("skills" "workflows" "workflow-engine")
    for dir in "${required_dirs[@]}"; do
        if [ ! -d "$install_path/$dir" ]; then
            print_color "$RED" "✗ Required directory not found: $dir"
            exit 1
        fi
    done

    print_color "$GREEN" "✓ Installation verified"
}

# Function to update config file
update_config_file() {
    local install_path=$1
    local devin_cli_path=$2
    local default_model=$3
    local permission_mode=$4

    print_color "$CYAN" "Updating config.yaml..."

    local config_path="$install_path/config.yaml"

    if [ ! -f "$config_path" ]; then
        print_color "$YELLOW" "⚠ config.yaml not found, skipping"
        return
    fi

    # Create backup
    cp "$config_path" "$config_path.bak"

    # Update paths
    sed -i.bak "s|global_root:.*|global_root: $install_path|g" "$config_path"
    sed -i.bak "s|skills_dir:.*|skills_dir: $install_path/skills|g" "$config_path"
    sed -i.bak "s|workflows_dir:.*|workflows_dir: $install_path/workflows|g" "$config_path"
    sed -i.bak "s|workflow_engine_dir:.*|workflow_engine_dir: $install_path/workflow-engine|g" "$config_path"
    sed -i.bak "s|session_work_dir:.*|session_work_dir: $install_path/work|g" "$config_path"

    # Update Devin CLI path if provided
    if [ -n "$devin_cli_path" ]; then
        if grep -q "devin_cli_path:" "$config_path"; then
            sed -i.bak "s|devin_cli_path:.*|devin_cli_path: $devin_cli_path|g" "$config_path"
        else
            echo "devin_cli_path: $devin_cli_path" >> "$config_path"
        fi
    fi

    # Update default model if provided
    if [ -n "$default_model" ]; then
        if grep -q "default_model:" "$config_path"; then
            sed -i.bak "s|default_model:.*|default_model: $default_model|g" "$config_path"
        else
            echo "default_model: $default_model" >> "$config_path"
        fi
    fi

    # Update permission mode if provided
    if [ -n "$permission_mode" ]; then
        if grep -q "default_permission_mode:" "$config_path"; then
            sed -i.bak "s|default_permission_mode:.*|default_permission_mode: $permission_mode|g" "$config_path"
        else
            echo "default_permission_mode: $permission_mode" >> "$config_path"
        fi
    fi

    # Remove backup
    rm -f "$config_path.bak"

    print_color "$GREEN" "✓ config.yaml updated"
}

# Function to add to PATH
add_to_path() {
    local path_to_add=$1
    local persist=$2

    # Check if already in PATH
    if [[ ":$PATH:" != *":$path_to_add:"* ]]; then
        if [ "$persist" = true ]; then
            # Determine shell config file
            local shell_config=""
            if [ -n "$ZSH_VERSION" ]; then
                shell_config="$HOME/.zshrc"
            elif [ -n "$BASH_VERSION" ]; then
                shell_config="$HOME/.bashrc"
            else
                shell_config="$HOME/.profile"
            fi

            # Check if PATH export already exists
            if grep -q "export PATH=.*$path_to_add" "$shell_config" 2>/dev/null; then
                print_color "$YELLOW" "⚠ $path_to_add already in PATH in config file"
            else
                echo "export PATH=\"$path_to_add:\$PATH\"" >> "$shell_config"
                print_color "$GREEN" "✓ Added $path_to_add to PATH (persistent)"
            fi
        else
            export PATH="$path_to_add:$PATH"
            print_color "$YELLOW" "✓ Added $path_to_add to PATH (current session)"
        fi
    else
        print_color "$YELLOW" "⚠ $path_to_add already in PATH"
    fi
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --global-path)
            GLOBAL_INSTALL_PATH="$2"
            shift 2
            ;;
        --persist)
            PERSIST=true
            shift
            ;;
        --devin-cli-path)
            DEVIN_CLI_PATH="$2"
            shift 2
            ;;
        --default-model)
            DEFAULT_MODEL="$2"
            shift 2
            ;;
        --permission-mode)
            PERMISSION_MODE="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --global-path PATH       Path to devin-orchestrator installation (default: ~/.devin-orchestrator)"
            echo "  --persist                Persist environment variables to shell config"
            echo "  --devin-cli-path PATH    Path to Devin CLI executable"
            echo "  --default-model MODEL    Default model to use (default: swe-1.6)"
            echo "  --permission-mode MODE   Default permission mode (default: dangerous)"
            echo "  --help                   Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Main execution
main() {
    print_color "$CYAN" "========================================"
    print_color "$CYAN" "devin-orchestrator Environment Setup"
    print_color "$CYAN" "========================================"
    echo ""

    test_installation "$GLOBAL_INSTALL_PATH"

    # Set environment variables
    print_color "$CYAN" "Setting environment variables..."

    set_env_var "DEVIN_ORCHESTRATOR_ROOT" "$GLOBAL_INSTALL_PATH" "$PERSIST"
    set_env_var "DEVIN_ORCHESTRATOR_SKILLS_DIR" "$GLOBAL_INSTALL_PATH/skills" "$PERSIST"
    set_env_var "DEVIN_ORCHESTRATOR_WORKFLOWS_DIR" "$GLOBAL_INSTALL_PATH/workflows" "$PERSIST"
    set_env_var "DEVIN_ORCHESTRATOR_WORKFLOW_ENGINE_DIR" "$GLOBAL_INSTALL_PATH/workflow-engine" "$PERSIST"
    set_env_var "DEVIN_ORCHESTRATOR_WORK_DIR" "$GLOBAL_INSTALL_PATH/work" "$PERSIST"

    if [ -n "$DEVIN_CLI_PATH" ]; then
        set_env_var "DEVIN_CLI_PATH" "$DEVIN_CLI_PATH" "$PERSIST"
    fi

    if [ -n "$DEFAULT_MODEL" ]; then
        set_env_var "DEVIN_DEFAULT_MODEL" "$DEFAULT_MODEL" "$PERSIST"
    fi

    if [ -n "$PERMISSION_MODE" ]; then
        set_env_var "DEVIN_DEFAULT_PERMISSION_MODE" "$PERMISSION_MODE" "$PERSIST"
    fi

    # Add to PATH if dispatch script exists
    if [ -f "$GLOBAL_INSTALL_PATH/dispatch_skill.py" ]; then
        add_to_path "$GLOBAL_INSTALL_PATH" "$PERSIST"
    fi

    # Update config file
    update_config_file "$GLOBAL_INSTALL_PATH" "$DEVIN_CLI_PATH" "$DEFAULT_MODEL" "$PERMISSION_MODE"

    echo ""
    print_color "$CYAN" "========================================"
    print_color "$GREEN" "Environment setup complete!"
    print_color "$CYAN" "========================================"
    echo ""

    if [ "$PERSIST" = true ]; then
        print_color "$GREEN" "Environment variables have been persisted to your shell config."
        print_color "$YELLOW" "You may need to restart your terminal or run 'source ~/.bashrc' (or ~/.zshrc) for changes to take effect."
    else
        print_color "$YELLOW" "Environment variables are set for the current session only."
        print_color "$YELLOW" "Use --persist flag to make changes permanent."
    fi

    echo ""
    print_color "$CYAN" "Current environment variables:"
    echo "DEVIN_ORCHESTRATOR_ROOT=$DEVIN_ORCHESTRATOR_ROOT"
    echo "DEVIN_ORCHESTRATOR_SKILLS_DIR=$DEVIN_ORCHESTRATOR_SKILLS_DIR"
    echo "DEVIN_ORCHESTRATOR_WORKFLOWS_DIR=$DEVIN_ORCHESTRATOR_WORKFLOWS_DIR"
    if [ -n "$DEVIN_CLI_PATH" ]; then
        echo "DEVIN_CLI_PATH=$DEVIN_CLI_PATH"
    fi
    if [ -n "$DEFAULT_MODEL" ]; then
        echo "DEVIN_DEFAULT_MODEL=$DEFAULT_MODEL"
    fi
}

main
