# Voice Bot Complete Startup Guide

## Overview
This guide shows you how to start all services for the voice bot application with the new cache implementation.

## Quick Start (Recommended)

### 1. One-Command Startup
```bash
# Start everything at once
docker-compose up -d

# This will start:
# - Redis cluster (3 nodes)
# - Prometheus monitoring
# - Grafana dashboard
# - Alertmanager (if configured)
```

### 2. Start Voice Bot Application
```bash
# Activate virtual environment
source venv/bin/activate

# Start the webhook server (cache initializes automatically)
python server.py
```

## Detailed Startup Process

### Step 1: Verify Environment Setup

```bash
# Check if .env file exists with cache configuration
cat .env

# Should include:
# CACHE_L1_SIZE=500
# CACHE_BUSINESS_TTL=1800
# CACHE_KNOWLEDGE_TTL=3600
# CACHE_COMPRESSION=true
# METRICS_ENABLED=true
```

### Step 2: Start Infrastructure Services

```bash
# Method 1: Start all services at once
docker-compose up -d

# Method 2: Start services individually
docker-compose up -d redis-1 redis-2 redis-3    # Redis cluster
docker-compose up -d prometheus                  # Metrics collection
docker-compose up -d grafana                    # Dashboard
docker-compose up -d alertmanager               # Alerts (optional)
```

### Step 3: Verify Redis Cluster

```bash
# Check Redis cluster status
./scripts/redis-cluster.sh status

# Test Redis cluster
./scripts/redis-cluster.sh test
```

### Step 4: Start Voice Bot Application

```bash
# Install/update dependencies
pip install -r requirements.txt

# Start the main application
python server.py
```

## Service Access URLs

Once everything is running, you can access:

- **Voice Bot API**: http://localhost:8000
- **Health Check**: http://localhost:8000/health
- **Cache Health**: http://localhost:8000/cache/health
- **Cache Stats**: http://localhost:8000/cache/stats
- **Metrics**: http://localhost:8000/metrics
- **Grafana Dashboard**: http://localhost:3000 (admin/secure_admin_password_2024)
- **Prometheus**: http://localhost:9090
- **Alertmanager**: http://localhost:9093

## Verification Steps

### 1. Check All Services

```bash
# Check Docker containers
docker-compose ps

# Should show all services as "Up"
```

### 2. Verify Cache System

```bash
# Test cache endpoint
curl http://localhost:8000/cache/health

# Check cache statistics
curl http://localhost:8000/cache/stats
```

### 3. Test Voice Bot

```bash
# Test webhook endpoint
curl http://localhost:8000/test-call

# Check overall health
curl http://localhost:8000/health
```

## Troubleshooting

### Services Not Starting

```bash
# Check logs for specific service
docker-compose logs redis-1
docker-compose logs prometheus
docker-compose logs grafana

# Restart problematic service
docker-compose restart redis-1
```

### Cache Issues

```bash
# Check Redis cluster
./scripts/redis-cluster.sh status
./scripts/redis-cluster.sh logs

# Restart Redis cluster
./scripts/redis-cluster.sh restart
```

### Application Issues

```bash
# Check application logs
tail -f logs/voice-bot.log

# Restart application
python server.py
```

## Alternative Startup Scripts

### Option 1: Create a Startup Script

Create `scripts/start-all.sh`:

```bash
#!/bin/bash
set -e

echo "🚀 Starting Voice Bot Services..."

# Start infrastructure
echo "Starting infrastructure services..."
docker-compose up -d

# Wait for services
echo "Waiting for services to be ready..."
sleep 30

# Verify Redis cluster
echo "Verifying Redis cluster..."
./scripts/redis-cluster.sh status

# Start application
echo "Starting voice bot application..."
source venv/bin/activate
python server.py
```

### Option 2: Using Docker for the App Too

Update `docker-compose.yml` to include the voice bot:

```yaml
  voice-bot:
    build: .
    container_name: voice-bot-app
    ports:
      - "8000:8000"
    environment:
      - METRICS_ENABLED=true
    depends_on:
      - redis-1
      - redis-2
      - redis-3
      - prometheus
    volumes:
      - .:/app
    networks:
      - voice-bot-network
```

Then start everything with:
```bash
docker-compose up -d
```

## Development Workflow

### For Development

```bash
# Start infrastructure only
docker-compose up -d redis-1 redis-2 redis-3 prometheus grafana

# Run app in development mode
python server.py
```

### For Production

```bash
# Start everything including monitoring
docker-compose up -d

# Run app with proper logging
python server.py >> logs/voice-bot.log 2>&1 &
```

## Monitoring Your Services

### Real-time Monitoring

```bash
# Monitor Redis cluster
./scripts/redis-cluster.sh monitor

# Monitor all Docker services
docker-compose logs -f

# Monitor specific service
docker-compose logs -f redis-1
```

### Check Service Health

```bash
# Quick health check script
#!/bin/bash
echo "=== Service Health Check ==="
echo "Redis Cluster: $(curl -s http://localhost:8000/cache/health | jq -r .status)"
echo "Voice Bot: $(curl -s http://localhost:8000/health | jq -r .status)"
echo "Prometheus: $(curl -s http://localhost:9090/-/ready && echo 'healthy' || echo 'unhealthy')"
echo "Grafana: $(curl -s http://localhost:3000/api/health | jq -r .status)"
```

## Environment-Specific Configurations

### Local Development

```bash
# .env for development
ENVIRONMENT=development
METRICS_ENABLED=true
CACHE_L1_SIZE=500
LOG_LEVEL=DEBUG
```

### Production

```bash
# .env for production
ENVIRONMENT=production
METRICS_ENABLED=true
CACHE_L1_SIZE=1000
LOG_LEVEL=INFO
STRUCTURED_LOGGING_ENABLED=true
```

## Complete Service Overview

When everything is running, you'll have:

1. **Redis Cluster** (3 nodes) - Cache storage
2. **Prometheus** - Metrics collection
3. **Grafana** - Monitoring dashboard
4. **Voice Bot Application** - Main application with cache integration
5. **Alertmanager** (optional) - Alert management

This setup provides a complete, production-ready voice bot system with comprehensive caching, monitoring, and observability.