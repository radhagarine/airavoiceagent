#!/bin/bash

# Voice Bot Stop Script
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_step() {
    echo -e "${BLUE}==>${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# Stop voice bot application
stop_voice_bot() {
    print_step "Stopping voice bot application..."
    
    if [ -f voice-bot.pid ]; then
        PID=$(cat voice-bot.pid)
        if kill -0 $PID 2>/dev/null; then
            kill $PID
            sleep 2
            # Force kill if still running
            if kill -0 $PID 2>/dev/null; then
                kill -9 $PID
            fi
            print_success "Voice bot application stopped"
        else
            print_warning "Voice bot was not running"
        fi
        rm voice-bot.pid
    else
        # Try to find and kill any running server.py processes
        PID=$(pgrep -f "python.*server.py" || echo "")
        if [ -n "$PID" ]; then
            kill $PID
            print_success "Found and stopped voice bot process"
        else
            print_warning "No voice bot process found"
        fi
    fi
}

# Stop infrastructure services
stop_infrastructure() {
    print_step "Stopping infrastructure services..."
    
    # Stop Docker services
    docker-compose down
    
    print_success "Infrastructure services stopped"
}

# Stop only specific services
stop_redis() {
    print_step "Stopping Redis cluster..."
    docker-compose stop redis-1 redis-2 redis-3 redis-cluster-init
    print_success "Redis cluster stopped"
}

stop_monitoring() {
    print_step "Stopping monitoring services..."
    docker-compose stop prometheus grafana alertmanager
    print_success "Monitoring services stopped"
}

# Clean up volumes (optional)
clean_volumes() {
    print_step "Cleaning up data volumes..."
    read -p "This will delete all Redis, Prometheus, and Grafana data. Are you sure? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        docker-compose down -v
        print_success "All data volumes removed"
    else
        print_warning "Volume cleanup cancelled"
    fi
}

# Show status after stopping
show_status() {
    print_step "Current status:"
    
    # Check if any containers are still running
    RUNNING=$(docker-compose ps -q)
    if [ -z "$RUNNING" ]; then
        print_success "All services stopped"
    else
        print_warning "Some services may still be running:"
        docker-compose ps
    fi
    
    # Check for voice bot process
    if pgrep -f "python.*server.py" > /dev/null; then
        print_warning "Voice bot process may still be running"
    fi
}

# Show usage
show_usage() {
    echo -e "${BLUE}Voice Bot Stop Script${NC}"
    echo "Usage: $0 [OPTIONS]"
    echo
    echo "Options:"
    echo "  all             Stop all services (default)"
    echo "  app             Stop only the voice bot application"
    echo "  infrastructure  Stop all infrastructure services"
    echo "  redis           Stop only Redis cluster"
    echo "  monitoring      Stop only monitoring services"
    echo "  clean           Stop all and remove data volumes"
    echo "  --help          Show this help message"
    echo
}

# Main execution
main() {
    case ${1:-all} in
        all)
            echo -e "${BLUE}🛑 Stopping Complete Voice Bot System${NC}"
            echo "====================================="
            stop_voice_bot
            stop_infrastructure
            show_status
            ;;
        app)
            echo -e "${BLUE}🛑 Stopping Voice Bot Application${NC}"
            echo "================================="
            stop_voice_bot
            show_status
            ;;
        infrastructure)
            echo -e "${BLUE}🛑 Stopping Infrastructure Services${NC}"
            echo "=================================="
            stop_infrastructure
            show_status
            ;;
        redis)
            echo -e "${BLUE}🛑 Stopping Redis Cluster${NC}"
            echo "========================="
            stop_redis
            show_status
            ;;
        monitoring)
            echo -e "${BLUE}🛑 Stopping Monitoring Services${NC}"
            echo "=============================="
            stop_monitoring
            show_status
            ;;
        clean)
            echo -e "${BLUE}🧹 Stopping and Cleaning All Services${NC}"
            echo "====================================="
            stop_voice_bot
            clean_volumes
            show_status
            ;;
        --help|help)
            show_usage
            ;;
        *)
            print_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
}

# Run main function
main "$@"