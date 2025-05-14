# Voice Bot Production Monitoring Guide

## 🏗️ Architecture Overview

The production monitoring stack includes:

- **Prometheus**: Metrics collection and storage ✅
- **Grafana**: Visualization and dashboards ✅  
- **Alertmanager**: Alert routing and notifications ⚠️ (Optional - see alternatives below)
- **Pushgateway**: For batch job metrics (optional) ✅

## 🚀 Quick Start

### 1. Initial Setup

```bash
# Deploy monitoring stack (Prometheus + Grafana work reliably)
# Note: Alertmanager may require additional configuration
docker-compose up -d prometheus grafana pushgateway

# Enable monitoring in your voice bot
# In .env file:
METRICS_ENABLED=true
STRUCTURED_LOGGING_ENABLED=true

# Start your voice bot
python server.py
```

### 2. Access Services

- **Grafana**: http://localhost:3000 (admin/secure_admin_password_2024)
- **Prometheus**: http://localhost:9090
- **Voice Bot Metrics**: http://localhost:8000/metrics

## 🚨 Alert Solutions

### Option 1: Simple Email Alerts (Recommended for Production)

Since Alertmanager can be complex, use Grafana's built-in alerting:

1. **Enable Grafana Unified Alerting**:
   ```yaml
   # In docker-compose.yml, add to Grafana environment:
   - GF_UNIFIED_ALERTING_ENABLED=true
   - GF_ALERTING_ENABLED=true
   ```

2. **Configure SMTP in Grafana**:
   ```yaml
   # Add these to Grafana environment:
   - GF_SMTP_ENABLED=true
   - GF_SMTP_HOST=smtp.gmail.com:587
   - GF_SMTP_USER=your-email@gmail.com
   - GF_SMTP_PASSWORD=your-app-password
   - GF_SMTP_FROM_ADDRESS=alerts@yourcompany.com
   ```

3. **Create alerts in Grafana UI**:
   - Go to Alerting > Alert Rules
   - Create rules for high error rate, memory usage, etc.
   - Set up notification channels (email, Slack, etc.)

### Option 2: Alternative Alert Tools

**A. PagerDuty Integration**:
```yaml
# Add to Grafana environment
- GF_INSTALL_PLUGINS=grafana-pagerduty-datasource
```

**B. Slack Webhooks**:
```yaml
# Add to Grafana environment  
- GF_INSTALL_PLUGINS=grafana-slack-webhook
```

**C. Cloud-based Monitoring**:
- Use Grafana Cloud (free tier available)
- Use DataDog, New Relic, or similar services
- These provide alerting out-of-the-box

## 📊 Production-Ready Key Metrics

The system tracks:

- **Operation Duration**: Response times for all operations
- **Success Rates**: Success/failure rates by operation  
- **Business Lookups**: Success/failure rates for business lookups
- **System Resources**: Memory and CPU usage
- **Active Calls**: Current number of active calls
- **Error Rates**: Errors by type and operation

## 🔒 Production Security Hardening

### 1. Change Default Credentials

```yaml
# In docker-compose.yml
environment:
  - GF_SECURITY_ADMIN_PASSWORD=your_secure_password_here
  - GF_SECURITY_SECRET_KEY=very_long_random_secret_key
  - GF_USERS_ALLOW_SIGN_UP=false
```

### 2. Enable HTTPS with Reverse Proxy

```yaml
# Add nginx service to docker-compose.yml
nginx:
  image: nginx:alpine
  ports:
    - "443:443"
    - "80:80"
  volumes:
    - ./nginx.conf:/etc/nginx/nginx.conf
    - ./ssl:/etc/ssl/certs
  depends_on:
    - grafana
    - prometheus
```

### 3. Network Isolation

```yaml
# Add to docker-compose.yml
networks:
  monitoring:
    internal: true  # Isolate internal traffic
  public:
    # Only expose what's needed
```

## 📁 Backup Strategy

### Automated Backups

```bash
# Create backup script
#!/bin/bash
BACKUP_DIR="./backups/$(date +%Y%m%d_%H%M%S)"
mkdir -p $BACKUP_DIR

# Backup Prometheus data
docker run --rm \
  -v voice-bot_prometheus-data:/data \
  -v $BACKUP_DIR:/backup \
  alpine tar czf /backup/prometheus.tar.gz /data

# Backup Grafana data  
docker run --rm \
  -v voice-bot_grafana-data:/data \
  -v $BACKUP_DIR:/backup \
  alpine tar czf /backup/grafana.tar.gz /data
```

## 🔍 Monitoring Without Alertmanager

Since Alertmanager can be complex, here's how to get production monitoring:

### Core Monitoring (Works Reliably)

1. **Prometheus** collects all metrics ✅
2. **Grafana** provides dashboards and visual alerts ✅
3. **Grafana Alerting** replaces Alertmanager for notifications

### Production Setup without Alertmanager

```yaml
# Simplified docker-compose for production
services:
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus-data:/prometheus
    restart: unless-stopped
    
  grafana:
    image: grafana/grafana:latest  
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD}
      - GF_SMTP_ENABLED=true
      - GF_SMTP_HOST=${SMTP_HOST}
      - GF_SMTP_USER=${SMTP_USER}
      - GF_SMTP_PASSWORD=${SMTP_PASSWORD}
      - GF_UNIFIED_ALERTING_ENABLED=true
    volumes:
      - grafana-data:/var/lib/grafana
    restart: unless-stopped
    depends_on:
      - prometheus
```

## 🔧 Production Environment Configuration

```bash
# Production .env additions
ENVIRONMENT=production
METRICS_ENABLED=true
STRUCTURED_LOGGING_ENABLED=true

# Grafana configuration
GRAFANA_PASSWORD=your_secure_password
SMTP_HOST=smtp.gmail.com:587
SMTP_USER=alerts@yourcompany.com
SMTP_PASSWORD=your_app_password

# Optional: Push metrics to external services
PUSHGATEWAY_URL=https://your-pushgateway.com
```

## 📈 Scaling and High Availability

### Multiple Prometheus Instances

```yaml
# For high availability
prometheus-1:
  # Primary instance
prometheus-2:  
  # Replica with different storage
```

### External Storage

```yaml
# Use cloud storage for persistence
volumes:
  prometheus-data:
    driver: <cloud-storage-driver>
    driver_opts:
      # Cloud-specific options
```

## 🛠️ Troubleshooting Production Issues

### Health Check Script

```bash
#!/bin/bash
# Production health check
echo "Checking services..."

# Check Prometheus
curl -f http://localhost:9090/-/ready || echo "Prometheus DOWN"

# Check Grafana
curl -f http://localhost:3000/api/health || echo "Grafana DOWN"

# Check Voice Bot
curl -f http://localhost:8000/health || echo "Voice Bot DOWN"

# Check metrics collection
if ! curl -s http://localhost:8000/metrics | grep -q "operation_total"; then
    echo "Metrics not being collected"
fi
```

### Common Production Issues

1. **High Memory Usage**:
   ```yaml
   # Set memory limits
   deploy:
     resources:
       limits:
         memory: 2G
   ```

2. **Disk Space Issues**:
   ```yaml
   # Configure retention
   command:
     - '--storage.tsdb.retention.time=30d'
     - '--storage.tsdb.retention.size=10GB'
   ```

3. **Query Performance**:
   ```yaml
   # Optimize Prometheus
   command:
     - '--query.max-concurrency=20'
     - '--query.timeout=120s'
   ```

## 🚀 Alternative Production Solutions

If self-hosting becomes complex:

### 1. Grafana Cloud
- Managed Prometheus + Grafana
- Built-in alerting
- Free tier available
- Easy migration from self-hosted

### 2. Application Performance Monitoring (APM)
- **DataDog**: Full APM with Python integration
- **New Relic**: Easy setup with auto-instrumentation  
- **Elastic APM**: Open source option

### 3. Cloud Provider Solutions
- **AWS CloudWatch**: Native AWS integration
- **Google Cloud Monitoring**: For GCP deployments
- **Azure Monitor**: For Azure environments

## 📋 Production Checklist

Before going live:

- [ ] Change all default passwords
- [ ] Set up HTTPS with valid certificates
- [ ] Configure backup strategy
- [ ] Set up health checks
- [ ] Configure alerts (Grafana or external service)
- [ ] Test alert delivery
- [ ] Set up log rotation
- [ ] Configure resource limits
- [ ] Test disaster recovery
- [ ] Document runbooks

## 🎯 Recommended Production Path

1. **Start with core monitoring** (Prometheus + Grafana)
2. **Use Grafana's built-in alerting** instead of Alertmanager
3. **Set up automated backups**
4. **Configure HTTPS and security**
5. **Consider migrating to managed service** as you scale

## 📞 Production Support Strategy

### Alert Response Levels

- **P1 (Critical)**: Service down, major functionality broken
- **P2 (High)**: Performance degraded, partial outage  
- **P3 (Medium)**: Minor issues, workarounds available
- **P4 (Low)**: Cosmetic issues, feature requests

### Escalation Path

1. **Grafana alerts** → Primary on-call
2. **No response in 15 minutes** → Escalate to secondary
3. **No response in 30 minutes** → Escalate to manager
4. **Critical P1 issues** → Immediate management notification

This production guide provides a reliable path to production monitoring without getting stuck on Alertmanager configuration issues. The core monitoring (Prometheus + Grafana) is rock-solid and provides everything you need for production observability.