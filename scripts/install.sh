#!/bin/bash
# Install or update devin-orchestrator on Linux/Mac

set -e

# Default values
GLOBAL_INSTALL_PATH="$HOME/.devin-orchestrator"
WORKSPACE_PATH="$(pwd)"
SKIP_WORKSPACE_SETUP=false

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

# Function to check prerequisites
check_prerequisites() {
    print_color "$CYAN" "Checking prerequisites..."

    # Check Python
    if command -v python3 &> /dev/null; then
        local python_version=$(python3 --version 2>&1)
        print_color "$GREEN" "✓ Python found: $python_version"
    else
        print_color "$RED" "✗ Python not found. Please install Python 3.8 or higher."
        exit 1
    fi

    # Check Git
    if command -v git &> /dev/null; then
        local git_version=$(git --version 2>&1)
        print_color "$GREEN" "✓ Git found: $git_version"
    else
        print_color "$RED" "✗ Git not found. Please install Git."
        exit 1
    fi

    # Check pip
    if command -v pip3 &> /dev/null; then
        local pip_version=$(pip3 --version 2>&1)
        print_color "$GREEN" "✓ pip found: $pip_version"
    else
        print_color "$RED" "✗ pip not found. Please install pip."
        exit 1
    fi

    print_color "$GREEN" "All prerequisites satisfied."
}

# Function to install dependencies
install_dependencies() {
    print_color "$CYAN" "Installing Python dependencies..."

    local script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    local requirements_path="$script_dir/../requirements.txt"

    if [ -f "$requirements_path" ]; then
        pip3 install -r "$requirements_path"
        print_color "$GREEN" "✓ Dependencies installed"
    else
        print_color "$YELLOW" "⚠ requirements.txt not found, skipping dependency installation"
    fi
}

# Function to install globally
install_global() {
    local install_path=$1

    print_color "$CYAN" "Installing devin-orchestrator to $install_path..."

    # Create installation directory
    if [ ! -d "$install_path" ]; then
        mkdir -p "$install_path"
        print_color "$GREEN" "✓ Created installation directory"
    fi

    # Copy core directories
    local script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    local project_root="$(dirname "$script_dir")"

    local directories_to_copy=(
        "skills"
        "workflows"
        "workflow-engine"
        "adapters"
        "contracts"
    )

    for dir in "${directories_to_copy[@]}"; do
        local source_path="$project_root/$dir"
        local dest_path="$install_path/$dir"

        if [ -d "$source_path" ]; then
            rm -rf "$dest_path"
            cp -r "$source_path" "$dest_path"
            print_color "$GREEN" "✓ Copied $dir"
        else
            print_color "$YELLOW" "⚠ $dir not found, skipping"
        fi
    done

    # Copy individual files
    local files_to_copy=(
        "dispatch_skill.py"
        "config.yaml"
    )

    for file in "${files_to_copy[@]}"; do
        local source_path="$project_root/$file"
        local dest_path="$install_path/$file"

        if [ -f "$source_path" ]; then
            cp "$source_path" "$dest_path"
            print_color "$GREEN" "✓ Copied $file"
        else
            print_color "$YELLOW" "⚠ $file not found, skipping"
        fi
    done

    # Create work directory
    local work_path="$install_path/work"
    if [ ! -d "$work_path" ]; then
        mkdir -p "$work_path"
        print_color "$GREEN" "✓ Created work directory"
    fi

    # Make dispatch_skill.py executable
    if [ -f "$install_path/dispatch_skill.py" ]; then
        chmod +x "$install_path/dispatch_skill.py"
        print_color "$GREEN" "✓ Made dispatch_skill.py executable"
    fi

    print_color "$GREEN" "✓ Global installation complete"
}

# Function to setup workspace
setup_workspace() {
    local workspace=$1
    local global_path=$2

    print_color "$CYAN" "Setting up workspace at $workspace..."

    # Create .devin/workflows directory
    local devin_workflows_path="$workspace/.devin/workflows"
    if [ ! -d "$devin_workflows_path" ]; then
        mkdir -p "$devin_workflows_path"
        print_color "$GREEN" "✓ Created .devin/workflows directory"
    fi

    # Copy workflow manifests
    local global_workflows_path="$global_path/workflows"
    if [ -d "$global_workflows_path" ]; then
        for manifest in "$global_workflows_path"/*.manifest.yaml; do
            if [ -f "$manifest" ]; then
                local filename=$(basename "$manifest")
                cp "$manifest" "$devin_workflows_path/$filename"
                print_color "$GREEN" "✓ Copied $filename"
            fi
        done
    else
        print_color "$YELLOW" "⚠ Global workflows directory not found"
    fi

    print_color "$GREEN" "✓ Workspace setup complete"
}

# Function to update config
update_config() {
    local install_path=$1

    print_color "$CYAN" "Updating configuration..."

    local config_path="$install_path/config.yaml"

    if [ -f "$config_path" ]; then
        # Use sed to update paths in config
        sed -i.bak "s|global_root:.*|global_root: $install_path|g" "$config_path"
        sed -i.bak "s|skills_dir:.*|skills_dir: $install_path/skills|g" "$config_path"
        sed -i.bak "s|workflows_dir:.*|workflows_dir: $install_path/workflows|g" "$config_path"
        sed -i.bak "s|workflow_engine_dir:.*|workflow_engine_dir: $install_path/workflow-engine|g" "$config_path"
        sed -i.bak "s|session_work_dir:.*|session_work_dir: $install_path/work|g" "$config_path"

        # Remove backup file
        rm -f "$config_path.bak"

        print_color "$GREEN" "✓ Configuration updated"
    else
        print_color "$YELLOW" "⚠ config.yaml not found"
    fi
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --global-path)
            GLOBAL_INSTALL_PATH="$2"
            shift 2
            ;;
        --workspace-path)
            WORKSPACE_PATH="$2"
            shift 2
            ;;
        --skip-workspace-setup)
            SKIP_WORKSPACE_SETUP=true
            shift
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --global-path PATH       Path for global installation (default: ~/.devin-orchestrator)"
            echo "  --workspace-path PATH    Path to workspace to setup (default: current directory)"
            echo "  --skip-workspace-setup   Skip workspace setup"
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
    print_color "$CYAN" "devin-orchestrator Installation Script"
    print_color "$CYAN" "========================================"
    echo ""

    check_prerequisites
    install_dependencies
    install_global "$GLOBAL_INSTALL_PATH"
    update_config "$GLOBAL_INSTALL_PATH"

    if [ "$SKIP_WORKSPACE_SETUP" = false ]; then
        setup_workspace "$WORKSPACE_PATH" "$GLOBAL_INSTALL_PATH"
    fi

    echo ""
    print_color "$CYAN" "========================================"
    print_color "$GREEN" "Installation complete!"
    print_color "$CYAN" "========================================"
    echo ""
    print_color "$WHITE" "Global installation: $GLOBAL_INSTALL_PATH"
    print_color "$WHITE" "Workspace: $WORKSPACE_PATH"
    echo ""
    print_color "$CYAN" "Next steps:"
    print_color "$WHITE" "1. Update $GLOBAL_INSTALL_PATH/config.yaml with your Devin CLI path"
    print_color "$WHITE" "2. Set environment variables if needed"
    print_color "$WHITE" "3. Run workflows using Cascade"
}

main
