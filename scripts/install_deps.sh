#!/bin/bash
# Install Python dependencies for devin-orchestrator on Linux/Mac

set -e

# Default values
REQUIREMENTS_PATH=""
UPGRADE=false
DEV=false
USER_INSTALL=false

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

# Function to install from requirements.txt
install_from_requirements() {
    local req_path=$1
    local upgrade=$2
    local user_install=$3

    if [ -z "$req_path" ]; then
        local script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        req_path="$script_dir/../requirements.txt"
    fi

    if [ ! -f "$req_path" ]; then
        print_color "$RED" "✗ requirements.txt not found at: $req_path"
        exit 1
    fi

    print_color "$CYAN" "Installing dependencies from $req_path..."

    local pip_args=("install" "-r" "$req_path")

    if [ "$upgrade" = true ]; then
        pip_args+=("--upgrade")
    fi

    if [ "$user_install" = true ]; then
        pip_args+=("--user")
    fi

    if pip3 "${pip_args[@]}"; then
        print_color "$GREEN" "✓ Dependencies installed successfully"
    else
        print_color "$RED" "✗ Failed to install dependencies"
        exit 1
    fi
}

# Function to install core dependencies
install_core_dependencies() {
    local upgrade=$1
    local user_install=$2

    print_color "$CYAN" "Installing core dependencies..."

    local core_packages=(
        "PyYAML>=5.1"
    )

    local pip_args=("install")
    if [ "$upgrade" = true ]; then
        pip_args+=("--upgrade")
    fi
    if [ "$user_install" = true ]; then
        pip_args+=("--user")
    fi
    pip_args+=("${core_packages[@]}")

    if pip3 "${pip_args[@]}"; then
        print_color "$GREEN" "✓ Core dependencies installed"
    else
        print_color "$RED" "✗ Failed to install core dependencies"
        exit 1
    fi
}

# Function to install development dependencies
install_dev_dependencies() {
    local upgrade=$1
    local user_install=$2

    print_color "$CYAN" "Installing development dependencies..."

    local dev_packages=(
        "pytest>=7.0.0"
        "pytest-cov>=4.0.0"
        "ruff>=0.1.0"
        "bandit>=1.7.0"
        "safety>=2.0.0"
        "pip-audit>=2.0.0"
    )

    local pip_args=("install")
    if [ "$upgrade" = true ]; then
        pip_args+=("--upgrade")
    fi
    if [ "$user_install" = true ]; then
        pip_args+=("--user")
    fi
    pip_args+=("${dev_packages[@]}")

    if pip3 "${pip_args[@]}"; then
        print_color "$GREEN" "✓ Development dependencies installed"
    else
        print_color "$RED" "✗ Failed to install development dependencies"
        exit 1
    fi
}

# Function to show installed packages
show_installed_packages() {
    print_color "$CYAN" "Installed packages:"
    pip3 list
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --requirements-path)
            REQUIREMENTS_PATH="$2"
            shift 2
            ;;
        --upgrade)
            UPGRADE=true
            shift
            ;;
        --dev)
            DEV=true
            shift
            ;;
        --user)
            USER_INSTALL=true
            shift
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --requirements-path PATH  Path to requirements.txt file"
            echo "  --upgrade                 Upgrade packages to latest versions"
            echo "  --dev                     Install development dependencies"
            echo "  --user                    Install to user directory"
            echo "  --help                    Show this help message"
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
    print_color "$CYAN" "devin-orchestrator Dependency Installer"
    print_color "$CYAN" "========================================"
    echo ""

    check_prerequisites

    if [ "$DEV" = true ]; then
        install_dev_dependencies "$UPGRADE" "$USER_INSTALL"
    elif [ -z "$REQUIREMENTS_PATH" ]; then
        # Default: install from requirements.txt
        install_from_requirements "$REQUIREMENTS_PATH" "$UPGRADE" "$USER_INSTALL"
    else
        # Custom requirements path
        install_from_requirements "$REQUIREMENTS_PATH" "$UPGRADE" "$USER_INSTALL"
    fi

    # Always install core dependencies if not using requirements.txt
    if [ -n "$REQUIREMENTS_PATH" ] && [ ! -f "$REQUIREMENTS_PATH" ]; then
        install_core_dependencies "$UPGRADE" "$USER_INSTALL"
    fi

    echo ""
    print_color "$CYAN" "========================================"
    print_color "$GREEN" "Dependency installation complete!"
    print_color "$CYAN" "========================================"
    echo ""

    show_installed_packages
}

main
