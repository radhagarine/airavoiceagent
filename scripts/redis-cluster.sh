#!/bin/bash

# Redis Cluster Setup Script for Voice Bot
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}Voice Bot Redis Cluster Manager${NC}"
echo "================================="

# Function to print colored output
print_status() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# Check if Docker is running
check_docker() {
    echo "Checking Docker status..."
    if ! docker info > /dev/null 2>&1; then
        print_error "Docker is not running. Please start Docker first."
        echo "  - On macOS with Colima: run 'colima start'"
        echo "  - On other systems: start Docker Desktop"
        exit 1
    fi
    print_status "Docker is running"
}

# Start Redis cluster
start_cluster() {
    echo -e "\n${BLUE}Starting Redis Cluster...${NC}"
    
    # Start Redis nodes
    echo "Starting Redis nodes..."
    docker-compose up -d redis-1 redis-2 redis-3
    
    # Wait for nodes to be ready
    echo "Waiting for Redis nodes to be ready..."
    sleep 10
    
    # Check if nodes are running
    for i in {1..3}; do
        if docker-compose ps redis-$i | grep -q "Up"; then
            print_status "Redis node $i is running"
        else
            print_error "Redis node $i failed to start"
            exit 1
        fi
    done
    
    # Initialize cluster
    echo "Initializing Redis cluster..."
    docker-compose up redis-cluster-init
    
    # Verify cluster
    echo "Verifying cluster setup..."
    sleep 5
    
    if verify_cluster; then
        print_status "Redis cluster is ready!"
        echo -e "\n${GREEN}Cluster nodes:${NC}"
        echo "  - redis-1: localhost:7001"
        echo "  - redis-2: localhost:7002"
        echo "  - redis-3: localhost:7003"
        echo -e "\n${GREEN}You can now start your voice bot application.${NC}"
    else
        print_warning "Cluster may not be properly configured. Check logs for details."
    fi
}

# Stop Redis cluster
stop_cluster() {
    echo -e "\n${BLUE}Stopping Redis Cluster...${NC}"
    docker-compose stop redis-1 redis-2 redis-3 redis-cluster-init
    print_status "Redis cluster stopped"
}

# Remove cluster data
reset_cluster() {
    echo -e "\n${BLUE}Resetting Redis Cluster...${NC}"
    read -p "This will delete all Redis data. Are you sure? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        docker-compose down
        docker volume rm -f voice-bot_redis-1-data voice-bot_redis-2-data voice-bot_redis-3-data 2>/dev/null || true
        print_status "Redis cluster data removed"
        echo "Run '$0 start' to create a fresh cluster"
    else
        echo "Reset cancelled"
    fi
}

# Verify cluster status
verify_cluster() {
    # Check if all nodes are in cluster mode
    local nodes_ok=0
    
    for port in 7001 7002 7003; do
        node_num=$(echo $port | sed 's/700//')
        if docker exec voice-bot-redis-$node_num redis-cli -p $port cluster nodes > /dev/null 2>&1; then
            nodes_ok=$((nodes_ok + 1))
        fi
    done
    
    if [ $nodes_ok -eq 3 ]; then
        return 0
    else
        return 1
    fi
}

# Show cluster status
status_cluster() {
    echo -e "\n${BLUE}Redis Cluster Status${NC}"
    echo "===================="
    
    # Check Docker containers
    echo -e "\n${YELLOW}Container Status:${NC}"
    docker-compose ps redis-1 redis-2 redis-3
    
    # Check cluster info
    echo -e "\n${YELLOW}Cluster Information:${NC}"
    for i in {1..3}; do
        port=$((7000 + i))
        container="voice-bot-redis-$i"
        
        if docker ps | grep -q $container; then
            echo -e "${GREEN}Node $i (port $port):${NC}"
            docker exec $container redis-cli -p $port cluster info | grep -E "cluster_state|cluster_slots_assigned|cluster_known_nodes"
        else
            echo -e "${RED}Node $i (port $port): Not running${NC}"
        fi
    done
    
    # Show cluster nodes
    echo -e "\n${YELLOW}Cluster Nodes:${NC}"
    if docker ps | grep -q voice-bot-redis-1; then
        docker exec voice-bot-redis-1 redis-cli -p 7001 cluster nodes
    else
        print_error "No Redis nodes running"
    fi
}

# Show logs
logs_cluster() {
    echo -e "\n${BLUE}Redis Cluster Logs${NC}"
    echo "=================="
    docker-compose logs redis-1 redis-2 redis-3
}

# Test cluster
test_cluster() {
    echo -e "\n${BLUE}Testing Redis Cluster${NC}"
    echo "===================="
    
    if ! docker ps | grep -q voice-bot-redis-1; then
        print_error "Redis cluster is not running"
        return 1
    fi
    
    # Test basic operations
    echo "Testing basic operations..."
    
    # Set a test value
    docker exec voice-bot-redis-1 redis-cli -p 7001 set test_key "Hello Redis Cluster" > /dev/null
    
    # Get the value from different nodes
    for i in {1..3}; do
        port=$((7000 + i))
        value=$(docker exec voice-bot-redis-$i redis-cli -p $port get test_key 2>/dev/null)
        if [ "$value" = "Hello Redis Cluster" ]; then
            print_status "Node $i can read the test value"
        else
            print_error "Node $i cannot read the test value"
        fi
    done
    
    # Clean up test key
    docker exec voice-bot-redis-1 redis-cli -p 7001 del test_key > /dev/null
    
    # Test key distribution
    echo -e "\nTesting key distribution..."
    for i in {1..10}; do
        docker exec voice-bot-redis-1 redis-cli -p 7001 set "test_key_$i" "value_$i" > /dev/null
    done
    
    echo "Keys per node:"
    for i in {1..3}; do
        port=$((7000 + i))
        key_count=$(docker exec voice-bot-redis-$i redis-cli -p $port keys "test_key_*" 2>/dev/null | wc -l)
        echo "  Node $i: $key_count keys"
    done
    
    # Clean up test keys
    docker exec voice-bot-redis-1 redis-cli -p 7001 eval "return redis.call('del', unpack(redis.call('keys', 'test_key_*')))" 0 > /dev/null 2>&1
    
    print_status "Cluster test completed successfully"
}

# Monitor cluster
monitor_cluster() {
    echo -e "\n${BLUE}Monitoring Redis Cluster${NC}"
    echo "========================"
    echo "Press Ctrl+C to stop monitoring"
    
    while true; do
        clear
        echo -e "${BLUE}Redis Cluster Monitor - $(date)${NC}"
        echo "====================================="
        
        # Show brief status
        for i in {1..3}; do
            port=$((7000 + i))
            container="voice-bot-redis-$i"
            
            if docker ps | grep -q $container; then
                # Get memory usage and connections
                memory=$(docker exec $container redis-cli -p $port info memory 2>/dev/null | grep used_memory_human | cut -d: -f2 | tr -d '\r')
                connections=$(docker exec $container redis-cli -p $port info clients 2>/dev/null | grep connected_clients | cut -d: -f2 | tr -d '\r')
                keys=$(docker exec $container redis-cli -p $port dbsize 2>/dev/null)
                
                echo -e "${GREEN}Node $i (port $port):${NC} Memory: $memory, Connections: $connections, Keys: $keys"
            else
                echo -e "${RED}Node $i (port $port): Offline${NC}"
            fi
        done
        
        # Show cluster state
        echo -e "\n${YELLOW}Cluster State:${NC}"
        if docker ps | grep -q voice-bot-redis-1; then
            state=$(docker exec voice-bot-redis-1 redis-cli -p 7001 cluster info 2>/dev/null | grep cluster_state | cut -d: -f2 | tr -d '\r')
            slots=$(docker exec voice-bot-redis-1 redis-cli -p 7001 cluster info 2>/dev/null | grep cluster_slots_assigned | cut -d: -f2 | tr -d '\r')
            nodes=$(docker exec voice-bot-redis-1 redis-cli -p 7001 cluster info 2>/dev/null | grep cluster_known_nodes | cut -d: -f2 | tr -d '\r')
            
            echo "State: $state, Slots: $slots/16384, Nodes: $nodes"
        fi
        
        sleep 2
    done
}

# Show help
show_help() {
    echo -e "\n${BLUE}Redis Cluster Manager - Usage${NC}"
    echo "============================="
    echo
    echo "Commands:"
    echo "  start     - Start the Redis cluster"
    echo "  stop      - Stop the Redis cluster"
    echo "  restart   - Restart the Redis cluster"
    echo "  reset     - Reset cluster data (WARNING: deletes all data)"
    echo "  status    - Show cluster status"
    echo "  logs      - Show cluster logs"
    echo "  test      - Test cluster functionality"
    echo "  monitor   - Monitor cluster in real-time"
    echo "  help      - Show this help message"
    echo
    echo "Examples:"
    echo "  $0 start     # Start the cluster"
    echo "  $0 status    # Check cluster status"
    echo "  $0 test      # Test cluster operations"
    echo "  $0 monitor   # Monitor cluster in real-time"
    echo
    echo "Notes:"
    echo "  - Make sure Docker is running before using this script"
    echo "  - The cluster uses ports 7001, 7002, and 7003"
    echo "  - Data is persisted in Docker volumes"
    echo
}

# Cleanup function for graceful exit
cleanup() {
    echo -e "\n${YELLOW}Monitoring stopped${NC}"
    exit 0
}

# Trap Ctrl+C for monitor function
trap cleanup SIGINT

# Main script logic
main() {
    check_docker
    
    case ${1:-help} in
        start)
            start_cluster
            ;;
        stop)
            stop_cluster
            ;;
        restart)
            echo -e "${BLUE}Restarting Redis Cluster...${NC}"
            stop_cluster
            sleep 3
            start_cluster
            ;;
        reset)
            reset_cluster
            ;;
        status)
            status_cluster
            ;;
        logs)
            logs_cluster
            ;;
        test)
            test_cluster
            ;;
        monitor)
            monitor_cluster
            ;;
        help|*)
            show_help
            ;;
    esac
}

# Check if script is being sourced or executed
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi