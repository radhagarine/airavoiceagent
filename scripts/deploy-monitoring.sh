#!/bin/bash

# Production deployment script for voice bot monitoring
set -e

echo "🚀 Setting up Voice Bot Monitoring Stack..."

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker first:"
    echo "   - If using Colima: run 'colima start'"
    echo "   - If using Docker Desktop: start the application"
    exit 1
fi

echo "✅ Docker is running"

# Create monitoring directory structure
mkdir -p monitoring/grafana/provisioning/datasources
mkdir -p monitoring/grafana/provisioning/dashboards
mkdir -p monitoring/grafana/dashboards
mkdir -p logs
mkdir -p scripts

# Set permissions for Grafana (important for production)
sudo chown -R 472:472 monitoring/grafana/

# Environment setup
if [ ! -f .env ]; then
    echo "Creating .env file..."
    cat > .env << EOF
# Existing environment variables
DAILY_API_KEY=your_daily_api_key
TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
OPENAI_API_KEY=your_openai_api_key
CARTESIA_API_KEY=your_cartesia_api_key
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_service_key
LANCEDB_PATH=/path/to/your/lancedb_data

# Monitoring configuration (production ready)
ENVIRONMENT=production
APP_VERSION=1.0.0
METRICS_ENABLED=true
STRUCTURED_LOGGING_ENABLED=true
LOG_LEVEL=INFO
PUSHGATEWAY_URL=

# Alerting email configuration (update these)
ALERT_EMAIL_FROM=alerts@yourcompany.com
ALERT_EMAIL_TO=team@yourcompany.com
ALERT_EMAIL_PASSWORD=your-app-password
ONCALL_EMAIL=oncall@yourcompany.com
EOF
    echo "Please update the .env file with your actual values"
fi

# Start monitoring stack
echo "🐳 Starting monitoring stack..."
docker-compose up -d

# Wait for services to be ready
echo "⏳ Waiting for services to start..."
sleep 30

# Check services
echo "🔍 Checking service status..."
docker-compose ps

# Display access URLs
echo ""
echo "✅ Monitoring stack deployed successfully!"
echo ""
echo "Access your monitoring services:"
echo "📊 Grafana:     http://localhost:3000 (admin/secure_admin_password_2024)"
echo "📈 Prometheus:  http://localhost:9090"
echo "🔔 Alertmanager: http://localhost:9093"
echo "📤 Pushgateway: http://localhost:9091"
echo ""
echo "Your voice bot metrics: http://localhost:8000/metrics"
echo "Your voice bot health:  http://localhost:8000/health"
echo ""
echo "⚠️  Remember to:"
echo "1. Update alertmanager.yml with your email settings"
echo "2. Configure your firewall for production ports"
echo "3. Set up SSL certificates for HTTPS"
echo "4. Update Grafana admin password in docker-compose.yml"
echo ""
echo "🔒 Security checklist for production:"
echo "- Change default passwords"
echo "- Configure SSL/TLS"
echo "- Set up proper authentication"
echo "- Configure network security groups"
echo "- Set up log rotation"
echo ""
echo "Run 'docker-compose logs -f' to see the logs"