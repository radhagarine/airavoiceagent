#!/bin/bash

# Voice Bot Complete Startup Script
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# Function to print colored output
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

print_info() {
    echo -e "${PURPLE}ℹ${NC} $1"
}

# Check if Docker is running
check_docker() {
    print_step "Checking Docker status..."
    if ! docker info > /dev/null 2>&1; then
        print_error "Docker is not running. Please start Docker first."
        exit 1
    fi
    print_success "Docker is running"
}

# Check if .env file exists
check_env() {
    print_step "Checking environment configuration..."
    if [ ! -f ".env" ]; then
        print_warning ".env file not found. Creating from .env.example..."
        if [ -f ".env.example" ]; then
            cp .env.example .env
            print_info "Please update .env with your actual values"
        else
            print_error ".env.example not found. Please create .env file manually."
            exit 1
        fi
    fi
    print_success "Environment configuration found"
}

# Install Python dependencies
install_dependencies() {
    print_step "Installing Python dependencies..."
    
    # Check if virtual environment exists
    if [ ! -d "venv" ]; then
        print_step "Creating virtual environment..."
        python3 -m venv venv
    fi
    
    # Activate virtual environment
    source venv/bin/activate
    
    # Install dependencies
    pip install -r requirements.txt > /dev/null 2>&1
    print_success "Dependencies installed"
}

# Start infrastructure services
start_infrastructure() {
    print_step "Starting infrastructure services..."
    
    # Start all infrastructure services
    docker-compose up -d redis-1 redis-2 redis-3 prometheus grafana
    
    print_success "Infrastructure services started"
    
    # Wait for services to be ready
    print_step "Waiting for services to be ready..."
    sleep 10
    
    # Initialize Redis cluster
    print_step "Initializing Redis cluster..."
    docker-compose up redis-cluster-init > /dev/null 2>&1
    
    # Verify Redis cluster
    print_step "Verifying Redis cluster..."
    sleep 5
    
    if ./scripts/redis-cluster.sh status > /dev/null 2>&1; then
        print_success "Redis cluster is ready"
    else
        print_warning "Redis cluster may need more time to initialize"
    fi
}

# Start voice bot application
start_voice_bot() {
    print_step "Starting voice bot application..."
    
    # Activate virtual environment
    source venv/bin/activate
    
    # Start the server in background
    nohup python server.py > voice-bot.log 2>&1 &
    VOICE_BOT_PID=$!
    
    # Save PID for later
    echo $VOICE_BOT_PID > voice-bot.pid
    
    # Wait a moment and check if it's running
    sleep 3
    if kill -0 $VOICE_BOT_PID 2>/dev/null; then
        print_success "Voice bot application started (PID: $VOICE_BOT_PID)"
    else
        print_error "Failed to start voice bot application"
        exit 1
    fi
}

# Verify all services
verify_services() {
    print_step "Verifying all services..."
    
    # Check Docker services
    print_info "Docker services status:"
    docker-compose ps
    
    # Wait for voice bot to be fully ready
    print_step "Waiting for voice bot to be fully ready..."
    for i in {1..30}; do
        if curl -s http://localhost:8000/health > /dev/null 2>&1; then
            break
        fi
        sleep 1
    done
    
    # Health checks
    echo
    print_info "Service health checks:"
    
    # Voice Bot Health
    if curl -s http://localhost:8000/health | jq -r .status 2>/dev/null | grep -q "healthy"; then
        print_success "Voice Bot: Healthy"
    else
        print_warning "Voice Bot: Not responding (may still be starting)"
    fi
    
    # Cache Health
    if curl -s http://localhost:8000/cache/health 2>/dev/null | jq -r .status 2>/dev/null | grep -q "healthy"; then
        print_success "Cache System: Healthy"
    else
        print_warning "Cache System: Not fully ready"
    fi
    
    # Prometheus
    if curl -s http://localhost:9090/-/ready >/dev/null 2>&1; then
        print_success "Prometheus: Ready"
    else
        print_warning "Prometheus: Not ready"
    fi
    
    # Grafana
    if curl -s http://localhost:3000/api/health >/dev/null 2>&1; then
        print_success "Grafana: Ready"
    else
        print_warning "Grafana: Not ready"
    fi
}

# Show access information
show_access_info() {
    echo
    print_step "Service Access Information"
    echo "=================================="
    print_info "Voice Bot API:       http://localhost:8000"
    print_info "Health Check:        http://localhost:8000/health"
    print_info "Cache Health:        http://localhost:8000/cache/health"
    print_info "Cache Statistics:    http://localhost:8000/cache/stats"
    print_info "Metrics:             http://localhost:8000/metrics"
    echo
    print_info "Grafana Dashboard:   http://localhost:3000"
    print_info "  Username: admin"
    print_info "  Password: secure_admin_password_2024"
    echo
    print_info "Prometheus:          http://localhost:9090"
    print_info "Alertmanager:        http://localhost:9093"
    echo
    print_info "Redis Cluster:"
    print_info "  Node 1: localhost:7001"
    print_info "  Node 2: localhost:7002"
    print_info "  Node 3: localhost:7003"
    echo
    print_success "All services are running!"
    echo
    print_info "Logs:"
    print_info "  Voice Bot: tail -f voice-bot.log"
    print_info "  Redis: ./scripts/redis-cluster.sh logs"
    print_info "  All Docker: docker-compose logs -f"
    echo
    print_info "To stop all services: ./scripts/stop-all.sh"
}

# Show usage if no argument provided
show_usage() {
    echo -e "${BLUE}Voice Bot Startup Script${NC}"
    echo "Usage: $0 [OPTIONS]"
    echo
    echo "Options:"
    echo "  all             Start all services (default)"
    echo "  infrastructure  Start only infrastructure (Redis, Prometheus, Grafana)"
    echo "  app             Start only the voice bot application"
    echo "  verify          Verify all services are running"
    echo "  --dev           Development mode (start app in foreground)"
    echo "  --help          Show this help message"
    echo
}

# Clean shutdown function
cleanup() {
    print_warning "Stopping services..."
    if [ -f voice-bot.pid ]; then
        PID=$(cat voice-bot.pid)
        if kill -0 $PID 2>/dev/null; then
            kill $PID
            print_success "Voice bot stopped"
        fi
        rm voice-bot.pid
    fi
}

# Trap signals for clean shutdown
trap cleanup EXIT

# Main execution
main() {
    case ${1:-all} in
        all)
            echo -e "${PURPLE}🚀 Starting Complete Voice Bot System${NC}"
            echo "======================================"
            check_docker
            check_env
            install_dependencies
            start_infrastructure
            start_voice_bot
            verify_services
            show_access_info
            ;;
        infrastructure)
            echo -e "${PURPLE}🔧 Starting Infrastructure Services${NC}"
            echo "=================================="
            check_docker
            start_infrastructure
            verify_services
            ;;
        app)
            echo -e "${PURPLE}🤖 Starting Voice Bot Application${NC}"
            echo "================================="
            install_dependencies
            if [ "$2" == "--dev" ]; then
                print_step "Starting in development mode..."
                source venv/bin/activate
                python server.py
            else
                start_voice_bot
                verify_services
            fi
            ;;
        verify)
            verify_services
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