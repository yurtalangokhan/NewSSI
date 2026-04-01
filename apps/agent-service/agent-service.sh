#!/usr/bin/env bash
# agent-service helper script
# Usage: ./agent-service.sh <command> [options]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
MAKEFILE_DIR="$SCRIPT_DIR"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}$1${NC}"
    echo -e "${GREEN}========================================${NC}"
}

print_error() {
    echo -e "${RED}Error: $1${NC}" >&2
}

# Check if make is available
if ! command -v make &> /dev/null; then
    print_error "make is not installed"
    exit 1
fi

# Parse command
COMMAND="${1:-help}"
shift || true

case "$COMMAND" in
    # Installation
    i|install)
        make -C "$MAKEFILE_DIR" install
        ;;
    i-dev|install-dev)
        make -C "$MAKEFILE_DIR" install-dev
        ;;
    i-client|install-client)
        make -C "$MAKEFILE_DIR" install-client
        ;;
    sync)
        make -C "$MAKEFILE_DIR" sync
        ;;

    # Running
    run)
        make -C "$MAKEFILE_DIR" run-service
        ;;
    service)
        make -C "$MAKEFILE_DIR" run-service
        ;;
    streamlit)
        make -C "$MAKEFILE_DIR" run-streamlit
        ;;
    studio)
        make -C "$MAKEFILE_DIR" run-studio
        ;;

    # Testing
    test)
        make -C "$MAKEFILE_DIR" test
        ;;
    test-cov|coverage)
        make -C "$MAKEFILE_DIR" test-cov
        ;;

    # Code Quality
    lint)
        make -C "$MAKEFILE_DIR" lint
        ;;
    fix)
        make -C "$MAKEFILE_DIR" fix
        ;;
    typecheck|type)
        make -C "$MAKEFILE_DIR" typecheck
        ;;

    # Database
    migrate)
        make -C "$MAKEFILE_DIR" migrate
        ;;
    migration)
        make -C "$MAKEFILE_DIR" new-migration NAME="$1"
        ;;
    mig-status)
        make -C "$MAKEFILE_DIR" migration-status
        ;;

    # Docker
    docker-up|up)
        make -C "$MAKEFILE_DIR" docker-up
        ;;
    docker-build|build)
        make -C "$MAKEFILE_DIR" docker-build
        ;;
    docker-down|down)
        make -C "$MAKEFILE_DIR" docker-down
        ;;
    docker-logs|logs)
        make -C "$MAKEFILE_DIR" docker-logs
        ;;

    # Pre-commit
    precommit)
        make -C "$MAKEFILE_DIR" precommit-install
        ;;

    # Utilities
    check|env)
        make -C "$MAKEFILE_DIR" check-env
        ;;
    info)
        make -C "$MAKEFILE_DIR" info
        ;;
    clean)
        make -C "$MAKEFILE_DIR" clean
        ;;

    # Development commands
    dev)
        print_header "Starting development environment"
        echo -e "${YELLOW}Starting services...${NC}"
        make -C "$MAKEFILE_DIR" docker-up
        ;;

    full-test)
        print_header "Running full test suite"
        echo -e "${YELLOW}Running tests...${NC}"
        make -C "$MAKEFILE_DIR" test-cov
        echo ""
        echo -e "${YELLOW}Running linter...${NC}"
        make -C "$MAKEFILE_DIR" lint
        echo ""
        echo -e "${YELLOW}Running type checker...${NC}"
        make -C "$MAKEFILE_DIR" typecheck
        ;;

    help|--help|-h)
        echo -e "${GREEN}agent-service Helper Script${NC}"
        echo ""
        echo "Usage: $0 <command> [options]"
        echo ""
        echo -e "${YELLOW}Installation:${NC}"
        echo "  install, i              Install production dependencies"
        echo "  install-dev, i-dev     Install all dependencies including dev"
        echo "  install-client, i-client Install only client dependencies"
        echo "  sync                   Sync dependencies"
        echo ""
        echo -e "${YELLOW}Running:${NC}"
        echo "  run, service            Run FastAPI service"
        echo "  streamlit               Run Streamlit app"
        echo "  studio                  Run LangGraph Studio"
        echo ""
        echo -e "${YELLOW}Testing:${NC}"
        echo "  test                    Run all tests"
        echo "  test-cov, coverage      Run tests with coverage"
        echo ""
        echo -e "${YELLOW}Code Quality:${NC}"
        echo "  lint                    Run ruff linter"
        echo "  fix                     Fix auto-fixable issues"
        echo "  typecheck, type         Run mypy type checker"
        echo ""
        echo -e "${YELLOW}Database:${NC}"
        echo "  migrate                 Apply all migrations"
        echo "  migration <name>        Create new migration"
        echo "  mig-status              Show migration status"
        echo ""
        echo -e "${YELLOW}Docker:${NC}"
        echo "  docker-up, up           Start services in watch mode"
        echo "  docker-build, build     Build Docker images"
        echo "  docker-down, down       Stop services"
        echo "  docker-logs, logs       View logs"
        echo ""
        echo -e "${YELLOW}Utilities:${NC}"
        echo "  check, env              Check environment setup"
        echo "  info                    Show project info"
        echo "  clean                   Clean cache files"
        echo "  precommit               Install pre-commit hooks"
        echo ""
        echo -e "${YELLOW}Development:${NC}"
        echo "  dev                     Start development with docker"
        echo "  full-test               Run tests, lint, and typecheck"
        echo ""
        echo -e "${YELLOW}Examples:${NC}"
        echo "  $0 install"
        echo "  $0 run"
        echo "  $0 test"
        echo "  $0 docker-up"
        echo "  $0 migration add_users_table"
        ;;

    *)
        print_error "Unknown command: $COMMAND"
        echo "Run '$0 help' for usage information"
        exit 1
        ;;
esac
