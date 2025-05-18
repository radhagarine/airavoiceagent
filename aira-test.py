#!/usr/bin/env python
"""
AIRA Unified Test CLI

A consolidated testing tool for the AIRA voice bot system that provides
commands for testing various components including:
- Twilio configuration and integration
- Redis cache cluster
- Business account mapping
- System health
- Voice bot components

Usage:
  ./aira-test.py <command> [options]

Examples:
  ./aira-test.py twilio --phone +14155551234
  ./aira-test.py health
  ./aira-test.py business-lookup +14155551234
  ./aira-test.py redis status
"""

import os
import sys
import json
import argparse
import subprocess
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv
import requests

# Load environment variables
load_dotenv()

# ----- Utility Functions -----

def print_header(title, width=80):
    """Print a formatted header."""
    print(f"\n{'=' * width}")
    print(f"{title.center(width)}")
    print(f"{'=' * width}")

def print_section(title):
    """Print a section header."""
    print(f"\n{'-' * 10} {title} {'-' * 10}")

def print_success(message):
    """Print a success message."""
    print(f"✅ {message}")

def print_error(message):
    """Print an error message."""
    print(f"❌ {message}")

def print_warning(message):
    """Print a warning message."""
    print(f"⚠️ {message}")

def print_info(message):
    """Print an info message."""
    print(f"ℹ️ {message}")

def mask_token(token):
    """Mask the auth token for display, showing only first/last 5 chars."""
    if not token:
        return "None"
    if len(token) <= 10:
        return "***" # Too short to partially show
    return token[:5] + "..." + token[-5:]

def normalize_phone(phone: str) -> str:
    """Normalize a phone number by removing all non-digit characters."""
    import re
    return ''.join(filter(str.isdigit, phone))

def run_command(command, silent=False):
    """Run a shell command and return output."""
    try:
        if silent:
            return subprocess.check_output(command, shell=True, stderr=subprocess.DEVNULL).decode("utf-8")
        else:
            return subprocess.check_output(command, shell=True).decode("utf-8")
    except subprocess.CalledProcessError as e:
        print_error(f"Command failed with exit code {e.returncode}")
        if e.output:
            print(e.output.decode("utf-8"))
        return None

# ----- Twilio Testing Functions -----

def test_twilio_config():
    """Test Twilio configuration from environment or config file."""
    print_section("Testing Twilio Configuration")
    
    # Check for twilio_handler.py
    if not os.path.exists("utils/twilio_handler.py"):
        print_error("utils/twilio_handler.py not found")
        return False
    
    # Import utilities to test
    try:
        sys.path.append('.')
        from utils.twilio_handler import get_twilio_manager
    except ImportError as e:
        print_error(f"Error importing Twilio handler: {str(e)}")
        return False
    
    # Check for config file path
    config_path = os.getenv("TWILIO_CONFIG_PATH")
    if config_path:
        if os.path.exists(config_path):
            print_success(f"Twilio configuration file found at {config_path}")
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                print_success("Config file parsed successfully")
                
                accounts = config.get("accounts", {})
                print_info(f"Found {len(accounts)} accounts in config file")
                
                for account_sid, account_info in accounts.items():
                    print_info(f"Account: {account_sid[:8]}...")
                    print_info(f"  Name: {account_info.get('name', 'Unnamed')}")
                    print_info(f"  Phone Numbers: {len(account_info.get('phone_numbers', []))}")
            except Exception as e:
                print_error(f"Error reading config file: {str(e)}")
        else:
            print_warning(f"Twilio configuration file not found at {config_path}")
    
    # Check for direct environment variables
    if os.getenv("TWILIO_BUSINESS_MAPPING"):
        print_success("TWILIO_BUSINESS_MAPPING environment variable is set")
        try:
            mapping = json.loads(os.getenv("TWILIO_BUSINESS_MAPPING"))
            print_info(f"Found {len(mapping)} entries in TWILIO_BUSINESS_MAPPING")
        except Exception as e:
            print_error(f"Error parsing TWILIO_BUSINESS_MAPPING: {str(e)}")
    
    # Check for primary account credentials
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    
    if account_sid and auth_token:
        print_success("Found TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN in environment")
        print_info(f"Account SID: {account_sid[:8]}...")
        print_info(f"Auth Token: {mask_token(auth_token)}")
    
    # Initialize the Twilio manager to test implementation
    try:
        manager = get_twilio_manager()
        accounts = manager.get_all_accounts()
        print_success(f"Successfully initialized Twilio manager with {len(accounts)} accounts")
        
        # Display some metrics
        phone_map = manager.get_all_phone_mappings()
        print_info(f"Found {len(phone_map)} phone-to-account mappings")
        
        if accounts:
            for account_id, account_info in accounts.items():
                print_info(f"Account: {account_id}")
                print_info(f"  Name: {account_info.get('name', 'Unnamed')}")
                print_info(f"  Phone Count: {account_info.get('phone_count', 0)}")
        
        return True
    except Exception as e:
        print_error(f"Error initializing Twilio manager: {str(e)}")
        return False

def test_twilio_phone(phone: str):
    """Test a specific phone number with the Twilio integration."""
    print_section(f"Testing Twilio Phone: {phone}")
    
    try:
        sys.path.append('.')
        from utils.twilio_handler import get_twilio_manager, get_client_for_phone, get_business_name
    except ImportError as e:
        print_error(f"Error importing Twilio handler: {str(e)}")
        return False
    
    manager = get_twilio_manager()
    
    # Check if phone is mapped to an account
    account_sid = manager.get_account_for_phone(phone)
    
    if account_sid:
        print_success(f"Phone {phone} is mapped to account: {account_sid[:8]}...")
        
        # Get business name for this phone
        business_name = get_business_name(phone)
        print_info(f"Business Name: {business_name}")
        
        # Test client creation
        client = get_client_for_phone(phone)
        if client:
            print_success("Successfully created Twilio client for this phone number")
            
            # Test client authentication with Twilio API
            try:
                account_info = client.api.accounts(account_sid).fetch()
                print_success("Client authenticated successfully with Twilio API")
                print_info(f"Account Status: {account_info.status}")
                print_info(f"Account Type: {account_info.type}")
                return True
            except Exception as e:
                print_error(f"Client authentication failed: {str(e)}")
                return False
        else:
            print_error("Failed to create Twilio client for this phone")
            return False
    else:
        print_warning(f"Phone {phone} is not mapped to any account")
        
        # Try normalized versions
        normalized = normalize_phone(phone)
        if normalized != phone:
            print_info(f"Normalized phone: {normalized}")
            print_info(f"Try adding this normalized version to your configuration")
        
        # Show available mappings
        print_info("Available phone mappings:")
        for i, (p, a) in enumerate(list(manager.phone_map.items())[:5]):
            print_info(f"  {p} -> {a[:8]}...{a[-4:]}")
            if i >= 4 and len(manager.phone_map) > 5:
                print_info(f"  ... and {len(manager.phone_map) - 5} more")
                break
        
        return False

def test_business_lookup(phone: str):
    """Test business lookup functionality."""
    print_section(f"Testing Business Lookup: {phone}")
    
    try:
        sys.path.append('.')
        from utils.supabase_helper import get_business_by_phone, normalize_phone_number
    except ImportError as e:
        print_error(f"Error importing Supabase helper: {str(e)}")
        return False
    
    # Try different phone formats
    formats_to_try = [
        phone,
        normalize_phone_number(phone),
        normalize_phone_number(phone, strip_country_code=True)
    ]
    
    if phone.startswith('+'):
        formats_to_try.append(phone[1:])
    
    # Try lookup with each format
    business = None
    for fmt in formats_to_try:
        print_info(f"Trying phone format: {fmt}")
        result = get_business_by_phone(fmt)
        if result:
            business = result
            print_success(f"Business found with format: {fmt}")
            break
    
    if business:
        print_success("Business lookup successful:")
        print_info(f"Business ID: {business.get('id')}")
        print_info(f"Business Name: {business.get('name')}")
        print_info(f"Business Phone: {business.get('phone')}")
        print_info(f"Business Type: {business.get('type', 'default')}")
        return True
    else:
        print_error(f"No business found for {phone}")
        return False

# ----- Health Check Functions -----

def check_system_health(server_url: str = "http://localhost:8000"):
    """Check the health of the voice bot system."""
    print_section("System Health Check")
    
    # Check if server is running
    try:
        resp = requests.get(f"{server_url}/health", timeout=5)
        if resp.status_code == 200:
            health_data = resp.json()
            status = health_data.get("status", "unknown")
            
            if status == "healthy":
                print_success("System Status: HEALTHY")
            elif status == "degraded":
                print_warning("System Status: DEGRADED")
            else:
                print_error(f"System Status: {status.upper()}")
            
            # Check component status
            components = health_data.get("components", {})
            for name, status in components.items():
                if status == "healthy":
                    print_success(f"{name}: HEALTHY")
                elif status == "degraded":
                    print_warning(f"{name}: DEGRADED")
                else:
                    print_error(f"{name}: {status.upper()}")
            
            return True
        else:
            print_error(f"Health check failed with status code: {resp.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print_error(f"Failed to connect to server: {str(e)}")
        print_info(f"Make sure the server is running on {server_url}")
        return False

def check_cache_health(server_url: str = "http://localhost:8000"):
    """Check the health of the cache system."""
    print_section("Cache Health Check")
    
    try:
        resp = requests.get(f"{server_url}/cache/health", timeout=5)
        if resp.status_code == 200:
            cache_health = resp.json()
            status = cache_health.get("status", "unknown")
            
            if status == "healthy":
                print_success("Cache Status: HEALTHY")
            elif status == "degraded":
                print_warning("Cache Status: DEGRADED")
            else:
                print_error(f"Cache Status: {status.upper()}")
            
            # Check L1 and L2 cache
            l1_cache = cache_health.get("l1_cache", {})
            print_info(f"L1 Cache: {l1_cache.get('size', 0)} of {l1_cache.get('max_size', 0)} items used")
            print_info(f"L1 Utilization: {l1_cache.get('utilization_percent', 0)}%")
            
            l2_cache = cache_health.get("l2_cache", {})
            if l2_cache.get("status") == "healthy":
                print_success("Redis Connection: HEALTHY")
                print_info(f"Redis Version: {l2_cache.get('redis_version', 'unknown')}")
                print_info(f"Connected Clients: {l2_cache.get('connected_clients', 0)}")
                print_info(f"Memory Usage: {l2_cache.get('used_memory_human', 'unknown')}")
            else:
                print_error(f"Redis Connection: {l2_cache.get('status', 'UNKNOWN').upper()}")
                print_error(f"Error: {l2_cache.get('error', 'Unknown error')}")
            
            return True
        else:
            print_error(f"Cache health check failed with status code: {resp.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print_error(f"Failed to connect to server: {str(e)}")
        print_info(f"Make sure the server is running on {server_url}")
        return False

def check_agent_health(server_url: str = "http://localhost:8000"):
    """Check the health of the agent system."""
    print_section("Agent System Health Check")
    
    try:
        resp = requests.get(f"{server_url}/agents/health", timeout=5)
        if resp.status_code == 200:
            agent_health = resp.json()
            status = agent_health.get("status", "unknown")
            
            if status == "healthy":
                print_success("Agent System Status: HEALTHY")
            elif status == "degraded":
                print_warning("Agent System Status: DEGRADED")
            elif status == "not_initialized":
                print_warning("Agent System: NOT INITIALIZED")
            else:
                print_error(f"Agent System Status: {status.upper()}")
            
            # Check registry status
            registry = agent_health.get("registry", {})
            if registry:
                total_types = registry.get("total_types", 0)
                default_type = registry.get("default_type", "unknown")
                print_info(f"Registered Agent Types: {total_types}")
                print_info(f"Default Agent Type: {default_type}")
                
                # Check agent health
                agent_health_data = registry.get("agent_health", {})
                for agent_type, health in agent_health_data.items():
                    status = health.get("status", "unknown")
                    if status == "healthy":
                        print_success(f"Agent '{agent_type}': HEALTHY")
                    else:
                        print_warning(f"Agent '{agent_type}': {status.upper()}")
            
            return True
        else:
            print_error(f"Agent health check failed with status code: {resp.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print_error(f"Failed to connect to server: {str(e)}")
        print_info(f"Make sure the server is running on {server_url}")
        return False

def check_redis_status():
    """Check Redis cluster status."""
    print_section("Redis Cluster Status")
    
    # Check if redis-cluster.sh exists
    if os.path.exists("scripts/redis-cluster.sh"):
        print_success("Redis cluster script found")
        
        # Make the script executable
        run_command("chmod +x scripts/redis-cluster.sh", silent=True)
        
        # Run the status check
        output = run_command("./scripts/redis-cluster.sh status")
        if output:
            print_info("Redis cluster status output:")
            print(output)
            return True
        else:
            print_error("Failed to get Redis cluster status")
            return False
    else:
        # Try direct docker-compose check
        print_warning("Redis cluster script not found, trying docker-compose")
        output = run_command("docker-compose ps redis-1 redis-2 redis-3", silent=True)
        
        if output and "Up" in output:
            print_success("Redis containers are running")
            print_info(output)
            return True
        else:
            print_error("Redis containers are not running or docker-compose not found")
            return False

# ----- Main Command Functions -----

def cmd_twilio(args):
    """Twilio testing command handler."""
    print_header("TWILIO CONFIGURATION TEST")
    
    # Test Twilio configuration
    success = test_twilio_config()
    
    # If a phone number is provided, test it
    if args.phone:
        success = test_twilio_phone(args.phone) and success
    
    return 0 if success else 1

def cmd_business(args):
    """Business lookup testing command handler."""
    print_header("BUSINESS LOOKUP TEST")
    
    if not args.phone:
        print_error("Phone number is required for business lookup test")
        return 1
    
    # Test business lookup
    success = test_business_lookup(args.phone)
    
    # Check Twilio configuration for this phone
    twilio_success = test_twilio_phone(args.phone)
    
    return 0 if success and twilio_success else 1

def cmd_health(args):
    """Health check command handler."""
    print_header("SYSTEM HEALTH CHECK")
    
    server_url = args.server
    
    # Check system health
    system_success = check_system_health(server_url)
    
    # Check cache health
    cache_success = check_cache_health(server_url)
    
    # Check agent health
    agent_success = check_agent_health(server_url)
    
    if args.redis:
        # Check Redis status
        redis_success = check_redis_status()
    else:
        redis_success = True
    
    # Summarize results
    print_section("Health Check Summary")
    if system_success:
        print_success("System Health: PASSED")
    else:
        print_error("System Health: FAILED")
    
    if cache_success:
        print_success("Cache Health: PASSED")
    else:
        print_error("Cache Health: FAILED")
    
    if agent_success:
        print_success("Agent System Health: PASSED")
    else:
        print_error("Agent System Health: FAILED")
    
    if args.redis:
        if redis_success:
            print_success("Redis Status: PASSED")
        else:
            print_error("Redis Status: FAILED")
    
    return 0 if system_success and cache_success and agent_success and redis_success else 1

def cmd_redis(args):
    """Redis cluster command handler."""
    print_header("REDIS CLUSTER MANAGEMENT")
    
    # Check if redis-cluster.sh exists
    if not os.path.exists("scripts/redis-cluster.sh"):
        print_error("Redis cluster script not found at scripts/redis-cluster.sh")
        return 1
    
    # Make the script executable
    run_command("chmod +x scripts/redis-cluster.sh", silent=True)
    
    # Run the specified command
    command = f"./scripts/redis-cluster.sh {args.action}"
    print_info(f"Running command: {command}")
    output = run_command(command)
    
    if output is not None:
        print(output)
        return 0
    else:
        return 1

def cmd_server(args):
    """Server command handler."""
    print_header("SERVER MANAGEMENT")
    
    action = args.action
    
    if action == "start":
        print_info("Starting server...")
        
        # Check if scripts/start-all.sh exists
        if os.path.exists("scripts/start-all.sh"):
            run_command("chmod +x scripts/start-all.sh", silent=True)
            output = run_command("./scripts/start-all.sh")
            if output:
                print(output)
                return 0
        else:
            # Use direct command
            print_info("Using direct Python command to start server")
            try:
                subprocess.Popen(["python", "server.py"])
                print_success("Server started")
                return 0
            except Exception as e:
                print_error(f"Failed to start server: {str(e)}")
                return 1
                
    elif action == "stop":
        print_info("Stopping server...")
        
        # Check if scripts/stop-all.sh exists
        if os.path.exists("scripts/stop-all.sh"):
            run_command("chmod +x scripts/stop-all.sh", silent=True)
            output = run_command("./scripts/stop-all.sh")
            if output:
                print(output)
                return 0
        else:
            # Use pkill
            print_info("Using pkill to stop server")
            try:
                run_command("pkill -f 'python server.py'", silent=True)
                print_success("Server stopped")
                return 0
            except Exception as e:
                print_error(f"Failed to stop server: {str(e)}")
                return 1
                
    elif action == "status":
        print_info("Checking server status...")
        
        # Try to connect to server
        try:
            resp = requests.get("http://localhost:8000/health", timeout=2)
            if resp.status_code == 200:
                print_success("Server is running")
                health_data = resp.json()
                print_info(f"Status: {health_data.get('status', 'unknown')}")
                return 0
            else:
                print_warning(f"Server returned unexpected status code: {resp.status_code}")
                return 1
        except requests.exceptions.RequestException:
            print_error("Server is not running")
            return 1
    
    else:
        print_error(f"Unknown action: {action}")
        return 1

# ----- Main CLI Setup -----

def main():
    """Set up the CLI parser and execute commands."""
    parser = argparse.ArgumentParser(
        description="AIRA Voice Bot Test CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test Twilio configuration
  ./aira-test.py twilio
  
  # Test a specific phone number with Twilio
  ./aira-test.py twilio --phone +14155551234
  
  # Test business lookup for a phone number
  ./aira-test.py business-lookup +14155551234
  
  # Check system health
  ./aira-test.py health
  
  # Check Redis cluster status
  ./aira-test.py redis status
  
  # Start the server
  ./aira-test.py server start
  """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Twilio command
    twilio_parser = subparsers.add_parser("twilio", help="Test Twilio configuration and integration")
    twilio_parser.add_argument("--phone", type=str, help="Test a specific phone number")
    
    # Business lookup command
    business_parser = subparsers.add_parser("business-lookup", help="Test business lookup functionality")
    business_parser.add_argument("phone", type=str, help="Phone number to look up")
    
    # Health command
    health_parser = subparsers.add_parser("health", help="Check system health")
    health_parser.add_argument("--server", type=str, default="http://localhost:8000", help="Server URL")
    health_parser.add_argument("--redis", action="store_true", help="Check Redis status")
    
    # Redis command
    redis_parser = subparsers.add_parser("redis", help="Manage Redis cluster")
    redis_parser.add_argument("action", choices=["start", "stop", "restart", "status", "test", "monitor"], help="Redis action")
    
    # Server command
    server_parser = subparsers.add_parser("server", help="Manage server")
    server_parser.add_argument("action", choices=["start", "stop", "status"], help="Server action")
    
    # Parse args and handle the selected command
    args = parser.parse_args()
    
    # If no command provided, show help
    if not args.command:
        parser.print_help()
        return 0
    
    # Execute the selected command
    if args.command == "twilio":
        return cmd_twilio(args)
    elif args.command == "business-lookup":
        return cmd_business(args)
    elif args.command == "health":
        return cmd_health(args)
    elif args.command == "redis":
        return cmd_redis(args)
    elif args.command == "server":
        return cmd_server(args)
    else:
        print_error(f"Unknown command: {args.command}")
        return 1

if __name__ == "__main__":
    sys.exit(main())