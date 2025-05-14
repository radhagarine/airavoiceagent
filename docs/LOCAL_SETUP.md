# Voice Bot Local Development Setup

## Prerequisites

1. **Python 3.8+** installed
2. **Docker and Docker Compose** (or Colima on macOS)
3. **Git** for cloning the repository
4. **Twilio account** with phone number
5. **Daily.co account** with API key
6. **OpenAI API key**
7. **Cartesia API key**
8. **Supabase account** (optional, for business lookup)

## Quick Start

### 1. Clone and Setup Python Environment

```bash
# Clone the repository
git clone <your-repo-url>
cd voice-bot

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Copy the example environment file and configure it:

```bash
# Copy the example file
cp .env.example .env

# Edit .env with your actual values
```

Required variables in `.env`:

```bash
# Required API Keys
DAILY_API_KEY=your_daily_api_key
TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
OPENAI_API_KEY=your_openai_api_key
CARTESIA_API_KEY=your_cartesia_api_key

# Optional (for business lookup)
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_service_key
LANCEDB_PATH=/path/to/your/lancedb_data

# Monitoring (optional - disabled by default)
METRICS_ENABLED=false
STRUCTURED_LOGGING_ENABLED=false
```

### 3. Start the Voice Bot

```bash
# Start the webhook server
python server.py
```

The server will start on http://localhost:8000

### 4. Configure Twilio Webhook

1. Go to your Twilio Console
2. Navigate to Phone Numbers > Manage > Active numbers
3. Click on your Twilio number
4. In the "Voice Configuration" section:
   - Set "A call comes in" webhook to: `http://your-ngrok-url.ngrok.io/call`
   - Method: HTTP POST

For local testing, use ngrok:

```bash
# Install ngrok: https://ngrok.com/download
# Start ngrok tunnel
ngrok http 8000

# Use the provided HTTPS URL in Twilio webhook
```

### 5. Test the Setup

1. Call your Twilio number
2. You should hear: "Please wait while we connect you to our assistant..."
3. After a brief hold, you'll be connected to the AI voice bot

## Optional: Enable Monitoring

### Start Monitoring Stack

```bash
# Make scripts executable
chmod +x scripts/*.sh

# Start monitoring (Prometheus + Grafana)
docker-compose up -d prometheus grafana

# Enable monitoring in .env
METRICS_ENABLED=true
STRUCTURED_LOGGING_ENABLED=true

# Restart voice bot
python server.py
```

### Access Monitoring

- **Grafana**: http://localhost:3000 (admin/secure_admin_password_2024)
- **Prometheus**: http://localhost:9090
- **Voice Bot Metrics**: http://localhost:8000/metrics
- **Voice Bot Health**: http://localhost:8000/health

## Troubleshooting

### Common Issues

1. **"Cannot connect to Docker daemon"**
   ```bash
   # On macOS with Colima
   colima start
   
   # On other systems, start Docker Desktop
   ```

2. **"ImportError" when starting server**
   ```bash
   # Make sure virtual environment is activated
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Calls not connecting**
   - Verify Twilio webhook URL is correct
   - Check ngrok is still running
   - Verify all API keys are correct in .env

4. **No metrics in Grafana**
   - Ensure METRICS_ENABLED=true in .env
   - Check Prometheus targets: http://localhost:9090/targets
   - Verify voice bot is accessible: http://localhost:8000/health

### Development Tips

1. **Use ngrok for stable testing**:
   ```bash
   # Get a stable subdomain (requires ngrok account)
   ngrok http 8000 --subdomain=your-voice-bot
   ```

2. **Monitor logs**:
   ```bash
   # Voice bot logs
   python server.py

   # Docker logs
   docker-compose logs -f
   ```

3. **Test business lookup** (if using Supabase):
   ```bash
   python debug_phone.py
   ```

## Development Workflow

1. **Make changes** to your code
2. **Restart the server** if needed
3. **Test with phone calls**
4. **Check metrics** in Grafana (if monitoring enabled)
5. **Review logs** for any issues

## File Structure

```
voice-bot/
├── server.py                 # Main webhook server
├── bot.py                    # Voice bot implementation
├── monitoring.py             # Monitoring system
├── requirements.txt          # Python dependencies
├── .env.example             # Environment template
├── .env                     # Your configuration (not in git)
├── docker-compose.yml       # Monitoring stack
├── monitoring/              # Monitoring configuration
├── utils/                   # Helper modules
└── scripts/                 # Deployment scripts
```

## Next Steps

- Review the bot behavior in `bot.py`
- Customize business logic in `utils/supabase_helper.py`
- Add your own knowledge base integration
- Set up production monitoring (see PRODUCTION_MONITORING.md)

## Support

For issues:
1. Check the troubleshooting section above
2. Review logs for error messages
3. Verify all environment variables are set correctly
4. Test individual components (API keys, database connections)

Remember: The voice bot works perfectly without monitoring - monitoring is just for observability and can be added later.