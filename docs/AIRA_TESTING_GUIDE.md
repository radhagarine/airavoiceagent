# AIRA Testing Guide

This guide explains how to use the unified test CLI tool to test and verify the AIRA voice bot system.

## Overview

The `aira-test.py` script provides a consolidated way to test various components of the AIRA voice bot system, including:

- Twilio integration and configuration
- Business information lookup
- System health checks
- Redis cache cluster status
- Server management

## Installation

1. Make the script executable:

```bash
chmod +x aira-test.py
```

2. Ensure you have the required Python dependencies:

```bash
pip install requests python-dotenv
```

## Command Reference

### Twilio Tests

Test Twilio configuration and integration:

```bash
# Test general Twilio configuration
./aira-test.py twilio

# Test a specific phone number
./aira-test.py twilio --phone +14155551234
```

This command:
- Checks Twilio environment variables and configuration files
- Verifies the `TwilioBusinessManager` is working properly
- Tests account and phone number mappings
- If a phone number is provided, tests mapping and client creation for that number

### Business Lookup Tests

Test business information lookup for a specific phone number:

```bash
./aira-test.py business-lookup +14155551234
```

This command:
- Tests the Supabase business lookup functionality
- Tries various phone number formats to find a match
- Shows business information if found
- Also checks Twilio integration for the same phone number

### Health Checks

Perform comprehensive health checks of the running system:

```bash
# Basic health check
./aira-test.py health

# Health check with Redis verification
./aira-test.py health --redis

# Health check for a different server
./aira-test.py health --server http://example.com:8000
```

This command:
- Checks overall system health
- Verifies cache system status
- Checks agent system health
- Optionally checks Redis cluster status

### Redis Management

Manage and test the Redis cluster:

```bash
# Check Redis status
./aira-test.py redis status

# Start Redis cluster
./aira-test.py redis start

# Stop Redis cluster
./aira-test.py redis stop

# Test Redis functionality
./aira-test.py redis test

# Monitor Redis in real-time
./aira-test.py redis monitor
```

This command uses the existing `scripts/redis-cluster.sh` script to manage Redis operations.

### Server Management

Manage the voice bot server:

```bash
# Start the server
./aira-test.py server start

# Stop the server
./aira-test.py server stop

# Check server status
./aira-test.py server status
```

## Troubleshooting

### Common Issues

1. **"Failed to connect to server"**

   Make sure the server is running on the expected URL (default is http://localhost:8000)

2. **"Redis cluster script not found"**

   Ensure `scripts/redis-cluster.sh` exists or use Docker directly.

3. **"No business found for phone number"**

   - Check that the phone number is in the correct format
   - Verify Supabase connection details in `.env` file
   - Ensure the business exists in the database

4. **"Failed to create Twilio client"**

   - Verify Twilio credentials in `.env` file
   - Check that the phone number is correctly mapped to an account
   - Ensure the account has proper permissions

## Adding New Tests

The unified test CLI is designed to be extendable. To add new test categories:

1. Create a new command function in the script
2. Add a new subparser in the main function
3. Update the help text with examples

## Example Workflow

A typical testing workflow might look like:

```bash
# Start the Redis cluster
./aira-test.py redis start

# Start the server
./aira-test.py server start

# Check system health
./aira-test.py health

# Test business lookup for a specific phone number
./aira-test.py business-lookup +14155551234

# Test Twilio integration for the same phone number
./aira-test.py twilio --phone +14155551234
```

## Interpreting Results

The script uses emoji indicators to help interpret results:

- ✅ Success
- ❌ Error
- ⚠️ Warning
- ℹ️ Information

Pay special attention to components marked with ❌ or ⚠️ as these might indicate issues.