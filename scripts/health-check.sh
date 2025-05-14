#!/bin/bash

# Health check script for monitoring services
set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🏥 Voice Bot Monitoring Health Check"
echo "===================================="

# Check Docker containers
echo -e "\n📦 Docker Container Status:"
docker-compose ps

# Check Prometheus
echo -e "\n📈 Checking Prometheus..."
if curl -s http://localhost:9090/-/ready > /dev/null; then
    echo -e "${GREEN}✅ Prometheus is ready${NC}"
else
    echo -e "${RED}❌ Prometheus is not ready${NC}"
fi

# Check Grafana
echo -e "\n📊 Checking Grafana..."
if curl -s http://localhost:3000/api/health > /dev/null; then
    echo -e "${GREEN}✅ Grafana is ready${NC}"
else
    echo -e "${RED}❌ Grafana is not ready${NC}"
fi

# Check Alertmanager
echo -e "\n🔔 Checking Alertmanager..."
if curl -s http://localhost:9093/-/ready > /dev/null; then
    echo -e "${GREEN}✅ Alertmanager is ready${NC}"
else
    echo -e "${RED}❌ Alertmanager is not ready${NC}"
fi

# Check Voice Bot metrics
echo -e "\n🤖 Checking Voice Bot metrics..."
if curl -s http://localhost:8000/metrics > /dev/null; then
    echo -e "${GREEN}✅ Voice Bot metrics endpoint is accessible${NC}"
    echo "📊 Available metrics:"
    curl -s http://localhost:8000/metrics | grep -E "^# HELP" | head -5
else
    echo -e "${RED}❌ Voice Bot metrics endpoint not accessible${NC}"
fi

# Check Voice Bot health
echo -e "\n🤖 Checking Voice Bot health..."
if curl -s http://localhost:8000/health > /dev/null; then
    echo -e "${GREEN}✅ Voice Bot health endpoint is accessible${NC}"
    echo "🏥 Health status:"
    curl -s http://localhost:8000/health | python3 -m json.tool
else
    echo -e "${RED}❌ Voice Bot health endpoint not accessible${NC}"
fi

# Check disk space
echo -e "\n💾 Checking disk space..."
DISK_USAGE=$(df -h . | awk 'NR==2 {print $5}' | sed 's/%//')
if [ "$DISK_USAGE" -gt 80 ]; then
    echo -e "${RED}⚠️  Disk usage is high: ${DISK_USAGE}%${NC}"
else
    echo -e "${GREEN}✅ Disk usage is OK: ${DISK_USAGE}%${NC}"
fi

# Check memory usage
echo -e "\n🧠 Checking memory usage..."
MEMORY_USAGE=$(free | awk '/Mem:/ {printf "%.0f", $3/$2 * 100}')
if [ "$MEMORY_USAGE" -gt 80 ]; then
    echo -e "${RED}⚠️  Memory usage is high: ${MEMORY_USAGE}%${NC}"
else
    echo -e "${GREEN}✅ Memory usage is OK: ${MEMORY_USAGE}%${NC}"
fi

# Check log files
echo -e "\n📋 Recent logs:"
echo "Last 5 lines from docker-compose logs:"
docker-compose logs --tail=5

echo -e "\n✅ Health check completed!"