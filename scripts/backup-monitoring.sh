#!/bin/bash

# Backup script for monitoring data
set -e

BACKUP_DIR="./backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_PATH="${BACKUP_DIR}/monitoring_backup_${DATE}"

echo "🔄 Starting monitoring backup..."

# Create backup directory
mkdir -p "${BACKUP_PATH}"

# Backup Prometheus data
echo "📈 Backing up Prometheus data..."
docker-compose exec -T prometheus tar -czf /tmp/prometheus_backup.tar.gz /prometheus
docker cp voice-bot-prometheus:/tmp/prometheus_backup.tar.gz "${BACKUP_PATH}/prometheus_data.tar.gz"

# Backup Grafana data
echo "📊 Backing up Grafana data..."
docker-compose exec -T grafana tar -czf /tmp/grafana_backup.tar.gz /var/lib/grafana
docker cp voice-bot-grafana:/tmp/grafana_backup.tar.gz "${BACKUP_PATH}/grafana_data.tar.gz"

# Backup configuration files
echo "⚙️  Backing up configuration files..."
cp -r monitoring "${BACKUP_PATH}/config"
cp docker-compose.yml "${BACKUP_PATH}/"
cp .env "${BACKUP_PATH}/env_backup"

# Create backup archive
echo "📦 Creating final backup archive..."
tar -czf "${BACKUP_DIR}/monitoring_backup_${DATE}.tar.gz" -C "${BACKUP_DIR}" "monitoring_backup_${DATE}"
rm -rf "${BACKUP_PATH}"

# Clean old backups (keep last 7)
echo "🧹 Cleaning old backups..."
ls -t "${BACKUP_DIR}"/monitoring_backup_*.tar.gz | tail -n +8 | xargs rm -f

echo "✅ Backup completed: ${BACKUP_DIR}/monitoring_backup_${DATE}.tar.gz"
echo "📂 Backup size: $(du -h ${BACKUP_DIR}/monitoring_backup_${DATE}.tar.gz | cut -f1)"